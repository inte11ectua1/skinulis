# Общий roadmap (зависимости, интеграция, gate)

**Статус:** дорожная карта и зависимости; фактическое выполнение см. в [STATUS](../STATUS.md) и GitHub Issues/PR. На 26.10.2026 PR по T-02, O-01, L-01 приняты, T-01 остаётся открытой для доказательств защиты `main`; начата постановка задач M1. Нумерация M0–M7 — последовательные фазы, а не календарные недели. Разрешена параллельность при согласованном контракте.

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

## Переход к M1 — назначенные Issues (26.10.2026)

- **Тимур:** [T-03 #10](https://github.com/inte11ectua1/skinulis/issues/10) — FastAPI + sync SQLAlchemy, PostgreSQL 17, Alembic, Compose, `/health`, `/version`. Можно начинать после merged T-02.
- **Олег:** [O-02 #11](https://github.com/inte11ectua1/skinulis/issues/11) — pure money parser/equal/custom/by_items и unit-тесты после согласования необходимых Q-01/Q-02; без DB/API.
- **Лера:** [L-02 #12](https://github.com/inte11ectua1/skinulis/issues/12) — каркас aiogram и typed httpx mock client без реального Telegram-токена и без выдуманных API-контрактов.
- **Тимур после T-03:** [T-04 #13](https://github.com/inte11ectua1/skinulis/issues/13) — PR GitHub Actions lint/types/Postgres tests+coverage/Docker build; обязательный status check после первого подтверждённого workflow.

T-03, O-02, L-02 — параллельные независимые PR с человеческим ревью. T-04 зависит от T-03; **G1 пока не проверен**. Подробные состояния и открытые зависимости: [STATUS](../STATUS.md).

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

