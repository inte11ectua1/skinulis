# L-03 — Telegram-онбординг, профиль, группы и приглашения

> Исторический срез L-03. Расходы и принятый server preview добавлены в
> [L-04](L-04_EXPENSES.md). Live Telegram/ручные проверки реального бота отложены
> до отдельного разрешения Тимура (Issue37/6468318123); прежний ручной чек-лист ниже
> не является командой запускать их сейчас.

[Issue #24](https://github.com/inte11ectua1/skinulis/issues/24), база `main` `8ab4c3c`,
28.10.2026. PR #18, #26, #27 проверены как merged. Контракт
[T-06](../contracts/T-06_IDENTITY.md) утверждён
[Тимуром в #22](https://github.com/inte11ectua1/skinulis/issues/22#issuecomment-6437632203).
Старые отметки proposed/mock-ready в STATUS, L-01 и L-02 — исторический контекст.
L-03 использует принятые UQ-01/02 и групповые UQ-04/05; финансовые вопросы,
expense-preview UQ-03 и L-04 здесь не реализуются. Backend/миграции/Compose не меняются.

## Подготовка и безопасный запуск

Python 3.12.15, uv 0.13.5, команды из корневого README. Зависимости не добавлены,
pyproject/lock и порог покрытия сохранены. Поднимите свой локальный API с PostgreSQL17
и миграциями до `0003_groups_identity`, как описано в README. Используйте отдельную
тестовую БД/Compose project; пользовательские данные и volumes не удаляйте.

В существующем `.env` добавьте настройки в редакторе, не перезаписывая файл.
`.env.example` содержит только пустые значения секретов.

| Переменная | Требование бота |
|---|---|
| TELEGRAM_BOT_TOKEN | Обязательный токен отдельного тестового бота, без default; используется только Telegram session |
| BOT_SERVICE_TOKEN | Обязательный отдельный credential, 43–128 URL-safe символов, тот же у API и бота; генерировать локально `secrets.token_urlsafe(48)` и сохранять без публикации |
| API_BASE_URL | Default `http://localhost:8000`; HTTP(S), без credentials/query/fragment; production — только внутренний адрес |

Переменные процесса имеют приоритет над `.env`. SecretStr скрывает секреты из repr
и ошибок валидации. Бот не импортирует backend Settings, не читает БД или JWT key,
не отправляет Bearer JWT и не принимает actor из текста/callback. Для `/internal`
он передаёт `X-Bot-Service-Token` и `X-Telegram-ID` из `from_user.id` проверенного
Telegram Update. Production reverse proxy должен закрывать `/internal` снаружи
(Тимур/T-09); production isolation этим PR не проверяется.

```sh
uv sync --frozen
uv lock --check
uv run python -m bot.main
```

Один polling-процесс на токен, `handle_as_tasks=False`, MemoryStorage и
SimpleEventIsolation. `Ctrl+C` закрывает HTTP/Telegram sessions и FSM; ошибки и
отмена также проходят cleanup. Нет настоящего тестового токена — не запускать
polling с подставным. Проверки ниже настоящего токена не требуют.

## Пользовательский путь и FSM

```text
/start → read profile → есть → меню
                     → 404 telegram_profile_not_found → выбор Create / Link
Create → отдельное согласие → bootstrap → подтверждённый профиль → меню
Link → код от публичного API → telegram-link → подтверждённая привязка → меню
deep-link → тот же onboarding → отдельное «Вступить» → join → карточка группы
```

| Состояние | Ввод/действие | Результат/восстановление |
|---|---|---|
| Onboarding.choice | Создать / Привязать / Не сейчас | Никакой записи до явного согласия; отказ очищает ввод |
| Onboarding.consent | Да, создать / Назад | POST bootstrap только после «Да»; повтор текущей кнопки не создаёт вторую операцию |
| Onboarding.link_code | Только одноразовый код | Пользователь сам получает `POST /users/me/telegram-link-code` с `{}` в своём JWT-авторизованном публичном API; TTL10min проверяет сервер. Пароль/JWT/email-доступ в боте не запрашиваются |
| Onboarding.uncertain | Проверить профиль | Ошибка чтения не означает нового пользователя. После неопределённого write — GET profile; наличие профиля не выдается за доказательство конкретной привязки, нужно сверить свой профиль и `/users/me` в API |
| Navigation.menu | Профиль / Мои группы / Создать группу | Меню ничего не создаёт; профиль и права перечитываются через API |
| GroupFlow.name → confirm | Имя → Создать / Изменить / Отмена | NFC → Unicode strip → 1..120 codepoints, без category C/ZWJ, как T-06. Одно нормализованное тело и UUID сохраняются до ответа |
| Просмотр группы | Участники / К группам | Название, owner и user IDs из API; чужих email/Telegram ID у участников нет |
| GroupFlow.invite_confirm | Создать приглашение | Owner проверяется API; реальный bot username получаем через Telegram getMe **до** записи; token показывается владельцу только при первой выдаче |
| GroupFlow.invite_uncertain | Читать metadata по страницам | Поиск своего client_request_id; найденный потерянный invite явно отозвать, затем явно создать новый. Нет автоматического POST и восстановления raw secret |
| GroupFlow.revoke_confirm | Да, отозвать | DELETE; повтор того же пути безопасен; consumed409 — отказ |
| GroupFlow.join_confirm | Вступить / Не вступать | Не раскрывать группу до join; deep-link `i_<43 URL-safe chars>`. Только явный POST текущего actor; отказ очищает token |
| GroupFlow.join_uncertain | Мои группы / Обновить | Нет слепого POST после timeout. Даже отсутствие группы в прочитанном списке не доказывает окончательный отказ |
| GroupFlow.busy | Запрос в пути | Последовательная обработка, экран инвалидирован до write; повтор не имеет второго эффекта |

`/help` сохраняет черновик. `/start` посреди диалога предлагает продолжить либо
`/cancel`, не заменяет данные другой ссылкой. `/cancel` очищает черновик, код и
invite-намерение, не отменяет записи API; затем читает профиль. Команда, пришедшая
во время HTTP-запроса, обрабатывается после его конечного timeout/ответа, не обещает
rollback. Новый `/start` нужен после «Не сейчас». Неожиданный текст не цитируется.

Все списки используют только `{items,limit,offset}`, limit20. «Далее» предлагается
для полной страницы; последняя следующая страница может быть пустой. Есть возврат,
обновление и явный пустой результат, нет `total`/`has_next` или обещания числа страниц.
Только owner видит приглашения в карточке; API проверяет доступ на каждом запросе,
в том числе через старую кнопку. Нет удаления группы/участника/смены owner.

Callback содержит случайный идентификатор текущего экрана и индекс серверного
действия, без actor/секретов. На новом экране, после подтверждения, отмены или
рестарта старая кнопка недействительна. Дубликаты последних4096 update IDs
подавляются в памяти процесса до вызова обработчика. После рестарта это не
durable dedup: старый write callback без FSM не выполняется; bootstrap и UUID
защищает сервер. Несохранённое имя/UUID/invite-намерение после рестарта теряются.
Сначала перечитайте профиль/группы/приглашения. Потерянный UUID не восстанавливается,
новое намерение с новым UUID может создать другую группу, даже с тем же именем.

Код привязки никогда не записывается в FSM; передаётся один раз в JSON body.
Invite-намерение хранится как SecretStr только до согласия/отмены и удаляется перед
POST join. Raw issued token не сохраняется в FSM. Ошибки содержат только локальные
тексты: сырые message/code/request_id не выводятся в чат/логи. Aiogram INFO с bot
identity отфильтрован; warning/error заменён общей диагностикой без exception args
и traceback. Ссылка выводится только владельцу, с отключённым preview.

## Подключённые маршруты

| Метод | Путь | Назначение |
|---|---|---|
| GET | /health | Доступность, без service headers и без создания профиля |
| GET | /internal/users/me | Read-before-create, профиль текущего Telegram actor |
| POST | /internal/users/bootstrap | Явный Telegram-only bootstrap, `{}` |
| POST | /internal/users/telegram-link | Потребление `{code}`, без merge |
| GET / POST | /internal/groups | Свои страницы / создание с name+client_request_id |
| GET | /internal/groups/{group_id} | Карточка, только member |
| GET | /internal/groups/{group_id}/members | Страницы участников |
| GET / POST | /internal/groups/{group_id}/invites | Owner metadata / выдача с client_request_id |
| DELETE | /internal/groups/{group_id}/invites/{invite_id} | Отзыв, owner only |
| POST | /internal/group-invites/join | Добровольное вступление с `{token}` |

UserProfile/Group/Member/InviteIssued/InviteProfile/Page — Pydantic v2 DTO из
утверждённых схем. DTO-поля дополнительно сверяются с реальным app.openapi() в тесте.
Identity IDs — строгие positive signed BIGINT. Один httpx.AsyncClient на процесс,
connect timeout3s, read/write/pool5s, общий deadline10s; автоматических retries нет,
redirect/proxy-env отключены. `async with`/`aclose()` безопасно закрывают клиент.

HTTP400/401/403/404/409/5xx, network/timeout и невалидный ответ централизованно
превращаются в безопасные ошибки. Только `404 telegram_profile_not_found` запускает
онбординг; прочие404 не означают отсутствия профиля. `link_code_invalid` объединяет
invalid/expired/used/revoked; `invite_invalid` — те же причины ссылки. Не угадывать
причину/имя скрытой группы. `already_member`, `group_full`, `owner_required`,
`invite_consumed`, no-merge конфликты и request_conflict имеют понятные тексты.

## Mock и реальные integration проверки

```sh
uv run pytest tests/unit/test_bot_client.py tests/unit/test_bot_handlers.py tests/unit/test_bot_runtime.py tests/unit/test_bot_identity_client.py tests/unit/test_bot_onboarding_groups.py
uv run pytest
uv run ruff check .
uv run ruff format --check .
uv run mypy .
uv run pre-commit run --all-files
uv run coverage run -m pytest
uv run python scripts/test_integration.py --cov --cov-append --cov-report=term-missing
```

Unit: httpx.MockTransport + mocked Telegram BaseSession; no real token, HTTP,
PostgreSQL или polling. Проверяются согласие/отказ, профиль, linking/конфликты,
UUID retry, списки/права, issue/null-token/recovery/revoke/join, cancel/restart,
double click/update, секреты в ответах/логах, ошибочные DTO/config/HTTP.

Штатный `scripts/test_integration.py` создаёт свой UUID Docker project и tmpfs DB,
удаляет только свои контейнеры через down **без -v**. Внешнюю PostgreSQL17 можно
использовать по существующему README: задать TEST_DATABASE_URL через безопасное
окружение, psycopg driver, bootstrap БД с суффиксом `_test`, роль с CREATEDB, затем:

```sh
uv run coverage run --append -m pytest -m integration
uv run coverage report --precision=2 --fail-under=60
```

Existing fixture создаёт/удаляет только собственные UUID-БД, а не bootstrap БД.
Новые `tests/integration/test_bot_identity_groups.py` применяют настоящие миграции,
поднимают Uvicorn на зарезервированном loopback socket и через обычный HTTP-клиент
прогоняют Dispatcher → API → PostgreSQL. Заменена только Telegram session:
profile → group → invite → onboarding второго actor → voluntary join, member403,
used invite404, owner revoke; отдельно register/login/code в публичном API → link
в боте → проверка того же user через public me. Секреты/actor не логируются.
API thread и sockets закрываются; пользовательские БД не используются.

В этой Windows-среде Docker не установлен: штатный runner завершается WinError2,
Docker build локально не проверен. Для реального прогона использован portable
PostgreSQL17.11 из официального EDB ZIP (SHA-256 сверён с
[опубликованным EDB checksum](https://github.com/EnterpriseDB/edb-installers/issues/682)),
свежий scratch cluster, случайный пароль, loopback, без системной установки сервиса.
После проверки процесс остановлен; пользовательские сервисы не останавливались.

Первый запуск существующего набора:64 passed /4 failed при default timezone
Europe/Moscow. Причина: первый и повторный DELETE представляют один revoked_at
как UTC Z и +03:00; тесты сравнивают JSON строка-в-строку. В отдельном task cluster
установлен UTC (как CI), без изменения тестов/backend: полный набор70 passed,
включая два новых настоящих HTTP сценария. Это не исправление non-UTC поведения;
вопрос Тимуру — унифицировать сериализацию времени либо явно закрепить UTC отдельно.

Итоговые команды, coverage и GitHub CI текущего commit фиксируются в PR. Предупреждение
Starlette о будущем httpx2 не подавляется; pytest cache в ограниченной Windows-среде
перенесён в отдельный доступный scratch каталог, проверки не отключаются.

## Ручная приёмка

- [ ] Тимур независимо проверил handlers, DTO, trusted actor, no-merge и recovery.
- [ ] CI текущего head: lint/types/tests/docker-build/ci success.
- [ ] Отдельный безопасно настроенный тестовый Telegram-бот: два тестовых пользователя
  проходят create/link → group → owner invite → voluntary join → revoke; повторные
  нажатия/перезапуск показывают корректное восстановление.
- [ ] Проверить реальные Telegram deep-links, getMe username и доставку клавиатур.
- [ ] После approval и checks человек выполняет merge и обновляет STATUS.

Live Telegram E2E здесь **не запускался**: отдельный реальный тестовый бот не настроен.
Mocked Telegram + настоящий API/PostgreSQL не заменяет эту ручную проверку. G2 и
production готовность этим документом не объявляются закрытыми.
