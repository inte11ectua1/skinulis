# T-10 — инциденты, логи и безопасный откат

[Issue #60](https://github.com/inte11ectua1/skinulis/issues/60) · реализация для
review, production validation ещё не выполнена. Этот документ **не разрешает**
rollout, polling, восстановление production DB или обход Environment approval.
Актуальная подготовка нового AWS описана в [PR #70](https://github.com/inte11ectua1/skinulis/pull/70);
исторические сведения старого аккаунта не являются адресом deployment.

## Формат и границы логирования

API и бот используют независимый stdlib-модуль `skinulis_logging.py` без импортов
backend в боте. Runtime image копирует этот модуль; coverage включает его вместе
с app/bot. Новые библиотеки и внешние сервисы не нужны.

Одна строка stdout — один JSON object:

```json
{"timestamp":"2026-11-02T00:00:00.000Z","level":"warning","service":"api","event":"http_request_completed","request_id":"709865cd-73d7-44f1-b1ba-5e90a03ef9ce","status":401,"method":"GET","route":"/users/me","duration_ms":2}
```

Обязательны timestamp UTC/Z, level, service, event, request_id. У lifecycle и
внесистемных событий request_id=null. Разрешены только status, method, статический
route template, duration_ms, outcome и canonical UUIDv4 request_id. Динамический
путь/ID, query, headers, тела, URL, email, Telegram ID, суммы и тексты исключений
в formatter не попадают. Сообщения/args/traceback сторонних logging-библиотек
заменяются фиксированными событиями **до** передачи handlers. Это projection,
а не попытка найти каждый возможный секрет регулярным выражением.

HTTP middleware всегда создаёт новый UUIDv4; входной X-Request-ID игнорируется.
Response X-Request-ID, error.request_id и события этого запроса совпадают.
ContextVar разделяет конкурентные запросы и сбрасывается после завершения.
Синхронные SQLAlchemy handlers получают контекст через ASGI threadpool.
Бот создаёт отдельный контекст update без записи update_id. HTTP-клиент бота
использует проверенный canonical UUIDv4 из response X-Request-ID для HTTP-события;
при timeout/невалидном заголовке сохраняет локальный ID. Это диагностический ID,
он не даёт полномочий. Автоматических повторов финансовых записей не добавлено.

Production API стартует `python -m app.core.serve`: Uvicorn access log выключен,
его runtime warnings/errors проходят через тот же formatter. Мигратор пишет
migration_started/completed/failed, API — api_started/stopped/runtime_failed.
Bot: bot_started/stopped/runtime_failed, bot_update_failed, bot_handler_failed,
telegram_delivery_failed, notification_claim_failed/notification_delivery_failed.
HTTP-клиент: http_client_completed/failed с outcome ok/input/auth/forbidden/missing/
conflict/server/timeout/network/unexpected. Polling failures классифицируются
также как retry и telegram без текста Telegram exception. Generic library_event
и database_driver_event намеренно не содержат исходного сообщения.

Caddy access log выключен; runtime filter удаляет request/error/err_trace и
заменяет msg фиксированным proxy_event, включая настоящий upstream 502.
PostgreSQL оставляет native startup/FATAL диагностику, не JSON API-формат.
log_statement=none, log_min_messages=fatal, log_min_error_statement=panic,
log_error_verbosity=terse, log_parameter_max_length=0 и
log_parameter_max_length_on_error=0 исключают обычные SQL ERROR/DETAIL/bind из
server log. Полезный исход запроса остаётся в API HTTP/DB событиях. Не включать
SQLAlchemy echo, SQL statement logging, HTTP debug/access dumps или публичный
сбор native PostgreSQL логов: это может раскрыть данные.

## Ротация и диск

Все пять services (включая одноразовый migrate и выключенный bot) используют
json-file: max-size="5m", max-file="3", compress="true". Около 15 MB на контейнер,
75 MB на пять текущих контейнеров, с небольшим превышением на размер записи.
Это не quota всего Docker: stopped containers, images/build cache, DB/WAL,
backups и Caddy volumes считаются отдельно. Запас на 20 GiB root контролировать
`df -h /`, `docker system df`, размером приватной backup directory. При <20%
свободного места сначала остановить новые релизы и найти рост; не выполнять
prune, down -v, volume rm, удаление WAL/backup или production данных автоматически.

Logging options применяются к **новым** контейнерам, не изменяют существующие.
Поэтому этот PR следует review/merge до первого production release; выбранный
release SHA должен содержать и модуль, и Compose/Caddy changes. Перезапуск ради
ротации на EC2 в рамках подготовки не выполнялся. Для уже работающего стека
изменения проводить только через разрешённый controller rollout.

Основания: [Docker json-file](https://docs.docker.com/engine/logging/drivers/json-file/),
[PostgreSQL 17 logging](https://www.postgresql.org/docs/17/runtime-config-logging.html),
[Caddy log filters](https://caddyserver.com/docs/caddyfile/directives/log).

## Read-only диагностика на сервере

Войти только проверенным SSH-over-SSM transport из [AWS_SSM_CD](AWS_SSM_CD.md).
Не использовать direct TCP fallback/accept-new и не открывать SSH всему интернету.
Сначала подтвердить account/instance/environment из защищённой конфигурации.
Доступ docker group root-equivalent; только выделенный deployment user.
Не печатать production.env, полный docker inspect/config, Docker auth store,
SSM session token или сырые request bodies даже при диагностике.

После первого успешного release, на сервере:

```sh
cd /opt/skinulis
release_sha="$(python3 -c 'import json; print(json.load(open("state/current.json"))["sha"])')"
cd "/opt/skinulis/releases/$release_sha"
stack() {
  docker compose --env-file /opt/skinulis/production.env \
    --project-directory "$PWD/deploy" -f deploy/compose.production.yaml "$@"
}
stack config --quiet
stack ps -a
stack logs --no-log-prefix --tail 100 api migrate
free -h
df -h /
docker system df
```

Для поиска UUID из ответа клиента (не вставлять JWT/код приглашения):

```sh
stack logs --no-log-prefix --tail 2000 api bot |
  python3 -c 'import json,sys; wanted=sys.argv[1];
for line in sys.stdin:
 try: item=json.loads(line)
 except ValueError: continue
 if item.get("request_id")==wanted: print(json.dumps(item))' UUID_FROM_RESPONSE
```

`--tail` ограничивает объём. Не отправлять логи в публичный issue без проверки.
Для daemon rotation: `docker inspect --format '{{json .HostConfig.LogConfig}}'
CONTAINER_ID` показывает только driver/options. Не читать внутренние Docker log
files напрямую. Проверить UTC/Z, service/event и отсутствие payload на безопасной
тестовой операции; не провоцировать ошибки настоящих финансовых записей.

| Симптом | Проверить / действие |
|---|---|
| 400 | Ошибка DTO либо смешаны JWT/service channels. Искать request_id, исправить клиент; payload в лог не добавлять. |
| 401 | Bearer expiry/signature либо неверный service credential. Проверить часы и выбор канала, значения секретов не выводить. Не ослаблять auth. |
| 403 | Actor не имеет требуемых прав. Проверить сценарий owner/member локально, не подменять ID. |
| 404 | Объект отсутствует/скрыт либо Caddy deny-policy. Не раскрывать чужую группу, не расширять /internal allowlist. |
| 409 | Конфликт версии/unique/одноразового токена. Сначала перечитать состояние, не повторять запись с новым idempotency UUID вслепую. |
| 500 | http_request_failed + completed/error.request_id. Воспроизвести на отдельной БД тестом. Не включать raw traceback/SQL в production. |
| /health 503 | database_unavailable + HTTP status. `stack ps -a`, db health, место, лимиты/связность database network, migrate exit code; SELECT1 действительно нужен. Не запускать API поверх неуспешной миграции. |
| Telegram/network/timeout | outcome, bot lifecycle, backend health и безопасная проверка сетевого доступа. Сохранить single polling; не запускать второй процесс для диагностики. |

## Release / OIDC / SSM / SSH / GHCR / Caddy

1. Посмотреть guard/publish/deploy jobs конкретного Release run. SHA должен быть
   full trusted main SHA с успешным push-main CI, не PR SHA. Проверить digest и
   OCI revision/source. Не заменять digest на latest и не переиздавать существующий
   SHA tag; registry 403/network failure не означает отсутствующий image.
2. Waiting Environment approval — штатная блокировка, не IAM/network error.
   Требуется независимый Олег/Лера, self-review/admin bypass запрещены.
   check-transport проверяет только транспорт, не разрешает rollout.
3. OIDC AccessDenied: exact repository immutable subject + production environment,
   aud=sts.amazonaws.com, правильный account/role. Не добавлять wildcard PR refs
   или AdministratorAccess. AWS credentials краткоживущие, static access keys не нужны.
4. SSM: agent Online, правильный instance ID, instance role, outbound HTTPS,
   доступные endpoints. Разрешены только StartSession на EC2/AWS-StartSSHSession
   и необходимые session channels. Не заменять это SendCommand/full SSM access.
5. SSH mismatch: остановиться, независимо проверить AWS Console host key, не
   переписывать known_hosts автоматически. Проверить deployment user/key и
   restricted authorized_keys без чтения private key в stdout.
6. Caddy TLS/ACME: DNS A/AAAA соответствует текущему EC2 public IP, SG80/443,
   время, доступность ACME, Caddy volumes writable UID10001, health/DB доступны.
   sslip.io — бесплатное имя без гарантий/SLA; EC2 public IP может измениться.
   Не считать локальный test CA публичным TLS и не использовать curl -k для приёмки.
7. Публичные 8000/5432/22 и Docker API должны оставаться закрыты. /internal,
   encoded/double-encoded paths/traversal закрыты proxy независимо от service token.

## Image rollback: только после согласования совместимости

Controller сохраняет current/previous/attempt state в `/opt/skinulis/state`.
Не редактировать его вручную. Сначала backup, выяснение Alembic head и решение
владельца о совместимости старого кода с **текущей** схемой. После первого релиза
previous может отсутствовать: тогда автоматического отката на пустой стек нет.

Read-only dry-run из текущего проверенного bundle:

```sh
python3 -m scripts.deployment --root /opt/skinulis --rollback
```

Только после отдельного разрешения, проверки previous immutable digest/OCI source,
совместимости схемы и backup, из того же bundle:

```sh
python3 -m scripts.deployment --root /opt/skinulis \
  --rollback --rollback-compatible --execute
```

Это **image** rollback: pull exact previous digest, остановка writers,
запуск/health/HTTPS проверка API, /version обязан совпасть с previous full SHA;
без Alembic downgrade/старого migrate. Polling по умолчанию false, отдельно
разрешается владельцем, единственный процесс. Авто-recovery после failed release
ограничен controller: старая схема либо явно reviewed compatibility. При изменении
схемы/неизвестной совместимости остановить writers, сохранить данные и разбирать
attempt.json. Не делать auto restore/downgrade, down -v или удаление volume.

## Backup и отдельная проверка восстановления

Доступный helper из current bundle (пишет только новый backup, **не запускался
на production DB в рамках T-10**):

```sh
python3 -m scripts.backup_postgres --directory /opt/skinulis/backups
```

Directory owner=deployment user/mode0700, custom dump mode0600, helper lock,
atomic finalization, pg_restore --list validation; backup не внутри DB volume.
Это ещё не доказательство успешного restore, off-host retention или расписания.
Хранить зашифрованную/приватную off-host копию и проверять её checksum.

Для restore drill использовать отдельный UUID Compose project с PostgreSQL17,
loopback-only портом, свежим временным паролем и **синтетическими** данными.
Никогда не брать production connection string/volume. Сначала `pg_restore --list`,
затем `pg_restore --no-owner --no-acl --exit-on-error` в пустую отдельную test DB,
сравнить число строк/инварианты и проверить сохранность после test DB restart.
Не применять --clean к существующей БД. Dump может содержать персональные данные:
не прикладывать к GitHub и не распечатывать SQL/данные. UUID test volume сохраняется
для оператора; этот runbook не разрешает удаление persistent data.
Пример локального drill после проверки, что Docker context указывает на ноутбук,
а файл содержит только синтетический dump (указать свой абсолютный путь). Команды
не выполнялись этим документом; production.env не используется:

```sh
(
  synthetic_dump=/absolute/path/to/synthetic.dump
  test -f "$synthetic_dump" || exit 1
  restore_container="skinulis-restore-test-$(python3 -c 'import uuid; print(uuid.uuid4().hex)')"
  POSTGRES_PASSWORD="$(python3 -c 'import secrets; print(secrets.token_urlsafe(48))')"
  export POSTGRES_PASSWORD
  docker run -d --name "$restore_container" --network none \
    --tmpfs /var/lib/postgresql/data -e POSTGRES_PASSWORD \
    postgres:17.11-bookworm@sha256:858bb5e98eed02eb8cafbcdc007f9a65d1b613972028944a8ec2133ccaf80d27
  for attempt in $(seq 1 30); do
    docker exec "$restore_container" pg_isready -U postgres && break
    sleep 1
  done
  docker exec "$restore_container" pg_isready -U postgres || exit 1
  docker exec "$restore_container" createdb -U postgres skinulis_restore_test
  docker exec -i "$restore_container" pg_restore --list < "$synthetic_dump" > /dev/null
  docker exec -i "$restore_container" pg_restore -U postgres -d skinulis_restore_test \
    --no-owner --no-acl --exit-on-error < "$synthetic_dump"
  docker exec "$restore_container" psql -U postgres -d skinulis_restore_test \
    -c "SELECT count(*) FROM pg_catalog.pg_tables WHERE schemaname='public'"
)
```

После этого проверяются ожидаемые synthetic row counts/инварианты конкретного
fixture. У примера tmpfs, поэтому он проверяет restore, **не** persistence при
restart; persistence отдельно покрыт `scripts/test_delivery.py` на retained UUID
volume. Не превращать tmpfs drill в restart-test и не удалять чужие volumes.
Предыдущий synthetic server backup/restore drill зафиксирован в PR #70; это не
production backup и не новый live restore в T-10.

## Чеклист первого production rollout (не выполнялся)

1. Независимо review/merge T-10 и согласовать T-09 документационные PR #69/#70:
   historical old-account deny из #69 не отменяет new-account readiness из #70.
2. Новый main SHA: все lint/types/tests/docker-build/ci зелёные, Release publish
   создал/проверил linux/amd64 image и immutable digest/OCI revision. Выбрать SHA,
   содержащий T-10, а не прежний dd78027 без JSON/rotation.
3. Закончить protected check-transport с independent approval; проверить OIDC,
   STS account, SSM, pinned key/deployment user. Проверить CloudTrail по run/session.
4. Read-only перепроверить EC2/DNS/SG80/443/закрытые22/8000/5432, Environment,
   distinct secrets/0600, external volumes, RAM/swap/disk и private backup directory.
5. Отдельное явное разрешение Тимура на публичный rollout. Только затем flag=true
   и manual Release из main: operation=deploy, sha=полный проверенный SHA,
   enable_polling=false, rollback_compatible=false до отдельного review схемы.
   Independent production approval обязателен и после разрешения владельца.
6. Controller: actual pull/provenance, DB healthy, migrate foreground один раз,
   API healthy, Caddy HTTPS/health/version/private boundary. С внешнего клиента
   проверить trusted TLS без -k, /health200 с DB, /version exact SHA, /docs/OpenAPI,
   /internal/raw encoded paths denied, закрытые прямые DB/API/daemon ports.
7. Сверить deployed image digest, persistence при разрешённом restart, backup и
   restore drill, rollback/dry-run evidence, JSON privacy/correlation и Docker log
   options. Никакого разрушительного rollback ради демонстрации на production.
8. Polling — отдельное разрешение/секрет владельца, затем ровно один процесс.
   Production validation #59/#60, человеческое review и acceptance доказать
   ссылками до закрытия задач; G5 не следует только из зелёного CI.
