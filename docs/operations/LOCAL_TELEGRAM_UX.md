# Локальная проверка редизайна #84 на Mac

Это отдельный тестовый стек: `@skinulis_testing_bot` → локальный FastAPI → отдельная
PostgreSQL 17. AWS и `@skinulis_expenses_bot` не используются. Когда Mac выключен,
тестовый бот недоступен. Нужны Docker Desktop, Git, Python/uv закреплённых проектом версий.

## Подготовка без Telegram

Из корня checkout ветки редизайна:

```sh
uv sync --frozen
uv run python scripts/local_ux.py init
uv run python scripts/local_ux.py up
uv run python scripts/local_ux.py check
```

`init` выполняется **один раз**: не перезаписывает существующий файл. Он создаёт
`~/.config/skinulis/ux84.env` с правами 0600 вне Git, случайным именем Compose project,
loopback-портом, отдельными DB/JWT/service секретами и **пустым** TELEGRAM_BOT_TOKEN.
`up` собирает локальный образ и запускает только db → migrate → api; миграции
применяются только к новой локальной БД. API URL выводится после запуска.
`check` проверяет Compose и реальную связь локального API с PostgreSQL. Он выводит
только наличие токена, никогда его значение; запросов Telegram не делает.

При занятом порте можно изменить только API_PORT в этом частном файле на свободный
порт 1024–65535. Не копируйте production.env. Не добавляйте API_BASE_URL/DATABASE_URL:
скрипт отклоняет настройки, способные перенаправить стек. Он допускает только локальный
Unix Docker socket; у бота нет подключения к DB, внешнего порта и DB credentials.

## Токен вводит только владелец

1. На Mac выполните `open -e "$HOME/.config/skinulis/ux84.env"`.
2. Вставьте **только токен тестового** `@skinulis_testing_bot` справа от
   `TELEGRAM_BOT_TOKEN=`. Остальные значения сохраните. Не вставляйте его в чат,
   shell-команду, Git или скриншот.
3. Сохраните файл как обычный текст. Закройте редактор.
4. Выполните `uv run python scripts/local_ux.py check`: ожидаются PASS и
   `telegram_token_present: true`, без значения. При ошибке прав верните
   `chmod 600 "$HOME/.config/skinulis/ux84.env"`.

Не используйте `cat`, `docker compose config`, `docker inspect` или полные логи
конфигурации для пересылки: они способны раскрыть секреты. Codex не должен читать
заполненный токен. Telegram не вызывается до отдельного разрешения владельца.

## Только после отдельного разрешения на настоящий тестовый polling

```sh
uv run python scripts/local_ux.py start-bot --allow-test-polling
```

Перед запуском проверяется локальный /health. Один фиксированный контейнер и replicas=1
не создают второй экземпляр при повторном `up`. В процессе запуска бот проверяет
`getMe`: разрешён только username `skinulis_testing_bot`; другой бот не начинает polling.
Эта проверка уже является внешним Telegram-запросом. Не запускайте параллельно
`python -m bot.main` или другой checkout с тем же токеном. Убедитесь, что такого
polling нет на другом компьютере: локальная защита не может проверить другие хосты.

Откройте https://t.me/skinulis_testing_bot с трёх аккаунтов и выполните
[сценарий приёмки](../ux/84_TELEGRAM_REDESIGN.md#ручная-приёмка-тремя-аккаунтами).
Все записи синтетические, только в отдельной тестовой группе. Бот не переводит деньги.

## Остановка без потери локальных данных

```sh
uv run python scripts/local_ux.py stop-bot
uv run python scripts/local_ux.py stop
```

Первая команда останавливает только локальный тестовый polling; вторая — весь его
локальный проект. Volumes сохраняются. Для продолжения: `up`, `check` и только после
разрешения `start-bot --allow-test-polling`. Не используйте `down -v`.
Production на AWS продолжает работать независимо.

## Что уже проверено автоматически

Изолированный db/migrate/api действительно запускался на Mac; /health подтвердил
PostgreSQL. Через loopback HTTP выполнены три синтетических профиля, имена, группа,
два join, equal/custom/by_items, confirm, правка и soft-delete. Это backend smoke,
**не live Telegram и не визуальная приёмка**. Токен при подготовке оставлен пустым,
внешние Telegram-запросы и polling не выполнялись.
