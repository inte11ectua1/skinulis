# Скинулись

Учебный сервис совместных расходов с Telegram-ботом, FastAPI и PostgreSQL.

> **Статус 26.10.2026:** M0 (подготовка) принята через PR #7/#8/#9; T-01 ещё ожидает окончательной проверки настроек защиты `main`. В T-03 подготовлен каркас FastAPI/PostgreSQL/Alembic/Compose. CI (T-04) и бот (L-02) — отдельные задачи; G1 пока не подтверждён. Текущие факты — в [STATUS](docs/STATUS.md).

## Начало работы

1. Откройте [START_HERE.md](START_HERE.md) и [AGENTS.md](AGENTS.md).
2. Изучите [правила продукта](docs/PRODUCT_RULES.md) и [технические решения](docs/TECHNICAL_DECISIONS.md).
3. Выберите свою [роль](docs/roles) и [дорожную карту](docs/roadmaps).
4. Следуйте [правилам разработки](CONTRIBUTING.md).

## Команда

- Тимур — платформа, безопасность, CI/CD.
- Олег — финансовый backend и тесты расчётов.
- Лера — Telegram-клиент и сквозные сценарии.

## Требования курса

[Официальный репозиторий курса](https://github.com/andrey-limasov/app-conf/).

## Текущие задачи M1

- **Тимур:** [T-03 — API, DB, Alembic, Docker](https://github.com/inte11ectua1/skinulis/issues/10); после T-03 — [T-04 — GitHub Actions CI](https://github.com/inte11ectua1/skinulis/issues/13).
- **Олег:** [O-02 — pure money parser и split functions](https://github.com/inte11ectua1/skinulis/issues/11), согласовать Q-01/Q-02 перед фиксацией спорного поведения.
- **Лера:** [L-02 — aiogram и mock HTTP client](https://github.com/inte11ectua1/skinulis/issues/12); не изобретать API до согласования UQ-01–UQ-09.

Каждая задача: отдельная ветка → PR → независимый review → merge → обновить [STATUS](docs/STATUS.md). [MASTER_ROADMAP](docs/roadmaps/MASTER_ROADMAP.md) описывает остальные фазы.

## Каркас Telegram-бота (L-02)

Команды `/start`, `/help`, `/cancel`, стартовое меню и проверка доступности API
описаны в [инструкции запуска бота](docs/bot/L-02_SETUP.md). Тесты используют mock
Telegram session и HTTP transport; настоящий токен и polling им не нужны.
Регистрация, приглашения, расходы и компенсации пока недоступны.
После локальной настройки `TELEGRAM_BOT_TOKEN` процесс запускается командой
`uv run python -m bot.main`, останавливается через `Ctrl+C`.

## Запуск API с PostgreSQL

Установите [Docker Desktop или Docker Engine с Compose](https://docs.docker.com/get-started/get-docker/)
и запустите Docker. Для локальной разработки нужны Linux containers; на Windows —
Docker Desktop с WSL2. Проверенный минимум: Engine 23.0.5, Compose 2.17.3.
Проверьте `docker version` и `docker compose version`.
Git, Python 3.12.15 и uv 0.13.5 устанавливаются по разделу ниже; для самого Docker
запуска локальная установка Python/uv не нужна — они включены в сборку образа.

После клонирования из корня репозитория создайте `.env` из `.env.example`, не
перезаписывая существующий файл, и заполните **POSTGRES_PASSWORD**. Новый локальный
пароль можно сгенерировать командой `uv run python -c "import secrets; print(secrets.token_urlsafe(32))"`
и сохранить только в `.env`. `DATABASE_URL` для Compose оставьте пустым. Если порт
8000 занят, измените `API_PORT`. В `.env` пароль со специальными символами
заключайте в одинарные кавычки.

```sh
docker compose config --quiet
docker compose up --build
```

Для запуска в фоне используйте `docker compose up --build -d`.
При первом запуске будет создан отдельный named volume PostgreSQL. База ждёт
готовности, сервис `migrate` выполняет `alembic upgrade head`, и только его exit 0
разрешает старт API. Финансовых и пользовательских таблиц пока нет.

```sh
docker compose ps -a
docker compose logs migrate
curl -i http://localhost:8000/health
curl http://localhost:8000/version
```

На Windows используйте `curl.exe` либо `Invoke-WebRequest`. В браузере откройте
[Swagger](http://localhost:8000/docs), [ReDoc](http://localhost:8000/redoc) и
[OpenAPI](http://localhost:8000/openapi.json).

| Маршрут | Результат |
|---|---|
| `GET /` | `{"name":"skinulis","docs":"/docs"}` |
| `GET /health` | реальный `SELECT 1`: HTTP 200, `{"status":"ok","database":"ok"}` |
| DB недоступна | HTTP 503, `error.code=database_unavailable`, безопасное сообщение и request ID |
| `GET /version` | `{"version":"0.1.0","commit_sha":null}` по умолчанию |

Версия задана в `app/__init__.py` и соответствует `project.version`. SHA не
вычисляется из отсутствующего в образе `.git`: при необходимости задайте настоящий
40-символьный `APP_COMMIT_SHA` в `.env` **до сборки**. После смены SHA пересоберите
образ. Пока это явный ввод разработчика, гарантий production provenance и CI нет.
Dockerfile фиксирует Python 3.12.15 и uv 0.13.5 по версии и digest; runtime работает
с UID 10001. БД PostgreSQL 17.11 приватна, порт API опубликован только на loopback.
Сервиса bot пока нет; будущий адрес внутри сети — `http://api:8000`, согласовать с Лерой.

### Миграции, локальный процесс и остановка

```sh
docker compose run --rm migrate
docker compose exec api alembic current
docker compose exec api alembic heads
```

Повторная миграция без новых ревизий — успешная пустая операция. Если миграция
завершилась с ошибкой, исправьте подключение/миграцию и повторите команду;
`docker compose up -d api` стартует API только после успешного migrate.
Новая модель наследует `app.models.Base` и импортируется в `app/models/__init__.py`;
добавление доменных моделей/миграций согласовывается с владельцем.

Для процесса API вне Docker используйте свою локальную PostgreSQL 17 и
`POSTGRES_HOST`/`POSTGRES_PORT`/пароль либо полный `DATABASE_URL` из схемы окружения.
Основной Compose не публикует DB наружу. После настройки:

```sh
uv run python -m app.core.migrate
uv run uvicorn app.main:create_app --factory --host 127.0.0.1 --port 8000
```

Для остановки своего проекта без потери PostgreSQL:

```sh
docker compose stop
# либо удалить контейнеры и сеть, сохранив named volume:
docker compose down
```

Не применяйте `down -v` к нужным данным. После возврата к проекту
`docker compose up --build -d` использует сохранённый volume.

### Проверка отказа БД и частые ошибки

Выполняйте только для своего локального Compose project:

```sh
docker compose stop db
curl -i http://localhost:8000/health
# ожидается 503
docker compose start db
# после готовности PostgreSQL снова ожидается 200
```

- **Cannot connect to Docker daemon:** запустите Docker Desktop/Engine и проверьте context.
- **POSTGRES_PASSWORD is missing:** заполните `.env`; пустой пароль намеренно блокирует Compose.
- **Port is already allocated:** поменяйте `API_PORT`, не останавливая чужой контейнер.
- **Password authentication failed:** пароль в существующем volume не меняется от редактирования `.env`. Верните соответствующее значение или смените пароль SQL-командой в своей БД; volume не удаляйте ради исправления ошибки.
- **migrate Exited (1), API не стартует:** проверьте `docker compose logs migrate`, DB health, имя базы, роль и единственную цепочку ревизий. Команда миграции намеренно скрывает connection details; не публикуйте секреты при диагностике.
- **health 503 после старта:** проверьте `docker compose ps` и доступность `db`; sync SQLAlchemy использует ограниченные таймауты и `pool_pre_ping`, восстановление не требует перезапуска API.

## Окружение разработки

Инструкция подходит для чистого компьютера. Нужны Git, доступ к GitHub и интернет для первой загрузки Python и зависимостей. Устанавливать Python отдельно не требуется: им управляет uv. Используем **uv 0.13.5** и **CPython 3.12.15**. Точный Python закреплён в [.python-version](.python-version), семейство `>=3.12,<3.13` и версия uv — в [pyproject.toml](pyproject.toml).

1. Установите Git по [официальной инструкции для вашей ОС](https://git-scm.com/install/).
2. Установите закреплённую версию uv официальным установщиком:

   macOS / Linux:

   ```sh
   curl -LsSf https://astral.sh/uv/0.13.5/install.sh | sh
   ```

   Windows (PowerShell):

   ```powershell
   powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/0.13.5/install.ps1 | iex"
   ```

   Способы установки и просмотр установщика перед запуском описаны в [документации uv](https://docs.astral.sh/uv/getting-started/installation/). Откройте новый терминал, чтобы обновился `PATH`. Если uv уже установлен, проверьте версию; настройка проекта требует именно `0.13.5`.

   При обновлении существующего окружения также выполните `uv python install --reinstall` из корня проекта: это обновит сборку закреплённого Python 3.12.15. uv 0.13.5 включает обновлённые сборки managed Python; смена версии uv сама по себе не обновляет уже установленный интерпретатор. [Описание релиза](https://github.com/astral-sh/uv/releases/tag/0.13.5).

3. Проверьте инструменты и клонируйте репозиторий в свою папку проектов. Если рабочая копия уже есть, перейдите в неё вместо повторного клонирования.

   ```sh
   git --version
   uv --version
   git clone https://github.com/inte11ectua1/skinulis.git
   cd skinulis
   ```

4. Из корня репозитория установите закреплённый Python и зависимости:

   ```sh
   uv python install
   uv sync --frozen
   uv lock --check
   uv run python --version
   uv run pre-commit install
   ```

   `uv python install` читает `.python-version`; получаем Python `3.12.15`. uv создаёт локальную `.venv` и устанавливает группу `dev` из `uv.lock`. Активация окружения для `uv run` не нужна. [Подробнее об установке Python](https://docs.astral.sh/uv/guides/install-python/).

   `--frozen` устанавливает сохранённый lock-файл без его обновления, но не проверяет соответствие `pyproject.toml`. Поэтому отдельно запускаем `uv lock --check`; в hooks используется `--locked`, который отклоняет устаревший lock-файл. [Поведение lock и sync](https://docs.astral.sh/uv/concepts/projects/sync/).

5. Для запуска Compose создайте локальный файл настроек, сохранив существующий `.env`:

   macOS / Linux:

   ```sh
   cp -n .env.example .env
   ```

   Windows (PowerShell):

   ```powershell
   if (!(Test-Path .env)) { Copy-Item .env.example .env }
   ```

   [.env.example](.env.example) содержит пустые секреты. Для Compose задайте свой локальный `POSTGRES_PASSWORD`; unit-тестам пароль не требуется. Поля и приоритет настроек описаны в [схеме окружения](docs/environment-schema.md). Настоящие значения храните только в локальном `.env` или предназначенном для них хранилище секретов; `.env` исключён из Git.

6. Выполните проверки из следующего раздела. Перед изменением файлов создайте отдельную ветку задачи от актуальной `main`, как описано в [CONTRIBUTING.md](CONTRIBUTING.md). Прямые изменения в `main` запрещены.

### Известное ограничение Windows

В [ревью PR #7](https://github.com/inte11ectua1/skinulis/pull/7#pullrequestreview-5655930834) на Windows 11 с uv 0.13.1 загрузка Python 3.12.15 завершилась ошибкой `Missing expected target directory for Python minor version link`. При этом frozen-установка, обе проверки pytest и все hooks прошли. Похожая проблема с junction описана в [upstream issue uv #19622](https://github.com/astral-sh/uv/issues/19622).

После обновления до uv 0.13.5 повторите `uv python install` и проверки ниже. На macOS установка с новой версией проверена; повторная проверка именно Windows ещё требуется, исправление ошибки не подтверждено.

```powershell
uv --version
uv python install
uv python find 3.12.15
uv sync --frozen
uv run python --version
uv run pytest
```

Если ошибка установки повторится, сохраните её полный текст и вывод `uv python dir` / `uv python list --only-installed` для диагностики. Не считайте команду установки успешной только по факту загрузки архива; результат остальных команд проверяйте отдельно.

## Проверки качества

Все команды выполняются из корня репозитория:

| Проверка | Команда |
|---|---|
| Воспроизводимая установка | `uv sync --frozen` |
| Соответствие lock-файла конфигурации | `uv lock --check` |
| Ruff lint | `uv run ruff check .` |
| Ruff format без изменения файлов | `uv run ruff format --check .` |
| mypy в строгом режиме | `uv run mypy .` |
| pytest | `uv run pytest` |
| Все pre-commit hooks | `uv run pre-commit run --all-files` |
| Совместимость установленных зависимостей | `uv pip check` |
| Известные уязвимости зависимостей из lock-файла | `uv audit --locked` |
| Поиск секретов отдельно | `uv run pre-commit run detect-secrets --all-files` |

Ruff проверяет ошибки Python, импорты, упрощения для Python 3.12 и типичные ошибки (`E4`, `E7`, `E9`, `F`, `I`, `UP`, `B`); ширина строки — 88. Для применения форматирования используйте `uv run ruff format .`. mypy обходит Python-файлы проекта в режиме `strict`, включая приложение, Alembic, скрипты и тесты; подключён официальный plugin Pydantic.

Два настоящих теста в `tests/unit/test_environment.py` подтверждают точное соответствие Python закреплённой версии и запуск внутри виртуального окружения. Они проверяют подготовку среды; продуктовые сценарии будут проверяться вместе с их реализацией.

`uv audit --locked` обращается к сервису OSV и требует интернет. В uv 0.13.5 команда экспериментальная: её предупреждение сохраняем. Успешный аудит означает отсутствие известных сервису проблем на момент проверки. [Описание команды](https://docs.astral.sh/uv/reference/cli/#uv-audit).

## pre-commit и секреты

`uv run pre-commit install` устанавливает hooks только в вашу рабочую копию. Их нужно устанавливать после каждого нового клонирования. [.pre-commit-config.yaml](.pre-commit-config.yaml) запускает проверку lock-файла, Ruff lint/format, mypy и detect-secrets через закреплённое окружение uv. Hooks проверяют файлы, известные Git; новые файлы включайте в индекс после просмотра содержимого. pytest и сетевой аудит зависимостей запускайте отдельно перед PR.

Проверка detect-secrets работает без baseline и без сетевой проверки найденных значений (`--no-verify`). Текстовый `uv.lock` тоже сканируется: отключён только фильтр, ошибочно считающий расширение `.lock` бинарным. [Документация detect-secrets](https://github.com/Yelp/detect-secrets#usage).

Если hook сообщил о подозрительном значении, проверьте файл локально, удалите секрет и повторите проверку. Опубликованный действующий секрет нужно отозвать. Не вставляйте найденные значения в issue, PR или логи и не добавляйте реальные секреты в исключения ради успешной проверки.

## Тесты и покрытие

`uv run pytest` выполняет unit-тесты и сохранённые проверки T-02. Интеграционные
тесты явно исключены выражением `not integration`; это не проверка реальной БД.
Для проверки PostgreSQL 17 установите и запустите Docker, затем выполните:

```sh
uv run python scripts/test_integration.py
```

Скрипт создаёт отдельный Compose project с временной PostgreSQL 17.11, случайным
паролем, динамическим loopback-портом и tmpfs вместо основного volume. Он проверяет
миграции на чистой БД и повторный запуск, HTTP health с реальным SELECT 1,
транзакции и отказ подключения. После выполнения удаляет только свой project.
Другие контейнеры и данные не затрагиваются. Для своей тестовой БД см.
[TEST_DATABASE_URL](docs/environment-schema.md#изолированные-тесты).

Покрытие текущего кода `app/` и `bot/` с учётом ветвей и порогом 60%
(source берётся из принятой конфигурации pyproject):

```sh
uv run pytest --cov --cov-report=term-missing
uv run python scripts/test_integration.py --cov --cov-append --cov-report=term-missing
```

Второй запуск дополняет отчёт первого проверками настоящей PostgreSQL.
Unit-прогон включает существующие денежные функции и mock-тесты каркаса бота;
он не проверяет реальный Telegram и ещё не реализованные продуктовые API.
CI и обязательные проверки относятся к T-04.
Starlette выдаёт предупреждение о будущем переходе TestClient с httpx на httpx2;
согласованный httpx пока работает, предупреждение не подавлено, новый стек не введён.

## Изменение зависимостей

Причина выбора uv описана в [принятом ADR 002](docs/adr/002-uv.md), одобренном через PR #7. T-03 добавляет FastAPI, Pydantic v2, pydantic-settings, sync SQLAlchemy, psycopg 3 (binary), Alembic и Uvicorn. L-02 добавляет aiogram 3.x и переносит существующий httpx из dev в runtime для клиента бота. Необходимое для aiogram согласование версии Pydantic и ограничения описаны в инструкции бота. Авторизация остаётся за следующими задачами.

Новую зависимость добавляйте командой `uv add <имя>` или `uv add --dev <имя>` для инструмента разработки. Просмотрите изменения `pyproject.toml` и `uv.lock`, запустите проверки и включите оба файла в один PR. Для целевого обновления используйте `uv lock --upgrade-package <имя>` и затем `uv sync --frozen`. Не редактируйте `uv.lock` вручную. Обновление Python или uv тоже оформляйте отдельным проверенным изменением закреплённых версий и инструкций.

