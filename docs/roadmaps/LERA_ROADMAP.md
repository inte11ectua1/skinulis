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

## Назначенная M4 — [L-05 #48](https://github.com/inte11ectua1/skinulis/issues/48)

**Mock/UI можно делать сейчас**: экраны group balances, greedy plan, входящие/outgoing pending, history, sender mark external transfer, receiver confirm/reject, sender cancel. Показывать только серверные суммы, partial/zero/negative, сообщения при changed debt409, stable UUID для repeated POST, best-effort notifications без заявлений о реальном платеже. Использовать [T-08 M4 контракт](../contracts/T-08_M4_BALANCES_SETTLEMENTS.md) для mock fixtures, передать client review замечания Тимуру по [T-08 #45](https://github.com/inte11ectua1/skinulis/issues/45); не изобретать URL и не выдавать чужое APPROVED. **Реальный HTTP подключать после merged [O-06 #46](https://github.com/inte11ectua1/skinulis/issues/46) и [O-07 #47](https://github.com/inte11ectua1/skinulis/issues/47).** Один mock-only PR не закрывает L-05; full HTTP+PostgreSQL integration тестируется отдельно без настоящего Telegram.

**G2/G3 live QA не начинать:** [Issue #38](https://github.com/inte11ectua1/skinulis/issues/38) закрыта как not_planned до отдельного сигнала Тимура. Unit/mock/PostgreSQL/CI тесты разработки обязательны; production `/internal` isolation — T-09.

## Для своего чата
«Разбей создание by_items на последовательные кнопки», «Проверь возможные ошибки мастера», «Дай промпт Codex для L-04 без изменения backend», «Составь E2E чек-лист».

