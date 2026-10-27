# Окружение API (T-03 / T-05)

Секреты хранятся в локальном `.env` / переменных окружения. В Git находится только
`.env.example`. Существующий `.env` не перезаписывать. При использовании `.env`
значения со специальными символами заключайте в одинарные кавычки. Не прикладывайте
полный вывод `docker compose config` к PR: после интерполяции он содержит пароль.
Для проверки синтаксиса используйте `docker compose config --quiet`.

## Переменные

| Переменная | Назначение | Обязательность / default | Безопасный пример |
|---|---|---|---|
| `APP_ENV` | Идентификатор среды | `dev`, `test` или `prod`; default `dev` | `dev` |
| `LOG_LEVEL` | Уровень логов приложения | default `INFO`, uppercase | `INFO` |
| `POSTGRES_DB` | База приложения / имя при инициализации контейнера | default `skinulis` | `skinulis` |
| `POSTGRES_USER` | Роль приложения / имя при инициализации контейнера | default `skinulis` | `skinulis` |
| `POSTGRES_PASSWORD` | Пароль PostgreSQL | Обязателен для Compose; для локального API можно вместо него задать полный URL | пусто в шаблоне, генерируется локально |
| `POSTGRES_HOST` | Хост для процесса API/Alembic вне Docker | default `localhost`; в Compose всегда `db` | `localhost` |
| `POSTGRES_PORT` | Порт для процесса вне Docker | default `5432`; в Compose всегда `5432` | `5432` |
| `DATABASE_URL` | Необязательный полный SQLAlchemy URL, только `postgresql+psycopg` | В локальном процессе имеет приоритет над компонентами; Compose его не передаёт | `postgresql+psycopg://skinulis:<encoded-password>@localhost:5432/skinulis` |
| `API_PORT` | Опубликованный порт API на хосте | Только Compose, default `8000`; bind `127.0.0.1` | `8000` |
| `APP_COMMIT_SHA` | Явно переданный настоящий SHA исходников | Необязательный build argument Docker; ровно 40 lowercase hex; пусто → JSON `null` | пусто |
| `API_BASE_URL` | Заготовка адреса API для будущего клиента бота | Backend не читает; конфигурацию сервиса bot согласовать с Лерой | `http://localhost:8000` с хоста, `http://api:8000` в Compose |
| `TELEGRAM_BOT_TOKEN` | Заготовка токена Telegram | Зарезервировано; backend не читает | пусто |
| `BOT_SERVICE_TOKEN` | Заготовка внутреннего service token | Зарезервировано до авторизации; backend не читает | пусто |
| `JWT_SECRET_KEY` | Ключ подписи HS256 | Обязателен для API, минимум 32 UTF-8 bytes случайного значения; без default. Migrate его не требует и не получает | пусто в шаблоне, генерируется локально |
| `JWT_ACCESS_TOKEN_TTL_MINUTES` | Срок access JWT | Default 15, от 1 до 60; алгоритм HS256 фиксирован кодом | `15` |
| `TEST_DATABASE_URL` | PostgreSQL для явно выбранных integration tests | Нужен только для `pytest -m integration`; имя базы заканчивается на `_test` | устанавливается тестовым скриптом |
| `POSTGRES_TEST_PASSWORD` | Пароль временной PostgreSQL из `compose.test.yaml` | Генерируется `scripts/test_integration.py`, в `.env` не нужен | генерируется в памяти |

`app/config.py` читает переменные процесса, затем `.env` из текущего рабочего
каталога; неизвестные переменные игнорируются. Секреты скрыты из repr настроек и
сообщений валидации. Полный URL и пароль нельзя логировать или сериализовать через
пользовательские ответы. `LOG_LEVEL` относится к логгеру приложения; access/error
логи Uvicorn на этом этапе используют его штатную конфигурацию.

Если URL не задан, `URL.create` SQLAlchemy собирает подключение из `POSTGRES_*`:
пароли с `@`, `:`, `/`, `%`, `#`, `$` не требуют ручного URL encoding. В полном
`DATABASE_URL` пароль должен быть URL-encoded. Пароль и URL никогда не передаются
через аргументы Docker build и не копируются в образ.

## Схема запуска

```text
host 127.0.0.1:API_PORT → api:8000 → db:5432 → named volume postgres_data
                                     ↑
                          migrate (один процесс, до api)
```

`db` не публикует порт. `migrate` ждёт healthy DB; `api` ждёт exit 0 миграции.
Миграции не выполняются в FastAPI lifespan / worker. При повторном `compose up`
сервис миграций может запускаться снова: Alembic применяет только новые ревизии.
Это одно выполнение на сервис, а не отдельная миграция в каждом API worker.

Engine и session factory принадлежат экземпляру приложения; на каждый запрос
создаётся отдельная sync Session. Dependency закрывает её и откатывает незавершённую
транзакцию. Будущие сервисы явно используют `with session.begin():` для атомарной
записи; автоматического commit после HTTP-ответа нет. Таймаут подключения и ожидания
pool — 3 секунды, `statement_timeout` — 3000 мс; `pool_pre_ping` восстанавливает
соединение после перезапуска PostgreSQL. Подключение не выполняется при импорте.

`app.models.Base` — единая metadata. Будущие модели импортируются через
`app/models/__init__.py` перед autogenerate. Начальная ревизия `0001_baseline`
не создаёт доменных таблиц; Alembic создаёт только свою `alembic_version`.
Добавление моделей/миграций требует согласования владельцев; нескольких heads
не оставлять. `Base.metadata.create_all()` не используется.

T-05 добавляет `0002_users` после baseline: users с положительным BIGINT ID,
CHECK/UNIQUE и nullable identity-парами; [предлагаемый контракт](contracts/T-05_IDENTITY.md).
API проверяет наличие JWT key при создании приложения; локальная Alembic-команда
использует DB Settings, не вызывает `require_jwt_secret`. Compose передаёт ключ
только сервису api, не migrate и не Docker build. Сменив ключ, оператор инвалидирует
старые tokens; ключ и пароль БД должны быть разными.

## Изолированные тесты

`uv run python scripts/test_integration.py` создаёт случайно названный Compose
project с PostgreSQL 17.11, случайным паролем и динамическим портом на loopback.
База находится в tmpfs. Для каждого теста fixture создаёт собственную БД с UUID,
затем удаляет только её. Указанная в `TEST_DATABASE_URL` база не удаляется.
После тестов скрипт удаляет только свой Compose project. Основной named volume
и контейнеры других проектов не затрагиваются.

Для внешней тестовой PostgreSQL 17 задайте URL базы с суффиксом `_test`; роль
должна иметь право `CREATE DATABASE`. Затем выполните
`uv run pytest -m integration`. Если URL отсутствует, выбранные интеграционные
тесты завершаются ошибкой. SQLite вместо PostgreSQL не поддерживается.
