# L-06 — offline Telegram UX regression

Issue [#62](https://github.com/inte11ectua1/skinulis/issues/62), база main `6132f99`.
GitHub проверен 02.11.2026: L-05 #54, O-07N #57 и T-08 #58 merged;
O-08 PR #74 на старте открыт и в ветку не включён. Область L-06 — bot,
его тесты и документация. Backend, контракт, миграции, proxy и production не меняются.

## Что именно проверяется

Это **offline E2E**: настоящий aiogram Dispatcher/FSM → настоящий httpx →
локальный FastAPI/Uvicorn → отдельная PostgreSQL17 с действующими миграциями.
Только Telegram session mocked. Второй слой — MockTransport для точного ввода
HTTP/DTO/network ошибок. Production API/DB, настоящий bot token, polling,
нагрузка O-08 и реальные уведомления не используются. G2/G3/G4 не verified.

Существующие fixtures local_api/database_url/telegram/Harness, expense fill/open_wizard
и restaurant переиспользованы. Общий choose теперь ищет кнопку **текущего nonce**
среди видимых сообщений: /help, /start и уведомления о старых кнопках могут быть
последними сообщениями без клавиатуры. Выбор старой клавиатуры этим не разрешается.

## Матрица expected / actual

Ниже actual относится к целевым локальным прогонам. Полные количества regression,
coverage и CI **окончательного head** находятся в описании PR; результаты разных
запусков не складываются как новые тесты.

| Сценарий | Expected | Actual / evidence |
|---|---|---|
| /start, явное согласие, duplicate Update | До согласия profile404; после один профиль и меню | HTTP+PG: test_bot_ux_e2e; одинаковый Update доставляется дважды |
| API account → одноразовый code → Telegram link | Код только в Telegram, JWT/password только в public API; код не в FSM/логах | HTTP+PG: тот же E2E, app user ID совпадает с зарегистрированным |
| Создание группы, owner invite, voluntary deep-link join | Одна группа, сведения видны после вступления; Dasha проходит onboarding | HTTP+PG: три пользователя, две ссылки, состав проверен API |
| equal/custom/by_items + server preview | Preview не пишет; после consent по одной записи; by_items total только API | HTTP+PG: E2E, исходный ресторан3200, нули custom0.00 сохранены |
| Expense list/detail и текущая версия | Показать API snapshot, original mutation не выдавать за current | E2E +9 recovery cases для трёх modes и network/invalid JSON/DTO после commit |
| Edit/delete перед original POST replay | GET показывает version2 либо недоступность удалённого; дубля нет | HTTP+PG: test_bot_ux_recovery, POST UUID/body byte-identical |
| Изменённый body со старым UUID | request_conflict409, без новой записи/автоключа | HTTP+PG: каждый recovery case; unit сохраняет frozen intent |
| Известные401/403/404 при save | Черновик остаётся, старый preview отключён; повтор осознанный | Unit matrix; настоящий invalid service token401 → тот же UUID/body → один expense |
| Изменение отклонённого черновика | Новое содержимое → новый intent/key, старую кнопку нельзя использовать | Unit test_changed_rejected_draft_is_a_new_intent |
| GET400/401/403/404/409/429/500, timeout/network/JSON/DTO | Русский текст, новый read-only retry nonce, нет write | Unit read matrix; прежний callback отвергается |
| HTTP429 на expense/settlement POST | Понятное ограничение, результат может быть неизвестен; frozen UUID, без autoretry | Unit rate-limit tests, повтор только явной кнопкой и тем же body |
| Expense mutation с чужой group/id/UUID | Не показывать неподтверждённую запись, сохранить recovery | Unit unexpected_mutation_group; GET чужого ID не вызывается |
| /start/help/cancel/back/continue | Активный ввод не исчезает; /cancel не обещает rollback | L-03/L-04/L-05 unit states + новый реальный cancel после commit |
| MemoryStorage restart и stale/forged callback | Старый nonce не пишет, сохранённая запись остаётся, UUID не восстанавливается автоматически | HTTP+PG cancel/restart + существующие mock restart tests |
| Malformed index, включая ² | UNKNOWN, без исключения/записи/утраты текущего экрана | Unit malformed_callback_index (4 inputs) |
| Ресторан и частичный перевод | 2200.00/-1400.00/-800.00 → pending500 без эффекта → confirmed1700.00/-900.00/-800.00 | HTTP+PG E2E; после confirm UI получает новые balances/plan |
| Confirm repeat/reject/cancel/terminal | Один эффект, rejected/cancelled без эффекта | E2E + test_bot_settlements, API terminal timestamp/no-op regression |
| Две full pending / changed debt / expense edit/delete / reverse | Только допустимый confirm;409 остаётся pending; confirmed history сохраняется | Существующие реальные test_bot_settlements и backend tests выполняются вместе |
| Empty/list/filter/pagination20 | Серверный порядок, items/limit/offset; без total/has_next | L-03/L-04/L-05 list/filter/21-record tests сохранены |
| Чужая группа/expense, чужой author | Safe404/403, нет финансовых изменений | Новый HTTP+PG access test и существующие regression |
| Owner не receiver; wrong sender/receiver | Owner не получает дополнительных прав, чужих кнопок нет | Новый HTTP+PG: Dasha→Anton, ownerTimur confirm403 |
| Forged actor callback/body, mixed JWT/service, invalid service | Из callback не извлекать actor; body400, mixed400, credential401 | Новый HTTP+PG, ledger и pending неизменны; контракт T-06 не менялся |
| Notification claim200 и verified recipient | Одна private attempt только в серверный Telegram ID, нейтральный текст | E2E + существующие unit/реальные test_bot_settlement_notifications |
| Claimed/terminal/no binding/204 | Нет send; повтор/restart не выдаёт новую попытку | L-05/O-07N реальные PG stamp/replay/migration/race tests сохранены |
| Claim400/401/403/404/409/429/5xx/timeout | Нет send или нового financial POST; incoming остаётся | Новая unit matrix8 + существующие network/malformed tests |
| Telegram blocked/OS/network/timeout/deadline | Pending/ledger не отменяются, исключение не публикуется | Существующие mocked session и real HTTP/PG delivery tests сохранены |
| Секреты/приватные данные/финансовая математика | Нет secret/SQL/raw exception в UX/logs; вычисляет только backend | E2E runtime-secret assertions, unit notification/privacy, существующие AST/logging tests |

## Дефекты и исправления

| ID | До | После |
|---|---|---|
| L06-01 | Expense save401/403/404 очищал draft через список; повтор терял ввод | Сохраняется business draft, требуется свежий preview. При неизменном intent UUID/body сохраняются; при изменении body ключ очищается |
| L06-02 | API read failure инвалидировал nonce и оставлял диалог без кнопки | Только для явно перечисленных read/preparation actions выдаётся fresh «Повторить просмотр». Финансовые writes сюда не входят |
| L06-03 | HTTP429 выглядел как непонятный API response | Отдельный локальный русский текст; conservative unknown-result policy и отсутствие autoretry сохранены |
| L06-04 | Структурно валидная, но не относящаяся к запросу expense mutation могла вести к чужому GET/ложному ACK | Проверяются group, expense ID при PUT и UUID при POST; несоответствие → uncertain recovery |
| L06-05 | Unicode digit ² проходил isdigit, затем int вызывал ValueError | Индекс callback должен быть ASCII; malformed данные получают UNKNOWN, текущий nonce остаётся |

Каждое поведение сначала воспроизведено падающим целевым тестом, затем закреплено
regression. Тестовые ошибки .test email (валидатор отвергает special-use domain)
и выбор последнего сообщения вместо текущего nonce исправлены в synthetic helpers,
а не в backend. Используется example.com; никакие email не отправляются.

## Безопасные UX тексты и восстановление

| Ситуация | Текст/действие |
|---|---|
| Неизвестный результат POST | «Ответ на изменение не подтверждён. Результат пока неизвестен. Сначала проверьте сохранённые данные»; explicit original retry с frozen UUID/body |
| Ограничение запросов | «Слишком много запросов. Подождите и повторите действие вручную; автоматических повторов нет» |
| Ошибка GET | Локальный safe error + «Ввод сохранён. Повторите просмотр или используйте /cancel»; новая кнопка только чтения |
| Известный отказ save | Черновик не сохранён, значения остаются; после восстановления доступа новый server preview и явное подтверждение |
| Старый callback/restart | «Эта кнопка больше не действует. Возможно, бот перезапущен и черновик потерян»; /start, сначала проверить записи |
| /cancel после отправки | «Сохранённые записи не отменяются… результат остаётся неизвестным: сначала проверьте свои данные» |
| Claim/send error | Без ложного сообщения «уведомление доставлено»; pending видна через меню, backend stamp не сбрасывается |

Воспроизводимый synthetic пример: E2E показывает расход «Ресторан»3200.00,
API shares1000.00/1400.00/800.00, затем pending500.00. Получатель видит вопрос
«Вы реально получили500.00…?» и предупреждение о реальных деньгах. После confirm
показываются серверные1700.00/-900.00/-800.00 и новый план. Уведомление содержит
только предложение `/start → Ожидают подтверждения`, без сумм/имён/ID/nonce.
Тестовые transcripts проверяются assertions; реальных Telegram screenshots нет.

## Как повторить проверки

На Linux / в CI, без настоящего Telegram:

```sh
uv sync --frozen
uv lock --check
uv run ruff check .
uv run ruff format --check .
uv run mypy .
uv run pytest
uv run pre-commit run --all-files
uv run coverage run -m pytest
uv run python scripts/test_integration.py --cov --cov-append --cov-report=term-missing
uv run coverage report --precision=2 --fail-under=60
```

Только новые unit: `uv run pytest tests/unit/test_bot_ux_regression.py`.
Только новая реальная интеграция:
`uv run python scripts/test_integration.py tests/integration/test_bot_ux_e2e.py tests/integration/test_bot_ux_recovery.py`.
Runner использует disposable Docker project/tmpfs. Без Docker разрешён отдельный
локальный PostgreSQL17 через TEST_DATABASE_URL (bootstrap DB оканчивается на `_test`,
роль CREATEDB, случайный пароль только в окружении). Затем
`uv run coverage run --append -m pytest tests/integration -m integration`.
Fixture создаёт и удаляет только собственные UUID-БД. Никаких production URL,
внешних тестовых серверов с реальными данными, prune/down -v/reset.

**Фактическое ограничение этой Windows-машины:** полный `uv run pytest` ещё на
неизменённой main останавливается при collection трёх deployment unit modules:
нет Unix fcntl. Обычный `mypy .` даёт15 существующих platform errors в
scripts/backup_postgres.py, scripts/deployment.py и test_deployment.py (flock,
geteuid/O_NOFOLLOW/O_DIRECTORY). Docker/установленного WSL нет. Никаких skip,
xfail, ignore или заглушек fcntl не добавлено; T-09 код не менялся.
Локально запускаются все test_bot*.py и integration-каталог. Дополнительный strict
`mypy --platform linux .` проверяет настоящий целевой Linux API; это не замена
стандартному mypy/pytest в Linux CI. pre-commit с default mypy на Windows имеет
тот же известный отказ, его результат указывается честно. Полный Linux CI обязан
проверить весь suite и все пять jobs на финальном head.

## Ограничения и handoff L-07

MemoryStorage и update dedup не durable. После рестарта key/draft могут потеряться;
нельзя обещать восстановление UUID или автоматически создавать новый POST.
Сначала история/списки и актуальные GET. /cancel не отзывает уже отправленный
запрос. Read retry никогда не превращается в скрытый write retry.

Best effort — at-most-once permission, не гарантия доставки. Claim/send loss может
означать пропуск; menu pending работает отдельно. Создание через public JWT API
само Telegram send не запускает, outbox/worker не добавлялись.

Backend bottlenecks/load O-08, production proxy/deployment T-09 и logging policy
T-10 не менялись. Новых нарушений actor/proxy контракта не обнаружено: проверки
локальные, без Caddy/production probes. Тимуру передаётся только portability
finding Windows/fcntl для будущей документации tooling; это не security approval.
Нужен обычный independent review Тимура и Олега.

В L-07: составить пользовательское руководство и короткий трёхпользовательский
smoke/demo по этому vertical path; сначала отдельно получить разрешение Тимура
на live Telegram и безопасное окружение/отдельного тестового бота. Затем проверить
реальные кнопки/доставку/лимиты/поведение после restart и оформить human acceptance.
Этот PR не выполняет L-07 и не объявляет G2/G3/G4 verified.
