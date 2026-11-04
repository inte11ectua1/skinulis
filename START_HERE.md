# «Скинулись» — стартовая точка команды

**Актуализация: 04.11.2026.** M1–M5 приняты владельцем по объёму реализации;
UX #84 реализован и объединён [PR #85](https://github.com/inte11ectua1/skinulis/pull/85).
Последний подтверждённый production release `c9ec9cea388fd9282fadc437ff2ce1c7390d4a0c`; [его main CI](https://github.com/inte11ectua1/skinulis/actions/runs/41824303985)
5/5, 1382 unit +458 PostgreSQL, branch coverage94,10%.
[Protected deploy](https://github.com/inte11ectua1/skinulis/actions/runs/41836839608)
success с независимым Environment approval Леры и enable_polling=true.
Публичный /version совпал; health/database/HTTPS работают. Владелец подтвердил новый
UI @skinulis_expenses_bot и ручное меню BotFather. Read-only runtime follow-up04.11 — VERIFIED (healthy, один polling,0007, прежний volume).

**Текущие Issues:** #84 **closed/completed** (UX принят владельцем с документированными исключениями),
#79 **open** (M6 Acceptance, ответственный Тимур). #80 **closed/not_planned**:
отдельный M7 отменён по решению владельца 04.11.2026; его задачи не планируются.
После PR #86 текущий `main` — `1d668e59cb994de45dc1e9c853a61eb6579d4628`;
[CI](https://github.com/inte11ectua1/skinulis/actions/runs/41862624252) 5/5.
[Автоматический Release](https://github.com/inte11ectua1/skinulis/actions/runs/41866257675)
остановился на guard, publish/deploy не запускались; production остаётся на предыдущем подтверждённом релизе.
[Актуальный аудит](docs/reviews/POST_RELEASE_AUDIT_2026-11-04.md) ·
[USER_GUIDE](docs/USER_GUIDE.md) · [3-user сценарий](docs/reviews/M6_THREE_USER_DEMO.md) ·
[STATUS](docs/STATUS.md). Исторические отчёты не доказывают новый runtime.

**G6 не закрыт:** routing FAIL absolute-form/foreign authority (пустой200, без доказанной
утечки), p95>500ms, 41/52 merged PR без независимого APPROVED, admin bypass и формальные
logging/live-E2E/учебные приёмочные пробелы. Environment approval не заменяет PR review;
согласие владельца не является исключением преподавателя.
Новые deploy/restart/migrations/polling/config/данные production или AWS changes —
только по отдельному разрешению. Этот документационный аудит ничего из этого не выполняет.

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

