# O-04 — реализация Expense CRUD equal/custom

Контрактные блокеры сняты [решением Тимура от 28.10.2026](https://github.com/inte11ectua1/skinulis/issues/36#issuecomment-6469818682),
подтверждены в [T-07](https://github.com/inte11ectua1/skinulis/issues/35#issuecomment-6469842260),
[L-04](https://github.com/inte11ectua1/skinulis/issues/37#issuecomment-6469846549)
и [PR #41](https://github.com/inte11ectua1/skinulis/pull/41#issuecomment-6469852025).
Это техническое решение, не персональный APPROVED-review Леры. Предыдущий
[checkpoint](https://github.com/inte11ectua1/skinulis/issues/36#issuecomment-6469108140)
сохранён в GitHub как история предложения; действующий контракт —
[O-04_EXPENSES](../contracts/O-04_EXPENSES.md), Pydantic/OpenAPI и
[JSON fixtures](fixtures/O-04_EXPENSES.json). Факт merge/независимое review — в PR.

## Реализация

- `app/schemas/expenses.py`: одна discriminated union equal/custom для create,
  preview и PUT; extra forbid, strict positive BIGINT JSON IDs/version, точные
  RUB strings. Принятая Q-03: NFC → strip → 1..120 code points → reject category C.
- `app/api/expenses.py`: шесть sync операций, публичные и /internal mirrors.
  Только существующие проверенные T-05/T-06 actors, без actor fields в JSON.
- `app/services/expenses.py`: подготовка через O-02, сохранённые snapshots,
  membership/read/page, group-first lock и атомарные storage primitives.
- `app/services/expense_crud.py`: весь request commit/rollback, original POST replay,
  author-only PUT/DELETE, expected_version и неизменяемое создание history.
- `app/services/expense_balances.py`: разрешённая read-only агрегация mutation
  envelope при confirmed, без публичного O-06 API/cache/plan и без O-07 state machine.
- `app/models/finance.py` + `0005_expense_replay_version`: JSONB intent/result и
  version; остальные таблицы/PK/FK/UUID scope не менялись.

Сервисы не доверяют payer из body: actor становится автором/плательщиком,
создание/чтение только member, изменение только author. Owner не исключение.
Payer может не входить в consumers. Group lock первая, expense lock следующая;
non-locking lookup group_id допустим до group lock. Сессия остаётся request-scoped,
write_transaction существующий, один commit. При ошибке после удаления старых
shares rollback восстанавливает expense, version, history и все доли.

## Снимки, история и точность

Equal/custom используют существующие parse_money/validate_expense_amount/split_*
без копирования математики. Все явно выбранные нули остаются в snapshot. Смена
состава группы не переписывает историю. Цена 1..100000000 коп., exact custom sum;
полная PUT заменяет все shares. Вложенную детализацию by_items O-04 не заменяет.
GET/list читают metadata+shares одним SQL snapshot; пагинация expenses перед join
не обрезает доли и не создаёт N+1. Пустой/несбалансированный snapshot — safe500.

POST хранит нормализованное первоначальное намерение и полную исходную envelope
в той же транзакции. Replay после PUT/DELETE возвращает её, не актуальные shares
или balances. Другой actor/тело —409 без исходных данных. Legacy history NULL
остаётся неизвестной, не восстанавливается из текущей записи. ORM guard запрещает
заменять/очищать уже установленную history, DTO её вообще не принимает.

PUT проверяет версию и увеличивает её; stale не перезаписывает данные. Первый
DELETE также проверяет версию и увеличивает её, повтор автора сохраняет tombstone
и version. Soft-delete сохраняет доли/позиции/confirmed; balances при повторном
DELETE вычисляется заново. Возврат балансов не превращает replay POST в актуальный
финансовый экран: сохранённая исходная envelope остаётся неизменной.

При confirmed проверяются суммы всех active snapshots; paid − shares + sent −
received суммируется точным SQL NUMERIC, cast выполняется ДО unary arithmetic.
Python int/format_money сохраняют точность, включая вектор выше signed BIGINT.
Все члены группы, включая нули, в ASC user_id, сумма вектора 0. Item shares не
вычитаются второй раз. Pending/rejected/cancelled и чужая группа исключены.

## Миграция

Единственная цепочка: 0005_expense_replay_version → 0004_financial_domain →
0003_groups_identity → 0002_users → 0001_baseline. Новые JSONB nullable, legacy
значения NULL; version BIGINT NOT NULL DEFAULT1, CHECK ck_expenses_version >0.
Старые migrations не переписаны, startup create_all/migrate отсутствуют.
Downgrade удаляет только новые поля и уничтожает replay history, поэтому это
не штатный откат реальных данных; тест выполняет его только на disposable БД.

## Проверки и границы

Новые HTTP+PostgreSQL tests проверяют оба actor канала, CRUD/preview, строгие
JSON/errors, суммы/нули, scope UUID, исходный replay после правок/удаления,
immutable history, версии, пагинацию, чужой доступ/owner restriction, confirmed
balances, реальное переполнение агрегата за BIGINT, corruption500/rollback.
Concurrency использует независимые request Sessions: pg_stat_activity доказывает
перекрытие на lock. Проверены same-key POST, conflicting POST, stale PUT,
PUT-vs-DELETE и повтор DELETE. Миграционный тест сохраняет существующие финансовые
строки и shares, проверяет NULL-history/version1, repeat/check/downgrade/re-upgrade.
Прежние O-02/O-03/identity/bot tests сохраняются; обновлены ожидаемые migration heads.

O-05, публичный GET /balances/plan, settlement state machine, Telegram handlers,
production deployment и отложенный live Telegram G2 не реализуются. Реальная
HTTP-интеграция Леры — после merge API; mocks можно строить по принятому контракту.
Независимое ревью Тимура/Леры и человеческий merge остаются обязательными.

Команды проверки: frozen sync/lock, Ruff check/format, mypy ., pre-commit --all-files,
pip check, audit --locked, git diff --check, Docker build. Тесты:

```powershell
uv run pytest --cov=app --cov=bot --cov-report=term-missing --cov-report=xml
uv run python scripts/test_integration.py --cov=app --cov=bot --cov-append --cov-report=term-missing --cov-report=xml
uv run alembic heads
uv run alembic history
```

alembic check/upgrade запускаются тестами только внутри штатной disposable БД.
Свежие результаты и реальный GitHub CI run указаны в PR; прежний run промежуточного
среза 7bb6415 не является проверкой завершённого API.

## Проверка завершённого scope — 28.10.2026

Локально 693 unit +207 PostgreSQL17 integration passed (всего 900, без skip/xfail).
В O-04 добавлены 106 unit и 69 integration относительно main; из integration
33 проверяют HTTP, 1 — upgrade существующей financial schema, 35 — primitives.
Branch coverage app+bot 96,56%; expense API 100%, finance models 100%,
Expense DTO 97,75%, CRUD orchestration 95,80%, shared primitives 96,36%.
Агрегация mutation balances 88,57%: защитные ветки невозможного при FK вектора
не вызываются искусственно ради процента; математические сценарии проверены.

Frozen sync/lock, Ruff check/format, mypy . (85 файлов), pre-commit --all-files,
pip check, audit --locked, diff check и Docker build --pull успешны; известных
уязвимостей в 72 внешних пакетах нет. Единственное предупреждение тестов —
существующая Starlette/httpx deprecation, без подавления/обновления зависимостей.
CI текущего head и независимое review отражаются в PR #41; локальные результаты
не выдаются за remote CI или персональное APPROVED другого участника.
