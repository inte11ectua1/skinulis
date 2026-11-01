# Окружение API (T-03 / T-05 / T-06)

Секреты хранятся в локальном `.env` / переменных окружения. В Git находится только
`.env.example`. Существующий `.env` не перезаписывать. При использовании `.env`
значения со специальными символами заключайте в одинарные кавычки. Не прикладывайте
полный вывод `docker compose config` к PR: после интерполяции он содержит пароль.
Для проверки синтаксиса используйте `docker compose config --quiet`.

**M5 / T-09 (31.10.2026):** подготовлены отдельный production Compose, Caddy policy,
trusted-main release workflow и контроллер deploy/rollback; [runbook](operations/DEPLOYMENT.md).
Последняя миграция — `0006_settlement_notification_claim`; новых миграций T-09 нет.
Ниже local/test environment сохранён, а production-схема добавлена отдельно в конце.
На 01.11.2026 SSH/EC2 preparation и pull опубликованного main digest проверены;
публичный HTTPS/production rollout/G5 ещё не подтверждены.
[Точные границы evidence](operations/T-09_EC2_PREFLIGHT.md).
Rollout и live Telegram требуют отдельного разрешения Тимура. Secrets только в protected Environment или private
runtime store на сервере; значения не включать в PR/logs/build args/config output.

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
| `BOT_SERVICE_TOKEN` | Внутренний credential доверенного бота | Обязателен для API, 43–128 URL-safe символов, без default; отдельный от JWT/DB/Telegram token. Migrate не получает | пусто; генерируется локально token_urlsafe(48) |
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
транзакцию. T-05 регистрация использует `session.begin()`, а T-06 write-сервисы явно
commit/rollback всей операции, включая autobegin от auth SELECT; вложенный begin
после auth не используется. Один сервис владеет одной top-level транзакцией; автоматического commit после HTTP-ответа нет. Таймаут подключения и ожидания
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

## T-06 service credential

API проверяет BOT_SERVICE_TOKEN при создании приложения; отсутствие/невалидный
формат/совпадение с JWT или DB password запрещают старт безопасной ошибкой.
Настройки скрывают credential из repr/errors. ASCII URL-safe формат исключает ':'
Telegram Bot API token. Compose передаёт service secret только api, не migrate и
не Docker build. Миграционный сервис работает без обоих auth secrets.
Тесты генерируют разные свежие JWT/service secrets в памяти для каждого теста,
не используют .env оператора. Production reverse proxy должен закрывать /internal
снаружи; это требование будущего T-09, не результат текущего deployment.

[Контракт T-06](contracts/T-06_IDENTITY.md) фиксирует утверждённые tech lead в Issue #22 заголовки, DTO,
ошибки, no-merge и безопасные повторы. Следующая ревизия 0003_groups_identity
добавляет groups, group_members, group_invites, telegram_link_codes после users;
один head, group-first locks, deferred owner-membership FK, без CASCADE.

## Production delivery — T-09

Шаблон `deploy/production.env.example` заполняется **на VPS вне release bundles**
как `/opt/skinulis/production.env` с mode0600, regular file. Неправильные или
совпадающие secrets запрещают rollout; controller не печатает resolved config.
Это отдельный файл: пользовательский локальный .env не перезаписывается.

| Переменная | Где хранится / ограничения |
|---|---|
| COMPOSE_PROJECT_NAME | VPS file; фиксировано skinulis-production, не менять между релизами |
| PUBLIC_DOMAIN | VPS file; public DNS name без scheme/path, реальная A/AAAA до ACME; .invalid не подходит |
| POSTGRES_VOLUME | VPS file; имя заранее созданного external persistent volume. Не менять на новый пустой volume при обновлении |
| POSTGRES_DB / POSTGRES_USER | VPS file; canonical SQL identifiers, lower-case, до63 символов |
| POSTGRES_PASSWORD | VPS only; минимум32 bytes случайного значения; не менять без отдельной процедуры смены пароля существующей БД |
| JWT_SECRET_KEY | VPS only; минимум32 случайных bytes; смена инвалидирует прежние JWT |
| BOT_SERVICE_TOKEN | VPS only; одинаковый у api/bot,43–128 URL-safe, отдельный от DB/JWT/Telegram |
| TELEGRAM_BOT_TOKEN | VPS only; нужен только для отдельно разрешённого enable_polling=true |
| JWT_ACCESS_TOKEN_TTL_MINUTES | VPS file,15 по умолчанию,1..60 |
| APP_IMAGE | Передаёт controller: только ghcr.io/inte11ectua1/skinulis@sha256:64hex, не latest/короткий SHA |
| APP_COMMIT_SHA | Встроен в образ из verified main SHA, не переопределяется runtime config |
| API_BASE_URL | Production bot: фиксировано http://api:8000, public proxy для bot-service не используется |
| PRODUCTION_ROLLOUT_ENABLED | GitHub repository variable; отсутствует/false до отдельного разрешения |
| SSH_HOST / SSH_USER / SSH_PORT / SSH_DEPLOY_DIR | GitHub production Environment variables; pinned host-key alias / skinulis-deploy / 22 / deploy root; TCP destination заменён SSM instance ID |
| AWS_ACCOUNT_ID / AWS_ROLE_ARN / AWS_INSTANCE_ID | GitHub production Environment variables, не secrets; отдельная OIDC role skinulis-github-production и одна EC2, region ap-southeast-2 закреплён workflow |
| SSH_PRIVATE_KEY / SSH_KNOWN_HOSTS | Только GitHub protected production Environment secrets; required independent approval, prevent self-review |
| GHCR read credential | Только для private package: VPS Docker credential store, read:packages. Проверенный текущий package доступен для anonymous pull; широкий личный GitHub token на сервер не копировался |

Только caddy публикует80/443. DB/API без ports, named PostgreSQL volume external,
api/bot non-root; мигратор получает только DB credentials. Bot polling по умолчанию
выключен, profile polling/один container, только явное разрешение. Unit/dry-run и
локальный trusted-CA TLS smoke не доказывают реальные Environment settings,
публичный ACME certificate, GHCR permissions или G5. Setup/диагностика/ограничения
image rollback без DB downgrade: [DEPLOYMENT](operations/DEPLOYMENT.md).

**Фактически настроено 01.11.2026:** Environment `production`, required reviewers
Олег/Лера, prevent_self_review=true, can_admins_bypass=false, protected branches
only. SSH_PRIVATE_KEY — отдельный deployment key, не AWS bootstrap key;
SSH_KNOWN_HOSTS проверен по доверенному fingerprint. Четыре SSH destination
variables заданы; значения и access addresses в документацию не копируются.
PRODUCTION_ROLLOUT_ENABLED=false. Runtime secrets сгенерированы на EC2 в0600-файле,
PUBLIC_DOMAIN ожидает выбора владельца, TELEGRAM_BOT_TOKEN пустой. Токен бота
может предоставить только владелец безопасным способом; polling не запускался.


Для AWS нет статических access-key secrets: deploy job после independent approval
получает временные credentials через OIDC. Trust использует exact immutable repo
subject + production Environment. Настройка владельцем и JSON policies:
[AWS_SSM_CD](operations/AWS_SSM_CD.md). `check-transport` не требует включать rollout
и не запускает controller/миграции/polling. IAM/реальное SSM соединение этим PR
не считаются проверенными; EC2 agent/session подтверждены владельцем отдельно.
