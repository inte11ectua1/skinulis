# T-09: GitHub OIDC → SSM → SSH

01.11.2026 · [Issue #59](https://github.com/inte11ectua1/skinulis/issues/59).
Transport принят в merged PR #68. [Актуальный readiness evidence](T-09_AWS_READINESS.md):
main CI/GHCR и настоящий local SSH-over-SSM проверены; GitHub OIDC ожидает IAM
provider inventory (Organizations SCP Deny) и создания runner role.
Rollout flag=false; production deployment и Telegram polling не выполнялись.

## Границы доверия

```text
trusted main CI → release guard → immutable GHCR digest
                                      ↓
manual main run → production independent approval → repeated release guard
                                      ↓
GitHub OIDC → temporary STS role → SSM AWS-StartSSHSession → SSH :22
                                      ↓
pinned ED25519 host key + dedicated deployment key → skinulis-deploy
                                      ↓
existing exact-release deployment controller (only operation=deploy)
```

SSM — только туннель к уже работающему SSH, не root shell/Run Command. Не нужны
inbound SSH от GitHub runner, bastion, платный runner или долгоживущие AWS access
keys. Существующий административный SSH с Mac не меняется. EC2 agent использует
свою **отдельную** `skinulis-ec2-ssm-role` / AmazonSSMManagedInstanceCore, а runner —
новую `skinulis-github-production`. Не прикреплять runner policy к EC2 role.
Исходящий HTTPS к AWS SSM/ssmmessages endpoints должен оставаться доступным.

Состояние EC2: владелец подтвердил encrypted EBS (`aws/ebs`), закрытые SG ports
8000/5432, IAM instance profile, Online agent и успешную интерактивную SSM-сессию.
Это не доказательство permissions новой GitHub роли и не публичный HTTPS acceptance.

Только deploy job получает `id-token: write`, после Environment approval. Guard и
publish не получают AWS credentials; PR CI не запрашивает OIDC или prod secrets.
Workflow разрешает только manual `main`; проверяются ancestry SHA, exact trusted CI
и все пять jobs. Guard повторяется после approval **до** AssumeRole. Проверяются
reviewers, prevent_self_review, protected branches и `can_admins_bypass=false`.

Environment subject сам по себе не кодирует ветку: защиту от PR обеспечивают вместе
точный subject, protected Environment, workflow main condition и release guard.
Не разрешать PR refs в Environment и не добавлять workflows, использующие этот
Environment без этих проверок. OIDC trust не делает произвольный SHA доверенным.

## AWS Console: действия владельца, без автоматического применения

В JSON заменить `<AWS_ACCOUNT_ID>` на 12-значный ID **того же** AWS account;
`<INSTANCE_ID>` — на ID EC2 skinulis-prod из задания/EC2 Console. В текущем T-09
это `i-036a41b6d30814aad`, region `ap-southeast-2`. Имена ключей policy и
`${aws:userid}` не менять; последняя строка — IAM variable, не placeholder.
Account ID/ARN — configuration, не secret; реальные значения не нужны в Git.

1. **IAM → Identity providers → Add provider → OpenID Connect.** Provider URL:
   `https://token.actions.githubusercontent.com`; audience: `sts.amazonaws.com`.
   Если такой provider уже есть, проверить URL/audience и использовать его;
   не создавать дубликат. Не вводить случайный/stale TLS thumbprint вместо
   штатной проверки AWS Console. Никаких access keys создавать не нужно.
2. **IAM → Roles → Create role → Custom trust policy.** Вставить
   [github-oidc-trust.json](../../deploy/aws/github-oidc-trust.json) после замены
   account ID. Имя роли **`skinulis-github-production`**, без IAM path.
   Не выбирать AdministratorAccess/PowerUserAccess/AmazonSSMFullAccess.
3. **Role → Permissions → Add permissions → Create inline policy → JSON.**
   Вставить [github-ssm-permissions.json](../../deploy/aws/github-ssm-permissions.json),
   заменить оба placeholders; имя `SkinulisProductionSshSessions`.
   Разрешены только StartSession к одной EC2 и AWS-StartSSHSession, data channel,
   завершение своих сессий. Никаких EC2/SG/IAM writes, SendCommand, shell/port-forward
   documents, Secrets Manager/Parameter Store, PassRole или доступа к DB secrets.
4. **Role → Trust relationships:** сверить exact audience и exact subject ниже.
   Session name ограничен `skinulis-gh-*`; workflow использует run ID/attempt.
   Max session duration оставить 1 hour; job запрашивает 1800 seconds, timeout25min.
5. Скопировать role ARN для GitHub Environment. Передать можно ARN, не access keys.
   Данные политики пока являются reviewable proposal; реальный IAM authorization
   проверяется только защищённым `check-transport` после принятия PR.

### Точный OIDC subject этого репозитория

Read-only GitHub API `GET /repos/inte11ectua1/skinulis/actions/oidc/customization/sub`
01.11.2026 вернул `use_default=true`, `use_immutable_subject=true` и prefix
`repo:inte11ectua1@105117564/skinulis@1421315056`. Поэтому policy использует:

```text
repo:inte11ectua1@105117564/skinulis@1421315056:environment:production
```

Не заменять на legacy subject без ID, `repo:*` или `pull_request`. Не менять
репозиторный OIDC template ради совпадения со старым примером. При transfer/rename
репозитория перепроверить canonical repo/IDs и согласовать изменения trust policy.
Никогда не печатать OIDC JWT или временные AWS credentials для диагностики.

### Обоснование прав и ограничения

StartSession ограничен region/account/instance и **единственным** AWS-owned
document (у его ARN пустой account segment). `SessionDocumentAccessCheck` требует
штатной проверки доступа к document при наличии ключа. Без дополнительных policies
обычный shell document не разрешён. AWS-StartSSHSession позволяет задавать port;
наш proxy фиксирует22 и не принимает произвольные параметры от workflow input.

`ssmmessages:OpenDataChannel` имеет `Resource: "*"`, потому что service authorization
reference не поддерживает resource ARN для этого action; ограничен RequestedRegion.
Это не разрешение StartSession на другие EC2. Не заменять policy целиком на `ssm:*`.
TerminateSession ограничен ARN сессии в account/region и **обоими** AWS-managed tags:
target-id равен нашей EC2, session-id равен `${aws:userid}` текущей STS session.
Это вариант для федеративных ролей, а не неверное сопоставление `${aws:username}`.
ResumeSession/List/Describe/SendCommand transport не использует и не разрешает.
`sts:GetCallerIdentity` нужен для проверки ожидаемых account/role/session и не
требует отдельного Allow. У runner нет права изменять IAM/SG/EC2.

SSM SSH stream зашифрован SSH: Session Manager не записывает содержимое команд.
CloudTrail сохраняет события AssumeRole/StartSession/TerminateSession, не runtime
secrets. Это ограничение аудита, не обещание записи SSH-сессии.
Deployment user не имеет sudo, но Docker group root-equivalent: компрометация
approved deploy job/key/role даёт широкие права на **эту EC2**. Не считать это
изоляцией от root; Environment/human review и защита main обязательны.

## GitHub: проверить Environment, затем добавить variables

**Settings → Environments → production**:

- Required reviewer: Олег `pylinolg-max` или Лера `Valeria18-new`;
  Prevent self-review включён, admin bypass выключен.
- Deployment branches: Protected branches only; canonical main защищена.
- Сохранить secrets `SSH_PRIVATE_KEY` (отдельный deployment key, **не** EC2 owner
  key) и `SSH_KNOWN_HOSTS` (уже out-of-band проверенный ED25519 ключ).
- Добавить variables `AWS_ACCOUNT_ID`, `AWS_ROLE_ARN`, `AWS_INSTANCE_ID`.
  Region закреплён `ap-southeast-2` в workflow/proxy/policy.
- Сохранить `SSH_HOST` **без замены на instance ID**: это lookup alias исходной
  записи known_hosts; `SSH_USER=skinulis-deploy`, `SSH_PORT=22`,
  `SSH_DEPLOY_DIR=/opt/skinulis`. Сетевой target — AWS_INSTANCE_ID через SSM,
  SSH_HOST больше не означает прямое TCP-подключение.
- Repository variable `PRODUCTION_ROLLOUT_ENABLED=false`.

SSH использует StrictHostKeyChecking=yes, только ED25519, явный private known_hosts,
GlobalKnownHostsFile=/dev/null, HostKeyAlias=SSH_HOST, public-key auth, без agent/
port forwarding и пользовательского SSH config. `CheckHostIP=no` соответствует
proxy transport: проверяется прежний host-key alias, публичный IP не является
дополнительным источником доверия. Нет accept-new, ssh-keyscan или direct fallback.
AWS failures/SSM offline/host-key mismatch завершают job с ошибкой до controller.

AWS CLI v2 поставляется GitHub ubuntu-24.04 runner; отсутствие v2 — отказ.
Session Manager plugin **1.2.896.0** загружается только с официального versioned
AWS HTTPS URL и проверяется pinned SHA256 до установки. Configure credentials
action pinned full commit SHA; credentials получаются OIDC, прежние очищаются.
Runtime DB/JWT/service/Telegram secrets остаются на EC2 и в runner не передаются.

## Проверка подключения без production rollout

После independent review и **человеческого** merge transport PR:

1. Дождаться успешных пяти main CI jobs и GHCR публикации соответствующего SHA.
2. Actions → Release → Run workflow → branch **main**, полный проверенный SHA,
   **operation=check-transport**, enable_polling=false, rollback_compatible=false.
   Flag оставитьfalse. Guard/publish выполняют обычную проверку digest/provenance.
3. Другой участник подтверждает protected production Environment.
4. Job проверяет AWS identity, выполняет SSH через SSM с прежним host-key pin;
   read-only команда проверяет OS username, наличие deploy root и Docker version.
   **Не отправляет release bundle, не запускает controller, containers/migrations
   или polling, не читает production.env.**
5. Сохранить run URL, успешный check message и CloudTrail AssumeRole/StartSession.
   В AWS проверить, что завершилась именно эта сессия; оставшуюся сессию может
   закончить владелец через Session Manager. Не публиковать session credentials.

При AccessDenied сверить exact immutable sub, audience, role ARN, region, instance
и AWS-owned document ARN; не расширять права до wildcard. При TargetNotConnected
проверить agent/profile/outboundHTTPS. При host-key error остановиться, повторно
сверить fingerprint через AWS console; не отключать StrictHostKeyChecking.

Только после успешного реального transport check, DNS/TLS/runtime/backup readiness
и **отдельного разрешения Тимура** обсуждается `operation=deploy`/flag=true.
Первый deploy без polling. Merge, rollout и live Telegram это задание не разрешает.

## Проверки кода и evidence boundary

```sh
bash -n scripts/install_ssm_plugin.sh
shellcheck scripts/install_ssm_plugin.sh
actionlint
uv run pytest tests/unit/test_release_policy.py tests/unit/test_remote_deploy.py tests/unit/test_ssm_transport.py
```

Тесты подменяют AWS/SSH network boundaries: проверяют отказ от недоверенного SHA,
неверной роли/отсутствующих credentials, ошибок SSM/host key, запрет direct fallback
и no-mutation diagnostic mode. Они не доказывают фактическое AssumeRole/IAM/SSM
соединение. PostgreSQL/Docker/routing regressions проверяются обычным CI отдельно.
Transport code берётся из trusted workflow commit, а Compose/controller bundle —
из exact guarded release checkout; старый SHA не возвращает старый direct transport.
PR #67 отдельно добавляет backup helper в allowlist; этот PR от main его не дублирует.

Основания: [GitHub AWS OIDC](https://docs.github.com/en/actions/how-tos/secure-your-work/security-harden-deployments/oidc-in-aws),
[immutable OIDC subjects](https://docs.github.com/en/actions/reference/security/oidc),
[AWS SSH over SSM](https://docs.aws.amazon.com/systems-manager/latest/userguide/session-manager-getting-started-enable-ssh-connections.html),
[session ownership для federated roles](https://docs.aws.amazon.com/systems-manager/latest/userguide/getting-started-restrict-access-examples.html),
[ssmmessages authorization](https://docs.aws.amazon.com/service-authorization/latest/reference/list_ssmmessages.html),
[plugin releases](https://github.com/aws/session-manager-plugin/releases).
