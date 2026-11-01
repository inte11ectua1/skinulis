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

## Завершённый M3 (30.10.2026)

[O-04 #36](https://github.com/inte11ectua1/skinulis/issues/36) / [PR #41](https://github.com/inte11ectua1/skinulis/pull/41) — **merged/closed**: equal/custom CRUD и version/UUID, preview и conditional mutation balances. [O-05 #39](https://github.com/inte11ectua1/skinulis/issues/39) / [PR #42](https://github.com/inte11ectua1/skinulis/pull/42) — **merged/closed**: by_items, stored positions/zero shares, all full PUT modes, original replay. Тимур закрыл аудит [T-07 #35](https://github.com/inte11ectua1/skinulis/issues/35) через [PR #44](https://github.com/inte11ectua1/skinulis/pull/44), который добавил проверку испорченных simple snapshots перед PUT и `no-store` на error responses. Эти защиты не откатывать.

## M4 — завершён (31.10.2026)

[O-06 #46](https://github.com/inte11ectua1/skinulis/issues/46)/[PR #51](https://github.com/inte11ectua1/skinulis/pull/51), [O-07 #47](https://github.com/inte11ectua1/skinulis/issues/47)/[PR #53](https://github.com/inte11ectua1/skinulis/pull/53) и дополнительная O-07N [#55](https://github.com/inte11ectua1/skinulis/issues/55)/[PR #57](https://github.com/inte11ectua1/skinulis/pull/57) **merged/closed**. T-08 [#45](https://github.com/inte11ectua1/skinulis/issues/45)/[PR #58](https://github.com/inte11ectua1/skinulis/pull/58) завершил финальный security review, [отчёт](../reviews/T-08_M4_FINAL_SECURITY_REVIEW.md). Реальные concurrency/PG CI пройдены, но это не live Telegram G4. Процессное замечание о независимых approvals сохраняется.

## Текущая задача M5 — [O-08 #61](https://github.com/inte11ectua1/skinulis/issues/61)

**Начинать сейчас от актуальной main**: security и свойства financial invariants, strict public/internal actor, реальные независимые PostgreSQL17 concurrent session tests и controlled load из 100 одновременно активных клиентов с p50/p95/p99/ошибками и воспроизводимым сценарием. Цель p95 ≤500 ms зависит от описанной нагрузки и **должна быть измерена**, а не заявлена заранее. Все деньги точные копейки, стабильные terminal effects и replay; не трогать bot и деплой без согласования. [Handoff](../operations/M5_DELIVERY_HANDOFF.md), [CI/требования](../TECHNICAL_DECISIONS.md).

**Безопасность:** никаких production DB/VPS/load/live Telegram. Добавить документацию нагрузки, PG race доказательства, 5/5 CI и independent review. Финальный PR `Closes #61` только когда весь scope измерен и принят, промежуточный `Refs #61`. M5 инфраструктура T-09 #59 развивается параллельно, не блокирует локальное O-08.

**Инфраструктурное решение 01.11.2026:** T-09 #59 сменён с VPS на ноутбук+Compose, публичных серверов для нагрузки нет. Для O-08 #61 продолжай тестировать только отдельную disposable PostgreSQL с согласованными нагрузочными профилями. Не измеряй p95 на рабочей БД ноутбука Тимура с реальными пользователями. [ADR003](../adr/003-laptop-as-demo-host.md).

## Для своего чата
«Проверь расчёты на контрпример», «Составь тест конкурентного подтверждения для PostgreSQL», «Раздели O-07 на безопасные PR», «Проверь атомарность изменения расхода».

