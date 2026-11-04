> **Актуализация 04.11.2026.** Текущий порядок: #84 (UX merged/released; owner acceptance и formal review gaps), #79 (единый M6 у Тимура, open/PARTIALLY), #80 (M7 open; подготовка, не завершённая защита). M5 closed; новый release `c9ec9ce` уже deployed с polling=true. Старые секции ниже — этапные срезы; не создавать отдельные L-07/O-09/M6 задачи и не утверждать G6 PASS.
> [Текущий аудит и границы доказательств](../reviews/POST_RELEASE_AUDIT_2026-11-04.md).

# Лера — личный roadmap

**Приоритет:** создать работающий mock Telegram flow и HTTP-клиент до готовности API, затем подключать по одному сценарию. Не зависит от глубокого знания SQL.

| ID | Фаза | Задача | Зависимость | Доказательство готовности |
|---|---|---|---|---|
| L-01 | M0 | Описать UX flows и экраны, сообщения об ошибках/отмене | product rules | flow table для /start, group, expenses, settlement |
| L-02 | M1 | aiogram skeleton, typed httpx client + mock test API; /start | uv config, mock schemas | bot handlers unit tests без live Telegram |
| L-03 | M2 | Онбординг, профиль, инвайты, список групп, deep links | T-06 API contract | sandbox E2E, неправильная invite обработана |
| L-04 | M3 | Expense wizard: equal/custom/by_items, previews, list/detail | O-04/05 OpenAPI fixtures | ресторанный сценарий end-to-end |
| L-05 | M4 | balances, plan, mark partial, incoming pending, confirm/reject/cancel | O-06/07 contract | до confirm балансы прежние, после обновились |
| L-06 | M5 | Retry UUID, timeout, errors/UX regression, UI screenshots | L-03/04/05 | 409/5xx понятны, timeout не удваивает запрос |
| L-07 | M6 | User guide, E2E smoke, сценарий live demo | all API integrated | инструкция от /start до confirm для 3 users |
| L-08 | M7 | Репетиция бот-демо, участие в вопросах | L-07 | 5-минутный live demo репетирован |

## Завершённая фаза M1 (27.10.2026)

**L-02** закрыта: [Issue #12](https://github.com/inte11ectua1/skinulis/issues/12), [PR #18](https://github.com/inte11ectua1/skinulis/pull/18). Есть aiogram-каркас, `/start`, `/help`, `/cancel`, типизированный async httpx-клиент для существующего `/health`, mock-тесты. Live Telegram/онбординг пока не подтверждены.

## Завершённая фаза M2 (28.10.2026)

**[L-03 #24](https://github.com/inte11ectua1/skinulis/issues/24) / [PR #28](https://github.com/inte11ectua1/skinulis/pull/28) — merged/closed.** Реализованы `/start` → явный Create/Link, Telegram-only и привязка существующего API-профиля, меню/создание групп, участники, одноразовые invite/deep links, отзыв/обработка used/expired, типизированный internal httpx client, FSM и восстановление после неопределённого ответа. Есть mocked Telegram session и интеграционные проверки с HTTP API + PostgreSQL; CI 5/5 успешно ([run](https://github.com/inte11ectua1/skinulis/actions/runs/40658217735)). **Live Telegram E2E на настоящем боте пока не подтверждено**, G2 формально pending; production isolation `/internal` — задача T-09. UTC-даты на backend унифицированы [PR #30](https://github.com/inte11ectua1/skinulis/pull/30).

## Завершённый M3 — [L-04 #37](https://github.com/inte11ectua1/skinulis/issues/37)

[PR #43](https://github.com/inte11ectua1/skinulis/pull/43) **merged, Issue closed 30.10.2026**: Telegram equal/custom/by_items expense FSM, server preview, list/details, full PUT/soft-delete, verified bot-service actor, original POST UUID и timeout recovery. Реальные mock Telegram → HTTP → PostgreSQL tests, **не** live Telegram. Финальный T-07 аудит в [PR #44](https://github.com/inte11ectua1/skinulis/pull/44) merged; error no-store и snapshot validation исправлены.

## M4 — завершён (31.10.2026)

[L-05 #48](https://github.com/inte11ectua1/skinulis/issues/48) / [PR #54](https://github.com/inte11ectua1/skinulis/pull/54) **merged/closed**. Балансы/план, pending/confirm/reject/cancel, original UUID replay, bot-service auth и best-effort приватные уведомления через O-07N [#55](https://github.com/inte11ectua1/skinulis/issues/55)/[PR #57](https://github.com/inte11ectua1/skinulis/pull/57) реализованы. [Последний CI](https://github.com/inte11ectua1/skinulis/actions/runs/41210779152) 5/5, 1460 unit+PG tests/94,76%. T-08 [#45](https://github.com/inte11ectua1/skinulis/issues/45) audit закрыт PR #58. Никакого live Telegram polling в этих тестах не было.

## M5 L-06 завершена; следующий план — L-07 / M6

**L-06 [#62](https://github.com/inte11ectua1/skinulis/issues/62) / [PR #75](https://github.com/inte11ectua1/skinulis/pull/75) merged/closed.** UX 400/401/403/404/409/429/5xx и timeout/network, UUID original replay/current GET, stale callbacks/double-click/restart/notification best effort проверены mock Telegram → настоящие локальные HTTP/PostgreSQL17; 35 новых unit и13 HTTP/PG сценариев. [L-06 regression matrix](../bot/L-06_UX_REGRESSION.md), [CI PR #75 5/5](https://github.com/inte11ectua1/skinulis/actions/runs/41517984688). Ни реальный Telegram polling, ни живые участники не проверялись.

**L-07 / M6 ещё не оформлена отдельной Issue:** user guide для 3 участников, пошаговая demo/smoke инструкция, сценарии ошибок и безопасные synthetic screenshots. Live Telegram/E2E — только по явному разрешению Тимура; G2/G3/G4 до такого теста not verified. [M5→M6 handoff](../operations/M5_CLOSEOUT_M6_HANDOFF.md).

## Для своего чата
«Разбей создание by_items на последовательные кнопки», «Проверь возможные ошибки мастера», «Дай промпт Codex для L-04 без изменения backend», «Составь E2E чек-лист».

