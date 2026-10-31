# T-08 — итоговый security / contract review M4 Balances, Settlements, Telegram

**Дата проверки:** 31.10.2026 · **Ответственный:** Тимур (tech lead), [T-08 #45](https://github.com/inte11ectua1/skinulis/issues/45). **База проверки:** `main` `3416dd3f555216e9ab77cdbddbd5a69d6b5aa310` (merge L-05 [PR #54](https://github.com/inte11ectua1/skinulis/pull/54)). Проверка выполнена по коду в GitHub + существующим unit/integration-тестам и успешным GitHub Actions на конечных головах PR; **не заявляется самостоятельный новый локальный запуск PostgreSQL, Docker, настоящего бота или продакшена**.

## Решение / scope

**Техническое решение по M4: PASS (код + проверенная CI/test evidence), критических/высоких блокирующих уязвимостей в выбранных путях не выявлено.** Балансы, ручные компенсации, one-time notification claim и Telegram UI реализованы в `main`. Это **не** формальное G4 `verified` и **не** независимый человеческий `APPROVED` за других участников. Статус «сделано» для личного T-08 audit означает публикацию и ревью этого отчёта, но не разрешение live Telegram и не обход branch protection.

| Объём | Issue / PR | Факт в main | CI на финальном PR head |
|---|---|---|---|
| O-06: read balances / greedy plan | [#46](https://github.com/inte11ectua1/skinulis/issues/46) / [#51](https://github.com/inte11ectua1/skinulis/pull/51) | `88df77d64deb1bd0dbd5702e91b648f954d45fb0`, 30.10 | [41096303217](https://github.com/inte11ectua1/skinulis/actions/runs/41096303217), **5/5**, 871 unit + 310 PG = **1181**, 95,58% |
| O-07: create/list/confirm/reject/cancel | [#47](https://github.com/inte11ectua1/skinulis/issues/47) / [#53](https://github.com/inte11ectua1/skinulis/pull/53) | `b055b7ea073a05b59a7fd7ce58bc3aff6a6ac9eb`, 31.10 | [41195690077](https://github.com/inte11ectua1/skinulis/actions/runs/41195690077), **5/5**, 918 unit + 365 PG = **1283**, 95,71% |
| O-07N: service-only notification claim | [#55](https://github.com/inte11ectua1/skinulis/issues/55) / [#57](https://github.com/inte11ectua1/skinulis/pull/57) | `572f87570d9b0a51db5aa88167a455daa779c0e3`, 31.10 | [41208270181](https://github.com/inte11ectua1/skinulis/actions/runs/41208270181), **5/5**, 929 unit + 382 PG = **1311**, 95,76% |
| L-05: Telegram UI/notify | [#48](https://github.com/inte11ectua1/skinulis/issues/48) / [#54](https://github.com/inte11ectua1/skinulis/pull/54) | `3416dd3f555216e9ab77cdbddbd5a69d6b5aa310`, 31.10 | [41210779152](https://github.com/inte11ectua1/skinulis/actions/runs/41210779152), **5/5**, 1058 unit + 402 PG = **1460**, 94,76% |

Все числа — **отдельные прогоны**, не суммировать их в «5 тысяч новых тестов». Пять статусов в каждом прогоне: `lint`, `types`, `tests`, `docker-build`, `ci` = success. На самом merge-коммите `main` `3416dd3` GitHub API может не показывать отдельных check-runs; зелёный evidence — **финальный head каждого PR**, совпадающий со вторым родителем merge. Качественные ветки и workflow здесь не изменяются.

## Контрольная матрица T-08

| Проверка | Код / тестовая опора | Результат |
|---|---|---|
| Деньги без float, overflow; signed canonical RUB; итоговая сумма вектора 0 | `app/services/expense_balances.py`: SQL `Numeric` cast **до** суммирования, Python `int`, `format_money`, `sum(balances)==0`; `tests/integration/test_balances_api.py` / `test_settlements_api.py` BIGINT/multiplied turnover | PASS |
| Источник истины: только active expenses, итоговые `expense_shares` и `confirmed`; zeros и обратный долг | `calculate_balances`: paid active − final shares + sender confirmed − receiver confirmed; никакого двойного учёта `expense_item_shares` и pending; участники из `group_members`, включая 0. Примеры restaurant3200 и soft-delete | PASS |
| Повреждённые финансовые снимки → safe500 без частичного действия | `calculate_balances`: sum/count снимков + `validate_receipts`; `ExpenseSnapshotInvalid`, глобальный safe500/no-store; real PG corruption/regression | PASS |
| Greedy plan детерминированный, не persisted и не «глобальный минимум» | `app/services/settlement_plan.py`: descending initial abs amount, tie numeric user_id ASC, two pointers, `min(remaining)`; `GET /settlement-plan` не пишет ни plan, ни pending. Fixtures/O-06 tests | PASS |
| Согласованный MVCC snapshot для GET | `read_balances`: отдельный PostgreSQL `REPEATABLE READ` + `SET TRANSACTION READ ONLY`; membership, receipts и ledger queries — одна транзакция. Reader/writer overlap tests `test_balances_api`, `test_settlements_api` | PASS |
| Public JWT / internal Telegram actor; membership/role и безопасные ошибки | `app/api/balances.py`, `app/api/settlements.py` (две явные auth зависимости), `telegram_dependencies.py` service credential, mixed-auth rejection, sender из проверенного actor; group/settlement foreign404, receiver-only confirm/reject, sender-only cancel, owner без override, no-store/WWW-Authenticate/ошибки с request_id | PASS |
| UUID create/replay, no double financial effect | `app/services/settlements.py`: unique(group,client_request_id), intent проверяется под group lock, same intent 200 original **pending** snapshot (даже после terminal), другой 409 без чужого JSON; mutation только status/resolved_at; terminal same-action 200/no-op с прежним resolved_at, иной 409 | PASS |
| Своевременный recheck текущего долга, concurrency | `require_member(...lock=True)` получает `groups FOR UPDATE` перед settlement; при confirm `calculate_balances` внутри write transaction, `<= min(debt,credit)` иначе 409 pending сохранён. Реальный PG `pg_blocking_pids`: duplicate UUID, double confirm, confirm vs reject/cancel, confirm vs expense PUT/DELETE в обоих порядках; DB trigger rollback | PASS |
| Notification recipient и at-most-once разрешение | `app/services/settlement_notifications.py`, `app/api/settlement_notifications.py`: **только /internal bot-service verified sender**, user DB id не Telegram chat id, recipient lookup из `users.telegram_id`, group lock → settlement lock; stamp при 200 и no-binding204; terminal/replay204; actor foreign safe404 | PASS |
| Миграция 0006, исторические pending, независимость finance | `alembic/versions/0006_settlement_notification_claim.py`: nullable TIMESTAMPTZ и `notification_claimed_at=created_at` для старых rows, new NULL; `alembic_version.version_num` расширено до64 из-за 34-символьного revision ID. PG fresh/repeat/downgrade/re-upgrade/check tests; financial ledger unaffected | PASS |
| Telegram private best-effort, fallback, recovery | `bot/settlement_notifications.py`, `bot/settlement_actions.py`: claim лишь после acknowledged create/recovery, 200 → одна `send_message` в проверенный Telegram ID, 204/error/timeout → no send; Telegram blocked/timeout не откатывает pending и не вызывает новый finance POST; нейтральный текст, GET list для актуального состояния. Unit+HTTP/PG tests `test_bot_settlement_notifications` | PASS |
| Нет bank API и live Telegram в рамках M4 | Сервер регистрирует внешние переводы вручную; bot не выполняет split/greedy и реальные платежи. В tests Telegram session замокана, live polling не запускался | PASS / gate deferred |

## Findings / ограничения

**T08-01 (процесс, medium, OPEN):** на просмотренных финальных PR #51/#53/#57/#54 **не зарегистрировано независимых `APPROVED` GitHub review**; наблюдались только `COMMENTED` assistant-assisted у #57/#54. Не выдавать requested reviewers, green CI, merged status или этот отчёт за реальные human approvals. **Не корректировать историю PR и не отключать/обходить защиту GitHub**; для принятия данного T-08 audit нужен review Олега и Леры на PR отчёта. Если команда сочтёт важным восстановить historical human evidence, это отдельная процессная задача/зафиксированное исключение, не доказанный approvals прошлых PR.

**T08-02 (документация, low, решено этим PR):** `docs/STATUS.md` сверху ещё содержит исторические «O-07N in progress / PR review», «O-07 not merged» несмотря на merge #53/#57/#54; обзорный раздел M4 устарел. Обновить **актуальный срез в начале**, исторические записи ниже сохранить как срезы с датами и не выдавать их за текущие. Roadmap Тимура также должен показывать завершённую кодовую приёмку и review PR.

**Границы / не findings кода:** production isolation `/internal` относится к T-09/M5 и не подтверждено этим review; M4 live Telegram E2E/G2/G3/G4 **намеренно не выполнялись** по решению Тимура (Issue #38 `not_planned`). Green mocked Telegram + real HTTP/PostgreSQL tests **не** означают live Telegram QA, банковскую интеграцию, production deployment или verified gate. Нагрузочный тест/системный O-08 не входили в T-08.

**Потенциальный residual risk:** best-effort notification claim — **at most one permission**, не гарантированная доставка. После выдачи claim ответ может потеряться, а после его получения статус уже стать terminal; интерфейс просит проверить актуальные входящие. Telegram notifications охватывают только flow создания через бота, не все public JWT POST; это **осознанная граница принятого контракта**, зафиксированная в [T-08_PENDING_NOTIFICATION](../contracts/T-08_PENDING_NOTIFICATION.md).

## Checklist закрытия T-08

- [x] Контракты M4 утверждены через [T-08 M4](../contracts/T-08_M4_BALANCES_SETTLEMENTS.md) / [PR #50](https://github.com/inte11ectua1/skinulis/pull/50) и [T-08 Notification](../contracts/T-08_PENDING_NOTIFICATION.md) / [PR #56](https://github.com/inte11ectua1/skinulis/pull/56); реализованы/merged O-06/O-07/O-07N/L-05.
- [x] Финальный security audit кодовых paths, actor/roles/UUID/terminal/overpay/locks and receipts / one-time notifications.
- [x] Cross-check реальных PG concurrency/migration и финишных CI 5/5 на каждом PR head с SHA и покрытием.
- [x] Документирован проверяемый результат, тестовые доказательства, остаточные риски и границы.
- [ ] Получить **независимый human review этого отчёта** от Олега/Леры с явной отметкой, что исторические missing approvals не считаются восстановленными задним числом.
- [ ] Merge документационный PR (с `Closes #45`) после green CI и необходимого review, проверить автоматическое закрытие #45. Не закрывать вручную раньше требований.

**Вердикт:** кодовая/техническая часть T-08 выполнена, **formal GitHub PR review/merge этого аудита ещё требуется**. Не смешивать с формальными gates или релизной приёмкой.
