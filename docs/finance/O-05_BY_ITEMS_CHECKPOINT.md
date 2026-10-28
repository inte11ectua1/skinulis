# O-05 — внутренний by_items срез и контрактный checkpoint

**Draft / Refs #39. Новые by_items HTTP DTO и режимные переходы ещё не приняты.**
Этот PR не закрывает весь Acceptance O-05 и не объявляет работающим новый wire API.

Проверено на старте: main `4b710f5`, [PR #41](https://github.com/inte11ectua1/skinulis/pull/41)
merged, Issue #36 closed, #39 open/assigned pylinolg-max, единственный actual
Alembic head `0005_expense_replay_version`. Содержимое main совпало с проверенной
финальной ревизией O-04 `323b098`; новые опубликованные комментарии проверены.

[Checkpoint с JSON и вопросами](https://github.com/inte11ectua1/skinulis/issues/39#issuecomment-6471710129)
опубликован **до кода**, связан с [T-07](https://github.com/inte11ectua1/skinulis/issues/35#issuecomment-6471710771)
и [L-04](https://github.com/inte11ectua1/skinulis/issues/37#issuecomment-6471711447).
Ответов по новым пунктам пока нет. Общие утверждённые URL/preview/actor/version/
errors/envelope/replay из [O-04](../contracts/O-04_EXPENSES.md) не переоткрываются.

## Что сделано без выбора внешнего контракта

В **существующем** `app/services/expenses.py` добавлены внутренние frozen types:
ReceiptItemInput, ByItemsExpense, PreparedExpenseItem и ExpenseItemSnapshot.
ExpenseSnapshot теперь может содержать сохранённую детализацию. Это Python-типы,
не публичные JSON-схемы; Pydantic union/маршруты не расширены молча.

prepare_expense принимает внутренний ordered receipt, нормализует названия по
принятой Q-03, разбирает RUB существующим parse_money, вызывает **split_equal
отдельно на каждой позиции**, проверяет 1..50 items и общий предел 100000000.
Final snapshot агрегирует union потребителей, включая все выбранные нули.
Входные коллекции не изменяются; алгоритм O-02 не переписан.

Ресторан: total320000; final10:100000,20:140000,30:80000; пицца30000 каждому.
Две позиции по1 коп. дают final10:2,20:0,30:0: независимый остаток каждой позиции,
без предварительного деления общей суммы. Input root amount во внутреннем receipt
отсутствует; отдельная HTTP-схема пока ждёт согласования.

## Хранение и замена

Используются существующие четыре таблицы O-03/O-04:

| Порядок записи | Содержимое |
|---|---|
| expenses | Серверный total и mode, verified internal actor |
| expense_shares | Единственный итоговый snapshot с нулями |
| expense_items | Position в порядке внутренней последовательности, title/стоимость |
| expense_item_shares | Сохранённые per-item shares, включая нули |

FK требуют финальную строку до item share; все ссылки group/expense/item согласованы.
Для полной **storage** замены явно удаляются item shares → items → final shares,
затем пишется новый снимок. Group lock/одна транзакция/rollback — прежние.
При ошибке реального CHECK в середине записи восстанавливаются старые item IDs,
порядок, title/total, final/item shares и history целиком. Старые initial intent/result,
UUID/group/payer/created_at не меняются, confirmed не трогаются.

Для receipt замены editor требует **явный внутренний allow_receipt=True**.
Это opt-in storage primitive для тестов/будущего согласованного адаптера,
**не разрешение HTTP-переходов**. Обычный O-04 adapter не включает этот флаг.
Тесты всех storage переходов не объявляются приёмкой by_items PUT/версий API.
Физическая замена текущих деталей не означает аудита всех промежуточных PUT-версий:
политику wire-переходов ещё согласуют, исходный POST history остаётся неизменным.

Soft-delete не удаляет ни одной detail/final строки; повтор сохраняет tombstone.
Новый member не меняет snapshots. Новых моделей/таблиц/migrations нет, head остаётся0005;
identity/auth/groups/бот/dependencies/CI/Docker/исторические migrations не менялись.

## Чтение и корректность

Metadata, final shares, items и item shares выбираются одним SQL/MVCC snapshot.
CTE выбирает только parent IDs страницы; UNION ALL добавляет final/detail rows,
не создавая произведения final×item shares. Исторический порядок берётся из position,
внутри items/final доли в numeric user_id ASC. Чтение не вызывает split_equal
и не перераспределяет деньги по текущему составу группы.

Проверяются: непустые item snapshots, сумма каждого item, сумма позиций = расходу,
union выбранных consumers со всеми нулями и точное per-user соответствие final.
Коррупция — ExpenseSnapshotInvalid → прежний безопасный500, без исправления данных.
В mutation_balances добавлена проверка активных stored receipts; **ledger арифметика
по-прежнему вычитает только expense_shares**, не item shares. Это прежняя ограниченная
агрегация O-04, не публичные O-06 endpoints/plan и не O-07 state machine.

Измерено на PostgreSQL: 50 items ×30 consumers =1500 detail shares +30 final rows;
detail read — **1 SQL/1530 rows**, а не45000. Page двух таких расходов — не более3 SQL
включая membership,3060 rows без смешения snapshots. Это проверка отсутствия N+1/
Cartesian amplification, не p95/load acceptance будущего O-08.

## Что именно предложено команде

[JSON fixtures](fixtures/O-05_PROPOSED.json) явно помечены proposed, не OpenAPI:

1. Item input только {title,amount,participants}; position вычислять1..N из массива,
   клиент position/item_id/group_id не передаёт. Root amount/participants/shares запрещены.
2. Item output {position,title,amount,shares:[{user_id,amount}]} без DB item_id;
   selected participants следуют из shares, включая0. Такой же output для preview.
3. Поле items добавлять **только by_items** profiles (detail/list/mutation/preview);
   equal/custom и старые original POST envelopes не получают даже items:null.
4. Разрешить все full-PUT переходы equal/custom↔by_items и by_items→by_items с прежними
   версиями/правами. Их включение в публичный адаптер требует ответа T-07/L-04.
5. В normalized by_items intent порядок items значим: normalized title/копейки/
   sorted consumers каждого item; поменять разные блюда местами с тем же UUID —409,
   переставить consumers внутри item — эквивалентный replay. Не сортировать блюда.

После решения необходимо добавить третью Pydantic ветку/response serialization,
by_items intent и original replay, согласованные публичные переходы, OpenAPI,
typed fixtures и реальные HTTP by_items/concurrency/preview/version tests.
Эти пункты **пока не реализованы и не отмечаются выполненными**. Сервер сейчас
отклоняет публичный by_items body прежней union; production intent/preview имеют
явные guards, чтобы внутренний receipt случайно не получил неверную семантику.
Исходный equal POST replay после внутренней receipt замены/soft-delete проверен:
возвращается старый JSON без новых полей, history не переписывается.

## Проверки и ревью

Новые unit: ресторан/копейки, нули/разные consumers, перестановки и неизменность
входов, NFC/strip/category C, строгие ID/деньги,1/50 и0/51, общий предел, сверка
с pure O-02 для воспроизводимых чеков. Новые PG:4уровня, FK/группы/author,
storage transitions, реальный mid-write CHECK rollback, corrupted item/final data,
large receipt/no N+1, MVCC чтение во время writer, overlapping first insert/replace/
delete с pg_stat_activity, immutable equal original replay, confirmed balances
без double counting, soft-delete/history и закрытый до решения новый wire.

Локально на Python 3.12.15 / uv 0.13.5: **732 unit +232 PostgreSQL integration =964
passed**, из них новые39+25. Combined coverage app+bot с учётом ветвлений **96.37%**
(2142/2193 lines,382/426 branches); coverage XML сформирован. Пройдены frozen sync,
lock check, Ruff/format, strict mypy (87 файлов), pre-commit all-files, pip check,
audit (72 пакета, нет известных уязвимостей), diff check и Docker build --pull.
Полный PG runner удалил только собственный UUID-named tmpfs test project.
В тестах одно предупреждение библиотеки Starlette о будущем TestClient/httpx;
ошибок/skip/xfail нет. Новые зависимости не добавлены.

**Новый** реальный GitHub run всех5 jobs и ссылка на точную ревизию — в PR.
Прошлая зелень #41 не считается проверкой этой ветки. Алгоритмы O-02/финансовые
правила не меняются.

Тимуру: проверить SQL/FK/lock/rollback/validation и принять новые контрактные пункты.
Лере: item DTO/нули/исторический порядок, preview, порядок intention и mode changes.
Approval/merge не подменяется авторской реализацией. #39 открыта, PR Draft Refs #39,
O-06/O-07/бот/deploy/live Telegram G2 не начинались.
