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

## Завершённая фаза M2 (28.10.2026)

- **[T-05 #21](https://github.com/inte11ectua1/skinulis/issues/21) / [PR #26](https://github.com/inte11ectua1/skinulis/pull/26) — merged/closed:** email registration/login, Argon2id, JWT, users/BIGINT, `0002_users`.
- **[T-06 #22](https://github.com/inte11ectua1/skinulis/issues/22) / [PR #27](https://github.com/inte11ectua1/skinulis/pull/27) — merged/closed:** group/member/invites, bot-service actor, linking, `0003_groups_identity`, утверждённые internal/публичные DTO.
- **[Issue #29](https://github.com/inte11ectua1/skinulis/issues/29) / [PR #30](https://github.com/inte11ectua1/skinulis/pull/30) — merged/closed:** UTC `Z` wire datetime и non-UTC PostgreSQL regression; это не live Telegram E2E.
- **[Issue #32](https://github.com/inte11ectua1/skinulis/issues/32) / [PR #33](https://github.com/inte11ectua1/skinulis/pull/33) — closed:** контрактные финансовые решения переданы в финальный PR Олега #31.

**M2 закрыт по коду; gate G2 не verified:** live Telegram E2E и production reverse-proxy restriction `/internal` пока без доказательства. T-01/G1 — отдельные старые контрольные пункты.

## Следующая задача по roadmap — T-07 (M3, Issue ещё не назначена)

Ревью безопасности и интеграции новых expense API O-04/O-05: actor (JWT/bot service), group membership, forbidden/hidden resources, validation/errors, pagination/OpenAPI, audit без раскрытия секретов. Совместно с Олегом/Лерой согласовать границы DTO, idempotency и UQ-03; не реализовывать O-04/O-05 за Олега или L-04 за Леру. T-09 deploy/CD остаётся M5, а не M3.

## Вопросы для своего ChatGPT-чата
«Что мой следующий gate?», «Проверь угрозы Telegram actor», «Сформулируй PR description и тестовый план», «Какие доказательства CI/CD нужны для преподавателя?».

