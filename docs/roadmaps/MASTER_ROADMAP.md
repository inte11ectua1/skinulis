# Общий roadmap (зависимости, интеграция, gate)

**Статус на 27.10.2026:** реализация **M1 Skeleton завершена**, Issues T-03 #10, O-02 #11, L-02 #12, T-04 #13 закрыты после merged PR #15–#19. Формальное закрытие gate G1 требует дополнительных доказательств (см. [STATUS](../STATUS.md), [CI](../operations/CI.md)). T-01 из M0 всё ещё открыта. Следующая фаза по плану — **M2 Identity**, Issues M2 пока не созданы. M0–M7 — фазы, не календарные недели.

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

## Текущая фаза — M2 Identity (Issues назначены 27.10.2026)

- **Тимур:** [T-05 #21](https://github.com/inte11ectua1/skinulis/issues/21) — регистрация/login, Argon2/JWT/users, **можно начинать**; затем [T-06 #22](https://github.com/inte11ectua1/skinulis/issues/22) — groups/invites/проверенный Telegram actor, **после T-05**.
- **Олег:** [O-03 #23](https://github.com/inte11ectua1/skinulis/issues/23) — SQLAlchemy-модели финансов/Alembic; **можно проектировать** параллельно T-05, но финальные FK/migrations только после согласования users/groups с Тимуром.
- **Лера:** [L-03 #24](https://github.com/inte11ectua1/skinulis/issues/24) — онбординг, профиль, группы/приглашения; **можно делать mock FSM**, интеграцию — после принятого API-контракта T-05/T-06, UQ-01/UQ-02.

Все четыре Issues созданы с назначенными владельцами; это **план работ**, а не результат реализации. До подтверждённого API и сквозных проверок не отмечать G2 verified или работающий профиль/группы.

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

