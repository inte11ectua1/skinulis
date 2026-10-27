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

## Текущая назначенная задача M2

**[L-03 #24](https://github.com/inte11ectua1/skinulis/issues/24) — assigned, mock-ready:** онбординг/профиль, одноразовая привязка, группы/приглашения через API Тимура ([T-05 #21](https://github.com/inte11ectua1/skinulis/issues/21) → [T-06 #22](https://github.com/inte11ectua1/skinulis/issues/22)). Сразу можно готовить mock FSM/fixtures, но не внедрять неподтверждённые HTTP endpoints/DTO. Начать с [UQ-01/UQ-02](../ux/L-01_CONTRACT_QUESTIONS.md) и согласования с Тимуром. Финансовые Q-01/Q-02 уже приняты в [Issue #11](https://github.com/inte11ectua1/skinulis/issues/11); бот не вычисляет деньги.

## Для своего чата
«Разбей создание by_items на последовательные кнопки», «Проверь возможные ошибки мастера», «Дай промпт Codex для L-04 без изменения backend», «Составь E2E чек-лист».

