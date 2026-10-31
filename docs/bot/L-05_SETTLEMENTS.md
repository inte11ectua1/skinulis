# L-05 — балансы и ручные переводы

Issue [#48](https://github.com/inte11ectua1/skinulis/issues/48), база `main` `b055b7e`.
Проверка GitHub 31.10.2026: PR43 (L-04), PR50 (T-08 contract), PR51 (O-06),
PR53 (O-07) merged. Исторические отметки PR review в STATUS не используются как
блокер. Источники: [T-08](../contracts/T-08_M4_BALANCES_SETTLEMENTS.md),
[O-07](../finance/O-07_IMPLEMENTATION.md), принятые
[O-06 fixtures](../finance/fixtures/O-06_BALANCES.json),
[O-07 fixtures](../finance/fixtures/O-07_SETTLEMENTS.json), фактический OpenAPI.
Security review T-08 #45 остаётся отдельной задачей.

## Пользовательский путь

`/start` → **Мои группы** → группа → **Балансы** → **План переводов** →
**Я перевёл деньги**. Сценарии L-03/L-04 сохраняются. Новых настроек/зависимостей
нет: подготовка окружения описана в [L-03](L-03_SETUP.md) и [L-04](L-04_EXPENSES.md).
Не запускайте живого Telegram-бота до отдельного разрешения Тимура.

Балансы берутся из API: `2200.00 ₽ — участнику должны`, `-1400.00 ₽ — участник
должен`, `0.00 ₽ — долгов нет`. Порядок и точные строки сохраняются, refresh заново
читает сервер. API не предоставляет имена других людей: показан `Участник #ID`.
Бот не считает/суммирует деньги, не округляет и не вычисляет доступный максимум.

План выводит серверные строки `Участник #20 → Участник #10: 1400.00 ₽`, несколько
строк или «По текущему плану переводов нет». Это рекомендации, не факт оплаты
и не обязательство; минимальное число переводов не обещается. Просмотр не создаёт
pending и не резервирует долг. Greedy остаётся на backend.

## Фиксация перевода

1. Выберите **Я перевёл деньги** в группе, балансах или плане.
2. Выберите другого участника; бот читает все страницы members и исключает себя.
3. Введите фактически отправленную положительную сумму, например `500.00`.
4. Проверьте receiver/amount и нажмите **Да, я уже перевёл деньги**.
5. API проверяет текущий долг/кредит и создаёт pending. Бот читает актуальный статус.

Проверка введённых данных на шаге4 — локальный экран ввода, без выдуманного
settlement-preview endpoint. Формат: ASCII, строго два знака, без знака/пробелов/
запятой/экспоненты/ведущих нулей, не `0.00`. Wire длина20 — по O-07; BIGINT максимум
и допустимую сумму окончательно проверяет API. **Лимит расхода1000000.00 не
применяется к компенсациям**, частичный перевод обычен. Sender берётся из actor.

Всегда показано: «Бот не переводит деньги и не проверяет банк. Подтверждайте только
реально полученные деньги». Приложение лишь фиксирует внешний перевод.

## Списки, история и права

| Экран | status / direction |
|---|---|
| Ожидают подтверждения | pending / incoming |
| Исходящие переводы | status отсутствует / outgoing |
| История переводов | status отсутствует / all |

Глобальная кнопка «Ожидают подтверждения» сначала предлагает выбрать свою группу.
История содержит все статусы, с фильтрами pending/confirmed/rejected/cancelled
или все; направления incoming/outgoing/all. UI «все статусы» означает отсутствие
status query, не status=all. Фильтры применяет сервер до пагинации. Default20,
`{items,limit,offset}`, порядок `(created_at,id) ASC`, без total/has_next. После
полной страницы следующая может быть пустой; есть назад и обновление.

Отдельного GET по ID нет. «Открыть перевод» перечитывает список с offset0;
если запись дальше, есть **Следующая страница поиска**. Поиск не использует старую
карточку как доказательство статуса. Create/replay ищет точные ID/UUID в outgoing
без status-фильтра. Не изобретаются query по UUID или GET /settlements/{id}.

| Статус | Действия и влияние |
|---|---|
| pending | Баланс прежний, долг не резервируется; receiver confirm/reject, sender cancel |
| confirmed | API учитывает один раз; бот обновляет оба GET balances и settlement-plan |
| rejected | Получатель отклонил; финансового эффекта нет |
| cancelled | Отправитель отменил заявку; финансового эффекта нет, внешний перевод не возвращается |

Перед confirm — отдельный вопрос о реальном получении указанной суммы.
Reject/cancel тоже требуют подтверждения. Owner не получает специальных прав.
Terminal-карточки содержат только чтение/навигацию. API проверяет роль при каждом
переходе, включая повтор. Same terminal transition200 сохраняет resolved_at;
несовместимый409 не переписывает историю.

409 `settlement_balance_conflict` означает изменившийся долг/кредит. Failed confirm
оставляет pending; получатель может отклонить, отправитель отменить. Сумма не
исправляется автоматически. Две pending на полный долг допустимы, но при неизменном
долге максимум одна станет confirmed. Expense PUT/DELETE сохраняет confirmed,
может создать обратный долг; бот показывает только новый расчёт API.

## FSM и восстановление

```text
receiver → amount → review → явное согласие → POST
                                      ├→201/200 → GET текущей записи
                                      └→timeout/5xx → frozen UUID/body → чтение/replay
pending → отдельное подтверждение → confirm/reject/cancel
                                 ├→200 → terminal; confirmed → GET balances + plan
                                 ├→409 → текущая запись, без исправления суммы
                                 └→timeout → GET → terminal или pending + same-action retry
```

Состояния `SettlementFlow`: receiver, amount, review, busy, search, create_unknown,
transition_confirm, transition_unknown. UUID и JSON замораживаются до записи;
retry сохраняет receiver, amount, UUID и проверенного sender. Автоматических
write retries нет. Новое намерение получает новый UUID.

**POST replay возвращает историческое pending-создание даже после terminal.**
Бот сообщает только о подтверждённом исходном создании и читает текущий status.
При неудачном чтении нет ложного текущего pending/успеха: есть повтор чтения.

После неизвестного confirm/reject/cancel сначала читается список. Terminal от API
показывается как текущий статус. Pending — только текущий снимок, исходный запрос
ещё мог выполняться: разрешён явный повтор того же role-authorized перехода,
другие действия временно не предлагаются. После известного конфликта снова
читается запись, доступны актуальные действия по роли.

В recovery просмотр балансов/плана/истории не теряет frozen request; есть
**К восстановлению заявки**, новое создание временно скрыто. 400/401/403/404/409/
429/5xx, network/timeout/malformed success дают безопасные локальные сообщения.
API message/payload/SQL/traceback/credentials не выводятся. Ответ другой группы
отвергается до отображения. Неизвестный конфликт не обходится новым UUID.

`/start` уважает активный ввод, `/help` его сохраняет. `/cancel` очищает весь FSM,
включая UUID; не отменяет серверный запрос и не вызывает settlement cancel.
«Отменить ввод» до POST закрывает черновик; «Отменить заявку» — отдельный API-переход.
Сохранены nonce, SimpleEventIsolation и bounded dedup L-03. MemoryStorage не durable:
после рестарта черновик/ключ может потеряться, сначала проверяют историю.
Автоматического восстановления/нового POST нет. Один polling-процесс.

Уведомления другим пользователям не отправляются. Получатель всегда открывает
pending через меню, независимо от доставки уведомления.

## API и тесты

| Метод | Маршрут |
|---|---|
| GET | /internal/groups/{group_id}/balances |
| GET | /internal/groups/{group_id}/settlement-plan |
| POST / GET | /internal/groups/{group_id}/settlements |
| POST | /internal/settlements/{id}/confirm |
| POST | /internal/settlements/{id}/reject |
| POST | /internal/settlements/{id}/cancel |

Create — только `{receiver_id,amount,client_request_id}`, transitions — `{}`.
Типизированный httpx сохраняет конечные timeout, закрытие клиента и T-06 заголовки
`X-Bot-Service-Token`, `X-Telegram-ID` из доверенного Update.from_user.id. Никаких
JWT/password в Telegram, DB/ORM или финансовых алгоритмов в боте.

```sh
uv sync --frozen
uv lock --check
uv run ruff check .
uv run ruff format --check .
uv run mypy .
uv run pytest
uv run pre-commit run --all-files
uv run coverage run -m pytest
uv run python scripts/test_integration.py --cov --cov-append --cov-report=term-missing
uv run coverage report --precision=2 --fail-under=60
```

Unit: `test_bot_settlements.py`, `test_bot_settlement_client.py`: настоящий Dispatcher,
MockTransport/mocked Telegram, знаки/нули/план, поля/роли/статусы, фильтры/страницы,
большие суммы, UUID/replay/current-read, stale/update/cancel/restart, безопасные
ошибки/секреты, совместимость DTO/fixtures с фактическим OpenAPI. L-03/L-04
regression сохранена, включая AST-проверку отсутствия money algorithms/DB imports.

`tests/integration/test_bot_settlements.py`: настоящий Uvicorn/loopback HTTP,
PostgreSQL17 в отдельной UUID-БД с миграциями; только Telegram session mocked.
Ресторан3200 →2200/-1400/-800, pending500 без эффекта, confirm →1700/-900/-800,
повтор без второго эффекта, две full pending, changed expense409, reject/cancel,
soft-delete после confirmed →-500/500/0. Transport теряет настоящий ответ после
commit для всех четырёх POST; проверяется исторический pending replay. Также
actor/foreign404,21 записи, поиск по страницам, компенсация2000000.00.

Существующий runner использует свой Docker project/tmpfs. Без Docker допустим
документированный TEST_DATABASE_URL к отдельному PostgreSQL17, bootstrap `_test`,
роль CREATEDB, случайный пароль через окружение. Затем
`uv run coverage run --append -m pytest -m integration`. Fixture удаляет только
собственные UUID-БД; пользовательские БД/чужие volumes не используются.
Точные результаты полного набора и CI итогового head фиксируются в PR.

Новых API-контрактов/миграций не требуется. L-06, банковские операции, deployment,
production isolation — вне scope. Ревью Тимура/Олега ожидается отдельно; G4 не
объявляется verified. Live Telegram запрещён до разрешения Тимура. STATUS
обновляется человеком после merge.
