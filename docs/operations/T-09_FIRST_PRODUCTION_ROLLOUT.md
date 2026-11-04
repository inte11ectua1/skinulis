> **Актуализация 04.11.2026.** PR #85 merged; main/release `c9ec9ce`, protected Release41836839608 success с polling input=true. Владелец подтвердил ответы production-бота и новый UI; меню настроено через BotFather. Read-only follow-up04.11 после штатного browser login подтвердил healthy API/db/Caddy/bot, ровно один Python polling на EC2, SQL revision0007 и прежний volume; рестарты/изменения не выполнялись. Это не прежний POLLING OFF и не полная учебная приёмка. Ниже сохранён датированный исходный срез/общий runbook; его прежние статусы не переносятся на04.11.
> [Текущий аудит и границы доказательств](../reviews/POST_RELEASE_AUDIT_2026-11-04.md).

# T-09 / T-10 — первый production rollout: evidence

Актуализация 02.11.2026. Refs #59, Refs #60. Этот документ фиксирует реальные
проверки; он не разрешает следующие deployment, polling или restore production.

> **Статус приёмки на 03.11.2026:** Issues T-09 #59 и T-10 #60 закрыты `completed` по решению владельца в ограниченном API-first scope; M5 принят. Упоминания «Issue открыта», «pending owner acceptance» и строки матрицы ниже — **снимок на дату первого rollout 02.11**, не актуальные GitHub статусы. Отчёт подтверждает deployment SHA `f7020cd`, **не** последний `main` `0de89b3`; polling по-прежнему off. [Closeout](M5_CLOSEOUT_M6_HANDOFF.md).

## Текущее состояние

