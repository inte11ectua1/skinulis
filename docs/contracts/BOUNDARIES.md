# Границы контрактов

**Деньги — Олег.** Int копейки, BIGINT в БД, строки «123.45» в API. Три режима equal/custom/by_items. Сервис рассчитывает балансы и план. Бот не выполняет финансовую математику.

**Авторизация — Тимур.** Публичные API JWT, внутренние bot-service запросы с проверенным служебным токеном. Actor из аутентификации, не из произвольного JSON. Проверка прав и членства на API.

**Telegram — Лера.** aiogram handlers, FSM и httpx-клиент по согласованным OpenAPI-схемам. Использовать mock fixtures, пока API не готов.

**Общий формат ошибок:** error.code, error.message, error.request_id. HTTP 400/401/403/404/409/500. Списки limit 20 по умолчанию; предварительный выбор limit+offset и стабильная сортировка по created_at и id.

**Транзакции:** все финансовые записи внутри одной группы под блокировкой groups FOR UPDATE, сначала group lock, потом запись. client_request_id UUID для идемпотентности. Confirm rechecks balance. Confirmed settlement immutable.

**Модели:** Тимур users/groups/members/invites/link codes; Олег expenses/items/shares/settlements. Новые миграции согласовывать, не оставлять несколько Alembic heads.

Контракт меняется только через issue, PR и ревью владельцев.