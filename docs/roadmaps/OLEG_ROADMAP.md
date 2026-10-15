# Олег — личный roadmap

**Приоритет:** начать с pure functions без зависимости от DB, затем миграции, API, конкурентные финансовые операции.

| ID | Фаза | Задача | Зависимость | Доказательство готовности |
|---|---|---|---|---|
| O-01 | M0 | Проверить деньги, ограничения, математику и тест-кейсы | product rules | утверждён test matrix и API input examples |
| O-02 | M1 | Pure functions equal/custom/by_items, parser копеек | O-01, base pyproject | unit tests 100/3, 0.01/3, invalid, sum exact |
| O-03 | M2 | Expenses/items/shares/settlements SQLAlchemy models + Alembic | T-03 schema ready | миграция from empty DB; FK, indexes, constraints |
| O-04 | M3 | Expense CRUD equal/custom, permissions, pagination, idempotency | T-05/06, O-02/03 | CRUD integration, atomic PUT/soft DELETE |
| O-05 | M3 | by_items persistence, computed total, snapshots | O-04 | ресторан shares 1000/1400/800, no double count |
| O-06 | M4 | balance service + greedy settlement plan | O-04/05 | invariant sum zero, stable plan and tests |
| O-07 | M4 | settlements state machine confirm/reject/cancel, partial, locks | O-06, T-06 | concurrency 2 pending same debt; only 1 confirm |
| O-08 | M5 | Cross-group security, retry, property/integration, load p95 test | O-07 | coverage >=60 globally, 100 concurrent report |
| O-09 | M6 | Performance fixes, migrations review, debt after soft-delete regression | O-08 | regression suite green under CI |
| O-10 | M7 | Financial demo rehearsal + questions | all | can explain transaction/rounding/invariants |

## Стартовая задача Codex
«Изучи AGENTS.md, docs/PRODUCT_RULES.md, docs/contracts/BOUNDARIES.md, docs/roles/OLEG_SPEC.md. Выполни только O-01/O-02: pure Python money parser и функции equal/custom/by_items без DB, HTTP и бота. Добавь unit tests: 100/3, 0.01/3, дубликаты, пустое множество, custom mismatch, by_items pizza. Не создавай миграции до согласования моделей. Прогони Ruff, pytest и опиши контракт».

## Для своего чата
«Проверь расчёты на контрпример», «Составь тест конкурентного подтверждения для PostgreSQL», «Раздели O-07 на безопасные PR», «Проверь атомарность изменения расхода».

