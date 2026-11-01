# T-09 / M5-L — ноутбук как локальный хост

**Решение (01.11.2026):** [ADR 003](../adr/003-laptop-as-demo-host.md). Вместо покупки VPS/домена — локальный Docker Compose + исходящий Telegram long polling, работающий, пока ноутбук включён. Это **не** публичный HTTPS/серверный CD и не оригинальный G5. [Issue T-09 #59](https://github.com/inte11ectua1/skinulis/issues/59) пересогласовывается командой.

## 0. Условия

Нужны Git, Docker Desktop/Engine с Compose, свободный порт 8000 на 127.0.0.1, интернет, Python 3.12/uv при локальных тестах. Работать на **своём** ноутбуке и с **своей тестовой** PostgreSQL; никаких действий с реальными чужими volumes. Установи Docker Desktop и разреши ему запускаться, если требуется постоянная работа. Ноутбук не должен переходить в сон.

`compose.yaml` не содержит Telegram-бота. Дополнительный `compose.laptop.yaml` использует один образ с app+bot из Dockerfile PR #64, добавляет профиль `polling`, разделяет приложение/БД/исходящий Telegram network. Внешние порты: **только 127.0.0.1:8000** для API, у PostgreSQL нет host ports. Публичный Caddy/домен/SSH не нужны.

## 1. Подготовка переменных окружения без публикации секретов

```sh
git switch main
git pull --ff-only
# Создать .env из .env.example, если файла ещё нет. НИКОГДА не перезаписывать существующий .env.
test -e .env || cp .env.example .env
```

В локальном неотслеживаемом `.env` в редакторе укажи **разные** случайные `POSTGRES_PASSWORD`, `JWT_SECRET_KEY` (от 32 байт), `BOT_SERVICE_TOKEN` (43–128 URL-safe символов), а также `TELEGRAM_BOT_TOKEN` **только когда сознательно запускаешь настоящего бота**. Токены в чат, issue, PR, скриншот или лог не отправлять. `POSTGRES_USER/DB` сохранять при повторных запусках, иначе риск подключиться к пустой/другой БД. `APP_ENV=dev`, `API_PORT=8000`, `API_BASE_URL` у bot **фиксирован** внутри Docker: http://api:8000.

Для сопоставления `/version` перед сборкой установи полный SHA проверенной `main` в своём локальном окружении (вводится в текущую оболочку, не коммитится):

```sh
export APP_COMMIT_SHA="$(git rev-parse HEAD)"
```

## 2. Безопасный предварительный запуск (без Telegram)

```sh
docker compose -f compose.yaml -f compose.laptop.yaml config --quiet
docker compose -f compose.yaml -f compose.laptop.yaml up --build -d db migrate api
docker compose -f compose.yaml -f compose.laptop.yaml ps -a
curl --fail http://127.0.0.1:8000/health
curl --fail http://127.0.0.1:8000/version
```

Проверь: `migrate` завершился с кодом 0, `db` и `api` healthy; `commit_sha` в JSON `/version` совпадает с `APP_COMMIT_SHA`. Не публикуй полное `docker compose config`, `docker inspect` environment и файлы `.env` — там возможны секреты.

## 3. Включение Telegram (только сознательно владельцем токена)

Если у тебя уже есть настоящий BotFather токен, никто другой не использует его параллельно и **ты разрешаешь локальное polling**, проверь его наличие в `.env` без печати значения. Затем:

```sh
docker compose -f compose.yaml -f compose.laptop.yaml --profile polling up --build -d
docker compose -f compose.yaml -f compose.laptop.yaml --profile polling ps
```

Бот подключается к Telegram исходящими запросами, принимает сообщения удалённых пользователей и вызывает `http://api:8000` внутри Docker. Удалённым пользователям не нужен твой IP или публичный API. Реальный Telegram E2E требует отдельного ручного согласия и QA-проверки; сам факт запуска контейнера не подтверждает G2/G3/G4. При offline/сне ноутбука сервис не отвечает.

**Не запускать одновременно** `uv run python -m bot.main` и Docker bot с одним токеном: конфликт long polling.

## 4. Остановка, данные и резервные копии

```sh
# Остановить бота отдельно, сохранив API и PostgreSQL:
docker compose -f compose.yaml -f compose.laptop.yaml --profile polling stop bot

# Остановить стек и удалить только контейнеры/сеть (данные в named volume остаются):
docker compose -f compose.yaml -f compose.laptop.yaml down
```

**Нельзя:** `down -v`, `docker volume prune`, `docker system prune --volumes`, удалять существующую `.env` или менять `COMPOSE_PROJECT_NAME` без плана. Резервные копии: прежде чем использовать реальные данные, подготовить архив/экспорт БД в закрытом месте **за пределами Docker volume и ноутбука**; восстановление проверять на отдельном тестовом compose-project, не на действующей БД. Не публикуй файл дампа в Git. Сценарий обновления: сделать backup, проверить зелёный CI в GitHub, `git pull --ff-only`, выполнить проверку `APP_COMMIT_SHA` и пересоздать Compose. Если миграция изменила схему, **не** обещать автоматический откат БД.

## 5. Критерии локальной приёмки T-09 (пока не проверены на ноутбуке)

- [ ] На **ноутбуке Тимура** чистый checkout, корректное private `.env`, Docker Compose config --quiet без ошибок; нет открытых DB портов и API доступен только на 127.0.0.1.
- [ ] PostgreSQL17 с named volume + один foreground migration job + API healthy; `/version.commit_sha` равен SHA рабочей `main`; повторный запуск не теряет тестовые расходы.
- [ ] Проверка внутреннего bot-service actor внутри локальной application сети; обычные публичные /internal routes **не открыты в LAN**, что нужно подтвердить конфигурацией/тестом; это **не** проверка внешнего Caddy reverse-proxy.
- [ ] После явного разрешения оператора работает **один** Telegram polling бот, другой клиент Telegram может создать расход/увидеть баланс/отметить подтверждение. Не использовать чужие реальные данные, тестировать с разрешёнными аккаунтами.
- [ ] Отдельный backup+restore на тестовом томе и safe stop/restart, секреты не появляются в логах.
- [ ] GitHub main CI 5/5, опубликованный релиз GHCR (если отдельное требование курса) подтверждён ссылкой/digest; документация/проверки приложены к #59.

**Текущий статус:** подготовленные конфигурации и CI не заменяют запуск на личном ноутбуке; laptop gate **ещё не verified**, оригинальный VPS/HTTPS G5 **не выполнен и потребует отдельного согласования**, если это обязательное требование преподавателя.
