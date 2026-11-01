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
| T-09 | M5 | GitHub CI/GHCR и laptop Docker Compose, локальный бот/DB, /health /version | T-04 | локальный cold-start+bot opt-in+DB persistence, /health и /version SHA |
| T-10 | M5 | JSON logs, request_id, rotation, health, rollback runbook | T-09 | локальные ошибки видны, логи без секретов |
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

## Завершённый M3 — [T-07 #35](https://github.com/inte11ectua1/skinulis/issues/35) (30.10.2026)

[T-07 #35](https://github.com/inte11ectua1/skinulis/issues/35) / [PR #44](https://github.com/inte11ectua1/skinulis/pull/44) **merged/closed** после O-04 PR #41, O-05 PR #42 и L-04 PR #43. Аудит public/internal actor, locks, replay, versions, финансовых snapshots и mock Telegram HTTP integration. Исправлены corrupt equal/custom PUT без safe rejection и error responses без `Cache-Control:no-store`; 20 PG regression tests, [финальный CI 5/5](https://github.com/inte11ectua1/skinulis/actions/runs/41064210033), всего 1147 tests и 95,46% coverage. [Подробный отчёт](../reviews/T-07_M3_SECURITY_REVIEW.md). PR #44 без зарегистрированного независимого APPROVED — не приписывать его команде.

## Завершённый M4 — [T-08 #45](https://github.com/inte11ectua1/skinulis/issues/45) / [PR #58](https://github.com/inte11ectua1/skinulis/pull/58) (31.10.2026)

**Merged/closed:** T-08 contracts #50/#56, backend O-06 #51, O-07 #53, notification claim #57, L-05 #54, [финальный отчёт](../reviews/T-08_M4_FINAL_SECURITY_REVIEW.md) #58. GitHub `main` на момент handoff `eb3ae28`; [CI PR #58 5/5](https://github.com/inte11ectua1/skinulis/actions/runs/41213175596). Нет independent human APPROVED на некоторых PR; не приписывать их задним числом. **Live Telegram gates G2/G3/G4 не verified**, T-01/G1 отдельно.

## Текущий M5 — [T-09 #59](https://github.com/inte11ectua1/skinulis/issues/59) / локальный ноутбук → [T-10 #60](https://github.com/inte11ectua1/skinulis/issues/60)

**Решение Тимура (01.11.2026):** VPS и домен не покупать. Ноутбук выполняет роль хоста с Docker Compose, FastAPI+PostgreSQL17+миграциями и **одним** aiogram polling контейнером. Никаких публичных API/DB портов, удалённого SSH, Caddy/HTTPS и self-hosted Actions runner. [ADR003](../adr/003-laptop-as-demo-host.md), [инструкция ноутбука](../operations/LAPTOP_HOSTING.md).

**T-09 #59 — актуальная приёмка M5-L:** PR #64 уже подготовил GHCR SHA, non-root app/bot image, production/VPS код и CI; новые действия — opt-in laptop compose, настоящий cold-start и локальный `/health`/ `/version`, сохранность данных между перезапусками, безопасное обновление/backup, проверка доступа только через localhost и отдельный реальный Telegram smoke **только после явной команды**. Отложенные server-side smoke не считать успешными; Issue #59 остаётся open до фактического laptop evidence и согласования пересмотра требований курса. Промежуточные PR используют `Refs #59`.

**T-10 #60:** JSON logging, request_id, Docker log rotation и инструкция по сбоям/восстановлению на **том же ноутбуке**, без SSH/production registry remote actions. Можно готовить параллельно после понятной конфигурации локального хоста.

**Олег O-08 #61** — PG concurrency/load в отдельной одноразовой тестовой БД, **Лера L-06 #62** — mocked Telegram + HTTP/PG UX regression. Их задачи не зависят от VPS. **G5-original не verified** (VPS/HTTPS остались в исходной версии требования); laptop M5-L — отдельная проверка, не эквивалент без согласования преподавателя.

## Вопросы для своего ChatGPT-чата
«Что мой следующий gate?», «Проверь угрозы Telegram actor», «Сформулируй PR description и тестовый план», «Какие доказательства CI/CD нужны для преподавателя?».