Тимур отдельно разрешил первый публичный rollout без Telegram polling.
[Release #41428440222](https://github.com/inte11ectua1/skinulis/actions/runs/41428440222)
**завершился успешно** после независимого Environment approval от **pylinolg-max**.
Запуск из `main`: `operation=deploy`, `enable_polling=false`,
`rollback_compatible=false`. Штатные guard/publish/deploy и OIDC → SSM → pinned SSH
прошли; ручного обхода protected CD не было. После завершения repository variable
`PRODUCTION_ROLLOUT_ENABLED` возвращена в **false**, значение перечитано через API.

Публичный API: **https://3-25-53-31.sslip.io**. Новые deployment и Telegram polling
по-прежнему требуют отдельного разрешения. Issues #59/#60 не закрываются этим
документом; итоговая приёмка принадлежит владельцу.

Проверенный release SHA:
`f7020cda3908d7e0c40c0b0f840e322b3d6cfda5`.

Проверенный image:
`ghcr.io/inte11ectua1/skinulis@sha256:245801d9eecc4904ea575556838e1a39bbcc91c04930c8545974d83d7286d0aa`.

Registry manifest/config digests, linux/amd64, OCI revision/source, non-root USER
и API CMD проверены повторно с Mac и EC2. Existing SHA tag не переиздавался.
[Trusted main CI](https://github.com/inte11ectua1/skinulis/actions/runs/41403773254)
и [Release publish](https://github.com/inte11ectua1/skinulis/actions/runs/41404910850)
успешны. [Protected transport](https://github.com/inte11ectua1/skinulis/actions/runs/41401010599)
уже пройден после независимого approval; повторный check-transport не запускался.

## Preflight нового EC2

Новый account `621150878773`, EC2 `i-0c920378dd242af2b`, Sydney/ap-southeast-2:
Running, Ubuntu24.04.5 AMD64, t3.small,2vCPU,1905MiB RAM, swap2047MiB.
Docker29.9.2/Compose5.6.1 active/enabled, SSM Online. Root20GiB gp3 encrypted.
На preflight свободно12,77GiB диска и1330MiB RAM. CPU credits324,59,
CPUSurplusCreditsCharged=0 за последний час. Budget$20/month, actual$0 на момент
проверки, notifications actual$10/$20; billing/forecast обновляются с задержкой.

SG разрешает только публичные TCP80/443. Inbound22/8000/5432/Docker API отсутствуют;
SSH идёт только через SSM с pinned host key и StrictHostKeyChecking=yes.
OIDC trust/permissions совпадают с main, Environment требует independent review,
prevent_self_review=true, can_admins_bypass=false, protected branches only.
Флаг rollout включается только на разрешённую попытку и возвращается false
после её завершения; нельзя оставлять его включённым для следующих релизов.

Действующий hostname `3-25-53-31.sslip.io` указывает на публичный IPv4 EC2
`3.25.53.31`: подтверждено Google/Cloudflare DNS и resolver на EC2.
На Mac resolver возвращал синтетический240.0.2.26; это не использовалось как
основание менять PUBLIC_DOMAIN. Env уже содержал корректный hostname, не менялся.
IP не является Elastic IP: stop/start может потребовать нового hostname/DNS
и повторной TLS-проверки. Платные дополнительные ресурсы не создавались.

## Private PostgreSQL и роли

По отдельному разрешению до rollout запущена только PostgreSQL17.11,
`skinulis-production_database` internal, без published ports, исходный external
volume `skinulis-production-postgres`. Caddy volumes сохранили UID/GID10001/0700.
До approval state/current.json отсутствовал и работала только private DB.
После approved Release state/current.json содержит указанные SHA/digest и polling=false.

| Роль | Проверенный результат |
|---|---|
| skinulis | LOGIN, NOSUPERUSER/NOCREATEDB/NOCREATEROLE/NOREPLICATION/NOBYPASSRLS; owner своей БД, CONNECT/CREATE и public USAGE/CREATE |
| skinulis_db_admin | Отдельный LOGIN/SUPERUSER с новым server-only secret, проверен TCP password-auth до ограничения runtime |
| skinulis_bootstrap_admin | OID10 сохранён как системный superuser, NOLOGIN, passwordNULL |

PostgreSQL запрещает снимать SUPERUSER с bootstrap OID10. Поэтому в одной
транзакции bootstrap переименован, создана новая runtime роль с прежними именем
и паролем и передано владение только прикладной БД. REASSIGN OWNED не выполнялся;
system catalogs не переподчинялись runtime. Production.env/секреты не менялись.
[Ограничение PostgreSQL17](https://www.postgresql.org/docs/17/sql-alterrole.html).

Новые TCP-сеансы проверили admin/runtime и отказ неверного пароля. Runtime не
состоит в admin/bootstrap/server-file/program roles; CREATE ROLE запрещён.
Representative CREATE/ALTER/INDEX/identity/CHECK/FK/rollback прошли. Обычный DB
restart сохранил роли и собственную synthetic запись; проверочные объекты удалены.
До rollout Alembic не запускался и прикладная БД была пустой. После rollout
новым TCP-сеансом подтверждена revision `0006_settlement_notification_claim`,
admin/runtime login и прежние ограничения runtime; public schema содержит11 таблиц.
Admin credential store остаётся только на сервере,0600 в каталоге0700, вне runtime env.

## Контрольная backup и восстановление

Из trusted bundle реально выполнен `python3 -m scripts.backup_postgres --directory
/opt/skinulis/backups`. Custom archive0600, directory0700; `pg_restore --list`
успешен. Архив893bytes,0TOC entries — это **пустая прикладная БД до миграций**,
а не доказательство восстановления расходов или заполненной application schema.

Plaintext archive SHA256:
`1d7a4d26d12ac49b2ad46150ea83e96779a22a792c645bf2baae3b193874614a`.

Реальный pg_restore выполнен в отдельном PostgreSQL17.11 container с network=none,
read-only rootfs, PGDATA только в tmpfs, без production mount/ports. Логическое
состояние source/restore совпало. В тестовом кластере отдельно provisioned admin
и restricted runtime с новыми test secrets; DDL-права проверены с rollback.
Контейнер удалён, Docker volume inventory не изменился. Production не
перезапускалась/не восстанавливалась; её роли, env и credential store не менялись.

**Dump database-only, с --no-owner --no-acl:** global roles/passwords, OWNER/ACL,
JWT/service/Telegram credentials и runtime configuration из него не восстанавливаются.
На новом кластере отдельно provision admin/runtime, назначить runtime owner своей
БД и public USAGE/CREATE, затем restore от runtime. Restore production требует
отдельного разрешения; auto downgrade/restore после миграций запрещён.

## Шифрование off-host и recovery key

Mac FileVault выключен; поэтому для новых off-host копий подготовлен age1.3.2
(операторская утилита, не Python/runtime dependency). Plaintext dump поступает
через pinned SSH-over-SSM в RAM; на Mac сохраняется только `.dump.age`,0600 в0700.
Source dump остаётся в защищённой backup directory на encrypted EBS.

Recovery identity хранится в **двух местах**:

1. macOS Keychain, service `skinulis.production.backup.age`, без plaintext keyfile
   на Mac и без iCloud sync; readback проверен отдельным процессом.
2. `/opt/skinulis/private/backup-age-identity.txt` на encrypted EBS,0600/0700,
   владелец deployment user. Это новый backup key, не пароль PostgreSQL/JWT/Telegram.

Public recipient отдельно в `backup-age-recipient.txt`. Не печатать identity,
не передавать его через argv, GitHub, логи или вместе с архивом в открытом файле.
Это не offline vault: потеря обоих хранилищ означает потерю возможности decrypt.
Для долговременной независимой offline escrow владелец выбирает дополнительное
защищённое хранилище; оно здесь не создавалось.

На фактическом893-byte archive проверены decrypt из Keychain и server recovery
copy, совпадение plaintext SHA256 и отказ после изменения ciphertext.
Ciphertext SHA256:
`02d540ecb8bcd61a75ab21b365fe32e06169ad04a26f375c3bd3a2584c70f3ab`.
Старый unencrypted893-byte off-host archive пустой БД не удалялся. Новые backup
со schema/user data сохраняются off-host только encrypted. Проверки после миграций
описаны ниже; plaintext новой backup и identity на Mac не сохранялись.

## Фактическая публичная и runtime приёмка

| Проверка 02.11.2026 | Результат |
|---|---|
| Доверенный HTTPS с Mac, default CA/hostname verification | TLS1.3, Let's Encrypt YE2; SAN совпадает с hostname, без отключения проверки |
| Срок сертификата | 02.11.2026 09:30:54 UTC — 31.01.2027 09:30:53 UTC |
| HTTP /health | 308 → https://3-25-53-31.sslip.io/health |
| HTTPS /health | 200, status=ok, database=ok; штатный endpoint выполняет SELECT1 |
| HTTPS /version | 200, version0.1.0, exact SHA f7020cda3908d7e0c40c0b0f840e322b3d6cfda5 |
| HTTPS /docs и /openapi.json | 200, text/html и application/json |
| Public JWT endpoints без/с неверным JWT | 401, единая безопасная ошибка, error.request_id совпадает с X-Request-ID |
| Raw /internal probes с Mac | Все26 получили404 на proxy, без backend request_id |
| Private service actor | Missing/wrong credential401; valid credential + отсутствующий synthetic actor404 telegram_profile_not_found; смешанный JWT/service400 ambiguous_actor |
| Public /internal с действительным service credential, проверка с EC2 | Пустой404 на proxy, без backend request_id; credential не покидал сервер |
| Telegram | Bot container и polling отсутствуют; diagnostic HTTP client не импортировал/не запускал bot |

21 raw request-target включал /internal, потомков, // и ///, percent/double-percent
encoding букв/slash, backslash, dot/traversal, semicolon, uppercase, encoded NUL,
absolute-form и network-path form. Ещё5 probes — POST/HEAD/OPTIONS/TRACE/CONNECT.
Query encoding на /health допускается; X-Original-URL/X-Rewrite-URL не меняют маршрут.
Проверки выполнены сырым HTTP поверх проверенного TLS, без нормализации HTTP-клиентом.

| Production service | Состояние | Публичные порты |
|---|---|---|
| db | Running/healthy, PostgreSQL17.11, persistent external volume | Нет |
| migrate | Exited0, restart_count0; migration_started1, migration_completed1, failed0 | Нет |
| api | Running/healthy, точный image digest выше, non-root | Нет |
| caddy | Running/healthy, UID10001 | Только80/443 |
| bot | Не создавался/не запускался | Нет |

У четырёх контейнеров OOM=false, restart_count0, фактический json-file driver
5m×3/compress=true. SG не публикует22/8000/5432/2375/2376; Docker API не опубликован.
Mac network/proxy принимает локальный connect() на эти порты, поэтому этот тест
не доказывает ни доступность EC2, ни отказ: независимый внешний TCP scan здесь
не подтверждён. Изоляция подтверждена actual SG rules и Docker port inventory;
неоднозначное сетевое наблюдение не выдаётся за успешную проверку портов.

API/migrate stdout проверен построчно: JSON, UTC/Z, фиксированные events и allowlist
полей. На400/401/private404 проверены server-generated UUIDv4 request_id, совпадение
HTTP/error/log; клиентский X-Request-ID игнорируется. Во всех фактических журналах
api/db/migrate/caddy отсутствовали server-only credentials и synthetic header,
query, password/email/Telegram-ID canaries. Caddy JSON не содержит request/error/
err_trace; access logging выключен. PostgreSQL native logs не объявляются API JSON.
Рабочие500/DB outages и live Telegram errors намеренно не вызывались: эти ветви
проверены unit/integration/isolated smoke в trusted CI, не fault injection на production.

## Backup после миграций и реальное изолированное восстановление

Штатный helper создал новый custom dump **35835bytes,84TOC entries**.
11 таблиц, Alembic revision `0006_settlement_notification_claim`; прикладных записей
на момент backup нет, alembic_version содержит1 строку. Это проверка схемы и
восстановления, а не доказательство восстановления заполненной финансовой истории.

Plaintext SHA256: `3be88e622aaec090deda2e978b09ce23a3090bee546d838dc28c85551b92bdaa`.
Encrypted off-host SHA256: `0ccd3b4580a3aea45b7385429bf103d267071295855cd0aa2022fe807b2d56ad`.

pg_restore --list и реальный pg_restore --single-transaction прошли в PostgreSQL17.11
с network=none, read-only root, tmpfs-only PGDATA, без production mount/ports.
Совпали имена таблиц, columns/defaults, индексы, FK/CHECK/UNIQUE и числа строк,
включая Alembic metadata. Четыре CHECK после dump/reparse получили нормализованные
скобки/array casts; исходные expressions повторно разобраны PostgreSQL в временных
таблицах **изолированного** кластера и дали те же определения, что restore.
Строковое отличие не скрывалось исключением constraints из сравнения.

Restricted runtime/admin отдельно provisioned с новыми test secrets; LOGIN,
NOSUPERUSER и ownership/DDL-права проверены. Database-only archive не содержит
cluster-global roles/passwords и original OWNER/ACL: восстановление ролей требует
отдельного защищённого provision. Production admin password не копировался.
Production DB не перезапускалась/не восстанавливалась; env, admin store и роли
не менялись. Временный контейнер удалён, volume inventory не изменён.
Предыдущий разрешённый DB restart подтвердил persistence ролей; destructive
rollback и перезапуск рабочей системы ради ошибки не выполнялись.

Новая off-host копия на Mac — только age ciphertext36035bytes,0600 в0700.
Decrypt из Keychain и независимой server recovery identity совпал с SHA256
исходного архива; повреждённый ciphertext отклонён. Ключи/пароли в evidence/Git
не включаются. Свободно **около12,6GiB** диска, доступно **около1,18GiB RAM**,
swap2GiB практически свободен; OOM/restart loops не наблюдались.

## Acceptance matrix и оставшиеся границы

Номера строк соответствуют порядку чекбоксов открытых Issues #59/#60.

| Issue / критерий | Статус | Evidence / граница |
|---|---|---|
| T-09.1 Topology/non-root/private DB/one migration | verified для API/DB/Caddy; pending live bot | Production inventory выше; один bot предусмотрен только выключенным profile |
| T-09.2 Trusted CD, immutable GHCR, concurrency/least privilege | verified | Trusted CI/publish и approved Release; guard проверил main/provenance/Environment |
| T-09.3 Approved SHA deployment/health/version | verified | Release41428440222, state/current.json и внешние health/version |
| T-09.4 HTTPS/private boundary/service actor | verified | Trusted TLS,26 raw probes, private actor negative/valid-credential checks |
| T-09.5 Environment/secrets/fail closed | verified | Actual protections/approval, pinned host,0600 env; token бота отсутствует и polling запрещён |
| T-09.6 Safe rollback/runbook | verified в dry-run/isolated scope | Controller tests, runbook, реальный isolated restore; destructive production rollback не выполнялся |
| T-09.7 Docs/tests/independent review | pending review этого evidence PR | Main CI5/5; documentation PR требует отдельный review |
| T-09.8 Actual HTTPS/GHCR/health/version/private DB | verified | Фактический deployment и таблицы результатов выше |
| T-09.9 Final acceptance/closure PR | pending owner acceptance | Refs #59; live polling не разрешён, Issue автоматически не закрывается |
| T-10.1 JSON API/bot/request_id | verified code + live API/migrate; live bot не запускался | Main CI и production logs/correlation выше |
| T-10.2 Privacy/redaction/negative tests | verified в указанном scope | CI400/401/500/Telegram failures; live400/401/private actor; prod500/Telegram не вызывались |
| T-10.3 Rotation/health/volumes | verified для работающих services, bot config checked | Реальный log driver5m×3 и health; бот выключен |
| T-10.4 Incident/rollback runbook | verified наличие | [Runbook](INCIDENTS_AND_ROLLBACK.md); backup/isolated restore выше |
| T-10.5 Quality/CI/independent review | pending review этого evidence PR | Trusted main CI5/5; новый docs PR проверяется отдельно |
| T-10.6 Final acceptance/closure | pending owner acceptance | Refs #60; Issues не закрыты автоматически |

Технические сигналы **G5** из MASTER_ROADMAP (GHCR SHA, реальный trusted HTTPS,
health с PostgreSQL, exact version SHA, external /internal deny, private DB)
подтверждены. Это не закрывает весь **M5**, T-01/G1, live G2/G3/G4 или чужие
O-08/L-06. Приёмка T-09/T-10 и оценка преподавателя остаются отдельными решениями.

Следующие действия владельца: review evidence PR; принять границы критериев;
для live bot отдельно предоставить credential безопасно и разрешить ровно один
polling process. До следующего deployment нужно новое явное разрешение и
независимый Environment approval; rollout flag оставлен false.
Временный sslip.io и непостоянный EC2 public IP требуют повторной DNS/TLS проверки
после stop/start. Backup schedule/retention не автоматизированы. Recovery проверен
в Keychain и на EC2, дополнительная offline escrow остаётся рекомендацией владельцу.
