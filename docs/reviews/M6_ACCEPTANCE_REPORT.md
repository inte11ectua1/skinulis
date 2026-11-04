> **Актуализация 04.11.2026.** PR #85 merged; main/release `c9ec9ce`, protected Release41836839608 success с polling input=true. Владелец подтвердил ответы production-бота и новый UI; меню настроено через BotFather. Свежий подсчёт процессов/контейнеров и revision БД NOT VERIFIED: AWS login истёк. Это не прежний POLLING OFF и не полная учебная приёмка. Ниже сохранён датированный исходный срез/общий runbook; его прежние статусы не переносятся на04.11.
> [Текущий аудит и границы доказательств](POST_RELEASE_AUDIT_2026-11-04.md).

# M6 Acceptance — техническая приёмка и открытые критерии

**Первоначальный аудит до финального deployment: 03.11.2026, Europe/Moscow. Ответственный: Тимур. Issue [#79](https://github.com/inte11ectua1/skinulis/issues/79). Итог: PARTIALLY, G6 не закрыт.**
Это проверка всего приложения, не только наличие документации. Полный DoD ещё
не принят: исторические review/protection и формальное соответствие логирования
требуют решения; performance500ms из ТЗ курса не достигнут. Live Telegram,
окончательная выкладка и репетиция не выполнены.
Ни согласие владельца с M5, ни green CI не являются исключением преподавателя.

**PR M6: [#81](https://github.com/inte11ectua1/skinulis/pull/81) · [required checks текущего head](https://github.com/inte11ectua1/skinulis/pull/81/checks).**
Запрошенный review не равен APPROVED; Issue #79 не закрывается.

> **POST-DEPLOY актуализация 03.11.2026:** PR81 merged; Release41591582318
> действительно deploy, production version=`7aa7c14`, main CI5/5. Полный новый
> [POST_DEPLOY_REPORT](POST_DEPLOY_REPORT.md) имеет итог NOT READY: один routing
> negative case unexpected empty200. Последующий read-only follow-up подтвердил
> containers/DB/migrations/image/volumes/logs и POLLING OFF; runtime VERIFIED.
> Ниже сохранён первоначальный аудит до этого deployment, включая старые SHA;
> он не является доказательством нового deployment. Formal DoD gaps остаются.

## 1. Границы, версии и источники доказательств

- Baseline `main`: [638a976](https://github.com/inte11ectua1/skinulis/commit/638a97616e6d408dda0647fe08a8ebc74657c1ba), PR #77/#78 merged.
- [Main CI #41541471109](https://github.com/inte11ectua1/skinulis/actions/runs/41541471109): **lint/types/tests/docker-build/ci — 5/5 success**.
  Из самого лога tests: 1278 unit +446 PostgreSQL integration =1724, combined branch **94.98%**, порог60%.
- [Release #41542597809](https://github.com/inte11ectua1/skinulis/actions/runs/41542597809): success, публикация, **не deploy**.
  GHCR digest `sha256:7140db7b9d920078f12f1f8223457fc5ef52082b4c4bb998bbccadf4797e2b39`.
  Анонимно получены manifest/config, их SHA256 пересчитаны; linux/amd64,
  OCI revision полный `638a97616e6d408dda0647fe08a8ebc74657c1ba`, non-root skinulis.
- Production read-only **https://3-25-53-31.sslip.io**: `/version` =
  `f7020cda3908d7e0c40c0b0f840e322b3d6cfda5`, **отличается от main**.
- [Первый approved deployment](https://github.com/inte11ectua1/skinulis/actions/runs/41428440222),
  [подробное историческое evidence](../operations/T-09_FIRST_PRODUCTION_ROLLOUT.md).
- Официальный DoD взят из [курса, immutable срез](https://github.com/andrey-limasov/app-conf/blob/8bff1a6f4d01f5417aeae4fa424e3f577085105c/definition-of-done.md).
  Номера L ниже — строки этого файла, включая вложенные требования и defense checklist.
  Тексты критериев сокращены своими словами; статус относится к указанному evidence.
- [Машинное evidence M6](M6_ACCEPTANCE_EVIDENCE.json), [полный аудит PR](M6_PR_REVIEWS.md),
  [USER_GUIDE](../USER_GUIDE.md), [3-user smoke/demo](M6_THREE_USER_DEMO.md).

Среда: настоящий MacBook, macOS15.3.2/arm64, Python3.12.15, uv0.13.5,
Docker Engine23.0.5/Compose2.17.3. PostgreSQL17.11 из закреплённого official image.
Новые тестовые credentials генерировались в памяти; `.env` оператора не перезаписан.
В JSON evidence публичные Git IDs нормализованы префиксами `git:`/`git-blob:`;
это обозначение идентификаторов, не буквальная строка `commit_sha` HTTP-ответа.
Нет AWS-операций, production migrations/deploy, изменения protection/secrets,
нагрузки production, live Telegram или отправки реальным пользователям.

Статусы: **PASS** — указана выполненная проверка; **FAIL** — обнаружено несоответствие;
**BLOCKED** — нужно внешнее действие/разрешение; **NOT VERIFIED** — доказательства
недостаточно. Историческое evidence явно датировано и не выдаётся за свежий SSH-аудит.

## 2. Полная матрица официального DoD

Владелец устранения всех проектных строк — **Тимур** (единая #79); там, где нужны
участник/преподаватель, он получает подтверждение, но не подменяет его своим решением.
Исходники в таблице — пути в этом репозитории; проверки выполнены на указанном SHA.

| DoD / строка | Проверяемый критерий | Статус | Evidence / оставшееся действие |
|---|---|---|---|
| 1 L16 | Публичность репозитория | PASS | REST repo `private=false`, GitHub доступен анонимно |
| 1 L17 | Качество истории в целом | FAIL | Change commits осмысленные, но literal Conventional не выполнен для начального seed, см. L18 |
| 1 L18 | Conventional сообщения | FAIL | Все non-merge кроме начального `Initial commit` имеют тип; seed не Conventional. Историю не переписывали, formal оценка у преподавателя; merge messages GitHub системные |
| 1 L19 | Отсутствие пустых wip/fix/test сообщений | PASS | Проверен `git log --no-merges`; таких сообщений нет |
| 1 L20 | История без секретов/мусора | PASS |655UTF-8 blobs main (9.38MB) проверены detect-secrets без network verification;3сигнала — public SSM package SHA256, подтверждены installer. По путям нет .env/.venv/cache/key; current hooks чисты |
| 1 L21 | Реальная стратегия веток | PASS | ADR001, CONTRIBUTING, feature→PR→main, история first-parent |
| 1 L22 | В main только PR | PASS | Все47 изменений first-parent после initial seed сопоставлены merged PR; это факт истории, не технический запрет admin push |
| 1 L23 | Независимый APPROVED каждого merged PR | FAIL | **37/48** merged PR без pre-merge human APPROVED; реестр по каждому PR ниже/в отдельном файле |
| 1 L24 | Правильный ignore | PASS | .gitignore + git path audit; env/cache/coverage/local evidence не tracked |
| 1 L25 | CONTRIBUTING | PASS | GitFlow/review/commit/test/contact правила присутствуют |
| 2 L31 | Config отделён от поведения | PASS | app/config.py, bot/config.py, pydantic Settings; тесты secrets/config |
| 2 L32 | Runtime-настройки через env | PASS | Settings + Compose interpolation; замена тестовых env и clean start |
| 2 L33 | Валидирующий settings layer | PASS | pydantic-settings, SecretStr, hide_input_in_errors; negative tests |
| 2 L34 | Секреты вне Git | PASS | Current hooks +655historical text blobs; credential findings нет после разбора3public digest false positives. Это результат эвристического сканирования, не математическое доказательство |
| 2 L35 | Безопасный env template | PASS | .env.example, пустые credentials, новые случайные значения в тестах |
| 2 L36 | Dev и prod конфигурации | PASS | compose.yaml отдельно от deploy/compose.production.yaml, environment-schema |
| 2 L37 | Автоматический secret hook | PASS | .pre-commit-config.yaml detect-secrets; all-files и CI lint |
| 3 L43 | Рабочий Dockerfile | PASS | Настоящий build в clean Compose, image imports non-root |
| 3 L44 | Оптимизация image | PASS | Следующие три строки + Docker build evidence |
| 3 L45 | Multi-stage | PASS | uv/builder/runtime stages, dev зависимости не устанавливаются в runtime |
| 3 L46 | Слои зависимостей | PASS | Lock/config COPY до исходников, BuildKit uv cache |
| 3 L47 | Non-root процесс | PASS | UID10001, проверка Docker image import smoke |
| 3 L48 | Local Compose | PASS | Проверен compose.yaml; новый уникальный project и volume |
| 3 L49–51 | Состав: API + PostgreSQL | PASS | API/Uvicorn и PostgreSQL20.11 реально запущены, migrate отдельный |
| 3 L52 | Необязательные дополнительные сервисы | PASS | Redis/прочие не нужны, стек не расширялся |
| 3 L53 | Cold start одной Compose-командой | PASS | `up --build -d`, пустая db, startup migration exit0, затем API; без ручного create_all |
| 3 L54 | Доступный loopback API | PASS | Случайный свободный 127.0.0.1 порт, реальные HTTP/auth/финансовые запросы |
| 3 L55 | Первичная миграция БД | PASS | `0006_settlement_notification_claim`; integration повтор upgrade, check, один head |
| 4 L61 | GitHub Actions pipeline | PASS | .github/workflows/ci.yml и живой main run |
| 4 L62 | Каждый PR в main запускает CI | PASS | pull_request main + synchronize по умолчанию; текущий M6 PR отдельно проверяется |
| 4 L63 | Все категории CI | PASS | lint/types/tests/docker-build/ci, trusted Release отдельно |
| 4 L66 | Lint | PASS | Ruff check, local и main CI |
| 4 L67 | Format | PASS | Ruff format --check, сохранён согласованный аналог black |
| 4 L68 | Types | PASS | mypy strict на всём проекте, включая bot/tests/scripts |
| 4 L71 | Автотесты | PASS | pytest unit и явный `-m integration` |
| 4 L72 | Изолированные тесты | PASS | UUID-БД fixture, disposable Docker project, synthetic env |
| 4 L73 | Настоящий PostgreSQL service | PASS | CI service PG17.11; локальный runner с тем же pinned image, не SQLite |
| 4 L74 | Coverage минимум60% | PASS | Combined branch app/bot/skinulis_logging, tests исключены; exact результаты в §3 |
| 4 L77 | Сборка контейнера | PASS | CI docker-build и локальный Compose build |
| 4 L78 | Реальная registry publication | PASS | GHCR anonymous metadata/digest audit, trusted main Release success |
| 4 L79 | Версионный image tag | PASS | Полный40hex SHA tag, immutable deploy digest и OCI revision проверены |
| 4 L81 | Green pipeline | PASS | Main CI5/5, publish success; CI M6 PR по ссылке в его описании |
| 4 L82 | Red CI запрещает merge | FAIL | Required5 checks strict/app_id15368 есть, но enforce_admins=false и rulesets=[]; универсальной блокировки нет |
| 5 L88 | Серверное приложение | PASS | Public API отвечает; первичный approved EC2 deployment evidence02.11 |
| 5 L89 | Публичная доступность | PASS | Свежие HTTPS GET health/version/docs/OpenAPI |
| 5 L90 | Reverse proxy | PASS | Caddy deployment evidence + свежие proxy404 на internal |
| 5 L91 | Доверенный HTTPS | PASS | Default CA verification, TLS1.3, LE YE2/SAN hostname; срок в §5 |
| 5 L92 | Server env вне кода | PASS | Protected production.env в rollout evidence; содержимое заново не читали/не меняли |
| 5 L93 | Автоматизированный deploy | PASS | Существующие release guard/controller + successful protected rollout, не новый запуск M6 |
| 5 L94 | Restart policy | PASS | production Compose unless-stopped; restart/persistence smoke в изоляции. Свежий reboot production не выполнялся |
| 6 L100 | Структурированные логи / выбранная библиотека | BLOCKED | JSON stdout проверен; реализован stdlib logging вместо перечисленных structlog/loguru. Нужно явное подтверждение преподавателя об эквивалентности либо отдельно согласованная правка |
| 6 L101 | Состав событий | FAIL | Timestamp/level/request_id/route есть; user context отсутствует намеренно, см. L105 |
| 6 L102 | Время события | PASS | UTC ISO Z, unit/integration logging и live response correlation |
| 6 L103 | Уровень | PASS | JSON level, тесты нормализации уровней |
| 6 L104 | Correlation ID | PASS | Server-generated request_id, X-Request-ID, безопасная error envelope |
| 6 L105 | Контекст endpoint и пользователя | FAIL | Route template есть; actor/user поля запрещены нынешним privacy allowlist. Не добавлять IDs без согласования; Тимур + преподаватель решают формальную приемку |
| 6 L106 | Health endpoint | PASS | GET /health реально выполняет SELECT1 |
| 6 L107 | Healthy HTTP200 | PASS | Local Compose и внешняя production проверка |
| 6 L108 | Проверка DB connection | PASS | Real PG и unavailable→503 integration; production database=ok |
| 6 L109 | Сбор/сохранение логов | PASS | Docker json-file, max-size5m/max-file3/compress=true; реальный delivery smoke |
| 6 L110 | Базовый просмотр событий | PASS | Incident runbook docker compose logs, JSON privacy/rotation tests; historical server audit |
| 7 L117 | README: суть продукта | PASS | README начало |
| 7 L118 | README: стек | PASS | Требования, версии Python/uv/PostgreSQL и архитектура |
| 7 L119 | README: local startup | PASS | Команды реально повторены на отдельном project |
| 7 L120 | README: deployment | PASS | Ссылка на DEPLOYMENT/runbook и оговорки protected rollout |
| 7 L121 | README: API usage | PASS | Swagger/OpenAPI + JSON examples/контракты |
| 7 L122 | README: участники | PASS | Тимур/Олег/Лера, ответственность |
| 7 L125 | CONTRIBUTING: Git | PASS | GitHub Flow, feature branch, PR |
| 7 L126 | CONTRIBUTING: сообщения | PASS | Conventional Commits |
| 7 L127 | CONTRIBUTING: review | PASS | Independent approval и явно раскрытый admin bypass, не доказательство всех approvals |
| 7 L128 | CONTRIBUTING: тестирование | PASS | uv/Ruff/mypy/pytest/PG/coverage/build команды |
| 7 L129 | CONTRIBUTING: связь с командой | PASS | Прямые GitHub handles/роли и issue/PR каналы в CONTRIBUTING (дополнено M6) |
| 7 L132 | Генерация OpenAPI | PASS | /docs + /openapi.json200, FastAPI explicit DTO |
| 7 L133 | Все операции описаны | PASS |53 operations, summary/typed params; M6 исправляет отсутствующие schema examples, regression test |
| 7 L134 | Примеры входов/выходов | PASS | M6: запросы и success examples разрешаются через refs для53operations; money DTO примеры валидируются без изменения wire behavior |
| 7 L137 | Минимум два ADR | PASS | ADR001 GitHub Flow и ADR002 uv, оба accepted через PR |
| 7 L138 | Полная структура ADR | PASS | Следующие4строки проверены в обоих файлах |
| 7 L139 | ADR: проблема | PASS | Разделы контекста |
| 7 L140 | ADR: принятое решение | PASS | Отдельные решения с границами |
| 7 L141 | ADR: причины | PASS | Альтернативы, обоснование выбора |
| 7 L142 | ADR: последствия | PASS | Плюсы/минусы/риски; исторические open чекбоксы не подменяют acceptance |

### Дополнительный обязательный defense checklist

| Строка | Контроль | Статус | Evidence / что ещё нужно |
|---|---|---|---|
| L156 | Cold Compose | PASS | §3 и isolated smoke |
| L157 | Полный test suite | PASS | §3, main и M6 CI |
| L158 |60% в test job | PASS | main `tests`94.98%; имя tests, а не переименование ради текста курса |
| L159 | Green CI/CD | PASS | CI/publish links §1; rollout отдельно approved исторически |
| L160 | Public URL | PASS | Свежий read-only HTTPS200 |
| L161 | Healthy endpoint | PASS |200 с database=ok |
| L162 | Полнота README | PASS | Матрица7 + исправление устаревшей M6 очереди |
| L163 | ADR count | PASS |2 принятых ADR |
| L164 | Презентация7мин | NOT VERIFIED | M7 #80, не создана в M6 |
| L165 | Пятиминутный demo script | PASS | M6_THREE_USER_DEMO; live rehearsal/доступность bot отдельно не проверены |
| L166 | Готовность отвечать всей команды | NOT VERIFIED | Нужна репетиция Тимура/Олега/Леры в M7 |

### Дополнительная сверка обязательного ТЗ курса

[project-requirements.md, тот же immutable срез](https://github.com/andrey-limasov/app-conf/blob/8bff1a6f4d01f5417aeae4fa424e3f577085105c/project-requirements.md)
тоже является официальным источником. **Расхождение с M5 handoff:** там waiver500ms
назван внутренним, но строки148–149 ТЗ прямо задают эту latency/concurrency норму.
По иерархии START_HERE решение владельца о закрытии #76 не изменяет требование курса.
Это не повод переписывать исторические измерения или объявлять waiver преподавательским.

| ТЗ / строки | Проверка | Статус | Evidence / граница |
|---|---|---|---|
| L27–33 / L300 | Бизнес CRUD | PASS | Expense POST/list/detail/PUT/soft-DELETE, real HTTP/PG + Compose |
| L48–54 / L301 | Auth/permissions | PASS | Register/login/JWT, owner/author/receiver; admin-edit-all лишь опциональный пример курса |
| L60–63 / L302 | Validation/uniqueness/FK | PASS | Pydantic400, email/group uniqueness, PG FK/restrict/race tests |
| L69–73 / L303 | PG/ORM/migrations/связи/индексы | PASS | PG17, sync SQLAlchemy,6Alembic revisions,11таблиц и PK/FK/index tests |
| L79–86 / L304 | Ошибки и logging | PASS | Глобальная error envelope400/401/403/404/409/500, privacy/correlation tests; formal actor logging gap отдельно |
| L96–104 | Стек | PASS | Python3.12/FastAPI/PG17/Alembic/Docker/Actions/pytest/Ruff/mypy |
| L138–140 | OpenAPI/docs/examples | PASS |53operations после M6 regression fix |
| L148 |95% запросов ≤500ms | **FAIL** | O09 p95 956.05/1098.46ms; нужно исправление с повторным измерением либо явное решение преподавателя |
| L149 |100concurrent connections | PASS |100independent clients, peak100,0HTTP500 после O09; ограниченный локальный тест, не AWS-SLA |
| L150 | Default pagination20 | PASS | DTO/query defaults, tests lists/filter/offset |
| L154–157 | Password hash/JWT/env/SQL safety | PASS | Argon2id, exp/HS256/claims, SecretStr, parameterized ORM; security regressions |
| L158 | CORS | PASS | CORSMiddleware не включён, cross-origin browser access по умолчанию не разрешён; Swagger same-origin, bot не браузер. Не заявляем поддержку стороннего web frontend |
| L162–166 / L320–321 | Test isolation/coverage/quality | PASS | Полный unit/PG набор, combined branch>60%, Ruff/mypy |
| L170–172 | Конфигурация и значимое состояние | PASS | Env Settings, финансовая история в PG; transient draft в bot memory не считается ledger |
| L308–314 | Инфраструктурный checklist | FAIL | Детальная DoD matrix выше: history/reviews/protection/logging formal gaps не закрыты общим greenCI |
| L318–319 | Структура/антипаттерны | PASS | Bounded review + тесты: routers/services/DTO, sync request Sessions, integer money, bot толькоHTTP; не абсолютное доказательство отсутствия всех дефектов |
| L325–327 | Live demo/команда/ADR | NOT VERIFIED |2ADRесть, offline script готов; live rehearsal и Q&A пока не подтверждены |

Указанные в учебных этапах ADR003/межкомандные практики не объявляются выполненными
наличием только ADR001/002; если преподаватель принимает также каждый учебный артефакт,
Тимуру нужно сверить свою ведомость практик. В опубликованном DoD минимальный ADR count2
выполнен, но это не автоматическая сдача всех занятий.

## 3. Выполненные проверки

### Frozen / quality / dependency checks

```sh
uv sync --frozen
uv lock --check
uv run ruff check .
uv run ruff format --check .
uv run mypy .
uv run pre-commit run --all-files
uv pip check
uv audit --locked
```

Baseline M6 и commit после исправления OpenAPI прошли все команды; PR CI проверяет текущий head.
История baseline main дополнительно просканирована по содержимому:655unique blobs,
все UTF-8,9378687bytes. Detect-secrets default plugins, verification network filter
выключен (никакие найденные строки сторонним сервисам не передавались);3hex-сигнала
в старых test_ssm_transport.py совпали с публичным SHA256 SSM plugin installer.
Текущие проверки/CI не ослаблялись. Deleted/unreachable objects вне baseline main
не объявляются проверенными; ограничения эвристического scanner сохраняются.

Проверка audit:72 пакета, известных уязвимостей не найдено; experimental warning
не подавлен. Версии/lock/порог/CI не ослаблены.

### Unit, PostgreSQL, combined branch coverage

```sh
uv run coverage run -m pytest
uv run python scripts/test_integration.py --cov=app --cov=bot --cov=skinulis_logging --cov-branch --cov-append --cov-report= --cov-fail-under=0
uv run coverage report --precision=2 --fail-under=60
```

Первый полный baseline прогон: **1278 unit +446 integration, 94.98% branch coverage**.
`--cov-fail-under=0` применяется только промежуточному запуску для объединения данных;
обязательная следующая команда проверяет60%. Unit/integration не подменены mocks БД;
фильтр по умолчанию `not integration` компенсирован явным runner.
**Итог после M6 examples (code commit `65042cc`):1280unit +446PGintegration =1726passed;
combined branch coverage app/bot/skinulis_logging — 95.00%.**
Frozen/lock/Ruff/format/strict mypy(147sourcefiles)/pre-commit/pip check/audit прошли.
Starlette/httpx deprecation warning сохранён, проверки не отключались.
Ссылки на required CI актуального PR head — в описании PR.

### Clean Compose и настоящие HTTP-сценарии

Выполнено на baseline main и повторено на commit с M6 OpenAPI examples. В каждом случае
новый `skinulis-m6-<random>` project, env только из памяти (`--env-file /dev/null`),
свободный loopback порт, пустой named volume. Команды:

```sh
docker compose --env-file /dev/null -p <unique-test-project> -f compose.yaml config --quiet
docker compose --env-file /dev/null -p <unique-test-project> -f compose.yaml up --build -d
docker compose --env-file /dev/null -p <unique-test-project> -f compose.yaml ps -a
# real GET /health, /version; auth/groups/finance requests from table §4
# psql: SELECT version_num FROM alembic_version
# docker compose ... logs --no-color --no-log-prefix api migrate
# docker compose ... down  (NO -v)
```

Env names: APP_ENV=test, POSTGRES_DB/USER/PASSWORD, JWT_SECRET_KEY, BOT_SERVICE_TOKEN,
API_PORT, APP_COMMIT_SHA. Credentials/токены не печатались. `up --build` действительно
собрал runtime image, db healthy, migrate exited0, API отвечает; revision0006.
В момент ps API healthcheck ещё `starting`, HTTP health200 уже проверен —
не выдаём этот ps за завершённый Docker healthcheck. Никаких чужих контейнеров нетронуто.
Тестовые volumes **сохранены**; команды удаления volumes не выполнялись.

Дополнительно локально выполнен штатный isolated delivery smoke:

```sh
T09_TEST_IMAGE=skinulis-ci:<full-built-source-sha> T09_EXPECTED_SHA=<same-sha> uv run python scripts/test_delivery.py
```

PASS: image/non-root, private ports, topology, DB restart сохраняет профиль,
настоящий изолированный Caddy TLS,26negative routing cases, internal actor,
JSON UTC/correlation/privacy и Docker rotation5m×3. Polling не запускался.
Первая попытка с тегом `skinulis-api:local` корректно отвергнута guard до запуска;
повтор выполнен с разрешённым CI tag того же собранного image.

## 4. Финансовый QA и offline Telegram

| Проверка | Фактический результат | Проверяющий набор |
|---|---|---|
| Копейки/остатки |100/3→33.34/33.33/33.33;0.01/3→0.01/0/0; порядок ID детерминирован | unit splits/money + expense_api точные границы; отдельный Compose smoke100/3 |
| Custom/нули |10→0/3.33/6.67, несовпадение400, нулевые выбранные доли сохраняются | expense_api/by_items_storage, Compose |
| Ресторан/позиции |3200, доли1000/1400/800, без двойного учёта item_shares | by_items_storage, bot_ux_e2e, Compose |
| Баланс/план |2200/-1400/-800, сумма0, рекомендации1400/800 | balances_api, independent ledger oracle O08, Compose |
| Partial/pending |500pending не меняет ledger; confirm→1700/-900/-800 | settlements_api/bot_settlements, Compose |
| Terminal/права |reject/cancel без эффекта, wrong receiver403, повтор confirm один эффект | settlements_api, notification_claim, Compose |
| Изменение после confirmed |equal3000→1500/-500/-1000; удаление→-500/500/0, confirmed неизменён | expense_api/settlements_api, Compose |
| UUID/version |Original replay без дубля, другой body409, stale version409 | expense_api, реальные TCP lost-response O08, Compose |
| Races |Overlap independent connections: sameUUID, full-debt confirm, confirm-vs-write, group-first, invite/link races | settlements_api/expense_api/groups_identity/O08/O09 |
| Isolation/rollback |Cross-group404, actor spoof400/401/403, trigger-failure atomic rollback, whole RR snapshot | соответствующие PG integration tests |
| Telegram вертикаль |Согласие/bootstrap/link, две ссылки, три режима, partial/terminal/error recovery | test_bot_ux_e2e + recovery + bot_settlements, настоящий Uvicorn/PG, только Telegram mocked |
| Connection lifecycle |19O09 regression cases, pool1 и12parallel readers, caller transaction не закрывается auth | test_o09_pool_lifecycle |

Сценарий пользователя и все ожидаемые суммы — в [USER_GUIDE](../USER_GUIDE.md) и
[3-user demo](M6_THREE_USER_DEMO.md). Реальные Telegram updates/доставка уведомлений
не проверены: **G2/G3/G4 live = NOT VERIFIED**, запуск требует отдельного разрешения.
Скриншоты Telegram не подделывались. Mock отправляет только в AsyncMock session.

### Найдено и исправлено в M6

1. OpenAPI описывал DTO, но у20success responses и8request bodies (включая `{}`)
   не было явных примеров, разрешаемых из schemas. Новый test сначала **FAIL** на
   старом коде. Добавлены только `json_schema_extra` в system/groups/expenses/
   settlements DTO; `extra=forbid`, validators, маршруты, денежные значения и права
   сохранены. После fix53operations имеют примеры. Второй тест валидирует точные
   expense examples/JSON roundtrip и сумму долей10000kopecks. Новых библиотек нет.
2. START_HERE/README/STATUS/roadmap продолжали требовать создание отдельных M6
   задач после уже созданной единой #79. Обновлены актуальные разделы; датированные
   M5 handoff и исторические записи не переписаны как будто M6 уже был принят.
3. Новых runtime/финансовых дефектов в выполненном наборе не обнаружено. Это
   ограниченный результат проверок, не доказательство отсутствия всех возможных багов.

### Нагрузочный аудит

[O08/O09 methodology](../operations/LOAD_TEST_M5.md),
[O09 raw aggregates](../operations/O-09_LOAD_RESULTS.json) повторно сопоставлены с
runner и отчётом.100 независимых клиентов, closed loop, barrier,10s warmup/30s
measurement, seed6108,80%read/20%write; mixed20groups×5, contention1group×5.
Errors включены в latency, nearest-rank percentiles, RPS включает drain; pool
metrics включают warmup, их нельзя сравнивать только с measured500.

Same-host O09 после lifecycle fix: mixed3876/3876success,126.92RPS,p95**956.05ms**;
contention3680/3680success,120.24RPS,p95**1098.46ms**; HTTP500/pooltimeouts=0.
**Performance500ms FAIL**, владелец снял blocker закрытия #76, однако норма есть
в официальном ТЗ курса L148. Преподавательского исключения нет; это не AWS capacity claim. Baseline Олега на Windows и
same-host Mac before/after — разные стенды, их absolute latencies не смешиваются.
Не измерялись Argon2/register, все UX и открытая arrival-rate нагрузка; один worker,
растущие данные и локальная VM ограничивают переносимость. Новая production нагрузка
не выполнялась. Group locks/RR/safety не ослаблялись; residual queue/CPU требует
отдельного профилирования, а не предположения, что единственная причина — GIL.

## 5. Production и безопасный следующий rollout

Свежий внешний read-only клиент с default CA/SNI: health200/databaseok, version200
со старым SHA, docs200/OpenAPI200 (41paths,53operations). TLS1.3, Let's Encrypt YE2,
SAN `3-25-53-31.sslip.io`, сертификат02.11.2026–31.01.2027.
`/internal`, `/internal/`, `/%69nternal/users/me`, `/%2569nternal/users/me`,
`/internal%2fusers/me`, `//internal/users/me`, `/x/../internal/users/me` →404.
Это7URL probes, не свежая полная security оценка всех возможных encoding bypasses;
полные26raw routing probes выполняются изолированным delivery smoke.

Environment production повторно прочитан: Oleg/Lera reviewers, prevent_self_review=true,
can_admins_bypass=false, protected_branches=true. **Это отдельная защита deployment**,
она не устраняет admin bypass у main. Repository rollout flag прочитан: **false**,
не менялся. Состояние live процессов/SG/volumes/roles на EC2 заново по SSH не
инспектировалось; соответствующие данные — историческое evidence02.11, текущий
публичный health доказывает подключение к БД, но не port-scan или отсутствие bot process.
Ни одного polling-процесса эти проверки не запускали.

**План одного финального rollout, не выполнен в M6:**

1. Независимый review и5/5CI M6 PR; merge делает человек. После merge заново
   определить текущую main, дождаться её trusted CI и Release publish; не использовать
   `638a976` автоматически, если main изменилась. Проверить OCI revision/amd64/digest.
2. Тимур отдельно разрешает deployment без polling. Read-only проверить account/
   instance/region, DNS/IP, private ports, env presence, volumes, encrypted backup,
   runtime/admin separation; не менять секреты или volumes ради прохождения checks.
3. Свежий штатный backup, list/SHA256 и isolated restore; database-only dump не
   содержит cluster roles/passwords/ownership ACL, recovery keys хранить отдельно.
   Не восстанавливать поверх production и не выполнять downgrade.
4. Только по новому разрешению временно flag=true и Release из trusted main:
   operation=deploy, полныйsha, enable_polling=false, rollback_compatible=false.
   Дождаться независимого Environment approval, не заменять workflow ручным SSH.
5. Проверить exact deployedSHA/digest, DB health/revision и migrate exit0,
   validHTTPS/redirect/docs/OpenAPI, `/internal` raw/encoded deny, private API/PG,
   JSON/privacy/rotation, отсутствие polling/OOM/restart loops; сохранить evidence.
6. Новый encrypted backup после миграций и isolated restore; вернуть flag=false
   даже при неудаче. При несовместимой схеме остановиться, не делать destructive rollback.

Production API уже доступен, но **проект ещё не готов объявлять обновлённым или полностью
принятым**. Техническую подготовку финального API rollout можно начинать после human
review/CI; само выполнение остаётся отдельным действием. Полное formal DoD требует
дополнительных подтверждений ниже.

## 6. Открытые действия и M7

| Действие | Кто нужен | Почему не закрыто в M6 |
|---|---|---|
| Рассмотреть37historical missing approvals и initial commit format | Тимур + преподаватель | Новый review не превращается в review до исторического merge; seed не Conventional. Нужна честная formal оценка, без rewrite истории |
| Устранить/согласовать admin bypass | Тимур | Branch protection менять запрещено задачей; действующий bypass опровергает универсальную CI-блокировку |
| Проверить red-check merge box у non-admin | Олег/Лера + Тимур | Исторический BLOCKED одновременно имел REVIEW_REQUIRED; UI причина не доказана. Без изменения правил и без merge failing PR |
| Performance500ms: устранение или преподавательское решение | Тимур + преподаватель | Официальное ТЗ L148; внутренний waiver M5 не отменяет эту норму |
| Решение о logging backend/user context | Тимур + преподаватель | JSON технически работает, но literal library/user-context требования не подтверждены; privacy не ослаблялся |
| Independent approval M6 PR | Олег или Лера | Запрос review не равно submitted APPROVED; merge агент не выполняет |
| Один финальный API rollout и smoke exactSHA | Тимур + Environment reviewer | Нужны отдельное разрешение и штатный protected CD |
| Live Telegram в безопасных test accounts | Тимур + команда | Не разрешено; offline tests не заменяют G2/G3/G4 live |
| Презентация/репетиция/Q&A | Команда, M7 #80 | Сценарий готов, фактическая командная репетиция не проводилась |

**M6 ready to close: PARTIALLY (Issue #79 оставить открытой, PR только Refs #79).**
Начать подготовку материалов M7 #80 можно с этим отчётом/guide/demo; утверждать,
что все обязательные DoD выполнены или проект уже можно окончательно сдавать,
нельзя. Внутренний latency waiver не расширяет официальные исключения курса.
