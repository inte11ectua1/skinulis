# Общий roadmap (зависимости, интеграция, gate)

**Актуальный статус 03.11.2026:** M1–M5 **завершены по принятому объёму реализации и первичному rollout**, включая T-09 #59, T-10 #60, O-08 #61, L-06 #62 и O-09 #76, все closed. [M5 closeout и handoff M6](../operations/M5_CLOSEOUT_M6_HANDOFF.md), [STATUS](../STATUS.md). G5 технически подтверждён первым public rollout (SHA `f7020cd`); baseline M6 `main` `638a976` ещё не был развёрнут. G1 (закрытая `not_planned` T-01 #2), G2/G3/G4 live Telegram и независимые GitHub review — отдельные **незакрытые вопросы приемки курса**. M6 выполняется Тимуром в единой [#79](https://github.com/inte11ectua1/skinulis/issues/79): DoD, финансы, offline Telegram, guide/demo. [Отчёт приёмки](../reviews/M6_ACCEPTANCE_REPORT.md); G6 PARTIALLY, не закрыт. M7 — [#80](https://github.com/inte11ectua1/skinulis/issues/80). M0–M7 — фазы, не календарные недели. Исторические вехи ниже не переписываются задним числом.

| Фаза | Тимур (T) | Олег (O) | Лера (L) | Общий gate |
|---|---|---|---|---|
| M0 Условия | T-01 Github/branch protection/ADR001; T-02 стек/uv/ADR002 | O-01 аудит математических инвариантов | L-01 UX-карта бота | Репо, правила и PR согласованы |
| M1 Skeleton | T-03 FastAPI/Postgres/Alembic/Compose; T-04 CI minimal | O-02 чистые split functions и unit-тесты | L-02 каркас aiogram и mock HTTP-клиент | Из main собирается локальный API; PR -> CI |
| M2 Identity | T-05 Auth/JWT, T-06 группы/invites и bot actor | O-03 модели финансов и миграции | L-03 /start, bootstrap/link и группы на mocked API | E2E профиль -> группа |
| M3 Expenses | T-07 review безопасности, интеграция API | O-04 CRUD equal/custom, O-05 by_items | L-04 мастера расходов по контракту | Ресторанный тест и bot flow |
| M4 Balances | T-08 audit locking/idempotency | O-06 балансы и settlement plan; O-07 компенсации | L-05 баланс, переводы, подтверждения | Частичный перевод обновляет баланс только после confirm |
| M5 Delivery (закрыт) | T-09 #59 GHCR/CD/VPS/Caddy, T-10 #60 логи; O-09 #76 pool fix | O-08 #61 PG/finance/load | L-06 #62 offline E2E/UX | Первичный GHCR/HTTPS G5 evidence; O-09 p95 waiver |
| M6 Acceptance (#79, выполняется) | Тимур: единый DoD audit, clean start, finance QA, offline Telegram, guide/demo | Консультация/review, отдельная Issue не нужна | Консультация/review, отдельная Issue не нужна | G6 PARTIALLY: технический QA есть, human/process/live/formal gaps раскрыты |
| M7 Defense | T-12 rehearsal PR to deploy | O-10 defense calculations/Q&A | L-08 Telegram live demonstration | 7m presentation, 5m live-demo, 8m Q&A |

## Итог M1 — принято в main (27.10.2026)

- **Тимур:** [T-03 #10](https://github.com/inte11ectua1/skinulis/issues/10) — FastAPI, PostgreSQL 17, Alembic, Compose, `/health`, `/version` — **closed**, [PR #15](https://github.com/inte11ectua1/skinulis/pull/15).
- **Олег:** [O-02 #11](https://github.com/inte11ectua1/skinulis/issues/11) — pure money parser/equal/custom/by_items, Q-01/Q-02 — **closed**, [PR #16](https://github.com/inte11ectua1/skinulis/pull/16) и [#17](https://github.com/inte11ectua1/skinulis/pull/17).
- **Лера:** [L-02 #12](https://github.com/inte11ectua1/skinulis/issues/12) — каркас aiogram, typed httpx mock client — **closed**, [PR #18](https://github.com/inte11ectua1/skinulis/pull/18).
- **Тимур:** [T-04 #13](https://github.com/inte11ectua1/skinulis/issues/13) — GitHub Actions lint/types/PostgreSQL tests/coverage/Docker build, требуемые checks — **closed**, [PR #19](https://github.com/inte11ectua1/skinulis/pull/19).

**Реализация M1 завершена.** Для G1 подтверждены локальные cold start/миграции/health и CI (включая намеренно красный run); окончательное доказательство блокировки merge из-за failed required checks в GitHub UI отсутствует, а PR #19 объединён без зарегистрированного независимого approval. Текущая защита для administrators отличается от первоначального ADR (см. STATUS).

## Завершённая фаза M2 — Identity (28.10.2026)

- **Тимур:** [T-05 #21](https://github.com/inte11ectua1/skinulis/issues/21) / [PR #26](https://github.com/inte11ectua1/skinulis/pull/26) — users, Argon2id, JWT auth, `0002_users`; [T-06 #22](https://github.com/inte11ectua1/skinulis/issues/22) / [PR #27](https://github.com/inte11ectua1/skinulis/pull/27) — groups/membership/invites, service Telegram actor/link, `0003_groups_identity`. Follow-up [#29](https://github.com/inte11ectua1/skinulis/issues/29) / [PR #30](https://github.com/inte11ectua1/skinulis/pull/30) — UTC `Z` API dates. Всё merged/closed.
- **Олег:** [O-03 #23](https://github.com/inte11ectua1/skinulis/issues/23) / [PR #31](https://github.com/inte11ectua1/skinulis/pull/31) — пять финансовых ORM-таблиц, constraints/FK/исторические доли и `0004_financial_domain`; docs checkpoint через [PR #33](https://github.com/inte11ectua1/skinulis/pull/33), [#32](https://github.com/inte11ectua1/skinulis/issues/32). Merge и закрытие 28.10, [финальный CI 5/5](https://github.com/inte11ectua1/skinulis/actions/runs/40678199167).
- **Лера:** [L-03 #24](https://github.com/inte11ectua1/skinulis/issues/24) / [PR #28](https://github.com/inte11ectua1/skinulis/pull/28) — Telegram onboarding, profile, groups/invites, типизированный HTTP service client, FSM/timeout и mock + PostgreSQL integration. Merged/closed 28.10.

**G2 — implementation complete, not verified:** тесты backend/бота и CI есть, но нет подтверждённого live Telegram E2E и production-изоляции `/internal`. Финансовые таблицы O-03 — это **хранилище**, не расходы CRUD, balances или settlements state machine.

## Завершённый этап M3 — Expenses (30.10.2026)

- **Олег:** [O-04 #36](https://github.com/inte11ectua1/skinulis/issues/36) / [PR #41](https://github.com/inte11ectua1/skinulis/pull/41) — equal/custom CRUD, versioned PUT/DELETE, UUID original replay, preview и confirmed mutation balances; [O-05 #39](https://github.com/inte11ectua1/skinulis/issues/39) / [PR #42](https://github.com/inte11ectua1/skinulis/pull/42) — by_items, позиции/нули и все mode transitions. **Merged/closed**.
- **Лера:** [L-04 #37](https://github.com/inte11ectua1/skinulis/issues/37) / [PR #43](https://github.com/inte11ectua1/skinulis/pull/43) — Telegram expense wizards, preview/list/details, безопасный replay/recovery, mock + PostgreSQL HTTP integration. **Merged/closed**, но не live Telegram.
- **Тимур:** [T-07 #35](https://github.com/inte11ectua1/skinulis/issues/35) / [PR #44](https://github.com/inte11ectua1/skinulis/pull/44) — аудит безопасности и исправления corrupt simple snapshot PUT + error no-store; **merged/closed**, [отчёт](../reviews/T-07_M3_SECURITY_REVIEW.md), [CI 5/5](https://github.com/inte11ectua1/skinulis/actions/runs/41064210033), 857 unit +290 PG integration.
- **G3** остаётся formally **not verified**: ресторанная арифметика и bot→HTTP→PostgreSQL с mocked Telegram transport тестировались, реальный Telegram E2E не проводился по просьбе Тимура. G2 тоже отложен, [Issue #38](https://github.com/inte11ectua1/skinulis/issues/38) закрыта `not_planned`. Не возобновлять.

## Завершённый M4 — Balances/Settlements (31.10.2026)

- **Тимур:** [T-08 #45](https://github.com/inte11ectua1/skinulis/issues/45) / [PR #58](https://github.com/inte11ectua1/skinulis/pull/58) **merged/closed**: контрактные PR #50/#56 и финальный [security report](../reviews/T-08_M4_FINAL_SECURITY_REVIEW.md), [CI 5/5](https://github.com/inte11ectua1/skinulis/actions/runs/41213175596).
- **Олег:** [O-06 #46 / PR #51](https://github.com/inte11ectua1/skinulis/pull/51), [O-07 #47 / PR #53](https://github.com/inte11ectua1/skinulis/pull/53), [O-07N #55 / PR #57](https://github.com/inte11ectua1/skinulis/pull/57) — **merged/closed**. Exact balances/greedy, settlement transitions/locks/replay и одноразовая защищённая notification claim.
- **Лера:** [L-05 #48 / PR #54](https://github.com/inte11ectua1/skinulis/pull/54) — **merged/closed**, Telegram balances/settlements, mocked notification + real HTTP/PG tests, [финальный CI 5/5, 1460 tests/94,76%](https://github.com/inte11ectua1/skinulis/actions/runs/41210779152).
- **Ограничения:** G4 **кодовые/PG доказательства есть, формальный live gate not verified**. Не зарегистрированы independent APPROVED reviews нескольких завершённых PR, [T08-01](../reviews/T-08_M4_FINAL_SECURITY_REVIEW.md) — процессный риск. Live Telegram не запускать до команды Тимура.

## M5 Delivery завершён; текущая M6 Acceptance #79

| Владелец | Реальный итог M5 |
|---|---|
| Тимур | [T-09 #59](https://github.com/inte11ectua1/skinulis/issues/59)/[T-10 #60](https://github.com/inte11ectua1/skinulis/issues/60), approved rollout Caddy/HTTPS/GHCR/DB, logs, runbook; [O-09 #76](https://github.com/inte11ectua1/skinulis/issues/76)/[PR #77](https://github.com/inte11ectua1/skinulis/pull/77) pool fix |
| Олег | [O-08 #61](https://github.com/inte11ectua1/skinulis/issues/61)/[PR #74](https://github.com/inte11ectua1/skinulis/pull/74), финансы, PostgreSQL races, измеренная нагрузка |
| Лера | [L-06 #62](https://github.com/inte11ectua1/skinulis/issues/62)/[PR #75](https://github.com/inte11ectua1/skinulis/pull/75), Telegram UX, mocked → real HTTP/PG offline E2E |

**G5:** проверен первый production API deployment (SHA `f7020cd`), но новый `main` не выкладывался. O-09 после fix: 100 clients, HTTP500=0, p95 956/1098ms; целевые 500ms **FAIL**, Тимур принял отклонение. [Evidence и ограничения](../operations/M5_CLOSEOUT_M6_HANDOFF.md).

**M6:** единая #79 назначена Тимуру, включая finance QA и user guide/demo; отдельные M6 Issues не создавать. [Матрица/результаты](../reviews/M6_ACCEPTANCE_REPORT.md), gate G6 не подтверждён. G1 admin/protection и formal review, G2/G3/G4 live Telegram остаются отдельными вопросами. Без явного разрешения Тимура не проводить live Telegram, AWS rollout или production stress.

## Release gates
- **G1 (после M1):** cold start, migration, /health 200, one real reviewed PR with green CI.
- **G2 (после M2):** auth, group permissions; no impersonation; setup works by README.
- **G3 (после M3):** three modes, CRUD, pagination, rounding; restaurant scenario tested.
- **G4 (после M4):** settlement transition, partial/duplicate/concurrent tests, no changes to confirmed.
- **G5 (после M5):** GHCR build publish tagged SHA, SSH deploy, HTTPS, migration, /version matches commit; secrets limited.
- **G6 (после M6):** DoD, ADR, contribution history, review proofs, runbook, load evidence and stable demo.

## Critical path
T-03 API skeleton -> T-05 auth + T-06 groups -> O-03 models -> O-04/05 CRUD -> O-06/07 money -> L-04/05 connected UI -> T-09 CD -> M6 acceptance. Параллельно CI начинается на M1. Лера работает с mock API до завершения бэкенда, чтобы не блокировать команду.

## Правила при отставании
Не исключать требования DoD и согласованные режимы. Сокращать анимации/UX-бонусы, не добавлять OCR, банк, валюты, Redis. Критический блокер — красный CI/неработающий деплой, даже если бот красивый.

## Учебные артефакты
Практики — последовательные шаги одного проекта. Следить за актуальным https://github.com/andrey-limasov/app-conf/ и закрывать опубликованные требования в issue с доказательствами: ADR, Git protection, чужие ревью, холодный запуск, схемы окружения, Docker optimization issue, live demo, покрытие и нагрузка.

