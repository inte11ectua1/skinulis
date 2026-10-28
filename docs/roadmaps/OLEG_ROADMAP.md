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

## Завершённая фаза M1 (27.10.2026)

**O-02** закрыта: [Issue #11](https://github.com/inte11ectua1/skinulis/issues/11), [PR #16](https://github.com/inte11ectua1/skinulis/pull/16) и [#17](https://github.com/inte11ectua1/skinulis/pull/17). Реализованы pure `parse_money`/`format_money`, `equal/custom/by_items` и unit-тесты. Q-01/Q-02 утверждены, часть Q-04 подтверждена; Q-03 и Q-05–Q-10 требуют отдельных решений до зависимых этапов. ORM/финансовых API здесь нет.

## Завершённая фаза M2 (28.10.2026)

**[O-03 #23](https://github.com/inte11ectua1/skinulis/issues/23) / [PR #31](https://github.com/inte11ectua1/skinulis/pull/31) — merged/closed.** Финансовые SQLAlchemy models `expenses`, `expense_items`, `expense_shares`, `expense_item_shares`, `settlements`, миграция `0004_financial_domain` после `0003_groups_identity`; signed BIGINT суммы, composite membership FK, RESTRICT, immutable-by-design snapshots через сервис будущего этапа, soft-delete fields. [PR #33](https://github.com/inte11ectua1/skinulis/pull/33) и [Issue #32](https://github.com/inte11ectua1/skinulis/issues/32) зафиксировали решения Q-03/Q-04/Q-10/position/resolved_at. [Финальный CI](https://github.com/inte11ectua1/skinulis/actions/runs/40678199167) прошёл все пять jobs. **Нет O-04/O-05 HTTP CRUD, group-first financial services, balances или settlement state machine**; SQL constraints не гарантируют межстрочные суммы. Независимый APPROVED-review PR #31 в GitHub не зарегистрирован.

## Следующие задачи roadmap — O-04 → O-05 (M3, Issues ещё не назначены)

**O-04:** групповые транзакции `SELECT groups FOR UPDATE`, расход `equal/custom`, доступ только участникам и редактирование только автором, `client_request_id`/replay, пагинация и soft-delete без изменения подтверждённых компенсаций; реализовать принятую Q-03 Unicode-политику на API boundary. Уточнить Q-06/Q-07/Q-08/Q-09 до фиксации DTO.

**O-05:** `by_items` 1..50 позиций, серверный итог из позиций, сохранённый итоговый `expense_shares` snapshot и **нулевые строки явно выбранных долей** Q-10. Не суммировать item shares второй раз в balances. Согласовать серверный expense preview UQ-03 до L-04 — он не утверждён.

## Для своего чата
«Проверь расчёты на контрпример», «Составь тест конкурентного подтверждения для PostgreSQL», «Раздели O-07 на безопасные PR», «Проверь атомарность изменения расхода».

