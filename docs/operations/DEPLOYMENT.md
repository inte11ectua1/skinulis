# T-09 — выпуск и production deployment

Актуализация 01.11.2026 · [Issue #59](https://github.com/inte11ectua1/skinulis/issues/59).
PR #64 merged. EC2 preparation/SSH, GHCR digest pull, isolated TLS smoke и
backup/restore реально проверены; [evidence и ограничения](T-09_EC2_PREFLIGHT.md).
**Публичный production rollout/ACME и G5 ещё не проверены.** Подготовительные
изменения EC2 разрешены Тимуром; rollout и live polling требуют отдельных
подтверждений. Частичный follow-up использует `Refs #59`, Issue остаётся открытой.

**Текущий destination 01.11.2026:** новый AWS account/EC2 в Sydney,
[подробное evidence](T-09_NEW_AWS_EC2.md). Старый сервер/account не менялись.
Новый EC2/Docker/SSM, fresh env/keys/volumes и минимальная GitHub OIDC role готовы;
политики из main прочитаны обратно. Environment обновлён с сохранением защиты.
[Protected check-transport](https://github.com/inte11ectua1/skinulis/actions/runs/41346841056)
ожидает независимого approval. Rollout=false; production не запускался.
PR #67/#68 merged; PG/TLS/backup evidence старого EC2 не переносится на новый.

## Архитектура и образы

Один runtime image `ghcr.io/inte11ectua1/skinulis:<full-40-char-SHA>` содержит
app, bot и Alembic. Зависимости у API и бота уже общие: второй образ не уменьшил
бы текущий dependency set. Изменены только упаковка/команды, не bot handlers.
Default CMD остаётся API; bot запускается `python -m bot.main`, migrate —
`python -m app.core.migrate`. Python3.12.15/uv0.13.5 и base digest сохранены,
runtime USER=skinulis/UID10001. Secrets не передаются в build args/layers.

Tag не перезаписывается workflow: existing tag → проверка OCI source/revision,
новая публикация не выполняется. Ошибки auth/network не считаются отсутствием tag.
**GHCR admin технически может переместить tag:** реальный deploy поэтому использует
`image@sha256:<64 hex>`, а не изменяемый tag. CI publisher собирает linux/amd64;
первый VPS должен быть amd64. ARM64 требует отдельно проверенного multiarch release.

Отдельный `deploy/compose.production.yaml`, без override локального compose.yaml:

```text
Internet :80/:443 → caddy → api:8000 → db:5432 → external named postgres_data
                           ↑            ↑
                     bot (1 polling)   migrate (1 foreground run)
```

| Сервис | Сети | Публичные порты / права |
|---|---|---|
| caddy | edge + application | Только TCP80/443; UID10001, read-only, cap NET_BIND_SERVICE, admin API off |
| api | application + database | Нет ports; non-root, read-only, no-new-privileges, tmpfs /tmp |
| bot | application + telegram egress | Нет ports/DB network; non-root; профиль polling выключен по умолчанию |
| migrate | database | Нет ports/JWT/service/Telegram credentials; один foreground процесс, restart=no |
| db | database | Нет ports; PostgreSQL17.11 pinned digest, persistent external volume; штатный entrypoint и postgres OS user |

application/database — internal networks. Bot имеет отдельный outbound egress
для Telegram. Фиксированные project=skinulis-production и container_name бота
запрещают Compose scaling; controller останавливает старого бота до нового.
Bot healthcheck подтверждает только живой процесс, **не** Telegram delivery.
Postgres/API имеют реальные healthchecks; Caddy проверяет HTTPS /health.

## Публичная граница /internal

`deploy/Caddyfile` применяет policy до reverse_proxy:

1. Отказ404 на percent encoding в path, backslash, double slash и dot segments.
   Encoding в query допускается; денежные/Unicode данные передаются JSON body.
2. Только явный allowlist публичных маршрутов. Все прочие, включая `/internal`
   и потомков, закрыты404. Новые публичные endpoints требуют проверки allowlist.
3. X-Original-URL/X-Rewrite-URL удаляются. Backend по-прежнему проверяет JWT,
   mixed channels, BOT_SERVICE_TOKEN и X-Telegram-ID; proxy не заменяет auth.

Тесты используют raw HTTP request-target, не нормализацию httpx/curl:
encoded/double-encoded slash и буквы, dot traversal, backslash, `//`, uppercase,
semicolon, NUL encoding, absolute-form, разные HTTP methods. Внутренний service
actor проверяется реальным bootstrap/me напрямую в private network. Публичные
пробы повторяются даже с корректным **тестовым** service credential.
OpenAPI может описывать internal DTO; это не доступ к самим endpoint.

Основания: [Caddy path normalization/matchers](https://caddyserver.com/docs/caddyfile/matchers),
[GitHub workflow_run security](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#workflow_run).
Workflow не загружает PR artifacts/caches в привилегированный job.

## GitHub Environment: настроить вручную после review

Следующая процедура остаётся инструкцией воспроизведения. На 01.11 Environment
уже создан через API: independent reviewers Олег/Лера, prevent_self_review=true,
protected branches only, **can_admins_bypass=false** (повторный GET подтвердил).
SSH secrets и destination variables заданы; rollout явно false. Это не означает,
что approval/deployment уже выполнялись или runner имеет сетевой доступ к SSH.

1. Settings → Environments → **production**.
2. Required reviewers: Олег и/или Лера, минимум один независимый reviewer.
   Включить **Prevent self-review**, отключить admin bypass в UI, если доступно.
3. Deployment branches: **Protected branches only**. Workflow дополнительно
   требует именно main. Не добавлять PR/fork refs. Guard через API проверяет
   required reviewers/prevent_self_review/branch policy;403/отсутствие правил — отказ.
   Guard также требует `can_admins_bypass=false`; неизвестное значение — отказ.
4. Только в этом Environment создать secrets из таблицы. Не создавать их
   repository/organization-level копии. Runtime DB/JWT/Telegram secrets на runner
   вообще не нужны — они остаются в private file на VPS.
5. До отдельного разрешения оставить repository variable
   **PRODUCTION_ROLLOUT_ENABLED отсутствующей либо false**. Не включать её заранее.

| Место | Имя | Назначение / формат |
|---|---|---|
| production secret | SSH_PRIVATE_KEY | Отдельный deployment key OpenSSH, без вывода в лог; доступ только к выделенному deployment user |
| production secret | SSH_KNOWN_HOSTS | Pinned server host key; fingerprint проверить через console/out-of-band. Не использовать blind ssh-keyscan/accept-new |
| production variables | SSH_HOST | DNS/IPv4 alias проверенного known_hosts; при SSM не TCP target |
| production variables | SSH_USER | Например skinulis; отдельный OS user. Docker group фактически даёт root-equivalent права |
| production variables | SSH_PORT | 1..65535, обычно22 |
| production variables | SSH_DEPLOY_DIR | Абсолютный путь без пробелов/dot segments, например /opt/skinulis |
| repository variable | PRODUCTION_ROLLOUT_ENABLED | По умолчанию false; true только после настройки Environment и разрешения |
| production variables | AWS_ACCOUNT_ID / AWS_ROLE_ARN / AWS_INSTANCE_ID | Account, отдельная OIDC role skinulis-github-production и единственная EC2 для SSM; JSON/Console setup в AWS_SSM_CD.md |
| Built-in job token | GITHUB_TOKEN | guard: contents/actions read; publisher: contents read/packages write; deploy: contents/actions read + id-token write только после Environment approval. Не сохраняется на VPS |
| VPS Docker credential store | GHCR read credential | read:packages и доступ к package; нужен серверу для private image pull, не входит в release bundle |
| VPS production.env | POSTGRES_PASSWORD, JWT_SECRET_KEY, BOT_SERVICE_TOKEN, TELEGRAM_BOT_TOKEN | Runtime only, отдельные случайные значения; требования ниже |

Public repo поддерживает Environment reviewers по
[GitHub Environment docs](https://docs.github.com/en/rest/deployments/environments).
Наличие файла YAML не доказывает, что protection/secrets реально настроены.

## Выпуск GHCR и отключённый rollout

`ci.yml` теперь проверяет PR, push main и ручной CI. Required job names сохранены:
lint, types, tests, docker-build, ci. PR CI не получает package write/prod secrets/SSH.

`deploy.yml` / **Release**:

- Автоматический workflow_run только после успешного **push-main CI**; публикация,
  **без SSH**. Manual workflow_dispatch тоже запускается только с ref=main.
- Guard проверяет canonical repository, full SHA, git ancestry origin/main,
  authoritative API CI run/path/event/head repository и все пять успешных jobs.
  Зелёный PR run не подходит. Для manual разрешён main ancestor с trusted CI;
  нужен commit, уже содержащий T-09 infrastructure.
- Publish получает package write только в своём job, использует pinned checkout,
  full SHA tag, OCI provenance и отдаёт digest. Registry login ephemeral, logout always.
- Deploy job только для **manual operation=deploy**, флага rollout=true и protected
  production Environment с approval. Обычный merge никогда не запускает SSH.
- Global concurrency cancel-in-progress=false сериализует release runs; VPS flock
  отдельно блокирует одновременно запущенные controller/migrator.

После принятого merge дождаться CI **на самом main commit**, затем Release/publish.
Проверить package permissions/visibility и digest в publish output. До этого
фактическое GHCR push/pull не считается проверенным. Не dispatch этот workflow на PR.

## Подготовка VPS после отдельного разрешения

1. Нужны Linux amd64, Docker + Compose plugin (минимум2.17, желательно актуальный
   поддерживаемый patch), Python≥3.12 на host, диск/backup, DNS A/AAAA на VPS.
   Открыть только SSH для администрирования и80/443 для Caddy; не8000/5432.
2. Выделить одного deployment user и постоянный root `/opt/skinulis`, доступный
   только администратору/deployment user. Установить Docker registry read credential
   через `docker login ghcr.io --password-stdin` с безопасным вводом. Не копировать
   credentials с ноутбука в Git или в build context.
3. Создать **новые** external volumes: skinulis-production-postgres,
   skinulis-production-caddy-data, skinulis-production-caddy-config. Не подменять
   volume существующей установки новым пустым; для существующих данных нужен
   отдельный осознанный план переноса/backup. Новые Caddy data/config volume roots
   должны принадлежать UID/GID10001; PostgreSQL инициализирует свой volume штатно.
   Ничего не удалять через down -v/prune.
   Несекретный bind-mounted Caddyfile должен читаться UID10001 (обычно0644);
   production.env при этом остаётся0600. Не применять права env-файла к Caddyfile.
4. Вне releases скопировать `deploy/production.env.example` в
   `/opt/skinulis/production.env`, установить0600. Заполнить PUBLIC_DOMAIN,
   POSTGRES_VOLUME, DB identifiers и runtime secrets. Пароль DB/JWT минимум32
   случайных bytes; service43–128 URL-safe symbols, отдельный от DB/JWT/Telegram.
   TELEGRAM_BOT_TOKEN допустимо оставить пустым, пока polling не разрешён.
   Shell variables не переопределяют этот env file в controller. Полный compose
   config/inspect env не публиковать; controller читает JSON config только в памяти.
5. Настроить Environment/host-key pin и backup PostgreSQL вне Docker volume.
   До миграции проверить восстановление backup и совместимость предыдущего image.
   Штатный POSTGRES_USER на пустом официальном image создаётся как superuser:
   оценить права отдельно, сохранить административный доступ и ограничить runtime
   роль необходимыми правами своей БД/DDL до публичной эксплуатации. Эти server-side
   действия здесь не выполнялись; не считать bootstrap-role автоматически least-privilege.
6. Только после разрешения Тимура поставить rollout flag=true и запустить Release
   **на main**, operation=deploy, sha=полный main SHA с trusted CI.
   enable_polling=false по умолчанию. Для запуска настоящего бота нужно отдельное
   разрешение и enable_polling=true. rollback_compatible=false, пока оператор
   отдельно не подтвердил совместимость старого приложения с новой схемой.

SSH-over-SSM transport передаёт только allowlisted compose/Caddy/controller files из
проверенного checkout в `root/releases/SHA`. Production env/key не передаются.
StrictHostKeyChecking=yes, BatchMode, без agent forwarding, без чужого SSH config.
AWS CLI + Session Manager plugin открывают AWS-StartSSHSession к instance ID,
порт22. HostKeyAlias использует pin **текущего** сервера; при новом EC2 его заново
проверяют через AWS Console и обновляют. Direct TCP fallback отсутствует.
`operation=check-transport` — protected read-only проверка, работает с flag=false:
без отправки bundle/вызова controller. Для `operation=deploy` нужен flag=true и
отдельное разрешение. Полные IAM policies, инструкции и evidence boundary — в
[SSM runbook](AWS_SSM_CD.md).

### Сетевой доступ GitHub runner

IP административного ноутбука и исходящий IP GitHub-hosted runner различаются.
Не открывать22 для0.0.0.0/0 и не добавлять все широкие Actions ranges.
Принятый в PR #68 transport — SSH поверх AWS SSM + OIDC, с exact production
trust, минимальной StartSession policy и проверкой host key. На новом EC2 нет
inbound22 вообще; для Mac administration также используется SSH-over-SSM.
Instance profile/Online agent и реальный Mac SSH проверены, отдельная GitHub role
создана по main policies. До protected check-transport после independent approval
GitHub → SSM не считать verified. Session Manager для EC2 не имеет отдельной
платы согласно [AWS pricing](https://aws.amazon.com/systems-manager/pricing/);
paid JIT node access/endpoints/runners не включались. Старый Mac SSH/EC2 не меняли.

### Ручной backup перед релизом

После review/merge helper входит в allowlisted release bundle. Из установленного
доверенного bundle под deployment user:

```sh
python3 -m scripts.backup_postgres --directory /opt/skinulis/backups
```

Каталог принадлежит этому пользователю,0700. Helper выбирает ровно один running
container по **обоим** Compose labels project=skinulis-production/service=db,
потоково сохраняет pg_dump custom format0600, проверяет pg_restore --list и
атомарно добавляет новую копию без замены старой. Lock запрещает параллельный dump.
Значения env/данные/DB diagnostics не печатаются. Никаких restore/drop/retention
операций helper не выполняет; удаляется только собственный незавершённый partial.

Перед миграцией проверить восстановление в **новом изолированном** PostgreSQL17
container/volume, сравнить контрольные данные и сохранить копию вне DB volume.
Резервная копия на том же EC2 не защищает от потери EC2/EBS: нужен согласованный
защищённый off-host target. Проверка 01.11 использовала только synthetic test DB,
два UUID volumes и private network; restore сохранился после restart. Тестовый dump
также скопирован на Mac с0600 и совпадающим SHA256. Production backup/restore ещё
не выполнялись, production DB не инициализирована. Автоматизация расписания,
retention и эксплуатационные задачи T-10 в этот follow-up не входят.

## Что делает controller

`python3 -m scripts.deployment` запускается из установленного `root/releases/SHA`.
**Без --execute — только dry-run/config validation.** Последовательность execute:

1. Проверка private env file, фиксированного project, digest, OCI revision/source/user.
2. Pull образа → DB healthy → schema preflight, сохранение previous/candidate в
   state/attempt.json. Current successful release ещё не меняется.
3. Stop bot/API → ровно один foreground migrate (не каждый worker).
4. API healthy → Caddy → внутренний DB-backed /health и /version → публичный HTTPS
   /health, exact commit_sha и запрет internal. Redirect не считается успешной пробой.
5. Только при explicit enable_polling — один bot. После всех probes atomic
   state/previous.json и state/current.json; файлы не содержат secrets.

При failure return!=0 и successful state не продвигается. Если схема осталась
той же, предыдущий image восстанавливается с health/SHA probes, **без migrations**.
При новой/неизвестной схеме writer containers остаются остановленными до решения
оператора. Explicit rollback_compatible разрешает image fallback только после
проверки совместимости оператором. Ни автоматического downgrade, ни удаления DB нет.
Даже rollback не включает polling без текущего explicit разрешения.

## Ручной image rollback

Сначала проверить state/current.json, previous.json, backup и совместимость схемы.
Root/env/volume/project не менять. Из **текущего** установленного release bundle:

```sh
python3 -m scripts.deployment --root /opt/skinulis --rollback
# Только после оценки совместимости и разрешения реального действия:
python3 -m scripts.deployment --root /opt/skinulis --rollback --rollback-compatible --execute
```

Откат выбирает сохранённый previous digest, проверяет его происхождение,
останавливает writers, поднимает прошлый API/Caddy и проверяет /health+/version.
**Миграции не запускаются**. Polling по умолчанию выключен, для него нужно явно
--enable-polling. Если код несовместим с новой схемой — image rollback не является
решением: maintenance, совместимый forward fix либо согласованное восстановление
backup с оценкой потери новых записей. Автоматического DB restore/downgrade нет.

Диагностика на VPS: `docker compose --env-file ... -f ... config --quiet`, `ps -a`,
exit code migrate, healthcheck API, private container logs. Не прикладывать env,
полный config, inspect Environment или raw credentials к Issue. Полноценные JSON
логи/rotation/observability относятся к T-10, а load100/p95 — к O-08.

## Автоматические проверки и оставшаяся приёмка

```sh
actionlint
uv run pytest tests/unit/test_release_policy.py tests/unit/test_deployment.py tests/unit/test_remote_deploy.py
# После локального build с настоящим APP_COMMIT_SHA; без registry publish/SSH:
T09_TEST_IMAGE=skinulis-t09-test:local uv run python scripts/test_delivery.py
```

Unit tests используют mocks для GitHub/GHCR/SSH и отказов Docker: чужой/PR SHA,
failed/skipped CI, unprotected Environment, tag reuse, image/schema/health failures,
rollback compatibility, server lock, dry-run, safe output. Docker smoke использует
настоящие app+bot image imports, fresh PostgreSQL17.11, migrate, restart DB с
сохранением профиля в **своём UUID named volume**, non-root Caddy и доверенный local
CA. Проверяются26 raw routing negatives, private service actor и exact image SHA.
UUID containers/networks очищаются; test-only named volume сохраняется. Никакого
реального Telegram, VPS, registry push или public ACME в этих тестах нет.

До закрытия #59 Тимуру остаётся: independent review/merge, main CI+GHCR evidence,
реальный VPS/DNS/secrets/Environment setup и отдельное разрешение deploy; затем
проверить публичный TLS chain, health(DB), version exact SHA, closed internal
включая raw negatives, отсутствие8000/5432 снаружи и controlled rollback.
Только после этих доказательств можно обсуждать G5 verified и полный Closes #59.

### Локальные evidence этой ветки (31.10.2026)

Frozen sync/lock, Ruff check/format, strict mypy (128 файлов), pre-commit со
сканером secrets, uv pip check, uv audit --locked (72 пакета, без известных
уязвимостей), native actionlint и pinned container actionlint прошли.
**1133 unit (в том числе75 новых infra cases) +402 PostgreSQL integration =1535 passed**,
combined branch coverage app+bot **94,76%**. Инфраструктурные тесты не включаются
в source покрытия приложения и не подменяют его процент.

Общий Docker image собран локально, app/bot imports работают от UID10001.
Production compose config --quiet/JSON validation и real Docker TLS smoke прошли
на Engine23.0.5/Compose2.17.3: cold migration0006, DB restart/persistent profile,
private service bootstrap/me, public exact SHA/health и26 raw routing negatives.
В локальных smoke сохранены свои test-only volumes, в частности
`skinulis-t09-test-167951254671-postgres`; также сохранён volume более раннего
успешного прогона `skinulis-t09-test-d88c7a92b10a-postgres`.
Эти UUID volumes содержат только искусственные тестовые данные; пользовательские
volumes не изменялись. Реального GHCR push, SSH или public ACME эти результаты
не доказывают. GitHub CI текущего PR подтверждается отдельными ссылками в его body.
