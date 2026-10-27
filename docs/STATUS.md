# Фактическое состояние проекта

**Срез:** 27 октября 2026 года. Источник истины — GitHub `main`, принятые PR, Issues, логи проверок и реальные URL. Этот документ отражает подтверждённое состояние, а не обещание готовой реализации.

Статусы задач: `planned → in progress → PR review → merged → verified`. `merged` не равно `verified`: для последнего нужны соответствующие CI, тесты и/или работающий сервис.

## M0 — подготовка и документация

| Задача | Состояние | Ответственный | Подтверждение / оставшееся |
|---|---|---|---|
| [T-01](https://github.com/inte11ectua1/skinulis/issues/2) GitHub и ADR 001 | **in progress** | Тимур | [PR #1](https://github.com/inte11ectua1/skinulis/pull/1) и [PR #6](https://github.com/inte11ectua1/skinulis/pull/6) merged; ADR 001 одобрен Лерой; `main.protected=true`, `delete_branch_on_merge=true`. Параметры защиты подтверждены административным API в T-04: PR/1 approval/stale/conversations/admin enforcement/no force-push/deletion, 5 required checks GitHub Actions, strict=true. Практический отказ direct push и визуальная причина блокировки красного merge box ещё не подтверждены; [evidence](operations/CI.md). Преподаватель по решению Тимура будет приглашён ближе к защите, сейчас не приглашать. |
| [T-02](https://github.com/inte11ectua1/skinulis/issues/5) Python 3.12, uv | **merged** | Тимур | [PR #7](https://github.com/inte11ectua1/skinulis/pull/7) merged после `APPROVED` Олега и исправления уязвимостей; CPython 3.12.15, uv 0.13.5. Локальные macOS проверки в PR, Windows junction issue при `uv python install` остаётся не перепроверенным на обновлённом uv. |
| [O-01](https://github.com/inte11ectua1/skinulis/issues/3) инварианты | **merged** | Олег | [PR #8](https://github.com/inte11ectua1/skinulis/pull/8) approved Тимуром и merged; финансовые документы, 105 сценариев, вопросы Q-01–Q-10. Это документация, не реализация тестов. |
| [L-01](https://github.com/inte11ectua1/skinulis/issues/4) Telegram UX | **merged** | Лера | [PR #9](https://github.com/inte11ectua1/skinulis/pull/9) approved Тимуром и merged; сценарии, 42 будущих QA-проверки, вопросы UQ-01–UQ-09. Требующие контрактов пункты остаются открытыми. |

**ADR:** 001 (GitHub Flow) принят PR #6; 002 (uv) принят PR #7. Текстовые статусы приняты в main через [PR #14](https://github.com/inte11ectua1/skinulis/pull/14).

## M1 — Skeleton (вторая фаза, назначенные задачи)

| Задача | Состояние | Ответственный | Зависимости |
|---|---|---|---|
| [T-03](https://github.com/inte11ectua1/skinulis/issues/10) API/DB/Alembic/Compose | **merged** | Тимур | [PR #15](https://github.com/inte11ectua1/skinulis/pull/15) merged; PostgreSQL 17.11, Alembic, Compose, локальное cold-start evidence ниже |
| [O-02](https://github.com/inte11ectua1/skinulis/issues/11) pure splits и parser | **merged** | Олег | [PR #16](https://github.com/inte11ectua1/skinulis/pull/16) и [#17](https://github.com/inte11ectua1/skinulis/pull/17) merged; parser/splits, Q-01/Q-02 и часть Q-04 приняты; финансовых моделей/API пока нет |
| [L-02](https://github.com/inte11ectua1/skinulis/issues/12) bot skeleton и mock HTTP | **merged** | Лера | [PR #18](https://github.com/inte11ectua1/skinulis/pull/18) merged; навигация/typed health client/mock-тесты, без live Telegram и онбординга |
| [T-04](https://github.com/inte11ectua1/skinulis/issues/13) PR CI | **PR review** | Тимур | [PR #19](https://github.com/inte11ectua1/skinulis/pull/19); первый CI зелёный, намеренный сбой даёт tests/ci failure и API BLOCKED; required checks настроены. Визуальная причина merge block ещё требует проверки; [evidence T-04](operations/CI.md) |

T-03, O-02, L-02 приняты и доступны в main `2de19e2`. T-04 выполняется на этой базе. Согласование shared-контрактов — через issue/PR, без молчаливого изменения PRODUCT_RULES.

## Release gates

| Gate | Статус | Условие проверки |
|---|---|---|
| G1 — cold start / миграция / health / CI | **not verified** | T-03, T-04: миграции на пустой БД, /health 200 и 503 при отказе DB, reviewed PR с зелёным CI, blocked merge при красном CI |
| G2 — auth и группы | **not verified** | M2 |
| G3 — расходы | **not verified** | M3 |
| G4 — компенсации | **not verified** | M4 |
| G5 — публикация и CD | **not verified** | M5 |
| G6 — приёмка / демонстрация | **not verified** | M6 |

## Открытые вопросы и ограничения

- Защита main и обязательные checks подтверждены административным API, хотя GitHub-коннектор продолжает возвращать 403. Отдельно остаётся визуальная проверка причины блокировки Merge при красном CI и практический отказ direct push; настройки и evidence см. [CI](operations/CI.md).
- Предпросмотр расхода без записи **UQ-03** не имеет принятого API-маршрута; до согласования O-04/O-05 и L-04 нельзя реализовать локальные денежные расчёты или временные расходы ради превью.
- Денежная грамматика/порядок ID **Q-01/Q-02** приняты в PR #17; прочие Q/UQ закрываются до соответствующих этапов по ответственным.
- API/PostgreSQL/Docker проверены локально в T-03 ([PR #15](https://github.com/inte11ectua1/skinulis/pull/15)); каркас бота принят PR #18, live Telegram/product E2E не проверены. CI и защита main — отдельное evidence T-04; G1 до подтверждения всех условий не закрывать.

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
  смене httpx для TestClient не подавлено. T-04 и G1 остаются отдельной работой.

## Проверки T-04 (27.10.2026)

[PR #19](https://github.com/inte11ectua1/skinulis/pull/19),
[первый зелёный CI](https://github.com/inte11ectua1/skinulis/actions/runs/40458001625),
[намеренно красный CI](https://github.com/inte11ectua1/skinulis/actions/runs/40458200449).
На GitHub Linux: 343 unit + 4 PostgreSQL integration passed, branch coverage
app + bot 97.79%, Docker build success; frozen/lock/Ruff/mypy/secrets/audit прошли.
Локально macOS повторены эти проверки и Compose integration runner; actionlint
также прошёл. Бизнес-код, тесты владельцев и lock не менялись.

Защита main настроена и повторно прочитана: required lint/types/tests/docker-build/ci
от GitHub Actions, strict up-to-date, PR с 1 approval, stale dismissal, conversations,
admin enforcement, no force-push/deletion/bypass. Красный head имел API BLOCKED,
но UI merge box недоступен; конкретная визуальная причина ещё не подтверждена.
Намеренная ошибка удалена до окончательного review; восстановленный run и снимок
API — в [CI evidence](operations/CI.md). Issue #13 открыта; G1 остаётся not verified
до независимого review/merge и оставшегося подтверждения merge box.
