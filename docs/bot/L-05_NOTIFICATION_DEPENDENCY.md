# L-05 — интеграция best-effort уведомления о pending

Задача [#48](https://github.com/inte11ectua1/skinulis/issues/48),
PR [#54](https://github.com/inte11ectua1/skinulis/pull/54).

## Зависимость согласована и принята

Прежний API-блокер снят: контракт Тимура [PR #56](https://github.com/inte11ectua1/skinulis/pull/56)
и backend Олега [PR #57](https://github.com/inte11ectua1/skinulis/pull/57) merged.
Фактическая main `572f875` включает утверждённые маршрут, DTO и миграцию0006.
Источник — [T-08_PENDING_NOTIFICATION](../contracts/T-08_PENDING_NOTIFICATION.md),
[O-07N implementation](../finance/O-07_IMPLEMENTATION.md#o-07n-одноразовое-разрешение-уведомления)
и [typed fixture](../finance/fixtures/O-07N_NOTIFICATION_CLAIM.json).
Это согласование контракта, не персональный human APPROVED бота.

## Реализация Леры

1. Только после подтверждённого финансового create201 или original replay200
   при восстановлении сохраняется подтверждённый ID и замороженное намерение FSM.
2. Typed ApiClient вызывает **POST /internal/settlements/{id}/notification-claim**
   **без body**, с прежними service credentials и trusted sender из Update.
3. Только **200 {recipient_telegram_id}** разрешает одну попытку
   `Bot.send_message` в соответствующий приватный чат. DTO — strict positive BIGINT,
   extra forbid, hide input и repr без Telegram ID. Нет user_id→chat_id,
   username lookup, подмены actor или получения identity из публичного API.
4. **204 с пустым телом**, error/timeout или malformed ответ означают отсутствие
   отправки. Автоматических claim retries нет; вызывающая сторона не повторяет
   финансовый POST из-за сбоя уведомления.
5. Одна ограниченная5s попытка SendMessage с нейтральным текстом без суммы/имён,
   без reply_markup и без nonce из FSM отправителя. Ошибки Telegram API, timeout,
   network/OS не мешают продолжению сценария и чтению текущего статуса.
6. Затем GET settlements показывает актуальный статус. Original pending replay
   не является доказательством нового pending, результат claim — не доказательство
   доставки или текущего финансового статуса.

Сообщение: «Для вас могла появиться заявка на подтверждение перевода.
Откройте /start → Ожидают подтверждения и проверьте актуальный статус.
Подтверждайте только реально полученные деньги. Бот не переводит деньги».

Логи содержат только фиксированные категории `Pending notification claim unavailable`
или `Pending notification delivery unavailable`, без exception payload, traceback,
Telegram ID, token, суммы, финансовых данных или идентификаторов заявки.

## Однократность и ограничения

За однократность отвечает принятый backend, не недолговечный FSM. Он проверяет
sender, memberships, current pending и Telegram-привязку receiver. Claim атомарно
фиксируется до ответа, включая no binding. Повтор после потерянного ответа,
terminal replay или повторного вызова вернёт204; штамп не сбрасывается после
Telegram403/timeout. Claim не меняет balance/status/original creation.

Финансовый POST может быть повторён только явно при восстановлении неизвестного
исхода, с прежним UUID/body/sender. Успешное восстановление вправе запросить claim,
но не новое разрешение на уже claimed/terminal запись. Ordinary GET, refresh,
receiver transitions, stale callbacks и restart без frozen create intent claim
не вызывают. Старые записи помечены миграцией0006 против ретро-уведомлений.

Best effort допускает пропуск: потеря claim-ответа после commit или сбой send
не восстанавливают разрешение. Гарантия «доставлено ровно один раз» не заявляется.
После claim возможен terminal-переход, поэтому текст предлагает проверить актуальный
статус, а не обещает, что pending ещё активно. Получатель всегда открывает incoming
через своё меню и свою авторизацию.

Это доставка при создании **через Telegram**. Public JWT create сам уведомление
не запускает. Универсальная доставка из всех каналов/outbox/worker не реализуются
этим PR. Новых dependencies, auth schemes, backend/services/migrations Леры нет.
MemoryStorage остаётся недолговечным, live Telegram и G4 по-прежнему отложены.

## Проверки и передача на review

- Unit/mock Telegram + HTTP: правильный приватный recipient, strict200/empty204,
  no binding, blocked/network/timeout/deadline, безопасные логи, нет POST-дублей,
  no delivery на terminal replay/duplicate/update/restart, меню без уведомления.
- Настоящие HTTP/Uvicorn + отдельная PostgreSQL17 UUID-БД: correct binding distinct
  from DB ID, persistent stamp, lost-create recovery, все terminal replay,
  lost claim response after commit, no binding/late binding, blocked/network,
  unchanged pending/ledger и incoming menu.
- Сохраняются restaurant/partial/repeat/reverse debt, L-03/L-04 и все backend
  concurrency/migration regression tests. Telegram session всегда mocked.
- Точные результаты полного набора, coverage и CI окончательного head указаны в PR.
  Моки и HTTP+PG не выдаются за live Telegram/G4 или независимый human approval.

При выполненном scope и зелёном CI PR возвращает **Closes #48**. Перед merge нужны
независимое ревью Тимура/Олега и разрешённые замечания. Агент merge не выполняет;
STATUS обновляется человеком после принятия PR. Live Telegram не запускать без
отдельного разрешения Тимура.
