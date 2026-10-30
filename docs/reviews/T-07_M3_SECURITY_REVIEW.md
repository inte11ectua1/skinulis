# T-07 — технический аудит безопасности M3 Expenses

Дата: **30.10.2026**. Задача: [Issue #35](https://github.com/inte11ectua1/skinulis/issues/35).
Аудит выполнен Codex по заданию Тимура. Это техническое ревью готовой реализации,
а не человеческий APPROVED от Олега или Леры. Issue закрывает Тимур после приёмки.

**Постфактум, 30.10.2026:** [PR #44](https://github.com/inte11ectua1/skinulis/pull/44) merged, [T-07 Issue #35](https://github.com/inte11ectua1/skinulis/issues/35) closed as completed. Последний [CI на PR head](https://github.com/inte11ectua1/skinulis/actions/runs/41064210033) 5/5 success на `124bbe5`. Сведения ниже об ожидающих merge/review — исторический срез отчёта до приёмки. Независимого зарегистрированного `APPROVED` PR #44 нет; не объявлять human approval, G2/G3 или production security verified.

## Проверенный срез и основания

База отдельной ветки аудита — актуальная `origin/main`
**`6f0fdd6ab6ee6990b45835012990cb69b86ee6b2`**. Рабочая копия перед началом чистая;
открытых PR при проверке не было. GitHub подтвердил merged:

| Компонент | PR / исходный head | Merge SHA | CI исходного head |
|---|---|---|---|
| O-04 equal/custom CRUD | [#41](https://github.com/inte11ectua1/skinulis/pull/41), `323b098f0ca04877df29684a89ec3d29882db9ee` | `4b710f56634242848a49877a81e7d08dd105892f` | [40700743497](https://github.com/inte11ectua1/skinulis/actions/runs/40700743497) |
| O-05 by_items | [#42](https://github.com/inte11ectua1/skinulis/pull/42), `19fa75d10cb13b932d0990d775f44571a56145e3` | `440031d5cfc0e090ce1651190d3e553a3a62c6d7` | [40728353389](https://github.com/inte11ectua1/skinulis/actions/runs/40728353389) |
| L-04 Telegram expense flow | [#43](https://github.com/inte11ectua1/skinulis/pull/43), `d403f6f4e5b56a8c78c9f1ddc39538533afb7fe2` | `6f0fdd6ab6ee6990b45835012990cb69b86ee6b2` | [41014559764](https://github.com/inte11ectua1/skinulis/actions/runs/41014559764) |

Принятые решения: [O-04 / Q-06–09 и UQ-03](https://github.com/inte11ectua1/skinulis/issues/36#issuecomment-6469818682),
[O-05 / ordered items, переходы и replay](https://github.com/inte11ectua1/skinulis/issues/39#issuecomment-6473059675).
Изучены AGENTS, PRODUCT_RULES, TECHNICAL_DECISIONS, BOUNDARIES, O-04/O-05 contracts,
O-01_OPEN_QUESTIONS, O-03_DATA_MODEL, L-04_EXPENSES, STATUS, личный и общий roadmap,
Issue #35 и комментарии #36/#39. Старые записи «preview не согласован» и
«O-05 не merged» не соответствуют этим решениям и фактическому GitHub.

Окружение: локальная macOS arm64, Python **3.12.15**, uv **0.13.5**,
Docker Engine **23.0.5**, Compose **2.17.3**. Runtime из frozen lock:
FastAPI 0.162.0, Pydantic 2.13.5, SQLAlchemy 2.1.6, psycopg 3.3.6,
Alembic 1.20.1, aiogram 3.31.0, httpx 0.28.1, PyJWT 2.15.1, Argon2-cffi 25.1.0.
PostgreSQL **17.11** — закреплённый image digest из `compose.test.yaml`.
Зависимости, CI, миграции и bot/** этим PR не меняются.

## Матрица Issue #35

Номера строк относятся к файлам этой ветки. «Проверено» означает чтение кода и
успешный запуск указанных автоматизированных сценариев; это не live Telegram QA.

| Требование | Результат / доказательство |
|---|---|
| Принятые DTO, preview и actor channels | Проверено: `app/api/expenses.py:65`, `app/schemas/expenses.py:48`. У всех шести операций два router mirrors, общий business service; union по split_mode и extra=forbid, включая item/share body. OpenAPI/fixtures проверяет `tests/unit/test_bot_expense_client.py:197`. |
| JWT / service identity, запрет смешения | Проверено: `app/api/dependencies.py:23`, `app/api/telegram_dependencies.py:26`. JWT проходит signature/expiry/user lookup; service credential сравнивается constant-time до доверия Telegram ID. Mixed channels →400, missing/invalid credential →401, неизвестный Telegram profile →404. `tests/integration/test_expense_api.py:311`, `:926` проверяют оба канала и отсутствие auth на каждой операции. |
| Member / author / owner, cross-group | Проверено: `app/services/groups.py:19`, `app/services/expenses.py:441`, `:564`. Чужой/несуществующий expense скрыт404; PUT/DELETE чужого расхода участником, включая owner, →403. `tests/integration/test_expense_api.py:243`, `:1230`, `:1332`. |
| Ввод, ошибки, секреты, SQL | Проверено: strict positive BIGINT IDs, exact RUB strings, Unicode NFC/strip/category C, bounded lists/items, safe envelope400/401/403/404/409/500. SQL строится SQLAlchemy с bind parameters, JSON IDs не являются actor, произвольные query/header IDs не читаются как полномочия. `app/schemas/expenses.py:30`, `app/core/errors.py:29`, `app/db.py:15`; `tests/integration/test_expense_api.py:955`, `:595`, `:642`. Лог неожиданных ошибок содержит только request_id, без SQL/payload/traceback. **Замечание T07-02 исправлено.** |
| Group-first, атомарность, confirmed | Проверено: `app/services/expenses.py:564`, `app/services/transactions.py:10`, `app/services/expense_crud.py:128`. Group lock → expense lock; один commit, любое исключение →rollback. `tests/integration/test_expense_api.py:993`, `:615`, `:1230`, `tests/integration/test_expense_service.py:196`. Confirmed не изменяются при PUT/DELETE, проверены в `test_expense_api.py:526`, `:1170`. |
| UUID, original replay, legacy | Проверено: `app/services/expense_crud.py:100`, `:128`, `app/models/finance.py:88`. Membership до replay; другой actor/intent →409 без исходного DTO. NULL legacy history →409, не реконструкция. История не переписывается при PUT/DELETE; исходная envelope возвращается после обоих. `test_expense_api.py:131`, `:353`, `:400`, `:899`, `:1087`. |
| Version и реальные гонки | Проверено: `app/services/expense_crud.py:235`, `:247`, `:269`; `test_expense_api.py:793`, `:816`, `:837`, `:1288`, `:1304`. POST/POST replay/conflict, PUT/PUT stale409, PUT/DELETE, двойной DELETE. Независимые request sessions/соединения; helper `test_expense_api.py:755` ждёт реального lock wait через pg_stat_activity. |
| Exact money, by_items snapshot, нули | Проверено: `app/services/expenses.py:149`, `:198`, `:244`; `app/services/expense_balances.py:15`. Каждый item делится отдельно, итоговый union сохраняет выбранные нули; balances вычитают только final shares. `test_expense_api.py:1087`, `:1170`, `tests/integration/test_by_items_storage.py:126`, `:143`, `:274`. Python int / SQL NUMERIC до арифметики; `test_expense_api.py:570` подтверждает агрегат выше BIGINT без потери точности. |
| Исторические snapshots, пагинация, no N+1 | Проверено с исправлением **T07-01**. `app/services/expenses.py:198`, `:334`, `:459`, `:534`: чтение сохранённых долей одним MVCC snapshot, LIMIT до детализации, без перераспределения по новым members. `test_expense_api.py:483`, `:1037`, `test_by_items_storage.py:328`, `:367`, `:415`. |
| Bot integration / timeout / fixtures | Проверено: раздел ниже; unit/mock и настоящий HTTP → PostgreSQL с заменой только Telegram transport. Никаких live update/polling или пользовательских JWT/паролей. |
| PostgreSQL, Alembic, CI, coverage | Локальные результаты ниже; единственный head0005, upgrade/repeat/check, legacy0004→0005 и downgrade/re-upgrade на UUID test DB. Новый GitHub CI фиксируется в разделе evidence. |

## Маршруты и проверенные сценарии

Каждая строка относится и к публичному пути, и к `/internal` mirror. Public actor
получается только через get_current_user, internal — через get_bot_user. Ни payer,
ни author из JSON/URL/query/непредусмотренных заголовков не задаёт полномочия.

| Метод / путь | Успех и отрицательные сценарии |
|---|---|
| POST /groups/{group_id}/expenses/preview | Все три режима, ресторан и копейки; только SELECT, нет UUID/expense/reservation; foreign group404, invalid consumers400; final POST заново проверяет membership. |
| POST /groups/{group_id}/expenses | 201 / normalized original replay200; изменение intent/actor409; повтор после PUT/DELETE возвращает именно исходную envelope; concurrent same-key не дублирует ни один из четырёх уровней. |
| GET /groups/{group_id}/expenses | Только member, default20/max100, stable(created_at,id), active only; empty/last page, offset выше BIGINT без SQL overflow; сохранены нулевые shares и новые members не меняют историю. |
| GET /expenses/{expense_id} | Saved profile; чужой/unknown/deleted404; equal/custom JSON без items, by_items с упорядоченными items; corrupted sum/item union →safe500. |
| PUT /expenses/{expense_id} | Только author, все 9 mode transitions, full replacement/version+1; stale409, owner/non-author403; mid-write DB failure откатывает children/version/history; повреждённый simple snapshot теперь тоже не заменяется. |
| DELETE /expenses/{expense_id}?expected_version=N | Author-only, первый DELETE проверяет version, stale409; tombstone/version при повторе сохраняются, snapshots/confirmed не уничтожаются; после timeout безопасен прежний ID/N. |

Datetime ответы сохранены UTC Z, в том числе с Europe/Moscow session timezone
(`tests/integration/test_expense_api.py:1044` и существующий `test_utc_timestamps.py`).
Отрицательные body/UUID/version/money/Unicode тесты подтверждают отсутствие записи
при400; сообщения ошибок не содержат чужих ID/email/Telegram ID или исходных DTO.
Неизвестные query/header поля не являются новым API и не наделяют правами;
их игнорирование установлено чтением dependency/router code, а не отдельным fuzz-run.

## Найденные проблемы и исправления

Critical: **0 обнаружено**. High: **0 обнаружено**. Medium: **1 исправлено**.
Low: **1 исправлено**. Обнаруженных незакрытых блокеров в проверенном M3 scope нет.

### T07-01 — Medium: PUT молча исправлял повреждённый simple snapshot

На исходной main `app/services/expenses.py:534` вызывал self.snapshot() перед
заменой только при наличии receipt items. У equal/custom старые final shares
удалялись без проверки их суммы/наличия. Если в БД уже был невалидный снимок,
полный PUT отвечал200, заменял его новым и скрывал проблему; наличие confirmed
не помогало, поскольку balances проверялись уже после замены повреждённых долей.
Это нарушение принятого Q-07/Q-10 «safe500 без авторемонта», не доказательство
того, что обычный клиент способен сам испортить PostgreSQL.

Минимальное исправление: проверка self.snapshot() теперь выполняется для **всех
режимов до удаления старых долей**, под существующими locks/transaction. При
ошибке откатывается также уже увеличенная версия. Математика, DTO, миграции и
права не менялись; к PUT simple-mode добавился один запрос проверки snapshot.

Новый regression: `tests/integration/test_expense_api.py:642`, 8 комбинаций
equal/custom × public/internal × с confirmed/без confirmed. Реальный SQL UPDATE
создаёт несогласованные доли в отдельной UUID-БД. До исправления: **8 failed**,
`assert 200 == 500`; после: **8 passed**. Проверяется safe error, отсутствие
названия из тела в error/log, полный rollback title/mode/amount/version/history,
сохранение повреждённых долей для разбора и неизменность confirmed.

### T07-02 — Low: error responses теряли no-store

У router dependency был no-store только на обычном Response. Обработчик исключения
строил новый JSONResponse без этого заголовка (`app/core/errors.py:33`). В итоге
ошибки400/401/403/404/409/500 нарушали O-04 wire contract, включая GET404.
Это нежелательное кеширование ошибок/состояния доступа; утечка чужого успешного
профиля через кеш в ходе аудита не обнаружена. Семантика запрета хранения:
[RFC 9111 §5.2.2.5](https://www.rfc-editor.org/rfc/rfc9111.html#section-5.2.2.5).

Исправление: общий error_response добавляет Cache-Control: no-store, сохраняя
X-Request-ID, error envelope и WWW-Authenticate. Распространение безопасного
заголовка на остальные API errors намеренно; статусы/сообщения не меняются.
Новый regression `tests/integration/test_expense_api.py:718`: все шесть статусов
на обоих каналах. До исправления **12 failed**, header отсутствовал; после
исправления весь новый набор **20 passed** вместе с T07-01.

Команды воспроизведения (до соответствующего исправления и затем после него):

```sh
uv run python scripts/test_integration.py tests/integration/test_expense_api.py -k corrupt_simple_snapshot -q
uv run python scripts/test_integration.py tests/integration/test_expense_api.py -k errors_are_not_cacheable -q
uv run python scripts/test_integration.py tests/integration/test_expense_api.py -k 'errors_are_not_cacheable or corrupt_simple_snapshot' -q
```

## Ревью L-04 и сопряжения

- `bot/expense_wizard.py:43`, `:64`, `:76`: три typed body без финансовой
  арифметики; edit читает актуальный profile/version, сохраняет исторические нули;
  смена режима очищает несовместимые данные. Любая правка сбрасывает preview.
- `bot/expense_actions.py:34`, `:123`: server preview без UUID/version; save
  сравнивает текущий business body с preview_body; unknown POST сохраняет
  UUID и точный sent_body, replay не генерирует новый ключ. Original POST envelope
  не показывается как current — далее GET. Нет автоматического POST retry.
- `bot/expense_actions.py:93`, `:210`: PUT timeout/conflict →GET/version,
  без повторного stale PUT/ложного заявления о своём успехе; неудачное чтение
  сохраняет recovery. DELETE timeout →тот же ID/expected_version.
- `bot/expense_views.py:25`, `:78`, `:130`: просмотр списка/деталей сохраняет
  неизвестное POST/DELETE намерение и кнопку восстановления; новые мутации в этом
  состоянии не предлагаются. WARNING перед изменением истории и серверные balances.
- `bot/handlers.py:157`, `bot/middleware.py:33`, `bot/main.py:18`: callback только
  текущего private chat/nonce/server action, nonce инвалидируется до dispatch,
  bounded update dedup, SimpleEventIsolation и handle_as_tasks=False.
- `bot/api_client.py:179`, `:252`: service-only headers, actor из Telegram sender,
  не из пользовательского ввода; no redirects/retries, bounded timeouts,
  в chat/log не выводятся raw API diagnostics или credentials.

Подтверждения: `tests/unit/test_bot_expenses.py:264`, `:288`, `:309`, `:474`,
`:589`, `:664`, `:694`, `:717`, `:763`; `tests/unit/test_bot_expense_client.py:28`,
`:125`, `:156`, `:197`; `tests/integration/test_bot_expenses.py:144`, `:220`, `:267`.
Последний набор использует настоящий Uvicorn/loopback HTTP/PostgreSQL, а transport
теряет реальный ответ **после commit**. Это разрешённая HTTP integration с mock
Telegram, не запуск настоящего бота и не live gate G2/G3.

## Выполненные проверки

| Команда / проверка | Фактический локальный результат |
|---|---|
| uv sync --frozen; uv lock --check | Успешно; lock не менялся |
| uv run ruff check . | Успешно |
| uv run ruff format --check . | Успешно, 137 файлов |
| uv run mypy . | Успешно, strict, 94 source files |
| uv run coverage run -m pytest -q | **857 passed**, integration исключены штатным marker |
| uv run python scripts/test_integration.py --cov --cov-append --cov-report=term-missing:skip-covered -q | **290 passed**, реальная PostgreSQL17.11; 20 новых regression cases |
| uv run coverage report --precision=2 --fail-under=60 | **95,46% branch-aware**, app + bot, tests не входят в source; порог60 сохранён |
| uv run alembic heads | Единственный 0005_expense_replay_version |
| Migration / alembic check | `tests/integration/test_postgres.py:20`, `test_expense_replay_migration.py:17`: empty upgrade, repeat, ORM drift check, сохранение legacy финансов, downgrade/re-upgrade; всё прошло |
| uv pip check | 70 установленных пакетов совместимы |
| uv audit --locked | 72 пакета, известных уязвимостей/adverse statuses не найдено |
| docker build --pull --progress=plain -t skinulis-t07-audit:local . | Успешно, image sha256:623bc8b54b4b4169e325d75019b18c7e804e1ea97f4eb4d9b6d7b66a289b47c8 |
| uv run pre-commit run --all-files; git diff --check | Успешно: lock, Ruff lint/format, strict mypy, detect-secrets; whitespace errors нет |

Combined coverage получено последовательными unit run и integration --cov-append,
без перезаписи unit data. 1147 успешных тестов суммарно. Единственное предупреждение
pytest — существующий Starlette/httpx deprecation, не подавлялось. uv audit сообщает
experimental status команды; зависимости не обновлялись ради аудита.
Точный SQL NUMERIC подход сверён с [PostgreSQL17 SUM](https://www.postgresql.org/docs/17/functions-aggregate.html),
порядок row locks — с [PostgreSQL17 locking](https://www.postgresql.org/docs/17/explicit-locking.html#LOCKING-ROWS).

Все БД создавал штатный fixture с UUID на выделенном tmpfs Compose project;
он удаляет только свои test DB. Runner остановил только собственные containers/network,
без удаления пользовательских БД/volumes. Личный .env не использовался как test config.

## GitHub CI evidence

Аудит опубликован в [PR #44](https://github.com/inte11ectua1/skinulis/pull/44).
[GitHub Actions run 41063450363](https://github.com/inte11ectua1/skinulis/actions/runs/41063450363)
на commit **`52079fcd9e0bca9ec8556bc96ae5236e799b5bfc`** завершён:
**lint / types / tests / docker-build / ci — все success**.
Логи Linux runner подтверждают **857 unit +290 PostgreSQL integration passed**,
combined branch coverage **95,46%**, Docker build success. Этот run проверяет
все изменения кода и тестов; последующий коммит добавляет только документационные
evidence. Текущие результаты окончательного head видны в checks PR #44.
CI-конфигурация и критерии не менялись, skip/xfail/continue-on-error не добавлялись.

## Ограничения и техническая приёмка

После двух исправлений и успешного нового CI M3 Expense API **готов к технической
приёмке и независимому review этого PR**. Обнаруженных обходов actor/member/author,
дубликатов или частичных финансовых записей в проверенных сценариях нет.
Это вывод о конкретном срезе и тестах, не обещание отсутствия любых дефектов.

Остаются явные границы:

1. Live Telegram G2/G3 **не запускались** по распоряжению Тимура. Зелёные mock/HTTP
   тесты не заменяют проверку настоящей доставки Telegram.
2. Production reverse-proxy isolation `/internal`, deployment, rate/load testing,
   settlement state machine и отдельные balances/plan API — не scope T-07.
   BOT_SERVICE_TOKEN остаётся доверенным credential всего бота; его компрометация
   не покрывается моделью «не доверять произвольному публичному telegram_id».
3. MemoryStorage/update dedup не durable: после restart UUID/черновик могут быть
   потеряны. Это принятое ограничение, бот предупреждает проверить сохранённые
   расходы и не создаёт новый POST автоматически.
4. Snapshot checks выявляют структурные несоответствия сумм/union; они не являются
   криптографическим аудитом привилегированных SQL-изменений. ORM assignment guard
   не делает JSONB immutable для администратора БД. Исправление T07-01 не чинит
   уже повреждённые данные и намеренно сохраняет безопасный отказ.
5. Решение tech lead в #36/#39 не выдаётся за личный APPROVED Леры. Человеческое
   review, окончательная приёмка отчёта и закрытие #35 остаются за командой/Тимуром.
   Main protection и формальные G1/G2/G3 этим PR не меняются и не объявляются verified.
