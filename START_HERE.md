# «Скинулись» — стартовая точка команды

**Актуализация: 28.10.2026.** Реализация **M1 Skeleton и M2 Identity закрыта** в GitHub: API auth/JWT, группы/приглашения/Telegram identity, финансовые SQLAlchemy-модели, Telegram-онбординг и CI находятся в `main`. **Это ещё не завершённый продукт:** финансовые CRUD/балансы/компенсации — следующий этап, live Telegram E2E и G2 не подтверждены. Формальная приёмка G1 и некоторые проверки T-01 открыты: [STATUS](docs/STATUS.md).

## Текущий этап: M3 Expenses (задачи назначены)

**M1 Skeleton:** [T-03 #10](https://github.com/inte11ectua1/skinulis/issues/10), [O-02 #11](https://github.com/inte11ectua1/skinulis/issues/11), [L-02 #12](https://github.com/inte11ectua1/skinulis/issues/12), [T-04 #13](https://github.com/inte11ectua1/skinulis/issues/13) — merged/closed.

**M2 Identity: все задачи закрыты 28.10.2026.** Тимур — [T-05 #21](https://github.com/inte11ectua1/skinulis/issues/21) / [PR #26](https://github.com/inte11ectua1/skinulis/pull/26) и [T-06 #22](https://github.com/inte11ectua1/skinulis/issues/22) / [PR #27](https://github.com/inte11ectua1/skinulis/pull/27); Олег — [O-03 #23](https://github.com/inte11ectua1/skinulis/issues/23) / [PR #31](https://github.com/inte11ectua1/skinulis/pull/31); Лера — [L-03 #24](https://github.com/inte11ectua1/skinulis/issues/24) / [PR #28](https://github.com/inte11ectua1/skinulis/pull/28). Follow-ups [UTC #29](https://github.com/inte11ectua1/skinulis/issues/29) / [PR #30](https://github.com/inte11ectua1/skinulis/pull/30) и [финансовая документация #32](https://github.com/inte11ectua1/skinulis/issues/32) / [PR #33](https://github.com/inte11ectua1/skinulis/pull/33) тоже закрыты. Реальный CI последнего [PR #31](https://github.com/inte11ectua1/skinulis/pull/31) зелёный 5/5.

**M3 назначен 28.10.2026:** Тимур — **[T-07 #35](https://github.com/inte11ectua1/skinulis/issues/35)** review безопасности/API и согласование контрактов; Олег — **[O-04 #36](https://github.com/inte11ectua1/skinulis/issues/36)** CRUD `equal/custom`, затем **[O-05 #39](https://github.com/inte11ectua1/skinulis/issues/39)** `by_items` (реализация заблокирована до merge O-04); Лера — **[L-04 #37](https://github.com/inte11ectua1/skinulis/issues/37)** mock-first мастера расходов по согласованному backend API. **G2 live Telegram QA отложена по решению Тимура:** [#38](https://github.com/inte11ectua1/skinulis/issues/38) закрыта как `not_planned` и никому не назначена; тестирование начнём после отдельной команды. Серверный expense preview UQ-03 и отдельные Q/UQ должны согласовываться до реализации; **не переносить денежные вычисления в бот**. Gate G2 остаётся без формального подтверждения до live Telegram E2E / production проверки `/internal`.

T-01 (GitHub protection) остаётся открытой до оставшихся практических доказательств; обязательный CI реализован, однако admin bypass и отсутствие независимого approval PR #19 должны учитываться при оценке gate G1. Преподавателя пока не приглашаем по решению Тимура. GitHub `main` — источник актуального состояния.

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

