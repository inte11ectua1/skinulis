# «Скинулись» — стартовая точка команды

**Актуализация 03.11.2026 · GitHub main `0de89b3`. M1–M5 завершены по согласованному объёму разработки; текущая следующая фаза — M6 Acceptance (план, Issues ещё не заведены).** [Статус](docs/STATUS.md) · [M5 closeout / M6 handoff](docs/operations/M5_CLOSEOUT_M6_HANDOFF.md).

## M5: закрытие и ограничения

- **Тимур:** T-09 [#59](https://github.com/inte11ectua1/skinulis/issues/59), T-10 [#60](https://github.com/inte11ectua1/skinulis/issues/60) — closed completed; первый approved API rollout на AWS/HTTPS, GHCR, private DB, JSON logs/runbook. API production проверялся на deployed SHA `f7020cd`, не на последнем `main`.
- **Олег:** O-08 [#61](https://github.com/inte11ectua1/skinulis/issues/61) / [PR #74](https://github.com/inte11ectua1/skinulis/pull/74) — security/finance/races и нагрузка.
- **Лера:** L-06 [#62](https://github.com/inte11ectua1/skinulis/issues/62) / [PR #75](https://github.com/inte11ectua1/skinulis/pull/75) — mock Telegram + local HTTP/PostgreSQL E2E, без live polling.
- **Тимур:** O-09 [#76](https://github.com/inte11ectua1/skinulis/issues/76) / [PR #77](https://github.com/inte11ectua1/skinulis/pull/77) — исправлен PostgreSQL double checkout; 100-client HTTP500 → 0, p95≈0.96/1.10s. **Цель p95≤500ms не достигнута**, но принята владельцем как необязательная для закрытия O-09. [Полный отчёт](docs/operations/LOAD_TEST_M5.md).
- После PR #77 [CI PR 5/5](https://github.com/inte11ectua1/skinulis/actions/runs/41533351706); post-merge main CI на момент среза выполнялся. Все Issue/PR закрыты; **не придумывать уже назначенные M6 issues**.
- **G5** имеет evidence первого rollout; **G1** не полностью принят (T-01 #2 закрыта `not_planned`); **G2/G3/G4** без live Telegram. Не все исторические PR имеют независимый GitHub APPROVED. Полный DoD/защита ещё впереди.

## M6: дальнейшая работа

Тимур — T-11 audit DoD/чистый запуск/demo readiness; Олег — финальная financial/PG QA без повторного ID O-09; Лера — L-07 user guide + сценарий для трёх пользователей. Сначала согласовать отдельные Issues и acceptance; live Telegram и новый AWS rollout требуют отдельной команды Тимура. М5 → M6 [handoff](docs/operations/M5_CLOSEOUT_M6_HANDOFF.md).

## Команда
- **Тимур** — technical lead, платформа, безопасность, DevOps и интеграция.
- **Олег** — финансовый backend, транзакции, миграции и расчётные тесты.
- **Лера** — Telegram-бот, пользовательские сценарии, API-клиент, end-to-end QA и пользовательская документация.

Олег получает более сложную логику и конкуренцию, Лера — ограниченный по контрактам самостоятельный пользовательский вертикальный срез. Тимур отвечает за риск CI/CD на защите, а не забирает весь backend.

## Основной принцип
**GitHub-репозиторий нашего приложения — единственный канонический источник решения и статуса.** ChatGPT-чаты, память проекта и Notion — помощники, не источники истины. Репозиторий команды — [`inte11ectua1/skinulis`](https://github.com/inte11ectua1/skinulis). Не путать его с учебным репозиторием `andrey-limasov/app-conf`.

## Читать в указанном порядке
1. `START_HERE.md` (этот файл).
2. `docs/PRODUCT_RULES.md` и `docs/TECHNICAL_DECISIONS.md` — ранее согласованные проектные решения.
3. `docs/TEAM_WORKFLOW.md` и `docs/contracts/BOUNDARIES.md`.
4. `docs/roadmaps/MASTER_ROADMAP.md` и `docs/STATUS.md`.
5. Свой файл `docs/roles/{TIMUR|OLEG|LERA}_SPEC.md` и `docs/roadmaps/{TIMUR|OLEG|LERA}_ROADMAP.md`.
6. `docs/operations/PRE_CODEX_SETUP.md`, `docs/operations/SHARED_CONTEXT.md`.
7. Корневой `AGENTS.md` перед запуском Codex.

## Иерархия правил
1. Актуальные опубликованные требования курса https://github.com/andrey-limasov/app-conf/ и отдельные согласования с преподавателем.
2. Принятые командой ADR и контракты, находящиеся в `main` собственного проекта.
3. PRODUCT_RULES / TECHNICAL_DECISIONS / BOUNDARIES, если не противоречат п. 1–2.
4. Персональные спеки / roadmap / задачи.
5. Советы ChatGPT и Codex.

При конфликте: не менять поведение молча; создать issue/ADR и согласовать. Примеры, сроки и названия репозиториев в комплекте — предложения. Требования курса сверять перед каждой новой практикой.

## Актуальный контекст для ChatGPT и Codex
**GitHub `main` — единственный источник истины.** Перед ревью/новой задачей читать свежие `docs/STATUS.md`, roadmaps, AGENTS.md, Issues и PR непосредственно из GitHub. Загруженные в ChatGPT-проект файлы — необязательная историческая справка; по решению Тимура их не требуется постоянно заменять. Не выдавать прежнюю копию вложения за последнюю версию GitHub.

## Вопрос каждому отдельному чату
«Я [Тимур/Олег/Лера] в проекте „Скинулись“. Используй мою спеку, мой roadmap и общее состояние; не изменяй контракты без согласования. Начни с следующей незаблокированной задачи, объясни критерии приёмки и дай конкретный промпт Codex. Если статус неактуален — попроси ссылку на текущие issue/PR, не выдумывай выполненное».

