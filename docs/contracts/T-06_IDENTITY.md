# T-06 — группы и Telegram identity

**Proposed для независимого ревью, не согласованный заранее контракт.**
База `3f6f2d6` после merged PR #26, принятый head `0002_users`.
[Предложение и запрос ревью в #22](https://github.com/inte11ectua1/skinulis/issues/22#issuecomment-6436799120),
[handoff Олегу #23](https://github.com/inte11ectua1/skinulis/issues/23#issuecomment-6436883933),
[handoff Лере #24](https://github.com/inte11ectua1/skinulis/issues/24#issuecomment-6436885598).
Ответов владельцев пока нет; отсутствие ответа не означает согласия.
T-05 находится в main, но независимого APPROVED-review PR #26 не получил.

## Установленные правила и предлагаемые решения

PRODUCT_RULES уже задаёт owner + первый member, максимум 30, добровольный join,
одноразовые invites TTL 24 часа с отзывом, link TTL 10 минут, no merge/delete.
В этой ветке предлагаются конкретные таблицы, DTO, внутренние пути, error.code,
пагинация, UUID replay и Q-03. Они требуют review до принятия и L-03 integration.
Финансовые Q-03/UQ-03/06–09 этим документом не закрываются.

**Дополнительные GET invites / DELETE revoke пока ожидают отдельного согласования.**
Ядро чтения/отзыва реализовано и тестируется; HTTP-маршруты ещё не включены.
Это оставшаяся часть полного T-06, не заявление о готовом пользовательском отзыве.

## Модель PostgreSQL / handoff O-03

Общая metadata `app.models.Base`, все identity/entity IDs — положительный signed
BIGINT (1..2^63−1). Никаких balance, financial tables, UUID вместо user/group ID.
UUID используется только как ключ повторного запроса, не идентификатор сущности.

| Таблица | PK / данные | Ограничения и FK |
|---|---|---|
| users | Не изменена T-05: id BIGINT, nullable email/hash/tg | users.id — общий FK target; Telegram-only имеет NULL email/hash |
| groups | pk_groups(id), owner_id BIGINT, name VARCHAR(120), client_request_id UUID, created_at TIMESTAMPTZ | fk_groups_owner -> users.id RESTRICT; uq_groups_request(owner_id,client_request_id); id>0; name length1..120 |
| group_members | pk_group_members(group_id,user_id), оба BIGINT; slot SMALLINT; joined_at TIMESTAMPTZ | fk_group_members_group/user RESTRICT; uq_group_members_slot(group_id,slot); ck_group_members_slot 1..30 |
| group_invites | pk_group_invites(id), group_id, UUID key, token_hash VARCHAR(64), created_at/expires_at/consumed_at/revoked_at, consumed_by BIGINT nullable | fk_group_invites_group/consumer RESTRICT; uq_group_invites_hash и uq_group_invites_request(group_id,client_request_id) |
| telegram_link_codes | pk_telegram_link_codes(id), user_id BIGINT, token_hash VARCHAR(64), created_at/expires_at/consumed_at/revoked_at | fk_telegram_link_codes_user RESTRICT; uq_telegram_link_codes_hash |

`fk_groups_owner_membership (groups.id,owner_id) -> group_members(group_id,user_id)`
— DEFERRABLE INITIALLY DEFERRED, NO ACTION. Он проверяется при commit, поэтому
разрешает insert group → insert member в одной транзакции, но запрещает сохранить
группу без владельца-участника или удалить его membership. Миграция добавляет этот
циклический FK после обеих таблиц. Дополнительно deferred composite
`fk_group_invites_consumer_membership(group_id,consumed_by)` гарантирует, что
успешный потребитель invite действительно входит в эту группу.
Slot — техническое место, не роль и не порядок отображения: 30 уникальных значений
на группу дают жёсткий DB-предел даже при прямом SQL. PK исключает дубли участника.
`ix_group_members_user_group` обслуживает список своих групп;
`ix_telegram_link_codes_user` — инвалидацию кодов. UNIQUE создают собственные
индексы, включая префикс group_id для invites. ORM relationships с неявными
каскадами/ленивым N+1 не добавлены.

CHECK для secrets: lowercase SHA-256 hex64; id>0; expires_at ровно created_at+24h
или +10min; consumed_at допускается только до expiry и без revoked_at; время
отзыва не раньше создания; consumed_at/consumed_by invite заполнены вместе.
Временные поля NOT NULL, кроме явно nullable terminal fields. Нет ON DELETE CASCADE.
FK будущих финансов: groups.id, users.id; для проверки принадлежности можно
использовать composite group_members(group_id,user_id). API удаления отсутствует;
не следует удалять memberships/history прямым SQL.

Ревизия **0003_groups_identity -> 0002_users**, один head. O-03 создаёт свою
следующую ревизию только от принятого актуального main, после проверки heads.
Ни ORM create_all, ни миграций внутри worker нет. Upgrade с пустой БД и с users
T-05, повтор upgrade и alembic check проверяются integration-тестами. Downgrade
удаляет новые таблицы и не обещает безопасный откат пользовательских данных.

## Транзакции и конкуренция

- У записи один владелец транзакции — service `write_transaction`: commit после
  всей операции, rollback на любой ошибке. Он включает транзакцию, уже открытую
  чтением JWT/Telegram dependency в той же request Session. Это top-level operation,
  его нельзя вкладывать в другую write-operation. Read-only запрос закрывает Session
  с rollback незавершённого чтения. Глобальной Session нет.
- Создание группы: INSERT + flush ID → owner member slot1 → flush → commit,
  включая deferred owner FK. UNIQUE owner/key защищает concurrent replay.
- Invite issue/join/revoke: **groups FOR UPDATE → invite row → membership**.
  Поиск group_id по hash до group lock не блокирует строки и не раскрывает данные.
  Expiry проверяется после ожидания всех locks. Join выбирает свободный slot,
  вставляет membership и помечает invite consumed в одном commit.
- Bootstrap/link сериализуются `pg_advisory_xact_lock(-telegram_id)`; весь диапазон
  отрицательных BIGINT зарезервирован для Telegram identity, без hash collision.
  Затем link берёт **user FOR UPDATE → code FOR UPDATE**. Issuance берёт user → codes.
  Эти операции не берут group locks. Будущие составные операции должны отдельно
  проверить порядок, не вкладывать identity write в group write.
- Bootstrap, link и issuance обслуживаются одной request Session. User UNIQUE
  telegram_id остаётся последней защитой; не переназначаем существующий профиль.
- Конкурентные тесты используют независимые соединения/транзакции: blocker держит
  реальный lock до подтверждения двух ожидающих workers в pg_stat_activity.
  Только start barrier без реального перекрытия не считается доказательством.

## Actor и service-поверхность / UQ-01

Публичные группы используют существующий `get_current_user` T-05 (Bearer JWT).
Служебные операции имеют отдельный `/internal` prefix и проверку
`X-Bot-Service-Token`, затем canonical positive BIGINT `X-Telegram-ID`.
Actor ID берётся ботом из sender Telegram update, никогда из пользовательского
текста/callback/введённого JSON. Backend сам Telegram update не получает.

BOT_SERVICE_TOKEN — отдельный случайный URL-safe secret 43–128 символов,
без default; рекомендуется `secrets.token_urlsafe(48)`. API fail-closed при
отсутствии/невалидности/совпадении с JWT или DB password. Формат исключает `:`,
поэтому Telegram Bot API token не подходит. Сравнение через compare_digest(bytes).
Секрет скрыт из Settings repr/errors; не попадает в build args/migrate/CI secrets.
Заголовки должны встречаться ровно один раз. Проверка credential предшествует
интерпретации Telegram ID и запросам DB.

Смешивание Authorization и service channel запрещено (`400 ambiguous_actor`).
Публичная JWT dependency отвергает служебные actor headers; JWT не заменяет
service credential. Service 401 имеет WWW-Authenticate: BotService, публичный — Bearer.

**Обязательное условие production T-09:** внешний reverse proxy закрывает весь
`/internal` (включая документацию для внешних клиентов, если она публикуется).
Здесь production proxy/deploy не создаётся и публичная изоляция production не
заявляется проверенной. Локальный Compose публикует API только на loopback;
даже внутри сети service credential обязателен. Компрометация доверенного бота/
service credential позволяет выдавать себя за Telegram actor — это граница доверия,
а не дополнительная проверка Telegram подписи backend-ом.

## HTTP и DTO / UQ-01/02/05

Все input models запрещают extra fields. Нельзя передать owner_id/member_id/user_id/
telegram_id через публичный JSON. В output ID допустимы как данные, не credentials.
OpenAPI доступен на /docs и /openapi.json; T-06 endpoints помечены proposed.
Значения секретов ниже placeholders, не действующие credentials.

| Метод | JSON / actor | Success |
|---|---|---|
| POST /groups | JWT; {name,client_request_id:UUID} | 201 Group |
| GET /groups | JWT; ?limit=20&offset=0 | 200 Page[Group] только своих |
| GET /groups/{id} | JWT, member | 200 Group |
| GET /groups/{id}/members | JWT, member; pagination | 200 Page[Member] |
| POST /groups/{id}/invites | JWT, owner; {client_request_id:UUID} | 201 InviteIssued |
| POST /group-invites/join | JWT; {token} | 200 Group после собственного join |
| Те же групповые пути с /internal | service credential + Telegram actor | Те же DTO/права, без JWT |
| GET /internal/users/me | service + Telegram actor | 200 UserProfile, 404 если ещё нет; не создаёт |
| POST /internal/users/bootstrap | service + actor; {} после Create consent | 200 UserProfile, включая deterministic replay |
| POST /users/me/telegram-link-code | JWT email account без tg; {} | 201 {code,expires_at} |
| POST /internal/users/telegram-link | service + actor; {code} | 200 UserProfile |

Group: `{id,name,owner_id,created_at}`. Member: `{user_id,joined_at,is_owner}`
без чужих email/telegram_id/hash. Page: `{items:[...],limit,offset}`, limit1..100,
default20, offset>=0. Порядок groups(created_at,id), members(joined_at,user_id).
Последняя пустая страница возвращает items:[]; нет total/has_next.
InviteIssued: `{id,group_id,client_request_id,created_at,expires_at,consumed_at,revoked_at,token}`.
Raw token только на первом выпуске, на replay token:null; consumed_by/hash не DTO.
UserProfile — существующая безопасная схема T-05.

Предлагаемый Q-03 для групп: Unicode NFC → strip внешних Unicode whitespace →
1..120 codepoints, запрет Unicode category C. Внутренние пробелы и регистр сохраняются;
одинаковые названия разрешены. Emoji с ZWJ (category Cf) пока отвергаются; это
осознанная часть предложения для review, не принятое правило финансовых названий.
DB дополнительно ограничивает длину, полная Unicode-политика выполняется API.

## Invites / UQ-02

`secrets.token_urlsafe(32)` даёт 256-bit secret длиной43; в БД только SHA-256.
Для случайного высокоэнтропийного секрета SHA-256 применим; пароли по-прежнему Argon2id.
TTL ровно24h. Предлагаемый Telegram payload `i_<token>` — 45 URL-safe символов
при Telegram лимите64; бот строит `https://t.me/<bot_username>?start=i_<token>`.
Backend не знает реальное имя бота и не выдаёт выдуманную готовую ссылку.
Не размещать token в API path/query, логах или сообщении об ошибке.

Действующий token даёт только добровольное вступление текущего actor. До join
название/состав группы не раскрываются. Invalid/expired/used/revoked имеют один
404 invite_invalid. Повтор участника —409 already_member, полная группа —409 group_full;
в обоих случаях token остаётся неиспользованным. Успешное потребление нельзя
повторить даже тем же actor; после timeout нужно прочитать свои группы, а при
неопределённости ждать/обновлять, не объявлять join неуспешным.

Создание группы: сохранить один client_request_id и normalized body; replay
возвращает ту же Group (201), другое имя с тем же ключом ->409 request_conflict.
Приглашение: сохранить UUID; replay возвращает ту же metadata без исходного секрета,
а не создаёт новый invite. Потерянный raw token нельзя восстановить. Предлагаемые
GET/DELETE позволят найти metadata по ключу, отозвать её и только после этого
явно создать новый invite с новым UUID. **До согласования/включения этих маршрутов
бот не должен обещать пользователю отзыв или восстановление потерянной ссылки.**

## Linking и timeout

Read profile → предложить Create ИЛИ Link. Bootstrap вызывается только после
явного Create-согласия; GET не создаёт пользователя. Повтор bootstrap возвращает
существующего Telegram-only или уже linked User, не меняя email/hash/ID.
Backend не может проверить UI-согласие, поэтому правильный вызов — ответственность L-03.

Link code выдаётся только JWT-владельцу email-профиля без tg. Новый выпуск под
user lock инвалидирует прежние unused codes. Бот получает только code, не password/
JWT. Code — capability proof контроля email-аккаунта; его нельзя пересылать посторонним.
Потребитель определяется проверенным Telegram actor, target user — записью hash кода.
Поэтому код собственного аккаунта нельзя выпустить с подставленным target user_id.
Держатель чужого украденного code может попытаться привязать свой Telegram до TTL —
это причина хранить его как секрет и не давать публичный consume endpoint.

Consumption атомарно ставит users.telegram_id и consumed_at; invalid/expired/used/
revoked не меняют данные. Любой уже зарегистрированный Telegram ID ->409 no merge,
даже если Telegram-only аккаунт пока пуст. У email-профиля уже есть tg ->409.
После timeout сначала GET /internal/users/me и сверка фактического профиля;
также владелец JWT может прочитать /users/me. Не выпускать новый code и не создавать
новый профиль автоматически. Без достоверной проверки результат остаётся неизвестным.
Raw code не хранится; использованный digest остаётся для single-use и диагностики
без возможности восстановления. Cleanup/retention policy — последующая эксплуатация.

## Ошибки / UQ-04

| HTTP | error.code | Смысл |
|---|---|---|
|400|validation_error|Body/UUID/name/secret format/header/pagination невалиден|
|400|ambiguous_actor|Смешаны каналы либо service headers на публичном JWT endpoint|
|401|invalid_token|Публичный JWT отсутствует/невалиден/пользователя нет|
|401|invalid_service_token|Service credential отсутствует/неверен/дублирован|
|403|owner_required|Участник не владелец|
|404|group_not_found|Неизвестная или скрытая чужая группа|
|404|telegram_profile_not_found|Проверенный Telegram actor ещё не имеет профиля|
|404|invite_invalid|Неверный/expired/used/revoked token или неизвестная invite metadata|
|404|link_code_invalid|Неверный/expired/used/revoked code|
|409|request_conflict|Повтор UUID с другим именем|
|409|already_member / group_full|Join не выполнен, invite не потреблён|
|409|invite_consumed|Ядро отзыва не отзывает уже использованное приглашение|
|409|telegram_identity_conflict|Telegram ID уже занимает существующий аккаунт, merge запрещён|
|409|telegram_already_linked / email_profile_required|Состояние target несовместимо с linking|
|500|internal_error|Неожиданный сбой без внутренних деталей|

Все ошибки: `{"error":{"code":"group_not_found","message":"Group not found","request_id":"example-request-id"}}`.
Validation400 вместо422, X-Request-ID, безопасные общие сообщения. Service401 —
проверка настройки доверенного бота, не повод запросить пароль/JWT в Telegram.
Новые ответы no-store; секреты/SQL params/headers/body не логируются.

## Проверки и оставшиеся границы

Локальные unit + реальные PostgreSQL17 тесты покрывают прежние auth endpoints,
схему/FK/UNIQUE/CHECK, чистую и T-05 миграции, repeat upgrade/check, owner/member,
cross-group, UUID replay, hash/TTL, join/full/rollback, concurrent same invite,
последний slot, bootstrap, link double-consume и bootstrap-vs-link no merge.
Время контролируется clock seam, без ожидания реальных24h/10min.
Docker smoke использует отдельный Compose project и volume с новыми credentials;
исходная пользовательская БД не используется. Результаты/evidence — в STATUS и PR.

Не реализованы bot handlers/FSM, financial models/API, expense-preview, production
proxy/deploy, Telegram account merge, group/member delete, ownership transfer,
refresh/revocation JWT. Реальный Telegram E2E остаётся L-03/G2 после review контрактов.

Источники: [PostgreSQL locks](https://www.postgresql.org/docs/17/explicit-locking.html),
[PostgreSQL constraints](https://www.postgresql.org/docs/17/ddl-constraints.html),
[SQLAlchemy transactions](https://docs.sqlalchemy.org/en/20/orm/session_transaction.html),
[Telegram deep links](https://core.telegram.org/bots/features#deep-linking).
