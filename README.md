# Скинулись

Учебный сервис совместных расходов с Telegram-ботом, FastAPI и PostgreSQL.

**O-07 merged (PR #53, проверено 31.10.2026):** ручные компенсации: POST/GET `/groups/{group_id}/settlements`,
POST `/settlements/{settlement_id}/{confirm,reject,cancel}` и `/internal` mirrors.
Создаёт verified sender, подтверждает/отклоняет receiver, отменяет sender.
Pending не меняет баланс; confirm проверяет свежий долг под group lock. После
timeout повторяйте прежние UUID/body: replay возвращает исходное pending-создание,
актуальный status читайте через GET списка. Банковский перевод происходит вне API.
[Реализация, права и гонки O-07](docs/finance/O-07_IMPLEMENTATION.md),
[typed fixtures](docs/finance/fixtures/O-07_SETTLEMENTS.json); OpenAPI `/docs`.

**O-07N #55 merged PR #57 и L-05 #48 merged PR #54:** защищённый bot-service `POST /internal/settlements/{settlement_id}/notification-claim` выдаёт одноразовое разрешение уведомить получателя (200 server-bound Telegram ID, 204 после claim/terminal/no binding). Alembic 0006 хранит отметку, миграция помечает исторические записи. Бот отправляет одну best-effort private notification **только** после 200 claim, без гарантии доставки и без банковского перевода. [Контракт](docs/contracts/T-08_PENDING_NOTIFICATION.md), [L-05 документация](docs/bot/L-05_SETTLEMENTS.md).

> **M4 завершён по реализации 31.10.2026:** [O-06 #46/PR #51](https://github.com/inte11ectua1/skinulis/pull/51), [O-07 #47/PR #53](https://github.com/inte11ectua1/skinulis/pull/53), [O-07N #55/PR #57](https://github.com/inte11ectua1/skinulis/pull/57), [L-05 #48/PR #54](https://github.com/inte11ectua1/skinulis/pull/54), [T-08 #45/PR #58](https://github.com/inte11ectua1/skinulis/pull/58) merged, Issues closed. [T-08 финальный security review](docs/reviews/T-08_M4_FINAL_SECURITY_REVIEW.md), [CI #58 5/5](https://github.com/inte11ectua1/skinulis/actions/runs/41213175596). **Следующий этап M5 Delivery** — назначены T-09 #59, T-10 #60, O-08 #61, L-06 #62. [Handoff](docs/operations/M5_DELIVERY_HANDOFF.md). Live Telegram G2/G3/G4 и production /internal isolation не verified; T-01/G1 по-прежнему open.

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

## Этапы и ближайшая работа

- **M1 Skeleton завершён по реализации:** [T-03 #10](https://github.com/inte11ectua1/skinulis/issues/10), [O-02 #11](https://github.com/inte11ectua1/skinulis/issues/11), [L-02 #12](https://github.com/inte11ectua1/skinulis/issues/12), [T-04 #13](https://github.com/inte11ectua1/skinulis/issues/13) закрыты. [CI evidence](docs/operations/CI.md).
- **M2 Identity завершён по коду:** [T-05 #21 / PR #26](https://github.com/inte11ectua1/skinulis/pull/26), [T-06 #22 / PR #27](https://github.com/inte11ectua1/skinulis/pull/27), [O-03 #23 / PR #31](https://github.com/inte11ectua1/skinulis/pull/31), [L-03 #24 / PR #28](https://github.com/inte11ectua1/skinulis/pull/28) merged, соответствующие Issues closed. Финансовая документация принята через PR #33, UTC API даты через PR #30. G2 требует отдельной проверки.
- **M3 Expenses завершён:** Олег [O-04 #36 / PR #41](https://github.com/inte11ectua1/skinulis/pull/41) и [O-05 #39 / PR #42](https://github.com/inte11ectua1/skinulis/pull/42) — expense CRUD и snapshots; Лера [L-04 #37 / PR #43](https://github.com/inte11ectua1/skinulis/pull/43) — Telegram expense UI; Тимур [T-07 #35 / PR #44](https://github.com/inte11ectua1/skinulis/pull/44) — audit и regression fixes. Issues закрыты, CI #44 зелёный. G3 не verified без отложенного live Telegram E2E.
- **M4 Balances/Settlements завершён:** O-06/PR #51, O-07/PR #53, O-07N/PR #57, L-05/PR #54 и T-08/PR #58 — merged/closed. Финансовая история, балансы, manual settlement и best-effort notifications через verified bot actor протестированы реальными HTTP/PostgreSQL и mock Telegram, не live polling.
- **M5 Delivery назначен:** Тимур [T-09 #59](https://github.com/inte11ectua1/skinulis/issues/59) (GHCR/CD/VPS/Caddy/network isolation) и [T-10 #60](https://github.com/inte11ectua1/skinulis/issues/60) (JSON логи/runbook); Олег [O-08 #61](https://github.com/inte11ectua1/skinulis/issues/61) (PG races/load 100 clients/p95), Лера [L-06 #62](https://github.com/inte11ectua1/skinulis/issues/62) (mock Telegram → HTTP/PG UX regression). O-08/L-06 могут стартовать параллельно, T-10 после T-09 infrastructure.
- **Границы:** T-01/G1 открыта, G2/G3/G4 formally not verified из-за отложенного live Telegram; G5 ещё не verified. Нет автоматического SSH/VPS/production actions без разрешения, PR jobs не получают secrets. Новые задачи: отдельная ветка → PR → CI 5/5 → independent human review → merge, полный PR body Closes #N. [Roadmap](docs/roadmaps/MASTER_ROADMAP.md), [STATUS](docs/STATUS.md).


## Telegram-бот: онбординг и группы (L-03)

`/start` читает профиль через T-06. Новый пользователь явно выбирает создание
Telegram-only профиля либо привязку API-аккаунта одноразовым кодом (10 минут).
Работают профиль, список/создание групп, участники, приглашения владельца,
отзыв и добровольное вступление по deep-link. Расходы добавляет L-04; компенсации — L-05.
Настройка `TELEGRAM_BOT_TOKEN`, отдельного `BOT_SERVICE_TOKEN`, адреса API,
команды, FSM и восстановление после timeout: [инструкция L-03](docs/bot/L-03_SETUP.md).
Запуск — `uv run python -m bot.main`, остановка — `Ctrl+C`, один polling-процесс.
Unit-тесты используют MockTransport и mocked Telegram session без настоящего токена,
сети и БД. Отдельные integration-тесты запускают настоящий локальный HTTP API
и PostgreSQL с заменой только Telegram session; это не live Telegram E2E.

## Финансовое хранилище (O-03, не CRUD)

[PR #31](https://github.com/inte11ectua1/skinulis/pull/31) добавил
SQLAlchemy 2 sync-модели `expenses`, `expense_items`, `expense_shares`,
`expense_item_shares`, `settlements` и единую миграцию
`0004_financial_domain → 0003_groups_identity`. Суммы хранятся в signed BIGINT
копейках, итоговые доли отделены от деталей позиций, FK проверяют членство,
soft-delete не уничтожает историю. [Контракт и точные ограничения](docs/finance/O-03_DATA_MODEL.md)
уточнены через [PR #33](https://github.com/inte11ectua1/skinulis/pull/33):
Q-03 Unicode/NFC — **проверка на реализованной API-границе O-04/O-05**, Q-10 сохраняет
явно выбранные нулевые доли, Q-04 использует точные SQL NUMERIC-агрегаты.
Модель БД сама не гарантирует сумму shares и бизнес-правила. Их проверяют **реализованные сервисы O-04/O-05** (права, snapshots, UUID replay, версионирование и T-07 safety checks). Балансы/план O-06 и автомат компенсаций O-07 merged. Финансовые правила обеспечивают сервисы, а не одни SQL constraints.

## Публичная аутентификация (T-05)

Реализованы JSON `POST /auth/register`, `POST /auth/login` и Bearer-защищённый
`GET /users/me`. Register возвращает 201 и профиль, login — access JWT с TTL
15 минут, me — профиль проверенного пользователя из PostgreSQL. Ошибки ввода —
400, неверные credentials/JWT — 401, занятый email — 409; все в общей error-оболочке.
Пароли хэшируются Argon2id, hash в ответах отсутствует. DTO/SQL/JWT-параметры
пока предложены на review: [контракт T-05](docs/contracts/T-05_IDENTITY.md).
Telegram bootstrap, группы и привязка описаны в разделе T-06 ниже.

Перед запуском API задайте в своём `.env` случайный `JWT_SECRET_KEY` минимум
32 bytes, отдельный `BOT_SERVICE_TOKEN` (43–128 URL-safe символов) и непустой `POSTGRES_PASSWORD`; настоящие значения в Git/команды не
вставляйте. Для **нового** `.env` можно выполнить следующий код: существующий
файл не перезаписывается, секреты не печатаются, права файла — 0600.

```sh
uv run python - <<'PY'
import os
import secrets
from pathlib import Path

template = Path(".env.example").read_text()
for name in ("POSTGRES_PASSWORD", "JWT_SECRET_KEY", "BOT_SERVICE_TOKEN"):
    template = template.replace(name + "=\n", name + "=" + secrets.token_urlsafe(48) + "\n")
with Path(".env").open("x") as stream:
    os.chmod(".env", 0o600)
    stream.write(template)
PY
```

В существующем `.env` добавьте JWT и отдельную BOT_SERVICE_TOKEN настройку безопасно в редакторе, сохранив
остальные значения. Алгоритм фиксирован HS256; `JWT_ACCESS_TOKEN_TTL_MINUTES`
при необходимости задаётся в пределах 1–60. Миграции не требуют JWT или service secret.
После запуска Compose откройте `/docs`: выполните register, затем login и
введите полученный access token в Authorize → HTTPBearer. `GET /users/me`
возвращает только actor токена; без Authorization получаете 401. Пароль передаётся
только JSON body публичному API, никогда Telegram-боту. Для проверки используйте
отдельный тестовый Compose project/БД, не production и не чужой volume.

## Группы и Telegram identity (T-06)

[HTTP/SQL контракт](docs/contracts/T-06_IDENTITY.md) описывает DTO, errors, locks,
timeout/retry и handoff O-03/L-03. Контракт утверждён
[решением Тимура в Issue #22](https://github.com/inte11ectua1/skinulis/issues/22#issuecomment-6437632203).
Это разрешение tech lead, не автоматическое личное APPROVED от Олега или Леры.
**Backend T-06 уже merged (PR #27), Telegram-клиент L-03 также merged (PR #28)**;
live Telegram E2E и production-изоляция `/internal` остаются отдельными проверками.

JWT-пользователь создаёт группу `POST /groups` с `{name,client_request_id:UUID}`,
становится owner/первым member. `GET /groups`, `/groups/{id}` и
`/groups/{id}/members` доступны только соответствующему участнику. Списки:
`{items,limit,offset}`, default20, max100, без total/has_next. Лимит30 защищён БД.
Owner выпускает `POST /groups/{id}/invites` с `{client_request_id:UUID}`;
другой JWT actor добровольно вызывает `POST /group-invites/join` с `{token}`.
Token одноразовый, TTL24h, хранится hash; raw возвращается только при первом выпуске.
Повтор участника/полная группа не расходуют token. Неизвестная/просроченная/
использованная/отозванная ссылка -> общий404 без раскрытия закрытой группы.
Owner читает все состояния приглашений через `GET /groups/{id}/invites`
(пагинация20/max100, сортировка created_at/id) и отзывает unused/expired приглашение
через `DELETE /groups/{id}/invites/{invite_id}`. Ответы — metadata без token/hash/consumer;
повтор DELETE возвращает ту же metadata, consumed ->409 без изменения. Бот использует
идентичные пути с /internal. После timeout выдачи перечитайте страницы, найдите
client_request_id; если raw token потерян, явно отзовите запись и только потом
выпустите другую с новым UUID. Восстановить секрет и автоматически выпустить новый нельзя.

У бота отдельные те же групповые операции под `/internal`, credential
`X-Bot-Service-Token` и `X-Telegram-ID` из sender update. Публичные JWT routes
не принимают служебные actor headers; смешивание каналов запрещено. Бот сначала
читает `GET /internal/users/me`;404 предлагает выбор Create/Link без записи.
Только после явного Create-согласия: `POST /internal/users/bootstrap` с `{}`.
Для привязки email-пользователь по JWT получает `POST /users/me/telegram-link-code`
с `{}`; бот передаёт code в `POST /internal/users/telegram-link` по service channel.
TTL10min, один раз, атомарно, merge уже существующих пользователей запрещён.
После timeout сначала читать профиль/список; не выпускать новую ссылку/код вслепую.

Для Swagger используйте отдельный тестовый Compose project и placeholders для
UUID, передавайте реальные тестовые секреты только в Authorize/body, не в URL.
Никогда не отправляйте пароль/JWT в Telegram. API требует отдельный service token,
миграции — нет. **В production T-09 внешний proxy обязан закрыть весь /internal**;
production-изоляция и live Telegram в T-06 не развёртываются. Клиент L-03 использует
утверждённые internal mirrors; детали проверки описаны в инструкции бота.

## Запуск API с PostgreSQL

Установите [Docker Desktop или Docker Engine с Compose](https://docs.docker.com/get-started/get-docker/)
и запустите Docker. Для локальной разработки нужны Linux containers; на Windows —
Docker Desktop с WSL2. Проверенный минимум: Engine 23.0.5, Compose 2.17.3.
Проверьте `docker version` и `docker compose version`.
Git, Python 3.12.15 и uv 0.13.5 устанавливаются по разделу ниже; для самого Docker
запуска локальная установка Python/uv не нужна — они включены в сборку образа.

После клонирования из корня репозитория создайте `.env` из `.env.example`, не
перезаписывая существующий файл, и заполните **POSTGRES_PASSWORD, JWT_SECRET_KEY, BOT_SERVICE_TOKEN** по безопасному примеру выше. Новый локальный
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
разрешает старт API. Создаются `users`, `groups/group_members`, `group_invites`, `telegram_link_codes`,
а после `0004_financial_domain` также **`expenses`, `expense_items`,
`expense_shares`, `expense_item_shares`, `settlements`**.
Расходные endpoints добавлены O-04/O-05, следующая миграция —
`0005_expense_replay_version`, затем одноразовая нотификация
`0006_settlement_notification_claim` (**актуальный единственный Alembic head**). Балансы O-06 и settlement transitions O-07 merged, без новой миграции M4.

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
Локальный Compose сохраняет API/DB без polling. Runtime-образ также содержит `bot/`;
отдельный `deploy/compose.production.yaml` запускает его с `python -m bot.main`
только в явно включённом профиле polling. [T-09 deployment runbook](docs/operations/DEPLOYMENT.md)
описывает private networks, Caddy и безопасный release controller. Реальные
SSH/VPS/Telegram действия требуют отдельного разрешения Тимура.

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
Unit-прогон включает pure money functions, тесты auth/groups и mock-тесты
Telegram FSM/client; PostgreSQL integration отдельно тестирует уже реализованный
backend и интеграцию L-03/L-04 с подменённой Telegram session. Проверяются реальные
Expense API O-04/O-05 и Telegram FSM через HTTP/PostgreSQL. Эти прогоны
**не являются live Telegram E2E** и не доказывают gate G3/G4. Новые O-06/O-07 PostgreSQL-сценарии проверяют backend на фактическом PR head; доказательства приведены в соответствующем PR.
Автоматизация этих проверок и статус защиты описаны ниже.
Starlette выдаёт предупреждение о будущем переходе TestClient с httpx на httpx2;
согласованный httpx пока работает, предупреждение не подавлено, новый стек не введён.

## GitHub Actions CI

[ci.yml](.github/workflows/ci.yml) запускается для каждого PR в main (включая новые
коммиты), push в main и ручного `workflow_dispatch`.
Нет фильтра по путям: изменение документации тоже проходит проверки.

| Job / check run | Проверка |
|---|---|
| `lint` | frozen sync, lock check, Ruff lint/format, совместимость пакетов, аудит зависимостей и detect-secrets |
| `types` | frozen sync, lock check, строгий `mypy .`, включая app, bot, тесты, Alembic и скрипты |
| `tests` | unit-тесты, затем явно `-m integration` с PostgreSQL 17.11, общее branch coverage app + bot >=60% |
| `docker-build` | сборка общего API/bot образа, non-root imports, disposable PostgreSQL/Caddy TLS smoke и raw routing negatives; без публикации/SSH/Telegram |
| `ci` | успех только если все четыре предыдущих job завершились `success`; fail/cancel/skip не принимаются |

Первые четыре job независимы; `ci` ждёт их все. Runner — Ubuntu 24.04,
Python 3.12.15 через uv, uv 0.13.5. Actions закреплены полными commit SHA,
PostgreSQL — тем же digest, что локально. Кэшируется только uv cache, с ключом
lock-файла и отдельным suffix для каждого job; `.venv`, `.env` и credentials
checkout не сохраняются. Permissions — `contents: read`; production secrets,
deploy, SSH и GHCR push отсутствуют.

В tests job используется один service-container, без второго Compose project.
Fixture создаёт для каждого integration-теста отдельную UUID-БД и удаляет только
её. Общий bootstrap `skinulis_test` остаётся до удаления service-container runner-ом.
Учётные данные в YAML — публичная тестовая заготовка исключительно для временной
БД с портом на loopback; её нельзя использовать вне CI.

CI накапливает `.coverage` командами `coverage run` и `coverage run --append`,
после обоих успешных pytest-прогонов выполняет `coverage report --fail-under=60`.
Branch/source/omit берутся из pyproject; тесты в процент не входят. XML и текстовый
отчёт хранятся в artifact 14 дней. Для локального повторения достаточно команд
качества выше, двух pytest-cov прогонов из раздела покрытия и `docker build .`.

Точные required checks, настройки main, проверка красного CI и troubleshooting:
[CI и защита main](docs/operations/CI.md). Успех workflow сам по себе не включает
branch protection; применённые настройки и доказательства фиксируются отдельно.

## T-09: production release и безопасный dry-run

[Deployment runbook](docs/operations/DEPLOYMENT.md) описывает общий API/bot image,
отдельный production Compose, Caddy HTTPS и публичный отказ `/internal`.
Локальный compose.yaml сохранён. На 01.11.2026 подготовлен новый EC2 в Sydney:
20GiB encrypted gp3, Docker/SSM, fresh keys/secrets, настоящий pinned SSH-over-SSM
и dry-run проверены. [Новый AWS evidence](docs/operations/T-09_NEW_AWS_EC2.md).
Изолированные PG/TLS/backup tests из предыдущего этапа относятся к старому EC2.
Публичный production rollout/ACME **ещё не выполнен**; Issue #59/G5 открыты.
[Исторические проверки старого EC2](docs/operations/T-09_EC2_PREFLIGHT.md).

[deploy.yml](.github/workflows/deploy.yml) публикует SHA-tag только после trusted
main CI, проверяет происхождение image и передаёт deploy **digest**. Rollout выключен
по умолчанию: нужен manual operation=deploy, repository flag и protected
production Environment с независимым approval. Polling требует отдельного флага.
PR pipeline не получает этих secrets/permissions.

Для AWS подготовлен [OIDC + SSH-over-SSM transport](docs/operations/AWS_SSM_CD.md):
временные AWS credentials, pinned ED25519 host key, отдельный deployment user,
без открытия SSH GitHub runner в интернет. Provider и отдельная role нового account
проверены по JSON из main, destination Environment обновлён с сохранением защиты.
Protected `operation=check-transport` проверяет только
подключение и Docker version с rollout flag=false; controller не запускается.
Его [реальный запуск](https://github.com/inte11ectua1/skinulis/actions/runs/41346841056)
ожидает независимого production approval; OIDC connection пока не verified.
Production rollout/HTTPS и live Telegram остаются отдельной приёмкой.

```sh
actionlint
uv run pytest tests/unit/test_release_policy.py tests/unit/test_deployment.py tests/unit/test_remote_deploy.py tests/unit/test_backup_postgres.py tests/unit/test_ssm_transport.py
docker build --build-arg APP_COMMIT_SHA="$(git rev-parse HEAD)" -t skinulis-t09-test:local .
T09_TEST_IMAGE=skinulis-t09-test:local uv run python scripts/test_delivery.py
```

Последняя команда использует свои UUID Docker networks/containers и PostgreSQL,
тестовый TLS CA и mock boundaries; настоящий Telegram не запускается. Проверяет
config, DB migration/restart, exact /version SHA, private service actor и26 raw
negative routing cases. Тестовый named volume сохраняется, чужие volumes не трогаются.
Серверный controller запускается только из установленного release bundle и по
умолчанию делает dry-run; инструкция setup/rollback и имена secrets — в runbook.
В release bundle также входит ручной `scripts.backup_postgres`: приватный custom
dump вне DB volume, проверка архива без restore и без удаления старых копий.
Автоматический график/retention не добавлены; восстановление проверять только
на отдельной тестовой БД, production restore требует отдельного разрешения.

## Изменение зависимостей

Причина выбора uv описана в [принятом ADR 002](docs/adr/002-uv.md), одобренном через PR #7. T-03 добавляет FastAPI, Pydantic v2, pydantic-settings, sync SQLAlchemy, psycopg 3 (binary), Alembic и Uvicorn. L-02 добавляет aiogram 3.x и переносит существующий httpx из dev в runtime для клиента бота. Необходимое для aiogram согласование версии Pydantic и ограничения описаны в инструкции бота. Авторизация T-05/T-06, Telegram-клиент L-03/L-04, финансовое хранилище O-03 и expense CRUD O-04/O-05 уже реализованы. Backend M4 O-06/O-07 уже merged; Telegram-клиент добавляет L-05.

Новую зависимость добавляйте командой `uv add <имя>` или `uv add --dev <имя>` для инструмента разработки. Просмотрите изменения `pyproject.toml` и `uv.lock`, запустите проверки и включите оба файла в один PR. Для целевого обновления используйте `uv lock --upgrade-package <имя>` и затем `uv sync --frozen`. Не редактируйте `uv.lock` вручную. Обновление Python или uv тоже оформляйте отдельным проверенным изменением закреплённых версий и инструкций.


## Расходы equal/custom — O-04

[Контракт и ошибки](docs/contracts/O-04_EXPENSES.md), [JSON fixtures](docs/finance/fixtures/O-04_EXPENSES.json),
[реализация и проверки](docs/finance/O-04_CONTRACT_CHECKPOINT.md). Миграция перед запуском:
`uv run python -m app.core.migrate` (явно настроенная собственная БД, без startup миграций).

Публичный клиент использует Bearer JWT. POST /groups/{id}/expenses принимает title,
split_mode, amount RUB-string и participants (equal) либо shares (custom), плюс
стабильный client_request_id UUID. Автор/плательщик берётся из проверенного actor,
его нельзя подставить в JSON. 201 — первая запись, 200 — исходный сохранённый
ответ при повторе того же нормализованного намерения/UUID даже после правок/удаления.
GET /groups/{id}/expenses и GET /expenses/{id} возвращают сохранённые доли с нулями;
список active, default20/max100, ASC(created_at,id), без пересчёта по новым members.

PUT /expenses/{id} — полная замена только автором, обязательный expected_version;
DELETE /expenses/{id}?expected_version=N — soft-delete с тем же ограничением автора.
Stale первый PUT/DELETE —409, успех повышает version. Повтор DELETE автора сохраняет
прежний tombstone/version. Все мутации возвращают {expense,balances}; при confirmed
балансы точно пересчитываются, без confirmed допустим null. Confirmed не изменяются.

POST /groups/{id}/expenses/preview проверяет тот же business body без UUID/version,
считает доли только сервером, ничего не пишет/не резервирует. После изменения
черновика клиент инвалидирует preview; POST повторно проверяет данные под lock.
Все шесть операций имеют /internal mirrors с существующим T-06 service actor;
публичный и служебный каналы не смешиваются. Бот не считает split и не ходит в БД.

После POST timeout повторять прежний UUID/исходное намерение, затем GET для
актуального экрана. После PUT timeout сначала GET/проверка version и snapshot;
не отправлять старую правку вслепую. DELETE можно повторить с прежним N.

## O-05: ресторанные чеки by_items

Принятый [контракт O-05](docs/contracts/O-05_BY_ITEMS.md) расширяет прежние public/internal
операции третьим split_mode=by_items. Вместо root amount передаются items с title,amount,
participants; сервер рассчитывает per-item и final shares с нулями. Ответы by_items
содержат items, equal/custom сохраняют прежний JSON без items. Все full-PUT переходы
разрешены с expected_version; original POST replay хранит исходные позиции/порядок.
[Fixtures](docs/finance/fixtures/O-05_BY_ITEMS.json); решение Тимура в Issue39/6473059675.

## Telegram-мастера расходов — L-04

В личном чате: «Мои группы» → группа → «Добавить расход» → equal/custom/by_items.
Бот собирает строки/состав/позиции, запрашивает серверный предпросмотр и сохраняет
только после подтверждения. Custom допускает выбранные `0.00`, by_items — 1–50
позиций без отдельного общего amount. Любая правка требует нового preview.
«Расходы» открывает список/детали; автор может пройти полный мастер редактирования
со сменой режима или подтвердить soft-delete с предупреждением о confirmed.

POST retry сохраняет UUID/исходный body, PUT timeout сначала перечитывает версию,
DELETE повторяет прежний target/version. Бот не считает деньги, не имеет DB и
не запрашивает JWT/пароль. Все `/internal` mirrors используют принятый T-06 actor.
[Инструкция L-04, FSM, ошибки, тесты и ограничения](docs/bot/L-04_EXPENSES.md).
Настройки запуска остаются из L-03. Live Telegram и ручные проверки с настоящим
ботом отложены до отдельного разрешения Тимура; G3 этим PR не объявляется verified.

## O-06: read-only balances и settlement-plan

GET /groups/{id}/balances возвращает signed RUB balances всех members, включая нули.
GET /groups/{id}/settlement-plan возвращает deterministic greedy transfers, не создаёт
settlements. Оба имеют /internal mirrors. [Реализация/MVCC](docs/finance/O-06_IMPLEMENTATION.md),
[контракт T-08](docs/contracts/T-08_M4_BALANCES_SETTLEMENTS.md).


## Telegram-балансы и ручные переводы — L-05

Группа → «Балансы» → «План переводов» → «Я перевёл деньги»: выберите другого
участника, введите фактически отправленную сумму и подтвердите внешний перевод.
API создаёт pending без изменения баланса. Получатель подтверждает только реально
полученные деньги или отклоняет; отправитель отменяет свою pending-заявку.
Confirmed учитывается один раз, rejected/cancelled не влияют на баланс.

История поддерживает серверные фильтры/пагинацию20. После confirm бот перечитывает
балансы и план. Повтор POST сохраняет UUID/body, затем читает текущий статус:
исторический pending replay не выдаётся за актуальный. После timeout перехода
сначала читается список; разрешён только явный повтор того же действия.

[Инструкция L-05, роли, FSM, ошибки и тесты](docs/bot/L-05_SETTLEMENTS.md).
После create/recovery бот запрашивает одноразовый notification-claim из merged
O-07N #57. Только200 разрешает одну приватную попытку уведомить получателя;
на204/error/timeout отправки нет. Сбой доставки не меняет pending/балансы и не
повторяет финансовый POST. Доставка не гарантируется; входящие доступны через меню.
[Контракт, проверки и ограничения уведомлений](docs/bot/L-05_NOTIFICATION_DEPENDENCY.md).
Настройки запуска прежние, финансовая математика остаётся на API. Бот не переводит
деньги. Live Telegram и ручное тестирование реальных пользователей запрещены
до отдельного разрешения Тимура. G4 не объявляется verified.
