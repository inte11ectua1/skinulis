# T-08 / M4 — утверждённый технический checkpoint: балансы, план и компенсации

**Дата:** 30.10.2026 · **Владелец решения:** Тимур, tech lead · [T-08 #45](https://github.com/inte11ectua1/skinulis/issues/45) · Исполнители [O-06 #46](https://github.com/inte11ectua1/skinulis/issues/46), [O-07 #47](https://github.com/inte11ectua1/skinulis/issues/47), [L-05 #48](https://github.com/inte11ectua1/skinulis/issues/48).

**Статус:** конкретный **технический выбор Тимура для реализации**, опубликованный через документационный PR с запросом независимого review Олега и Леры. Это **не** их персональное `APPROVED`, не доказательство готовых HTTP-маршрутов и не закрытие T-08. Любое обнаруженное несоответствие принятому `PRODUCT_RULES` исправлять отдельным согласованным решением, не скрытно. `main` на старте checkpoint: `fde5a65eb00c6a1122b6032f0ce6eb13bd24e254` после merged docs PR #49 и T-07 PR #44.

Источники: [PRODUCT_RULES](../PRODUCT_RULES.md) §§3–7, [TECHNICAL_DECISIONS](../TECHNICAL_DECISIONS.md) §§4–6, [BOUNDARIES](BOUNDARIES.md), [O-01_INVARIANTS](../finance/O-01_INVARIANTS.md) INV-B/INV-P/INV-C/INV-T, [O-01_OPEN_QUESTIONS](../finance/O-01_OPEN_QUESTIONS.md) Q-01/Q-04/Q-05/Q-06/Q-07, [O-04](O-04_EXPENSES.md), [O-05](O-05_BY_ITEMS.md), [T-07 review](../reviews/T-07_M3_SECURITY_REVIEW.md), существующие `app/models/finance.py` и `app/services/expense_balances.py`.

## 1. Общие границы и безопасность

- Использовать **существующие URL из TECHNICAL_DECISIONS §6**, перечисленные ниже; каждому публичному JWT route соответствует тот же route с префиксом `/internal` и **только** T-06 `get_bot_user` (валидный `X-Bot-Service-Token` + `X-Telegram-ID` из доверенного Telegram update). Не доверять присланным `sender_id`, `payer_id` или произвольным user headers. Публичный и внутренний auth не смешивать; существующие 400 `ambiguous_actor`/401 `invalid_token` или `invalid_service_token` сохраняются.
- Пользователь должен быть **текущим участником группы** на всех чтениях/мутациях; данные чужой или недоступной группы/компенсации скрыты 404 `group_not_found`/`settlement_not_found`. Внутри своей группы разрешено видеть записи компенсаций всех участников — это общие групповые финансы. Владелец группы не получает прав sender/receiver на чужие переходы.
- Pydantic v2, `extra=forbid` для body и nested DTO; positive BIGINT strict JSON integer IDs, UUID ключ строго в формате UUID; никакого float/неявного приведения. Все amounts — **строгие канонические ASCII-строки рублей** `(0|[1-9][0-9]*)\.[0-9]{2}`. Баланс может быть отрицательной форматированной строкой `"-900.00"`/нулём `"0.00"`; для `POST settlement` amount строго >0 и `<= 2^63−1` копеек **по размеру БД**, также `<=` актуальным остаткам. **Не применять лимит 1 000 000 ₽ для расхода к компенсациям**.
- Денежные вычисления исключительно в сервисе/backend на целых копейках и SQL `NUMERIC` до сложения/вычитания; суммы агрегатов могут превышать один BIGINT. Внешнее представление в рублях, без экспонент и знака `+`. Вернуть точные ответы, не просачивать сырой ORM/SQL или чужие данные.
- Все ответы финансовых маршрутов, **включая ошибки**, имеют `Cache-Control: no-store`. Не менять общую оболочку `{"error":{"code","message","request_id"}}`, `X-Request-ID`, WWW-Authenticate на 401 и безопасное логирование. UTC timestamps с `Z`, без внутренних исключений в теле.

## 2. O-06 — read-only балансы и план (Q-05 УТВЕРЖДЁН)

`GET /groups/{group_id}/balances` (и `/internal/groups/{group_id}/balances`) HTTP200:

```json
{"group_id":10,"balances":[{"user_id":10,"balance":"2200.00"},{"user_id":20,"balance":"-1400.00"},{"user_id":30,"balance":"-800.00"}]}
```

Все **текущие** члены группы, включая `0.00`, в порядке **numeric user_id ASC**. Баланс в копейках = уплаченные **активные** расходы − **итоговые** доли только активных расходов + отправленные `confirmed` − полученные `confirmed`. `pending/rejected/cancelled` не меняют баланс. Использовать только `expense_shares` (не второй раз `expense_item_shares`); новые члены не меняют исторические доли. Итоговый вектор должен суммироваться в точности в ноль. Проверять сохранённые снимки расходов как T-07: повреждение → safe500, без тихого исправления.

`GET /groups/{group_id}/settlement-plan` (и `/internal`) HTTP200:

```json
{"group_id":10,"transfers":[{"sender_id":20,"receiver_id":10,"amount":"1400.00"},{"sender_id":30,"receiver_id":10,"amount":"800.00"}]}
```

**Окончательное решение Q-05:** один раз рассортировать должников по **убыванию исходного абсолютного отрицательного баланса**, кредиторов по **убыванию исходного положительного баланса**; ties — по **numeric user_id ASC**. Работать двумя указателями без пересортировки. Каждая строка плана — `min(remaining debt,remaining credit)` >0, порядок в массиве — реальный порядок шагов алгоритма. Нули пропустить; все долги и требования должны исчерпаться. Пример из O-01 `{10:+800,20:+700,30:-700,40:-500,50:-300}`: `30→10:700, 40→10:100, 40→20:400, 50→20:300`; это четыре шага, **не гарантия глобально минимального числа переводов**. Пустой/нулевой вектор → `transfers:[]`. План вычисляется на запросе, **не** сохраняется и не создаёт pending/резервацию/банковский перевод.

GET не получает group `FOR UPDATE`, но обязан читать **один согласованный PostgreSQL MVCC snapshot** (один SQL statement/CTE или корректный read-only repeatable-read transaction): `READ COMMITTED` с несколькими SELECT без общего snapshot запрещён при гонках с expense PUT/confirm. Переиспользовать единый баланс-сервис для O-04 mutation envelope при confirmed, не менять сериализацию/оригинальный UUID replay старых расходов. Не добавлять mutable balance cache.

## 3. O-07 — запросы и ответы (строгий wire)

Действующие public URL и точно такие же /internal mirrors:

| Метод/URL | Body / query | Успех |
|---|---|---|
| `POST /groups/{group_id}/settlements` | `{"receiver_id":10,"amount":"500.00","client_request_id":"00000000-0000-4000-8000-000000000001"}` | 201 при создании; 200 при равном UUID replay |
| `GET /groups/{group_id}/settlements` | `limit=20&offset=0` + optional `status`, `direction` | 200 page |
| `POST /settlements/{id}/confirm` | пустое тело (или без body) | 200 актуальная запись |
| `POST /settlements/{id}/reject` | пустое тело (или без body) | 200 актуальная запись |
| `POST /settlements/{id}/cancel` | пустое тело (или без body) | 200 актуальная запись |

`sender_id` **всегда verified actor**, не тело запроса. `receiver_id` — положительный член **той же** группы, не sender. `amount` строго каноническая >0 RUB строка; `client_request_id` — UUID intent. `status`, `group_id`, `sender_id`, `resolved_at`, `id` в client body запрещены.

Запросы POST create и переходов возвращают **единую mutation envelope**:

```json
{"settlement":{"id":123,"group_id":10,"sender_id":20,"receiver_id":10,"amount":"500.00","status":"pending","client_request_id":"00000000-0000-4000-8000-000000000001","created_at":"2026-10-30T12:00:00Z","resolved_at":null}}
```

После confirm тот же envelope с `status:"confirmed"` и непустым UTC `resolved_at`; rejected/cancelled аналогично. В этих ответах **нет клиентского баланса** и банка: после успешного confirm бот делает GET balances+plan и показывает актуальный серверный расчёт. Не добавлять mutable `balance` к Settlement. Не возвращать секретные поля/телеграм-ID.

GET list:

```json
{"items":[{"id":123,"group_id":10,"sender_id":20,"receiver_id":10,"amount":"500.00","status":"pending","client_request_id":"00000000-0000-4000-8000-000000000001","created_at":"2026-10-30T12:00:00Z","resolved_at":null}],"limit":20,"offset":0}
```

Сортировка `(created_at,id) ASC`, `limit` default20, 1..100, `offset>=0`, пустая страница `items:[]`, никаких total/has_next без отдельного решения. `status` optional **одно значение** `pending|confirmed|rejected|cancelled`, `direction` optional `incoming|outgoing|all` (default `all`). `incoming` значит `receiver_id=actor_id`; `outgoing` значит `sender_id=actor_id`; `all` — все записи группы. Эти фильтры применяются **до пагинации**. Это позволяет Лере показать собственные входящие pending без считывания чужих страниц. Участник группы может читать все записи группы, но transition права отдельно.

`created_at` серверное UTC `Z`; `resolved_at` null в pending и UTC `Z` в terminal. `resolved_at >= created_at`; раз и навсегда установленное terminal состояние не меняется. По продукту реальный банковский перевод происходит **вне системы**: `POST settlement` лишь уведомляет о переводе и создаёт pending.

## 4. Идемпотентность POST create без новой миграции

В `settlements` **уже** есть `UNIQUE(group_id,client_request_id)`, `sender_id`, `receiver_id`, `amount_kopecks`, `created_at` — неизменяемые бизнес-поля. Меняются только `status` и `resolved_at`. Поэтому для MVP **НЕ добавлять JSONB initial-create history или новую Alembic revision** только ради replay: в отличии от редактируемого Expense, исходное создание Settlement однозначно восстановимо из существующих неизменяемых колонок и известного факта `status="pending"`, `resolved_at=null`.

- **Normalized intent** = `(group_id, verified sender_id, receiver_id, amount_kopecks)`; UUID индексируется на группу в таблице settlements. Сравнение amount — по целым копейкам (но строгая грамматика всё равно обязательна), sender берётся только из verified auth.
- При первом POST: group `FOR UPDATE`, проверить sender/group membership, текущий долг/кредит, создать ровно один pending, commit, **201 с первоначальной pending envelope**.
- Тот же UUID + тот же sender + intent после group membership проверки: **200 с восстановленной исходной pending envelope**, даже если запись уже confirmed/rejected/cancelled. **Это исторический результат create, НЕ текущий статус**. Бот для актуального состояния использует GET list с фильтрами. Replay проверяется **до** нового ограничения суммы из-за уже изменившихся балансов — иначе успешный POST после timeout не восстановить.
- Тот же UUID при другом sender/receiver/amount → **409 `request_conflict`** без reveal чужого намерения, body/ID/status. Actor и group membership проверить перед доступом к replay. В другой группе или в таблице расходов тот же UUID может существовать.
- При одновременных POST с одинаковым UUID группа сериализует их и UNIQUE служит второй защитой; ровно один 201, второй 200 либо 409. Для сравнения/recovery проверять `created_at` неизменным и воспроизводить канонический UTC `Z` JSON как при первом POST. **Не отправлять** клиенту старое pending как подтверждение актуального перевода; GET нужен и после первого неизвестного/потерянного ответа.
- **Техническое обязательство** O-07: сделать `sender_id/receiver_id/amount_kopecks/group_id/client_request_id/created_at` неизменяемыми в service layer на всём жизненном цикле, тестом доказать replay после каждого terminal transition. Если текущая реализация требует менять эти поля/ответ create нельзя однозначно восстановить, **остановиться и согласовать** отдельную минимальную миграцию/issue, а не выдумывать копирование expense JSONB.

## 5. Terminal state machine / locks

| Текущее состояние | Действие + actor | Результат |
|---|---|---|
| `pending` | `confirm` от receiver | проверить **свежие** balances, затем `confirmed`, `resolved_at=now`, HTTP200; ровно один финансовый эффект |
| `pending` | `reject` от receiver | `rejected`, resolved_at, HTTP200, эффект 0 |
| `pending` | `cancel` от sender | `cancelled`, resolved_at, HTTP200, эффект 0 |
| `confirmed` | снова `confirm` от receiver | HTTP200 с **текущим confirmed**/оригинальным resolved_at; эффект 0 |
| `rejected` | снова `reject` от receiver | HTTP200 с текущим rejected/resolved_at; эффект 0 |
| `cancelled` | снова `cancel` от sender | HTTP200 с текущим cancelled/resolved_at; эффект 0 |
| Любое terminal | иной transition от role-authorized actor | HTTP409 `settlement_state_conflict`, ничего не менять |
| Любое | action от wrong member (включая owner) | HTTP403 `settlement_receiver_required` или `settlement_sender_required` |
| Чужая/неизвестная группа, settlement ID | Любое действие | HTTP404 `group_not_found` / `settlement_not_found`, без раскрытия |

**Порядок для любой финансовой мутации:** определить group_id settlement без утечки (для action по ID — initial non-authorizing lookup), затем **`SELECT groups FOR UPDATE` первым**, подтвердить membership/право actor, затем `SELECT settlements FOR UPDATE`, проверить статус. Строки groups lock сериализуют expense PUT/DELETE, POST settlement и confirm. Один DB commit на мутацию, любые ошибки → rollback. При duplicate terminal request повтор сохраняет **тот же** `resolved_at`, ни одной доп. confirmed суммы.

На каждом **первом confirm** повторно получить **актуальный согласованный баланс** из active expense final shares и already confirmed settlements *под group lock*, проверив `B_sender<0, B_receiver>0`, и `0<amount<=min(-B_sender,B_receiver)`. При неверных ролях/исчезнувшем долге/возможной переплате **409 `settlement_balance_conflict`**, **сохранить pending** и resolved_at null. Pending не резервирует деньги, так что две pending на один долг допустимы; при конкурирующем подтверждении двух полных — только одно успешно, второе конфликтует. Confirm после expense soft-delete может законно создать обратный баланс — но **не** подтвердить сумму сверх свежего остатка. Confirmed денежная история не меняется от последующего expense PUT/DELETE: reverse debt возможен.

## 6. Ошибки и доступ

| HTTP / `error.code` | Когда |
|---|---|
| 400 `validation_error` | malformed JSON/UUID/body, сумма вне canonical syntax или BIGINT, невалидный limit/offset/status/direction, чужие body fields |
| 400 `invalid_participants` | receiver не член доступной группы / совпадает с sender (не раскрывать существование чужого user) |
| 400 `ambiguous_actor` | mixed JWT/service channel, существующая ошибка |
| 401 `invalid_token` / `invalid_service_token` | credential отсутствует/невалидный |
| 403 `settlement_receiver_required` / `settlement_sender_required` | member, но не владелец transition |
| 404 `group_not_found` / `settlement_not_found` | чужой group/settlement либо неизвестный ID |
| 409 `request_conflict` | один UUID, иной sender/receiver/amount |
| 409 `settlement_balance_conflict` | при create/confirm недостаточно свежего долга и кредита, sign changed |
| 409 `settlement_state_conflict` | несовместимая terminal transition |
| 500 `internal_error` | повреждённый ledger/snapshot/невозможный zero-sum, ошибка DB без деталей |

Ошибочные и неавторизованные попытки не изменяют ledger/settlement status и не выдают private JSON/status, даже на replay. Если у sender пропало членство, replay скрыт (в MVP удаление участника пока недоступно). Не добавлять 422, клиентские значения в error envelope, 401 без WWW-Authenticate или no-store.

## 7. QA matrix для O-06/O-07/T-08/L-05

| Сценарий | Ожидание |
|---|---|
| Ресторан 3200.00: Tim10 +2200, Anton20 −1400, Dasha30 −800 | Балансы и план `20→10:1400.00,30→10:800.00` |
| Anton20→Tim10 500.00 создаёт pending | Балансы **не изменились**, plan тоже |
| Tim confirm 500.00 | Балансы Tim +1700, Anton −900, Dasha −800; plan `20→10:900,30→10:800` |
| Повтор confirm той же записи | 200, тот же resolved_at, **нет второго финансового эффекта** |
| Две pending по 1400 на один долг, concurrent confirm двух соединений | Одна confirmed, вторая pending +409; group lock wait доказан PostgreSQL |
| Расход 100, pending100, PUT снижает долг до60 **раньше** confirm | confirm 409, запись pending, балансы не переплачены |
| confirm100 раньше последующего PUT на60 | confirmed остаётся, после PUT появляется reverse debt −40/+40 |
| Expense soft DELETE после confirmed500 | Не удалять settlement, reverse debt Tim −500/Anton +500 |
| POST UUID lost-response после commit, потом confirmed, тот же intent | 200 **исходный pending create result**; актуальный confirmed — в GET list |
| POST UUID тот же, sender другой или сумма/receiver отличаются | 409 без исходных DTO/ID, только один pending |
| `reject/cancel`/повтор/неправильный actor/state | права по таблице; terminal не переписывается |
| Детерминированные 5 членов и ties + zeros/new member | Q-05 порядок и balance matrix, selected 0 не теряется |
| foreign group, compromised/mixed headers, timeout, malformed requests | 401/403/404/409 без раскрытия секретов, no-store, rollback |
| Проверки большого оборота/несогласованного snapshot | exact SQL NUMERIC, safe500, **не** silent repair |
| READ concurrent expense mutation/settlement confirm | balances/plan один MVCC snapshot, нет половинчатого состояния |
| Regression M3 equal/custom/by_items и bot FSM | Старые URL/wire/replay/версия/preview не ломаются |
| Все 5 GitHub CI checks на текущих head, real PostgreSQL17, clean/repeated Alembic | Обязательные evidence; никакого live Telegram до команды Тимура |

**Порядок:** Тимур T-08 checkpoint и Олег O-06 могут начинать параллельно; O-07 **реализация** после merged O-06; Лера L-05 делает mock-first, реальные маршруты после O-06/O-07. На закрытие T-08 требуется независимое code/security review **реализаций O-06/O-07**, проверка реальных PG races и CI, а не только данный документ. Формальные G2/G3/G4 и production `/internal` (T-09) не объявляются verified.
