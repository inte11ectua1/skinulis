# Общий roadmap (зависимости, интеграция, gate)

**Статус на 28.10.2026:** **M1 Skeleton и M2 Identity завершены по реализации**. Для M2 [T-05 #21](https://github.com/inte11ectua1/skinulis/issues/21), [T-06 #22](https://github.com/inte11ectua1/skinulis/issues/22), [O-03 #23](https://github.com/inte11ectua1/skinulis/issues/23), [L-03 #24](https://github.com/inte11ectua1/skinulis/issues/24) closed, PR #26/#27/#28/#31 merged; follow-ups #29/#32 также closed. **G1/G2 не считаются формально verified**, см. [STATUS](../STATUS.md), [CI](../operations/CI.md). T-01 из M0 открыта. **M3 Expenses теперь назначен:** T-07 #35, O-04 #36, O-05 #39, L-04 #37; live Telegram QA G2 по решению Тимура отложена (Issue #38 закрыта как `not_planned`). **Ни одна M3 Issue ещё не означает реализованную функцию.** M0–M7 — фазы, не календарные недели.

| Фаза | Тимур (T) | Олег (O) | Лера (L) | Общий gate |
|---|---|---|---|---|
| M0 Условия | T-01 Github/branch protection/ADR001; T-02 стек/uv/ADR002 | O-01 аудит математических инвариантов | L-01 UX-карта бота | Репо, правила и PR согласованы |
| M1 Skeleton | T-03 FastAPI/Postgres/Alembic/Compose; T-04 CI minimal | O-02 чистые split functions и unit-тесты | L-02 каркас aiogram и mock HTTP-клиент | Из main собирается локальный API; PR -> CI |
| M2 Identity | T-05 Auth/JWT, T-06 группы/invites и bot actor | O-03 модели финансов и миграции | L-03 /start, bootstrap/link и группы на mocked API | E2E профиль -> группа |
| M3 Expenses | T-07 review безопасности, интеграция API | O-04 CRUD equal/custom, O-05 by_items | L-04 мастера расходов по контракту | Ресторанный тест и bot flow |
| M4 Balances | T-08 audit locking/idempotency | O-06 балансы и settlement plan; O-07 компенсации | L-05 баланс, переводы, подтверждения | Частичный перевод обновляет баланс только после confirm |
| M5 Delivery | T-09 GHCR/CD/VPS/Caddy, T-10 логи | O-08 integration/concurrency/load tests | L-06 E2E, UX errors, README | Merge -> image -> HTTPS /health /version |
| M6 Acceptance | T-11 DoD audit, reset/test clean environment | O-09 bugfix, invariants, PR audit | L-07 user guide, demo script, smoke bots | CI green, coverage >=60%, p95/100 concurrent documented |
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

## Текущая фаза — M3 Expenses (Issues назначены 28.10.2026)

- **Тимур [T-07 #35](https://github.com/inte11ectua1/skinulis/issues/35):** review безопасности и консистентности публичного/internal API, actor permissions, error DTO и пагинации на фоне новых финансовых операций.
- **Олег [O-04 #36](https://github.com/inte11ectua1/skinulis/issues/36) → [O-05 #39](https://github.com/inte11ectua1/skinulis/issues/39):** создать CRUD расходов `equal/custom` с group-first транзакциями, правами, идемпотентностью, затем `by_items` с сохранением positions/final snapshots. Не менять принятые Q-01/Q-02; применять Q-03 API Unicode-валидацию и Q-10 нулевые доли, оставшиеся Q-04/Q-06/Q-08/Q-09 согласовать на сервисной границе.
- **Лера [L-04 #37](https://github.com/inte11ectua1/skinulis/issues/37):** мастера расходов по реальным OpenAPI/fixtures O-04/O-05; пока контракты не согласованы — mocks, без вычисления денег в боте. **UQ-03 expense preview остаётся открытым**, не придумывать endpoint.
- **Интеграция/gate G3:** ресторанный тест, все три split modes, CRUD/soft-delete, cross-group denial и сценарии в Telegram; считать verified только по реальным доказательствам, а не по названию этапа.

Активные M3 Issues #35, #36, #37 и #39 созданы и назначены; #38 закрыта как `not_planned` до сигнала Тимура. O-05 **blocked** до merge O-04; L-04 может готовить mocks до реального API; T-07 согласует финансовые DTO и UQ-03 до фиксации контракта. **G2 live Telegram QA сейчас никому не назначена:** [#38](https://github.com/inte11ectua1/skinulis/issues/38) закрыта как `not_planned` по просьбе Тимура; тестирование начнём только после его отдельного сигнала. G2 остаётся unverified, production `/internal` — T-09. Предыдущие Issues M2 не переиспользовать.

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

