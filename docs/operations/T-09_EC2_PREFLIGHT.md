# T-09: фактическая подготовка EC2, 01.11.2026

Refs [#59](https://github.com/inte11ectua1/skinulis/issues/59).
Это evidence подготовки и изолированных тестов, **не production acceptance/G5**.
Тимур разрешил installation/preparation EC2. Публичный rollout и live Telegram
должны получить отдельное подтверждение после устранения блокеров.
Access addresses, instance/SG identifiers, ключи и runtime credentials здесь не публикуются.

**Последующий срез:** [AWS readiness после merged #66/#67/#68](T-09_AWS_READINESS.md).
Он обновляет main SHA/digest, EC2 profile/SG/EBS/SSM и IAM blocker. Исторические
формулировки ниже про отсутствующий instance profile и несозданный transport
не отменяют более поздние результаты; публичного rollout по-прежнему нет.

## Источник релиза

- [PR #64](https://github.com/inte11ectua1/skinulis/pull/64) merged.
- [PR #65](https://github.com/inte11ectua1/skinulis/pull/65) closed без merge;
  замены VPS ноутбуком нет. [PR #66](https://github.com/inte11ectua1/skinulis/pull/66)
  open, не является принятой main.
- Проверенная main: **3f67828c40be6e14786816ffbfbcb867fcc79a7f**.
- [Main push CI 5/5 success](https://github.com/inte11ectua1/skinulis/actions/runs/41235940015):
  lint, types, tests, docker-build, ci.
- [Release](https://github.com/inte11ectua1/skinulis/actions/runs/41236310059): guard и
  publish success, deploy skipped. Этот job не является evidence SSH rollout.
- Реальный публичный GHCR manifest и anonymous pull проверены с EC2, OCI revision
  равен main SHA, source=inte11ectua1/skinulis, platform=linux/amd64, user=skinulis.

```text
ghcr.io/inte11ectua1/skinulis@sha256:7d6b737f1a41a3b7f73102bef5c17b77c4793f65e1ecf7332448f92c590882c3
```

После review/merge follow-up перед rollout нужно заново проверить актуальные main,
CI и digest; подготовленный SHA не является разрешением развернуть старую версию.

## EC2 и системные изменения

| Проверка | Фактический результат |
|---|---|
| ОС/архитектура/type | Ubuntu24.04.5 LTS, x86_64, t3.small подтверждены |
| Ресурсы после подготовки | 2 vCPU,1.9GiB RAM, около1.4GiB available,34GiB свободно на root |
| Docker official APT | Engine/CLI29.9.2, containerd2.4.2, Buildx0.38.1, Compose5.6.1 |
| systemd | Docker/containerd enabled и active; hello-world amd64 успешно завершён |
| Docker API | Unix socket; dockerd -H fd://, TCP2375/2376 не слушаются |
| Python host | 3.12.3, соответствует controller≥3.12; imagePython3.12.15 сохранён |
| SSH | Trusted AWS ED25519 pin, StrictHostKeyChecking=yes; bootstrap доступ сохранён |
| Deployment user | Отдельный пользователь без sudo, отдельный ED25519 key, restrict в authorized_keys |
| Docker privilege | Только deployment user добавлен в docker; доступ фактически root-equivalent, это остаточное ограничение |
| Каталоги | /opt/skinulis/releases, state, backups, tests; private production.env0600 |
| Volumes | Три заранее созданных external production volumes; Caddy roots UID/GID10001 |
| Runtime secrets | DB/JWT/service сгенерированы непосредственно на EC2 и проверены настоящим image без сети |
| Polling/domain | Telegram token пустой, polling не запускался; PUBLIC_DOMAIN пока пустой |
| Swap/EBS | Swap не создавался: EBS encryption требует проверки через AWS Console |

Пакеты ставились из официального HTTPS Docker APT с Signed-By keyring; общий upgrade
ОС, смена sshd/SSHD access policy и разрушительные Docker cleanup не выполнялись.
После всех тестов running containers отсутствуют. TCP listeners: SSH и loopback DNS;
80/443/8000/5432/2375/2376 не слушаются. Это не заменяет audit AWS SG/NACL/routes.

## GitHub Environment

Через API создан production Environment, повторный GET подтвердил:

- required reviewers: pylinolg-max или Valeria18-new, минимум один independent approval;
- prevent_self_review=true, **can_admins_bypass=false**;
- protected_branches=true, custom_branch_policies=false;
- secrets SSH_PRIVATE_KEY/SSH_KNOWN_HOSTS и четыре destination variables установлены;
- deployment key отличается от AWS bootstrap key; вход с новым ключом реально проверен;
- repository PRODUCTION_ROLLOUT_ENABLED=**false**.

Runtime secrets в GitHub не передавались. Политики branch protection не менялись.
Environment approval не запрашивался, workflow deployment не dispatch-ился.
Возможность прямого SSH от GitHub-hosted runner пока не подтверждена и не разрешена
широким ingress. Поэтому имеющийся workflow ещё не является работающим end-to-end CD.

## Настоящие изолированные проверки EC2

Canonical main scripts/test_delivery.py запущен на EC2 под deployment user с
проверенным GHCR image, помеченным локальным test tag. Тестовые credentials
генерировались отдельно от production.env; настоящий Telegram не использовался.

- Production Compose config/JSON assertions прошли на Compose5.6.1.
- Non-root API/bot imports от UID10001, cold migration PostgreSQL17.11, реальный
  DB-backed /health, exact /version SHA прошли.
- Private HTTP client на application network выполнил bootstrap/me с проверенным
  synthetic bot-service actor. API/DB ports не опубликованы.
- DB restart сохранил профиль и тот же named test volume.
- Non-root Caddy с настоящим TLS и доверенным **тестовым local CA**: public-route
  health/docs/OpenAPI, 26 raw negative routing cases и private service actor прошли.
  Это loopback-тест EC2, **не внешняя проверка публичного сертификата**.
- Первый smoke упал из-за0640 на staged несекретном Caddyfile. Permission denied
  воспроизведён отдельно; исправлена только staging copy на0644, повтор прошёл.
  Runtime env остался0600; исходный main Caddyfile/CI не менялись.
- Canonical controller dry-run завершился с exit0 в temporary root с отдельными
  synthetic credentials/reserved example.com domain. --execute не использовался;
  настоящий production.env с пустым domain по-прежнему не готов к запуску.

Удалены только собственные UUID test containers/networks, synthetic named volumes
оставлены. Production volumes не инициализировались и production DB не изменялась.

## Backup/restore

Добавлен минимальный manual scripts/backup_postgres.py, поставляемый в release
bundle после review/merge. Новых runtime dependencies нет. Scheduler, retention,
полноценные logs/observability и T-10 не реализованы.

На EC2 helper-кандидат проверен двумя настоящими PostgreSQL17 контейнерами с
разными UUID volumes, без published ports, в отдельной internal network:

1. В source создана только synthetic test table/record.
2. Получен private custom dump, pg_restore --list завершился успешно.
3. Archive восстановлен в **отдельную пустую** test DB без --clean/drop/downgrade.
4. Значение совпало; source не изменился; после restart target запись сохранилась.
5. Test dump скопирован на Mac вне Git, каталог0700/файл0600, hash совпал.

```text
dump bytes: 1890
SHA256: 95b6a2838de0ccd07c9721a995027711d98a24e68fbf3baee75e81a1ef0cbdde
```

Это проверяет механизм на безопасных данных. Production backup пока отсутствует,
поскольку production DB не создана; постоянное защищённое off-host хранилище и
backup schedule не настроены. Не выдавать test dump за копию production.
Реальный restore/delete production требует отдельного разрешения Тимура.

## Проверки кода follow-up

Frozen sync/lock, Ruff check/format, strict mypy130 files, pre-commit/secrets,
pip check и audit72 packages прошли. Unit **1146 passed**, PostgreSQL integration
**402 passed** (existing isolated runner), всего **1548**, combined branch coverage
app+bot **94,76%**. Отдельный infrastructure набор release/deploy/SSH/backup:
**88 passed**, включая13 новых backup cases. Порог60 не менялся; infrastructure
source не добавлялся в coverage приложения. Есть прежний Starlette/httpx warning.
GitHub CI follow-up подтверждается run-ссылкой в PR body после его завершения.

## Невыполненная приёмка #59

verified относится только к явно указанному доказательству; isolated не означает public.

| Acceptance Issue #59 | Статус | Evidence / что осталось |
|---|---|---|
| Production topology, Compose, non-root image, health/migrations design | verified | Main PR64, digest/imports и real EC2 isolated smoke |
| Trusted-main Actions CD, SHA publish, permissions/concurrency | pending | Publisher/main CI verified; безопасный runner SSH transport ещё не настроен |
| SSH deployment main SHA, migrate once, containers, health/version | blocked | Нужны AWS/CD path и отдельное rollout confirmation; execute не запускался |
| Caddy public HTTPS/internal denial/private DB | blocked | 26 isolated negatives verified; нет domain/SG/ACME/external evidence |
| Environment/runtime secrets/domain setup | pending | Environment/key/private env verified; domain и cloud ingress/IAM checks остаются |
| Safe rollback/backup без DB downgrade | pending | Unit failures, canonical no-execute и real test dump/restore verified; production history/failover отсутствуют |
| Docs/static/dry-run CI и independent review | pending | Этот follow-up, local checks прошли; нужны final GitHub CI и human review |
| Настоящие GHCR/HTTPS/health/version/isolation evidence | blocked | GHCR digest pull verified; публичный rollout ещё не разрешён/не выполнен |
| Полный closing PR только после acceptance/review | pending | Refs #59, Issue открыта, merge/close не выполнялись |

## Точные блокеры для Тимура

1. Войти в открытую AWS Console: проверить SG/routes/EBS encryption и доступность
   IAM. SSH key сам по себе не предоставляет EC2/IAM API permissions. Metadata
   подтвердил отсутствие instance profile; AWS Console сейчас требует вход.
2. Выбрать domain/DNS. Предложен бесплатный sslip.io hostname по текущему public IP;
   нужен выбор владельца. При смене EC2 IP имя изменится; стабильный платный адрес
   или покупка домена не создавались. Ни EIP allocation, ни другие платные операции
   не выполнялись. Есть зависимость от стороннего DNS/ACME rate limits.
3. Разрешить безопасный runner path: SSM+OIDC предложен, либо временный /32 ingress.
   Оба требуют согласования IAM/transport изменений, PR и independent review.
   SSH0.0.0.0/0 не открывался; текущий доступ Mac не отключался.
4. После review/merge и закрытия технических блокеров отдельно подтвердить публичный
   rollout. Затем dispatch Release на актуальной main, operation=deploy,
   enable_polling=false, независимое Environment approval, реальный external audit.
5. Live Telegram — отдельное разрешение после API acceptance; token передаётся
   владельцем безопасно только на сервер. Сейчас его отсутствие не мешает API prep.
