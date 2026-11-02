# T-09: новый AWS EC2 и protected CD preflight

01.11.2026 · Refs [#59](https://github.com/inte11ectua1/skinulis/issues/59).
По отдельному разрешению Тимура подготовлен новый сервер в новом AWS account.
Старый EC2/account не изменялись. Это **не production rollout и не G5 acceptance**.
Адреса доступа, account/instance/SG identifiers, email и значения credentials
остаются в закрытых operator evidence вне Git.

## Созданные ресурсы

- Один On-Demand **t3.small**, Sydney `ap-southeast-2`, Linux AMD64,
  официальный стандартный Canonical Ubuntu 24.04.5 LTS, AMI от 23.10.2026.
  Owner Canonical и отсутствие paid Marketplace product codes проверены API.
- Один root **20 GiB gp3**, 3000 IOPS/125 MiB/s без платных надбавок,
  encrypted AWS-managed EBS key. Использованы существующие default VPC/subnet/IGW;
  новых EIP/NAT/ALB/RDS/PrivateLink endpoints и платных runners нет.
- IMDSv2 required, hop limit1; detailed monitoring выключен. CPU credits
  **Standard**: нет Unlimited surplus charges, но после исчерпания credits
  производительность ограничивается baseline. Это не нагрузочное тестирование.
- Security Group разрешает публичные TCP80/443. Inbound22 отсутствует:
  административный SSH и CD идут через SSM. Нет правил8000/5432/2375/2376.
  До rollout80/443 на самом host ещё не слушаются; это не публичный HTTP acceptance.
- Отдельные `skinulis-ec2-ssm-role`/instance profile и
  `skinulis-github-production` OIDC role. Новый EC2 admin key pair и отдельный
  deployment key; старые ключи не копировались.

## Host и runtime preparation

Docker Engine/CLI **29.9.2**, containerd **2.4.2**, Compose **5.6.1**,
Buildx **0.38.1** установлены из официального Docker APT repository.
Docker/containerd enabled, Docker active; daemon только Unix socket.
SSM Agent **3.3.4793.0** Online; Ubuntu SSH active, password/root login выключены.
Host Python3.12.3 поддерживает controller; runtime image сохраняет Python3.12.15.

На encrypted root создан swap2GiB0600, swappiness10. После bootstrap было
около1.4GiB available RAM и14GiB свободного диска; это снимок без application load.
При проверке sshd после установки обнаружен отсутствующий `/run/sshd`
у socket-activated Ubuntu SSH; каталог подготовлен, `sshd -t` и reload прошли.
Изменения выполнялись только на новом сервере.

`skinulis-deploy` имеет locked password, отдельный restricted authorized key,
не получает sudo и входит в docker group. **Docker group root-equivalent**:
approved CD имеет широкие права на эту EC2; не считать его непривилегированным.
`/opt/skinulis`/releases/tests0750, state/backups0700, runtime env0600.
DB/JWT/service credentials сгенерированы независимо на сервере из48 random bytes
каждый, без вывода значений и передачи runner-у. TELEGRAM_BOT_TOKEN пустой.
Подготовлено временное IP-derived DNS name; DNS-over-HTTPS подтвердил A record
нового EC2. Доверенный TLS ещё не выпускался. Обычный public IPv4 может
измениться после stop/start.

Созданы **пустые** external volumes skinulis-production-postgres,
skinulis-production-caddy-data/config; Caddy roots UID/GID10001,0700.
PostgreSQL data со старого account не переносились; production БД не инициализирована.

## Подтверждённые проверки

Источник bundle/image — `main` **dd78027bfdf293568284d36719b5ac1929c337ac**:
[trusted push CI 5/5](https://github.com/inte11ectua1/skinulis/actions/runs/41333607302).

```text
ghcr.io/inte11ectua1/skinulis@sha256:e299e3638f1721207140c8db7bddafff1b66373200a6e2feb4241c8a02fd3eb9
```

- На новом EC2 выполнен реальный anonymous digest pull. Проверены RepoDigests,
  OCI source/revision, linux/amd64 и non-root USER=skinulis.
- Точный allowlisted bundle из main установлен под releases/full-SHA.
  `docker compose ... config --quiet` и настоящий controller **dry-run** прошли.
- Краткоживущий контейнер этого image с `--network none`, read-only FS и
  fresh runtime env проверил Settings/JWT/service validators. Он не запускал
  API, миграции или polling, не обращался к PostgreSQL и был удалён через `--rm`.
- Реальный Mac → AWS-StartSSHSession → SSH под `skinulis-deploy` вернул
  правильного пользователя и Docker29.9.2. Credentials этой проверки — временная
  browser-authorized admin session, **не GitHub OIDC role**.
- ED25519 host key получен через authenticated AWS EC2 Console Output, pin
  проверен SSH с **StrictHostKeyChecking=yes**. Намеренно другой known_hosts key
  дал exit255/host-key rejection. Direct TCP fallback отсутствует.
- `uv sync --frozen`, `uv lock --check`, Ruff lint/format, strict mypy132 files
  и **1175 unit tests** прошли; среди них104 release/deployment/remote/SSM cases.
  Mock network boundaries этих unit cases не доказывают AWS authorization.

На **новом** EC2 также проверен настоящий backup helper из этого main bundle:
PostgreSQL17.11, свежий UUID test project, две отдельные test volumes и internal
network без published ports. Synthetic row → custom pg_dump → pg_restore в другую
БД → restart target → тот же row. Archive1809 bytes,0600; копия вне EC2 на Mac
проверена SHA256 `e6057eda4931f3e4f90630e519faf26360d619b9129165e72e8f7d840cabfb67`.
Test credentials удалены, удалены только собственные UUID containers/network/
volumes; archive сохранён. Production volumes не монтировались. Это проверка
механизма, не backup пользовательских данных и не настроенное расписание retention.

## OIDC и GitHub Environment

Существующий GitHub OIDC provider проверен по URL/audience. Новая role создана
по JSON **из принятой main**, с подстановкой только нового account/instance ID.
Trust и inline permissions прочитаны обратно и совпали с отрендеренными JSON.
Нет дополнительных managed policies у runner role. Session maximum1h,
workflow запрашивает1800s. Exact immutable subject:

```text
repo:inte11ectua1@105117564/skinulis@1421315056:environment:production
```

SSM permissions ограничены единственным новым EC2, AWS-StartSSHSession,
data channel в Sydney и завершением собственных tagged sessions.
Runner не имеет SendCommand/PassRole/IAM/EC2 writes. Administrative RunCommand
использовался владельцем для bootstrap, не добавлен в GitHub role.

В existing Environment `production` обновлены семь destination variables и
SSH_PRIVATE_KEY/SSH_KNOWN_HOSTS. Новые ключи и host pin, без переноса старых secrets.
До/после API подтвердил те же правила: independent Олег/Лера,
prevent_self_review=true, protected branches only, can_admins_bypass=false.
Repository variable **PRODUCTION_ROLLOUT_ENABLED=false**.

Запущен защищённый [Release check-transport](https://github.com/inte11ectua1/skinulis/actions/runs/41346841056)
на точном trusted main SHA: **guard/publish success, production approval pending**.
Pending deployments API показывает reviewers Олег/Лера и
`current_user_can_approve=false`. До их approval реальный GitHub OIDC → SSM
**не verified**. У job имя `deploy`, но input `operation=check-transport`
выбирает только read-only branch, без controller/bundle/containers/migrations.

## Стоимость и оставшееся

AWS Pricing API на01.11.2026: Linux t3.small Sydney **$0.0264/hour**,
gp3 **$0.096/GiB-month**, public IPv4 **$0.005/hour**.
При730h: compute$19.272 +20GiB$1.92 +IPv4$3.65 = **$24.84/month**
до credits, налогов и дополнительных transfer/backup costs. SSM Session Manager
для EC2 не имеет отдельной платы; paid JIT node access не включался.
Источники: [EC2](https://aws.amazon.com/ec2/pricing/on-demand/),
[EBS](https://aws.amazon.com/ebs/pricing/), [IPv4](https://aws.amazon.com/vpc/pricing/),
[SSM](https://aws.amazon.com/systems-manager/pricing/).

API нового account показал Free plan ACTIVE и **$120 remaining credits**;
это снимок, не обещание нулевого счёта или бессрочной работы. Настроенный ранее
месячный бюджет$20 с ACTUAL alerts$10/$20 сохранён и не повышался.
Credits/refunds исключены из бюджета; alerts не являются hard spending cap.
Расходы старого EC2 остаются в старом account и новым бюджетом не покрываются.

Остаются независимое approval и фактический успешный OIDC check-transport;
выбор устойчивого DNS и публичный ACME, backup реальных данных при их появлении,
проверка DB runtime privileges, отдельное разрешение на public rollout,
реальные HTTPS/health/PostgreSQL/version/private routing/persistence acceptance.
После этого Telegram token и разрешение на единственный polling — отдельно.
Старые isolated PG/TLS/backup evidence относятся к старому EC2, а не к новому.
Issue #59 остаётся open; T-10/O-08/L-06 не выполнялись, G5 не verified.
