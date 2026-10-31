# T-08 / M4 — решение tech lead: best-effort Telegram-уведомление получателя о pending

**Утверждено Тимуром 31.10.2026 для реализации.** [PRODUCT_RULES §7](../PRODUCT_RULES.md) требует best-effort уведомление, но **не** гарантированную доставку. Зависимости: [O-07N #55](https://github.com/inte11ectua1/skinulis/issues/55) — backend Олега; [L-05 #48](https://github.com/inte11ectua1/skinulis/issues/48) / [PR #54](https://github.com/inte11ectua1/skinulis/pull/54) — bot Леры; [T-08 #45](https://github.com/inte11ectua1/skinulis/issues/45) — финальный security review. В `main` уже реализованы O-06/PR #51 и O-07/PR #53. **Это решение Тимура, не выдуманное личное APPROVED Олега или Леры.** До новых кода/тестов/CI требования не считать выполненными. Настоящий Telegram polling/E2E запрещён до отдельного разрешения Тимура.

## 1. Необходимый новый сервисный endpoint (владение Олега)

`POST /internal/settlements/{settlement_id}/notification-claim` — **только** существующий проверенный T-06 bot-service actor (`get_bot_user`, сервисный токен + `X-Telegram-ID` из trusted update). Нет публичного JWT mirror, request body и выбора Telegram адресата клиентом.

Ответы:
- **200** `{"recipient_telegram_id":123456789}`, если verified actor **является sender этой settlement**, обе стороны текущие члены группы, статус **прямо сейчас pending**, разрешение на уведомление ещё никому не выдавали и `users.telegram_id` получателя привязан. Только в этом ответе можно передавать Telegram ID доверенному боту. Он не должен попадать в обычные GET settlements/member DTO или финансовые логи.
- **204 No Content**, если запрос валидно авторизован sender, но settlement terminal, уже была claim, либо у получателя нет Telegram-привязки. Причину не раскрывать, тело пустое, никакого уведомления. Для отсутствующей привязки claim всё равно **расходуется** (см. ниже).
- **404 `settlement_not_found`** для несуществующей, чужой, неразрешённой группы или actor != sender. Без раскрытия статуса/получателя. 401/400 для отсутствующих/неправильных bot service credentials и mixed JWT — по существующему T-06, safe error envelope.
- **No-store и X-Request-ID на 200/204/ошибках.** Strict path positive BIGINT. `recipient_telegram_id` — положительный BIGINT. Не логировать payload/Telegram ID.

Ответ **не говорит, что уведомление доставлено**. Это одноразовое *разрешение на попытку*. Backend никуда не отправляет Telegram API-запрос.

## 2. Durable at-most-once без кэша/очереди

Добавить nullable `settlements.notification_claimed_at TIMESTAMPTZ` в `app/models/finance.py` и Alembic **`0006_settlement_notification_claim`** с `down_revision="0005_expense_replay_version"`. Новые записи `NULL`; поле **не часть settlement business DTO, original POST intent/replay, подтверждений, балансов или плана**.

При `upgrade()` **backfill для всех существующих** `settlements`: `notification_claimed_at = created_at`. Иначе исторические pending или replay старых UUID неожиданно запустят уведомления при развертывании. Нормальные `downgrade`/fresh-upgrade/upgrade-repeat tests нужны. Старые `status`/`resolved_at` и финансовая история не меняются.

Порядок endpoint:
1. Неразрешающий SELECT по settlement ID для поиска `group_id`, без lock settlement. Если ID отсутствует — safe404.
2. Проверить текущего actor как **sender**, членство и захватить **`groups FOR UPDATE` первым** штатным `require_member(..., lock=True)`; затем `settlements FOR UPDATE`, повторно проверить group/sender/status. Не держать внешних сетевых операций под lock.
3. Если **не pending** или `notification_claimed_at != NULL` — 204; ничего не выдавать. Иначе найти `User.telegram_id` только по **серверному** `settlement.receiver_id`, не путать `users.id` с Telegram chat ID. Атомарно заполнить `notification_claimed_at = now UTC` и сделать commit, **даже если привязка отсутствует**. При наличии привязки вернуть 200 c проверенным `recipient_telegram_id`, иначе 204.
4. Claim **commit до Telegram send**. При двух конкурирующих claim только одна 200, следующая 204. При потере ответа после commit новый запрос 204; намеренно **не ретраить попытку выдачи разрешения**. При сбое доставки отметку не очищать: best effort допускает пропуск доставки, но не повторный спам.
5. `confirm/reject/cancel` сериализуются тем же group lock. Если terminal раньше claim —204; если terminal позже claim и раньше доставки — уведомление должно **лишь предлагать проверить актуальные входящие**, не утверждать, что pending всё ещё активно.

Никаких Redis/Celery/new background workers, банковских переводов, дополнительных settlement mutators, public Telegram IDs или перехода T-06 actor через поле JSON.

## 3. Интеграция бота Леры после merge backend #55

На **201 create** либо на **200 original create replay после неоднозначного POST** у бота уже есть `settlement.id`; вызвать `notification-claim` из typed httpx с *тем же trusted sender actor*, только в контексте создания/его восстановления. На 200 claim **одна попытка** `Bot.send_message(chat_id=recipient_telegram_id, ...)` в private Telegram, затем обычное GET list текущего статуса. На 204/error/timeout claim — **не отправлять**. Никогда не вызывать claim при обычных GET list, просмотре балансов, stale callback, receiver transitions или restarts без существующего frozen create intent.

Рекомендованный нейтральный текст, без суммы/имён/финансовых подробностей: «Для вас могла появиться заявка на подтверждение перевода. Откройте /start → Ожидают подтверждения и проверьте актуальный статус. Подтверждайте только реально полученные деньги. Бот не переводит деньги». Telegram private chat доступен только если пользователь ранее начал диалог; на 403 bot blocked/нет чата — безопасно игнорировать. Ни Telegram ID, ни token, ни текст исключения не логировать.

Отсутствие привязки/неудачная/потерянная доставка **не отменяют pending**, не инициируют ещё один `POST settlement`, не изменяют балансы, original history, состояние terminal или пользовательские роли. Incoming pending работает через меню даже без сообщения. Нельзя использовать `users.id` в качестве `chat_id`.

**Сфера гарантии:** доставка при создании через Telegram-бот. Создание pending через публичный JWT API само по себе не вызывает Telegram Bot API; при появлении требований к серверному уведомлению из любого канала обсуждать отдельный outbox/worker, **не представлять этот механизм как гарантию всех публичных API-созданий**. В рамках MVP текущий доступ к incoming pending всегда существует. Этот канал и ограничение явно документировать, не выдавая их за полноценную универсальную нотификацию.

## 4. Критерии приёмки

**Олег, backend #55:** real PostgreSQL17 tests: correct receiver.telegram_id, no binding (204 + persistent claim), terminal/replay (204), two independent simultaneous claims → exactly one 200; race claim vs confirm; non-sender/cross-group actor-safe404; service credential/mixed channel 401/400; no-store/errors/no identity in public DTO; migration backfill old pending, fresh/repeat/downgrade; existing M3/M4 finance state unaffected; GitHub CI 5/5.

**Лера, L-05 #48:** typed API call, correct private chat with mocked Telegram session, blocked bot/timeout/no binding, no repeat send after 200 original replay/terminal/duplicate callback/restart, no finance write retry after failed notification, no secrets leaked, all existing bot expense/M4 mock and HTTP+PG tests; docs and final CI 5/5.

**Порядок:** backend **#55** отдельным финальным PR `Closes #55` и независимый review → merge в `main` → Лера подтягивает backend, доделывает **PR #54**, меняет `Refs #48` на `Closes #48` только после полной приёмки, independent human review → merge. **T-08 #45 остаётся открытой** до финального security review получившегося M4 кода. Пропуски live Telegram не означают, что G2/G3/G4 verified.
