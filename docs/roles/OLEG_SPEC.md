# Спецификация роли: ОЛЕГ — financial backend engineer

## Миссия
Сделать денежное ядро детерминированным, конкурентно безопасным и доказуемо корректным. Уровень риска выше UI: код должен выдержать спорные и параллельные сценарии.

## Ownership
Модели expenses, expense_shares, expense_items, expense_item_shares, settlements; Alembic revisions; чистые split/plan функции; CRUD, balances, settlement state machine; unit+integration+concurrency tests; документация финансового API.

## Спецификация функциональности
1. Money parser/formatter: только точная строка RUB с 2 знаками -> int копейки; лимиты, validation.
2. equal: duplicate participant reject, stable id order, positive total; 0 share допустима; custom: неотрицательные shares и exact sum; by_items: server computes total, shares per item, combined expense_shares, no double counting.
3. Expense CRUD, author=payer, soft-delete, per-group participants and author permissions, snapshots, version-concurrency on PUT if needed. Full atomic replacement of nested rows.
4. Balances from active expenses and confirmed settlements only; sum=0 invariant and stable plan; payer needn't be consumer.
5. Compensation pending -> confirmed/rejected/cancelled; confirm must recheck debt/credit under group row lock; duplicate confirm no double effect; overpayment 409.
6. All finance mutations acquire groups FOR UPDATE first. Use idempotency UUID unique keys; tests for duplicate and overlapping concurrent settlements.
7. Editing/deleting expense after confirmed preserves settled transfer; reverse balance allowed and expected.

## Critical tests
- 100 RUB split 3; 1 kopeck split 3; custom wrong sum.
- Restaurant 3200, shares 1000/1400/800, Tim +2200, Anton -1400, Dasha -800; 500 confirmed yields +1700/-900/-800.
- Concurrent two full-debt pending confirms: at most one can confirm; same confirm twice unchanged.
- Cross-group participant, payer outside consumption, new member no retroactive allocation, soft-delete creates reverse debt after confirmed.
- Error during PUT leaves no partial shares/items.

## Acceptance
Financial unit tests fully deterministic; integration tests run on real PostgreSQL; all financial writes transactional; no float; API contracts Pydantic/OpenAPI; no bot-only math; performance scenario documented with 100 concurrent clients and p95 measurement.

## Coordination
Timur supplies actor/group membership; Oleg supplies schemas/endpoints and fixtures for Lera. Review all financial migrations with Timur. Do not edit T-ownership auth or L-ownership handlers unilaterally.

