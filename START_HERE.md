# «Скинулись» — стартовая точка команды

**Актуализация: 31.10.2026 · GitHub main `eb3ae28`.** Реализация **M1 Skeleton, M2 Identity, M3 Expenses и M4 Balances/Settlements завершена**. O-06 #46/PR #51, O-07 #47/PR #53, O-07N #55/PR #57, L-05 #48/PR #54 и T-08 #45/PR #58 — все merged/closed. Балансы, read-only план, ручные компенсации и best-effort Telegram-уведомления уже в main; [итоговый T-08 аудит](docs/reviews/T-08_M4_FINAL_SECURITY_REVIEW.md), [CI PR #58 5/5](https://github.com/inte11ectua1/skinulis/actions/runs/41213175596). **Текущий этап M5 Delivery назначен**; см. [STATUS](docs/STATUS.md) и [handoff](docs/operations/M5_DELIVERY_HANDOFF.md). G1/G2/G3/G4 ещё не formally verified; live Telegram по решению Тимура отложен.

## Текущий этап: M5 Delivery (задачи назначены 31.10.2026)

**Завершённое M4:** [T-08 #45](https://github.com/inte11ectua1/skinulis/issues/45), [O-06 #46](https://github.com/inte11ectua1/skinulis/issues/46), [O-07 #47](https://github.com/inte11ectua1/skinulis/issues/47), [O-07N #55](https://github.com/inte11ectua1/skinulis/issues/55), [L-05 #48](https://github.com/inte11ectua1/skinulis/issues/48) — все Issues закрыты. Реальные PostgreSQL/HTTP/Mock Telegram тесты есть; это не live Telegram E2E.

**Новые задания:**
- Тимур: **[T-09 #59](https://github.com/inte11ectua1/skinulis/issues/59)** — сначала trusted-main GHCR/CD, Compose/VPS, Caddy HTTPS, защита /internal и rollback; **[T-10 #60](https://github.com/inte11ectua1/skinulis/issues/60)** — JSON логи, request_id, ротация, incident runbook после согласованной T-09 инфраструктуры.
- Олег: **[O-08 #61](https://github.com/inte11ectua1/skinulis/issues/61)** — может начать сейчас, реальные PG race/security тесты и контролируемый load 100 clients/p95 с доказательствами.
- Лера: **[L-06 #62](https://github.com/inte11ectua1/skinulis/issues/62)** — может начать сейчас, mocked Telegram + real HTTP/PostgreSQL UX/regression для retry/timeout/ошибок.

**Зависимости:** T-09 — critical path, O-08 и L-06 могут выполняться параллельно; T-10 заканчивается после архитектуры/интеграции T-09. **Реальный VPS/SSH deployment, production secrets, live Telegram polling и нагрузка на production требуют отдельного разрешения Тимура**, не начинать их автоматически. Неполные PR — `Refs #N`, завершённые — `Closes #N` только после acceptance и human review. Документация задания — [M5 handoff](docs/operations/M5_DELIVERY_HANDOFF.md).

**Отложенное:** [T-01 #2](https://github.com/inte11ectua1/skinulis/issues/2)/G1 (admin bypass/direct push evidence), live Telegram G2/G3/G4 ([#38](https://github.com/inte11ectua1/skinulis/issues/38) not_planned). M5 G5 ещё не verified. Преподавателя не приглашать до решения Тимура; GitHub main остаётся единственным источником истины.

## Изменение инфраструктуры M5 (01.11.2026)

**Решение Тимура: без VPS и домена, ноутбук как локальный host.** Стек для демонстрации — `db/migrate/api` и один **opt-in** `bot` в Docker Compose, Telegram через исходящее polling, API только `127.0.0.1` и private DB. [ADR003](docs/adr/003-laptop-as-demo-host.md), [пошаговый runbook](docs/operations/LAPTOP_HOSTING.md), пересогласованная [T-09 #59](https://github.com/inte11ectua1/skinulis/issues/59). Прежние упоминания VPS/SSH/Caddy ниже/в архивной документации — исторический план, не команда на сервер. CI/GHCR остаются, локальное обновление делается вручную. **Оригинальный VPS/HTTPS G5 не verified; нужна отдельная сверка требований преподавателя.** T-10 #60 — логи/восстановление локального ноутбука, O-08 и L-06 без смены финансов/UX scope. Никакого включения настоящего polling без явного согласия владельца токена.

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

