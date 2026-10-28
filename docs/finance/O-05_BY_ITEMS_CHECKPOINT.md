# O-05 — реализация принятого by_items контракта

Checkpoint до кода: https://github.com/inte11ectua1/skinulis/issues/39#issuecomment-6471710129
Решение tech lead: https://github.com/inte11ectua1/skinulis/issues/39#issuecomment-6473059675
Review промежуточного среза: https://github.com/inte11ectua1/skinulis/pull/42#pullrequestreview-5685176812

Новые DTO/позиции/нулевые доли/все full-PUT переходы/ordered intent приняты Тимуром.
Это не независимый APPROVED Леры. Pre-approval guards сняты; существующая Pydantic
union расширена третьим режимом, API public/internal использует общий service.
Раздельные response DTO исключают items из equal/custom, включая original replay.

[Действующий контракт](../contracts/O-05_BY_ITEMS.md) и
[typed fixtures](fixtures/O-05_BY_ITEMS.json) заменяют proposed-набор. В существующем
expense service реализованы per-item split_equal, четыре уровня хранения, нули,
атомарная замена с group-first lock/RESTRICT rollback, MVCC read без N+1 и final-only
balances. Все включения receipt replacement в HTTP происходят после actor/version
проверки внутри прежней транзакции. Soft-delete и initial JSONB сохраняют историю.

Тесты: математика/границы/Unicode/strict IDs/money, public+internal CRUD/preview,
все mode transitions с confirmed, immutable ordered original replay после PUT/delete,
stale versions, actual mid-write CHECK rollback, foreign participants/author/group,
concurrent HTTP POST/PUT/DELETE с независимыми sessions и наблюдаемыми PG lock waits,
large receipt/read corruption, старый equal/custom JSON compatibility. Полный актуальный
результат unit/PG/coverage/CI на новом head — в PR #42; старая зелень6b1284e не заменяет его.

Схема: единственный head0005_expense_replay_version, без новых migrations/models.
O-06/O-07/бот/deploy/live G2 не выполняются. Issue39 не закрывается автоматически,
merge не выполняется; готовый код требует независимого review.
