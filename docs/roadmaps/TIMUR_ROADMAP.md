# Тимур — личный roadmap

**Приоритет:** сначала Git/CI и воспроизводимый запуск, затем auth/groups и CD. Завершение любого шага = PR + тесты + review + запись статуса.

| ID | Фаза | Задача | Вход | Доказательство готовности |
|---|---|---|---|---|
| T-01 | M0 | Публичный repo; collaborators; branch protection; PR template; CONTRIBUTING; ADR001 | Название repo | PR с human approval; прямой push отказан |
| T-02 | M0 | Python 3.12 / uv / pyproject / lock / ADR002 / .env.example / precommit | T-01 | uv sync --frozen; env без секретов |
| T-03 | M1 | FastAPI, sync SQLAlchemy, psycopg, Alembic, PostgreSQL, Compose, /health,/version | T-02 | cold docker compose up --build; /health 200, при DB down 503 |
| T-04 | M1 | PR workflow lint+types+pytest PostgreSQL+coverage+Docker build | T-03 | fail test blocks PR; all checks green |
| T-05 | M2 | Email registration/login/JWT/user models, negative access tests | T-03 | tests on 400/401/409; Argon2, JWT expiry |
| T-06 | M2 | Groups, memberships, invites, Telegram actor/link; finalize API contracts | T-05 | invite once 24h, group authorization tests |
| T-07 | M3 | Security and API review, uniform error handler/pagination/docs | O-03/04 | OpenAPI consistent, no actor spoofing |
| T-08 | M4 | Audit locks + idempotency with Oleg; threat scenarios | O-06/07 | race tests documented, no duplicate effects |
| T-09 | M5 | GHCR publish and VPS Docker Compose SSH CD, Caddy HTTPS, deploy job | T-04 | after merge SHA-tag image and /version matching |
| T-10 | M5 | JSON logs, request_id, rotation, health, rollback runbook | T-09 | failure visible, logs no secrets |
| T-11 | M6 | DoD audit, cold-start other machine, release smoke, evidence | all owners | evidence linked in STATUS |
| T-12 | M7 | PR->CI->approval->merge->CD demonstration | T-09/11 | live rehearsed and backup successful run linked |

## Завершённая фаза M1 (27.10.2026)

- **T-03:** [Issue #10](https://github.com/inte11ectua1/skinulis/issues/10), [PR #15](https://github.com/inte11ectua1/skinulis/pull/15) — FastAPI/PostgreSQL/Alembic/Compose, системные endpoints и cold-start проверены.
- **T-04:** [Issue #13](https://github.com/inte11ectua1/skinulis/issues/13), [PR #19](https://github.com/inte11ectua1/skinulis/pull/19) — GitHub Actions PR CI (Ruff, mypy, PostgreSQL, coverage, Docker); успешный и намеренно красный run зафиксированы. PR #19 merged без зарегистрированного независимого approval. Формальный G1 не verified из-за оставшейся проверки merge box и текущего admin bypass; [evidence](../operations/CI.md).

## Текущие задачи M2 (Issues назначены 27.10.2026)

**[T-05 #21](https://github.com/inte11ectua1/skinulis/issues/21) — ready:** регистрация/login, JWT/Argon2, users с положительным BIGINT ID, права доступа и negative tests. После T-05: **[T-06 #22](https://github.com/inte11ectua1/skinulis/issues/22) — blocked for implementation**: группы, membership/invites, Telegram service actor и безопасная привязка. До FK/DTO согласовать users/groups с Олегом ([O-03 #23](https://github.com/inte11ectua1/skinulis/issues/23)) и Telegram API c Лерой ([L-03 #24](https://github.com/inte11ectua1/skinulis/issues/24)). Не начинать T-09 deploy/CD раньше предусмотренного этапа.

## Вопросы для своего ChatGPT-чата
«Что мой следующий gate?», «Проверь угрозы Telegram actor», «Сформулируй PR description и тестовый план», «Какие доказательства CI/CD нужны для преподавателя?».

