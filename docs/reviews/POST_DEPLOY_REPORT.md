# M6 — POST-DEPLOY проверка

**Внешний smoke: 03.11.2026, 07:17–07:26 UTC. Внутренняя read-only проверка: 07:59–08:02 UTC (10:59–11:02 Europe/Moscow). Итог: NOT READY; внутреннее состояние VERIFIED.**
[Issue #79](https://github.com/inte11ectua1/skinulis/issues/79) остаётся открытой.
Проверка выполнена с Mac внешними HTTPS-запросами, GitHub/GHCR/AWS read-only API
и pinned SSH-over-SSM. Новый Release,
миграции, polling, restart, rollback и изменения AWS/production DB не запускались.
[Машинное evidence](POST_DEPLOY_EVIDENCE.json) содержит безопасные результаты.
Публичные Git SHA в JSON обозначены префиксом `git:` для secret scanner;
в настоящем HTTP commit_sha префикса нет.

## 1. Версия, CI и действительно выполненный deployment

- [PR #81](https://github.com/inte11ectua1/skinulis/pull/81) merged **03.11.2026 05:16:44 UTC**.
- Проверенная на этапе внешнего smoke `origin/main` и ожидаемый production SHA:
  `7aa7c14e563d5e72efd027d89d7b5765d2f570e3`.
- [Push-main CI #41582982671](https://github.com/inte11ectua1/skinulis/actions/runs/41582982671):
  `lint`, `types`, `tests`, `docker-build`, `ci` — **5/5 success**.
  Из новых CI logs: **1280 unit + 446 PostgreSQL integration = 1726 tests**,
  combined branch coverage **95,00%**, порог 60% сохранён.
- [Автоматический publish #41584158366](https://github.com/inte11ectua1/skinulis/actions/runs/41584158366)
  success; отдельно от настоящего deploy.
- [Manual Release #41591582318](https://github.com/inte11ectua1/skinulis/actions/runs/41591582318):
  `workflow_dispatch`, **operation=deploy**, `enable_polling=false`;
  `guard`, `publish`, `deploy` — success. Независимый Environment production
  approval получен от **pylinolg-max**. Шаг SSH-over-SSM завершился маркером
  `Approved remote release completed` в **06:48:44 UTC**.
- Публичный GHCR tag полного SHA проверен заново: manifest/config SHA256,
  linux/amd64, OCI revision и APP_COMMIT_SHA совпадают с ожидаемым SHA;
  runtime user `skinulis`.

Опубликованный image и APP_IMAGE из фактического deployment job:

```text
ghcr.io/inte11ectua1/skinulis@sha256:ff1530a0c0f2166d9e9236df968e32157e7713dad347c00660be78b7383d3f3f
```

**Совпадение publish → deployment input: PASS.** Controller перед выполнением
проверяет digest/revision/source image. Свежий `docker inspect` запущенного API
**PASS**: actual image ID/RepoDigests и OCI revision совпадают с опубликованным
digest и ожидаемым SHA; `state/current.json` подтверждает тот же release (§3).

Repository variable **PRODUCTION_ROLLOUT_ENABLED=false** прочитана GitHub API.
Переменная не изменялась. Environment требует independent reviewers Олег/Лера,
prevent_self_review=true и protected branches; protections не менялись.

## 2. Реальный внешний production smoke

URL: **https://3-25-53-31.sslip.io**. Default CA verification и hostname/SNI
включены, verify=false / curl -k не использовались. TLS1.3, Let's Encrypt YE2,
SAN соответствует hostname, сертификат действителен **02.11.2026–31.01.2027**.

| Проверка | Результат | Статус |
|---|---|---|
| GET /health | 200, `{"status":"ok","database":"ok"}` | PASS |
| Реальное подключение PostgreSQL | В принятом handler выполняется SELECT 1; health database=ok | PASS для подключения, не для Docker health |
| GET /version | 200, commit_sha точно равен полному ожидаемому SHA | PASS |
| GET /docs, /redoc, /openapi.json | 200; 41 OpenAPI path, новые HealthResponse examples присутствуют | PASS |
| Reverse proxy | Ответы API содержат Via: 1.1 Caddy; отказы ниже — Server: Caddy | PASS |
| HTTP /health | 308 → точный HTTPS URL | PASS |
| GET /users/me и /groups без токена | 401 invalid_token, error.code/message/request_id; X-Request-ID есть | PASS |
| Query с encoded /internal; X-Original-URL / X-Rewrite-URL | Health 200, internal response не получен | PASS |
| Секреты/traceback в проверенных ответах | Не обнаружены; финансовые записи/ответы не запрашивались | PASS в этом наборе |

Положительный smoke не является полным authenticated financial E2E: production
финансовые POST/PUT/DELETE и нагрузочные тесты намеренно не выполнялись.

Всего в итоговом HTTP-наборе **36 probes: 35 PASS, 1 FAIL**, дополнительно
TLS и HTTP→HTTPS redirect PASS. Из26 negative routing checks25PASS,1FAIL.

### Проверка закрытия /internal

**404** получены для всех следующих origin-form путей:

```text
/internal
/internal/
/internal/users/me
//internal/users/me
///internal/users/me
/%69nternal/users/me
/%49nternal/users/me
/internal%2fusers%2fme
/internal%252fusers%252fme
/%2569nternal/users/me
/internal%5cusers/me
/internal\users/me
/groups/../internal/users/me
/groups/%2e%2e/internal/users/me
/groups/%252e%252e/internal/users/me
/./internal/users/me
/internal;ignored/users/me
/INTERNAL/users/me
/internal%00/users/me
//localhost/internal/users/me
```

HEAD/OPTIONS/TRACE/CONNECT `/internal/users/me` →404. Существующий isolated
POST-negative case не повторялся: production проверялся только указанными
методами без тел и без service credentials. Absolute-form с production authority
`https://3-25-53-31.sslip.io/internal/users/me` →404.

**Новый FAIL:** raw request-target
`https://localhost/internal/users/me` при TLS SNI и HTTP Host production hostname
воспроизводимо возвращает **HTTP 200 от Caddy, Content-Length: 0**.
Тест `scripts/test_delivery.py` ожидает для этого request-target 400/404.
Контрольный absolute-form с production authority возвращает404.

Минимальное read-only воспроизведение (TLS verification включена):

```sh
curl --http1.1 --resolve 3-25-53-31.sslip.io:443:3.25.53.31 \
  --request-target https://localhost/internal/users/me \
  --max-time 15 --include https://3-25-53-31.sslip.io/health
```

Это **отклонение от ожидаемого deny status**, не доказательство получения
внутренних данных или обхода авторизации: body пустой, response X-Request-ID API
отсутствует. Вероятная причина — выбор virtual host по authority absolute-form;
причина пока не подтверждена изолированным regression test. Нельзя считать
весь routing negative набор зелёным. Нужны отдельные regression/fix PR,
независимое review и при необходимости отдельно разрешённый rollout; здесь
Caddy, код приложения и production не изменялись.

Начальный DNS path клиента возвращал 240.0.2.26 и имел transient timeout/TLS EOF.
Повтор подключался к известному публичному IPv4 3.25.53.31, сохраняя настоящий
hostname в SNI/Host и полную проверку TLS. Успешные ответы через оба пути
подтверждены. Единичный timeout uppercase path повторно дал404; таймауты сами
по себе не засчитывались как deny PASS. Ошибка absolute-form повторена отдельным
raw socket GET; это не просто сетевой timeout.

## 3. Контейнеры, миграции, volumes и polling — VERIFIED

**Свежий срез 03.11.2026 07:59–08:02 UTC**, после интерактивного восстановления
`aws login --profile skinulis-new-admin --region ap-southeast-2` самим владельцем.
Первоначальный session expired действительно блокировал прошлую проверку;
теперь этот пробел закрыт. [Машинное evidence](POST_DEPLOY_RUNTIME_EVIDENCE.json).
Публичные Git IDs в JSON имеют префикс `git:`, не входящий в wire commit_sha.

Подтверждены STS account **621150878773**, region **ap-southeast-2**,
EC2 **i-0c920378dd242af2b**, Running/x86_64, IPv4 **3.25.53.31**,
SSM **Online** (Agent3.3.4793.0). Подключение — только SSH-over-SSM
AWS-StartSSHSession с pinned ED25519 known_hosts, StrictHostKeyChecking=yes,
без direct fallback. Прочитаны выборочные Docker fields и bounded logs;
полный inspect/env/config и сырые логи не публиковались.

Актуальная main после merged [PR #82](https://github.com/inte11ectua1/skinulis/pull/82):
`71363d1b9e59de919efd3e9e91089d36adfa00c7`. Разница с deployed `7aa7c14` —
только пять документационных/evidence файлов PR82; новый rollout не запускался
и для закрытия этого read-only задания не требуется. Ожидаемый production SHA
остаётся полным `7aa7c14e563d5e72efd027d89d7b5765d2f570e3`.

| Компонент | Ожидаемое состояние | Фактическое состояние | Статус |
|---|---|---|---|
| AWS destination | Новый account/EC2, Sydney, SSM Online | Точные account/region/instance выше, SSM Online | PASS |
| Compose project | skinulis-production | Все четыре существующих контейнера имеют этот project label | PASS |
| api | Running, healthy | Running/healthy; started06:48:37UTC, restart0, OOM=false | PASS |
| db | Running, healthy, private | Running/healthy; started02.11 09:08UTC, restart0, OOM=false, ports={} | PASS |
| caddy | Running, healthy, public80/443 | Running/healthy; started06:48:43UTC, restart0, OOM=false; только80/443 | PASS |
| migrate | Один завершённый job, exit0 | Exited0;03.11 06:48:33–06:48:36UTC, restart0, OOM=false | PASS |
| bot | Не запущен | Bot service container отсутствует во всех Compose projects | PASS |
| Deployment state | Ожидаемый SHA/image, polling=false | current.json содержит ожидаемые SHA/digest/polling=false | PASS |
| Actual API image | Exact immutable digest/OCI revision | Docker inspect actual image ID/RepoDigests совпали с GHCR и Release; OCI revision=ожидаемый SHA | PASS |
| API DB connection | SELECT1 успешен | Свежий внешний health200, status=ok/database=ok | PASS |
| Alembic revision | Одна0006_settlement_notification_claim | Read-only SELECT вернул единственную0006_settlement_notification_claim | PASS |
| PostgreSQL volume | Существующий persistent external volume | skinulis-production-postgres, created01.11 20:22:25UTC, local/RW, mount /var/lib/postgresql/data | PASS для наличия/подключения volume |
| Caddy volumes | Существующие data/config | skinulis-production-caddy-data и skinulis-production-caddy-config подключены | PASS |
| Restart/OOM | Нет restart loop/OOM | RestartCount0/OOM=false у всех4; за последние30min Docker events oom/restart/die пусты | PASS в проверенном окне |
| Host resources | Запас RAM/disk/swap | MemAvailable≈1,20GiB; disk free≈12,50GiB/68,2%; swap2GiB, used28KiB; load≈0,13/0,19/0,15 | PASS |
| Public ports API/db | Не публикуются Docker | PortBindings={} у API/db/migrate; у Caddy только80/443 | PASS для Docker; AWS SG заново не инспектировалась |
| Rollout flag | false | Прочитан false через GitHub API, не менялся | PASS |

Docker Engine29.9.2. Наличие старого volume и работа DB подтверждены без чтения
пользовательских строк. Это не новая backup/restore/byte-for-byte проверка данных
и не доказательство reboot durability; restart/restore в этой задаче запрещены.

**Проверка схемы:** отдельный psql процесс с `default_transaction_read_only=on`,
statement_timeout5000ms; только
`SELECT version_num FROM public.alembic_version ORDER BY version_num`.
Миграции/DDL/запись в БД не запускались. У последнего migrate контейнера exit0,
в его4JSON строках migration_started=1/migration_completed=1/migration_failed=0.
Существующий исходный Alembic head совпадает с actual revision.

### Фактический Telegram polling: POLLING OFF

Проверены labels всех Docker containers, процессы всех running containers через
Docker top и доступные root `/proc/*/cmdline` host processes (только в памяти).
Bot service containers **0**, процессов стандартного запуска `python -m bot.main`
или `python ...bot/main.py` **0**, контейнеров с такими процессами **0**,
дополнительных running containers вне production project **0**.
Это подтверждение фактического состояния, а не вывод только из polling=false.
Raw process arguments/environments не публиковались; Telegram getUpdates,
отправка сообщений и запуск бота не выполнялись.

### JSON logs/privacy/rotation: VERIFIED в ограниченной выборке

- API:200/200 последних строк — JSON; timestamp UTC/Z, level, request_id
  присутствуют во всех200.100 request_id непустые и canonical UUIDv4;
  library/lifecycle записи могут иметь null. Неожиданных API fields0.
- Migrate:4/4 JSON, UTC/Z/level/request_id поля корректны; request_id=null для
  lifecycle ожидаем. Завершение миграции подтверждено событием и exit code.
- Caddy:19/19 последних строк текущего контейнера — JSON, включая startup;
  request/error/err_trace fields отсутствуют. Не все startup msg равны proxy_event;
  это не заявление о едином API-формате Caddy. За последние30min новых Caddy logs0.
- Error/critical/fatal/panic events в перечисленных выборках **0**; Docker
  production events OOM/restart/die за последние30min **0**. Это ограниченный
  временной срез, не обещание отсутствия всех исторических ошибок.
- В памяти сравнены строки с фактическими sensitive runtime env values:
  совпадений0; очевидных password/token/authorization/TelegramID/email/body/headers
  JSON fields0. Значения секретов и сырые логи не сохранялись в evidence.
- У api/db/caddy/migrate фактически `json-file`, max-size=5m, max-file=3,
  compress=true. Bot не существует, runtime LogConfig бота неприменим;
  декларация выключенного bot service остаётся в Compose.

Формальные вопросы stdlib logging вместо предложенных библиотек и отсутствия
actor context остаются в M6 DoD-матрице. Текущая runtime privacy проверка их
не превращает в согласованное преподавателем исключение.

## 4. Соответствие #79 и граница закрытия

| Область #79 | Post-deploy результат |
|---|---|
| A — deployed commit / green CI / coverage | PASS для release SHA7aa7c14, CI logs5/5 и95,00%; новый main71363d1 — docs-only merge PR82 |
| A — protection / все исторические approvals | Ранее выявленные FAIL остаются; не исправлялись |
| B — clean build / finance / concurrency / performance | CI release commit проверяет приложение; подробный audit в M6_ACCEPTANCE_REPORT. Production write/load не выполнялись. p95>500ms остаётся FAIL |
| C — guide / offline Telegram / demo | Артефакты PR81 merged; live Telegram NOT VERIFIED |
| D — финальный protected deploy / exact version | PASS по Release и свежему HTTPS /version; published/deploy input digest совпадает |
| D — полный post-deploy routing smoke | FAIL на ранее выявленном foreign-authority absolute-form; внутренний runtime inventory теперь VERIFIED |
| Полный официальный DoD / G6 | НЕ подтверждён; owner acceptance не является исключением преподавателя |

Сохраняются ограничения принятой [M6-матрицы](M6_ACCEPTANCE_REPORT.md):
37/48 исторических PR без зарегистрированного pre-merge APPROVED, admin bypass
main, p95 956/1098ms вместо500ms, формальные вопросы stdlib logging/actor context,
live Telegram NOT VERIFIED. Их не пытались устранять в этой задаче.

## 5. Решение и следующие действия

**Deployment: YES. Ожидаемый production SHA: YES. Полная POST-DEPLOY приёмка: NOT READY.**
Сохраняется ранее документированный blocker приёмки — unexpected empty200 на
одном negative routing case; подтверждённой утечки данных не обнаружено.
Эта отдельная read-only задача не меняла Caddy и не повторяла тот routing test.
**Пробел AWS/container evidence закрыт:** destination, actual image/state,
DB/revision/migrate/volumes, bounded JSON logs/rotation и POLLING OFF VERIFIED.

Внутреннее состояние production можно принять как **VERIFIED на момент среза**.
Безусловно завершить весь M6 пока не рекомендуем из-за прежнего routing FAIL;
его отдельная проверка/исправление не входит в текущую задачу. Остальные принятые
ограничения M6 также сохранены. Полное соответствие официальному DoD преподавателя
не подтверждено. Issue #79 не закрывается, M7 не начинался. Новый deploy, polling
или изменение production потребуют отдельного разрешения владельца.
