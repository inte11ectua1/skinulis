# T-09 — AWS readiness после merge #66/#67/#68

01.11.2026 · [Issue #59](https://github.com/inte11ectua1/skinulis/issues/59).
**Production rollout, публичный HTTPS и G5 не выполнены.** IAM provider/roles/
policies не создавались и не изменялись. Ниже только реальные проверки подготовки.

## Trusted main, CI и registry

- PR #66/#67/#68 merged; main `dd78027bfdf293568284d36719b5ac1929c337ac`.
- [Main CI](https://github.com/inte11ectua1/skinulis/actions/runs/41333607302):
  lint/types/tests/docker-build/ci success; **1175 unit +402 PostgreSQL integration
  =1577 tests**, combined app/bot branch coverage **94,76%**.
- [Release](https://github.com/inte11ectua1/skinulis/actions/runs/41334146071):
  guard/publish success, deploy **skipped**.
- Реальный опубликованный и скачанный на EC2 image:
  `ghcr.io/inte11ectua1/skinulis@sha256:e299e3638f1721207140c8db7bddafff1b66373200a6e2feb4241c8a02fd3eb9`.
  Anonymous GHCR manifest/config и Docker inspect подтвердили linux/amd64,
  OCI revision=полный main SHA, USER=skinulis. Runtime imports/JWT/service settings
  проверены в одноразовом non-root контейнере без сети и API/polling процесса.

## AWS и GitHub Environment

Read-only EC2/SSM API и SSH подтвердили:

- EC2 running, прежний public IP; t3.small, Ubuntu24.04 AMD64.
- EBS40GiB gp3 encrypted, около34GiB free; RAM1,9GiB, около1,4GiB available,
  swap отсутствует. Это не нагрузочный O-08 test.
- Docker29.9.2 / Compose5.6.1 active; production containers не запущены.
- Instance profile skinulis-ec2-ssm-role; Agent3.3.4793.0, PingStatus=Online.
- SG: public TCP80/443;22 только administrative /32 и AWS browser SSH prefix list.
  Правил8000/5432/2375/2376 нет; default route → active Internet Gateway.
  SG/routes/SSH configuration не менялись.
- EIP association отсутствует: stop/start может сменить public IP;
  платные ресурсы не создавались.
- GitHub production reviewers Олег/Лера, prevent_self_review,
  can_admins_bypass=false, protected branches only повторно проверены.
- Добавлены AWS_ACCOUNT_ID/AWS_ROLE_ARN/AWS_INSTANCE_ID по EC2 identity.
  ARN — ожидаемая роль, **не** доказательство её существования. SSH variables/
  secrets сохранены, SSH_HOST — прежний host-key alias; rollout flag=false.

## Реальный local SSM и IAM blocker

На Mac установлен официальный подписанный/notarized AWS CLI2.39.3 в user directory
и Session Manager plugin1.2.896.0 из подписанного macOS package. Системный daemon
плагина не устанавливался. Владелец завершил browser `aws login`; долговременные
access keys не создавались. STS подтвердил project account и временную
административную роль AccountFullAccessRole.

Через **локальные административные**, а не GitHub OIDC credentials прошёл настоящий
AWS-StartSSHSession → SSH с dedicated deployment key и pinned ED25519 known_hosts.
StrictHostKeyChecking=yes; remote username skinulis-deploy, Docker29.9.2.
CloudTrail StartSession event **a353aa13-b6ad-4947-8429-01ff6c85e832**, UTC
2026-11-01T18:08:34Z, document=AWS-StartSSHSession, errorCode отсутствует.
Controller/migrations/polling этой SSH-сессией не запускались.

Это **не GitHub OIDC**: GetRole(skinulis-github-production) вернул NoSuchEntity;
protected `operation=check-transport` пока не запускался. IAM provider Get/List
реально возвращают AccessDenied с explicit Deny в Organizations SCP.

Read-only Policy Simulator показал Organizations explicitDeny для OIDC Get/List/
Create, CreateRole/PutRolePolicy — allowed. Это предварительный анализ, **не IAM
write attempt и не гарантия авторизации**: агрегированная SSM simulation также
дала deny, хотя реальное SSM SSH подключение успешно. Без полного request context
симуляцию нельзя выдавать за live result.

Подготовлены private copies текущих trust/permissions JSON с account/instance
substitutions; `${aws:userid}` сохранён. Тимур отдельно разрешил минимальное
создание provider и отсутствующей runner role с policies из принятой main.
**После разрешения выполнен реальный CreateOpenIDConnectProvider**, UTC
2026-11-01T18:53:31Z: AWS вернул AccessDenied, explicit Deny в Organizations SCP
`p-lua7mktn`. Provider не создан. Выполнение остановлено до CreateRole/PutRolePolicy;
успешных IAM изменений нет. Это уже подтверждённый API отказ создания, а не
предположение на основании simulator. Ни обход SCP, ни расширение permissions
или переключение на другую identity не предпринимались.

Следующий шаг владельца: передать Organizations administrator точный AccessDenied
и запросить узкое исправление SCP для project account/GitHub OIDC provider:
Get/List/Create provider. Не отключать SCP целиком, не создавать root access keys
и не выдавать runner AdministratorAccess. Allow в IAM role не устраняет explicit
SCP Deny. После исправления доступа — повторить read-only inventory и применить
уже разрешённый setup в прежних границах, затем проверить GitHub transport.
Изменения существующих несовпадающих IAM ресурсов этим разрешением не покрываются.

## DNS, controller и backup

Кандидат **13-211-201-3.sslip.io** через Google и Cloudflare DoH разрешается в
текущий EC2 public IP; AAAA отсутствует, CAA запрета нет у hostname и parents.
Бесплатное имя не требует покупки/создания DNS resource. Ограничения: сторонний
DNS, ACME rate limits/availability и смена имени при смене IP. Настоящий публичный
TLS certificate **не получался/не проверялся**, Caddy/HTTP сервисы не запускались.
Локальный resolver дал синтетический240.0.1.197; TCP connect с Mac не считался
доказательством открытого EC2 порта. Проверены independent DoH, AWS SG и EC2 sockets.

Original production.env600, distinct generated secrets и пустой Telegram token
проверены без печати значений. PUBLIC_DOMAIN не менялся: кандидат проверен только
в disposable private copy. Canonical controller текущей main прошёл **dry-run**,
без --execute, production DB init/миграций или изменения original runtime env.

Read-only probes: production PostgreSQL volume пустой, PG_VERSION отсутствует;
Caddy data/config volumes пустые, UID10001/mode700. Backup helper сохранён в exact
release bundle allowlist после #67/#68.
Предыдущий synthetic dump с проверенным SHA256 снова восстановлен в отдельной
PostgreSQL17.11 (tmpfs, network=none/no ports): probe row=1, archive не изменился.
Удалён только собственный временный test container. Production data/volumes не
удалялись. Это test backup; production DB ещё не существует.
[Предыдущий backup/persistence evidence](T-09_EC2_PREFLIGHT.md).

## Оставшаяся приёмка

| Критерий #59 | Состояние / evidence |
|---|---|
| Topology/private DB/API/non-root/migration design | verified main CI/Compose; live production pending |
| Trusted main → SHA GHCR digest | verified: CI/Release/image выше |
| GitHub OIDC → SSM → approved SSH deploy | blocked IAM inventory/SCP и отсутствующей ролью; local SSM verified отдельно |
| Public HTTPS и /internal denial | pending rollout; isolated main Docker smoke success |
| Environment/secrets | Environment verified; новой runner IAM role ещё нет |
| Backup/restore, rollback без DB downgrade | synthetic restore verified, controller/unit checks success; production rollback не выполнялся |
| Документация/CI/review | evidence обновлено; follow-up требует independent review |
| Реальные HTTPS /health DB, exact /version, external private-port probes | pending: public deployment не разрешён |
| Закрытие #59/G5 | pending полной реальной приёмки и подтверждения Тимура |

После IAM readiness — protected check-transport на актуальной main и independent
approval. Затем domain/runtime/backup readiness и **отдельное** разрешение первого
публичного rollout с enable_polling=false. Live Telegram/merge не автоматизируются.
