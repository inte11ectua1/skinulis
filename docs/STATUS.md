# Фактическое состояние проекта

**Срез:** 27 октября 2026 года. Источник истины — GitHub `main`, принятые PR, Issues, логи проверок и реальные URL. Этот документ отражает подтверждённое состояние, а не обещание готовой реализации.

**Этап M1 (Skeleton): завершён по объёму задач.** [T-03 #10](https://github.com/inte11ectua1/skinulis/issues/10), [O-02 #11](https://github.com/inte11ectua1/skinulis/issues/11), [L-02 #12](https://github.com/inte11ectua1/skinulis/issues/12) и [T-04 #13](https://github.com/inte11ectua1/skinulis/issues/13) закрыты, код находится в `main`. **G1 — не полностью подтверждён как формальный gate**: нужна доказательная проверка причины блокировки красного CI в интерфейсе и незавершённые защитные проверки T-01; у PR #19 не зарегистрировано независимого APPROVED-ревью. Это не отменяет успешную реализацию M1.

Статусы задач: `planned → in progress → PR review → merged → verified`. `merged` не равно `verified`: для последнего нужны соответствующие CI, тесты и/или работающий сервис.

## M0 — подготовка и документация

| Задача | Состояние | Ответственный | Подтверждение / оставшееся |
|---|---|---|---|
| [T-01](https://github.com/inte11ectua1/skinulis/issues/2) GitHub и ADR 001 | **in progress** | Тимур | [PR #1](https://github.com/inte11ectua1/skinulis/pull/1) и [PR #6](https://github.com/inte11ectua1/skinulis/pull/6) merged; ADR 001 принят. `main.protected=true`, auto-delete веток включён. Пять required CI checks настроены; текущий GitHub API сообщает enforcement checks **`non_admins`** — администраторский обход возможен, поэтому предыдущая запись `enforce_admins=true` из T-04 уже не является актуальным доказательством. Практический отказ прямому push и визуальная причина блокировки merge при красном CI не подтверждены. [Evidence](operations/CI.md). Приглашение преподавателя отложено решением Тимура. |
| [T-02](https://github.com/inte11ectua1/skinulis/issues/5) Python 3.12, uv | **merged** | Тимур | [PR #7](https://github.com/inte11ectua1/skinulis/pull/7) merged после `APPROVED` Олега и исправления уязвимостей; CPython 3.12.15, uv 0.13.5. Локальные macOS проверки в PR, Windows junction issue при `uv python install` остаётся не перепроверенным на обновлённом uv. |
| [O-01](https://github.com/inte11ectua1/skinulis/issues/3) инварианты | **merged** | Олег | [PR #8](https://github.com/inte11ectua1/skinulis/pull/8) approved Тимуром и merged; финансовые документы, 105 сценариев, вопросы Q-01–Q-10. Это документация, не реализация тестов. |
| [L-01](https://github.com/inte11ectua1/skinulis/issues/4) Telegram UX | **merged** | Лера | [PR #9](https://github.com/inte11ectua1/skinulis/pull/9) approved Тимуром и merged; сценарии, 42 будущих QA-проверки, вопросы UQ-01–UQ-09. Требующие контрактов пункты остаются открытыми. |

**ADR:** 001 (GitHub Flow) принят PR #6; 002 (uv) принят PR #7. Текстовые статусы приняты в main через [PR #14](https://github.com/inte11ectua1/skinulis/pull/14).

## M1 — Skeleton (вторая фаза; реализация завершена 27.10.2026)

| Задача | Состояние | Ответственный | Зависимости |
|---|---|---|---|
| [T-03](https://github.com/inte11ectua1/skinulis/issues/10) API/DB/Alembic/Compose | **merged** | Тимур | [PR #15](https://github.com/inte11ectua1/skinulis/pull/15) merged; PostgreSQL 17.11, Alembic, Compose, локальное cold-start evidence ниже |
| [O-02](https://github.com/inte11ectua1/skinulis/issues/11) pure splits и parser | **merged** | Олег | [PR #16](https://github.com/inte11ectua1/skinulis/pull/16) и [#17](https://github.com/inte11ectua1/skinulis/pull/17) merged; parser/splits, Q-01/Q-02 и часть Q-04 приняты; финансовых моделей/API пока нет |
| [L-02](https://github.com/inte11ectua1/skinulis/issues/12) bot skeleton и mock HTTP | **merged** | Лера | [PR #18](https://github.com/inte11ectua1/skinulis/pull/18) merged; навигация/typed health client/mock-тесты, без live Telegram и онбординга |
| [T-04](https://github.com/inte11ectua1/skinulis/issues/13) PR CI | **merged, Issue closed** | Тимур | [PR #19](https://github.com/inte11ectua1/skinulis/pull/19) merged 27.10.2026; GitHub Actions lint/types/tests/docker-build/ci, PostgreSQL integration и покрытие ≥60%; [успешный run](https://github.com/inte11ectua1/skinulis/actions/runs/40459119340), [красный run](https://github.com/inte11ectua1/skinulis/actions/runs/40458200449), [подробности](operations/CI.md). PR объединён без зарегистрированного независимого APPROVED review. |

Все T-03, O-02, L-02 и T-04 приняты в `main` (на 27.10.2026 HEAD `d635398`). **Следующая фаза — M2 Identity**: T-05 (auth/JWT), T-06 (группы и Telegram actor), O-03 (финансовые ORM-модели/миграции), L-03 (онбординг и группы в боте). Созданы и назначены Issues M2: [T-05 #21](https://github.com/inte11ectua1/skinulis/issues/21) и [T-06 #22](https://github.com/inte11ectua1/skinulis/issues/22) — Тимур; [O-03 #23](https://github.com/inte11ectua1/skinulis/issues/23) — Олег; [L-03 #24](https://github.com/inte11ectua1/skinulis/issues/24) — Лера. Согласование shared-контрактов — через issue/PR без молчаливого изменения PRODUCT_RULES.

## M2 — Identity (27.10.2026; задачи назначены, реализация не начата)

| Задача | Статус | Ответственный | Условия старта и зависимости |
|---|---|---|---|
| [T-05 #21](https://github.com/inte11ectua1/skinulis/issues/21) Auth/users | **open / ready** | Тимур | Реализация регистрации/login, Argon2, JWT, PostgreSQL users и `/users/me`; от завершённого T-03/T-04 |
| [T-06 #22](https://github.com/inte11ectua1/skinulis/issues/22) Groups/Telegram actor | **open / blocked for implementation** | Тимур | После принятия T-05; группы, членство, приглашения, сервисная Telegram-идентификация и привязка; API контракты UQ-01/UQ-02 совместно с Лерой |
| [O-03 #23](https://github.com/inte11ectua1/skinulis/issues/23) Finance models/migrations | **open / design ready** | Олег | Модели/fixtures можно проектировать сейчас; final FK/migrations после согласования users/groups c T-05/T-06; без финансового CRUD |
| [L-03 #24](https://github.com/inte11ectua1/skinulis/issues/24) Telegram onboarding/groups | **open / mock ready** | Лера | FSM/mock client можно начать сейчас; реальные HTTP-интеграции только по принятым T-05/T-06 OpenAPI/fixtures |

**Правило интеграции M2:** не создавать конкурентные Alembic heads; Тимур согласовывает `users/groups` ID/FK с Олегом до финальной миграции O-03 и Telegram service DTO/deep links с Лерой до L-03 integration. Критические UQ-01/UQ-02 остаются в реестре до явного решения. G2 не подтверждён: auth/group actor и профиль → группа ещё не испытаны.

## Release gates

| Gate | Статус | Условие проверки |
|---|---|---|
| G1 — cold start / миграция / health / CI | **implementation complete; formal verification pending** | Cold start, миграции, /health 200/503 подтверждены в PR #15; CI зелёный и намеренно красный подтверждены в PR #19. Не завершена визуальная проверка failed-required-check причины блокировки; нет независимого approval PR #19; администраторский bypass требует отдельного решения об уровне защиты. |
| G2 — auth и группы | **not verified** | M2 |
| G3 — расходы | **not verified** | M3 |
| G4 — компенсации | **not verified** | M4 |
| G5 — публикация и CD | **not verified** | M5 |
| G6 — приёмка / демонстрация | **not verified** | M6 |

## Открытые вопросы и ограничения

- Последний доступный GitHub API подтверждает, что `main` защищена и перечислены required checks, но **enforcement_level=`non_admins`** (администратор не связан ими на тех же условиях). Это изменение после доказательств T-04; необходимо заново проверить фактические admin bypass settings. Визуальная причина блокировки Merge на красном CI и отказ direct push остаются непроверенными; см. [CI](operations/CI.md).
- Предпросмотр расхода без записи **UQ-03** не имеет принятого API-маршрута; до согласования O-04/O-05 и L-04 нельзя реализовать локальные денежные расчёты или временные расходы ради превью.
- Денежная грамматика/порядок ID **Q-01/Q-02** приняты в PR #17; прочие Q/UQ закрываются до соответствующих этапов по ответственным.
- API/PostgreSQL/Docker проверены локально в T-03 ([PR #15](https://github.com/inte11ectua1/skinulis/pull/15)); каркас бота принят PR #18, live Telegram и продуктовый E2E не проверены. CI реализован в merged [PR #19](https://github.com/inte11ectua1/skinulis/pull/19). G1 нельзя помечать формально verified до незакрытых доказательств и уточнения admin bypass.

## Локальные доказательства T-03 (26.10.2026)

- macOS arm64, Python 3.12.15, uv 0.13.5; Engine 23.0.5, Compose 2.17.3.
- Frozen-установка, lock check, Ruff lint/format, строгий mypy (19 файлов), все
  pre-commit hooks и проверка совместимости пакетов прошли. Аудит 54 зависимостей
  не обнаружил известных уязвимостей; исключения не добавлялись.
- Unit/T-02: 18 passed; отдельно реальная PostgreSQL 17.11: 4 integration passed.
  Объединённое branch coverage **существующего app/** — 98.69%, не покрытие будущего MVP.
- Холодный запуск на новом изолированном volume: db healthy → migrate exit 0 →
  api healthy; /, /health, /version, /docs, /redoc, /openapi.json — HTTP 200.
  При остановке DB /health → 503; после старта DB → 200 без перезапуска API.
- На чистой БД Alembic применяет 0001_baseline, повторный upgrade успешен,
  alembic check не находит drift. Намеренно ошибочная следующая ревизия в
  отдельном тестовом project: migrate exit 1, API не запущен.
- Runtime UID 10001, без .env/.git/tests/dev dependencies. Тестовые контейнеры
  остановлены, named volumes сохранены; другие проекты и .env не изменялись.
- Windows/Linux host отдельно не проверены; предупреждение Starlette о будущей
  смене httpx для TestClient не подавлено. Реализация T-04 принята, но формальная
  приёмка G1 остаётся отдельной.

## Проверки T-04 (27.10.2026)

[Merged PR #19](https://github.com/inte11ectua1/skinulis/pull/19) ([Issue #13 closed](https://github.com/inte11ectua1/skinulis/issues/13)),
[первый зелёный CI](https://github.com/inte11ectua1/skinulis/actions/runs/40458001625),
[намеренно красный CI](https://github.com/inte11ectua1/skinulis/actions/runs/40458200449).
На GitHub Linux: 343 unit + 4 PostgreSQL integration passed, branch coverage
app + bot 97.79%, Docker build success; frozen/lock/Ruff/mypy/secrets/audit прошли.
Локально macOS повторены эти проверки и Compose integration runner; actionlint
также прошёл. Бизнес-код, тесты владельцев и lock не менялись.

В ходе T-04 административным API были прочитаны required lint/types/tests/docker-build/ci,
strict up-to-date и правила PR/review; красный head имел API BLOCKED. После merge
защита **изменилась**: текущий ответ GitHub показывает enforcement_level=non_admins
для checks. Нельзя сохранять прежнее утверждение о запрете обхода администратором.
Визуальная конкретная причина блокировки merge box ещё не подтверждена.
Намеренная ошибка удалена; восстановленный run и снимок *исторических* настроек
в [CI evidence](operations/CI.md). Issue #13 закрыта после merge PR #19,
при этом в PR #19 не зарегистрировано чужого approval; G1 формально не verified.
