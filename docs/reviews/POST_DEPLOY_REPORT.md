# M6 — POST-DEPLOY проверка

**03.11.2026, 07:17–07:26 UTC (10:17–10:26 Europe/Moscow). Итог: NOT READY.**
[Issue #79](https://github.com/inte11ectua1/skinulis/issues/79) остаётся открытой.
Проверка выполнена с Mac внешними HTTPS-запросами и GitHub/GHCR API. Новый Release,
миграции, polling, restart, rollback и изменения AWS/production DB не запускались.
[Машинное evidence](POST_DEPLOY_EVIDENCE.json) содержит безопасные результаты.
Публичные Git SHA в JSON обозначены префиксом `git:` для secret scanner;
в настоящем HTTP commit_sha префикса нет.

## 1. Версия, CI и действительно выполненный deployment

- [PR #81](https://github.com/inte11ectua1/skinulis/pull/81) merged **03.11.2026 05:16:44 UTC**.
- Проверенная актуальная `origin/main` и ожидаемый production SHA:
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
**NOT VERIFIED**: это отдельная проверка, её не заменяет `/version`.

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

## 3. Контейнеры, миграции, volumes и polling

AWS CLI profile `skinulis-new-admin` вернул **session expired** при read-only
STS проверке. Account/instance не подтверждены новым AWS API ответом, SSH-over-SSM
не выполнялся. Старый AWS account и direct SSH fallback не использовались.

| Проверка | Статус и граница доказательства |
|---|---|
| API container healthy | NOT VERIFIED; публичный API обслуживает запросы |
| PostgreSQL container healthy | NOT VERIFIED; SELECT1 через API работает |
| Caddy container state/restarts | NOT VERIFIED; внешний Caddy отвечает |
| Последняя миграция exited0 / actual revision | NOT VERIFIED напрямую; успешный controller включает foreground migrate с exit-code-from, но raw remote stdout скрыт transport |
| Alembic head исходников | 0006_settlement_notification_claim; не подменяет чтение revision рабочей БД |
| Запущенный image digest / current.json | NOT VERIFIED напрямую; job input совпадает с опубликованным digest, HTTP SHA совпадает |
| Restart loops / OOM / критические server errors | NOT VERIFIED |
| PostgreSQL named volume сохранён | NOT VERIFIED; отсутствие destructive действий в этой проверке не доказывает mount/persistence |
| JSON logs / privacy / rotation 5m×3 | NOT VERIFIED на текущих контейнерах; принятое Compose/runbook содержит настройки |
| Telegram polling сейчас выключен | NOT VERIFIED как process count; фактический успешный Release имел enable_polling=false, эта проверка polling не запускала |
| Публичные порты API/DB и SG | NOT VERIFIED заново; без AWS/host доступа port scan не использовался как доказательство |

Read-only server inspection после безопасного обновления AWS login может снять
эти NOT VERIFIED без deployment, restart, миграций и изменений БД. Пароли,
ключи, production.env и database rows для отчёта не читались/не выводились.

## 4. Соответствие #79 и граница закрытия

| Область #79 | Post-deploy результат |
|---|---|
| A — актуальный main / green CI / coverage | PASS, новые CI logs 5/5 и95,00% |
| A — protection / все исторические approvals | Ранее выявленные FAIL остаются; не исправлялись |
| B — clean build / finance / concurrency / performance | Fresh CI проверяет текущий main; подробный audit в M6_ACCEPTANCE_REPORT. Production write/load не выполнялись. p95>500ms остаётся FAIL |
| C — guide / offline Telegram / demo | Артефакты PR81 merged; live Telegram NOT VERIFIED |
| D — финальный protected deploy / exact version | PASS по Release и свежему HTTPS /version; published/deploy input digest совпадает |
| D — полный post-deploy routing smoke | FAIL на foreign-authority absolute-form; внутренний runtime inventory NOT VERIFIED |
| Полный официальный DoD / G6 | НЕ подтверждён; owner acceptance не является исключением преподавателя |

Сохраняются ограничения принятой [M6-матрицы](M6_ACCEPTANCE_REPORT.md):
37/48 исторических PR без зарегистрированного pre-merge APPROVED, admin bypass
main, p95 956/1098ms вместо500ms, формальные вопросы stdlib logging/actor context,
live Telegram NOT VERIFIED. Их не пытались устранять в этой задаче.

## 5. Решение и следующие действия

**Deployment: YES. Ожидаемый production SHA: YES. Полная POST-DEPLOY приёмка: NOT READY.**
Новый конкретный blocker приёмки — unexpected empty200 на одном negative routing
case; подтверждённой утечки данных не обнаружено. Дополнительно внутренняя
проверка ограничена истёкшей AWS-сессией. Не утверждаем здоровые контейнеры,
проверенную рабочую Alembic revision или отсутствие polling только по health.

Следующие действия: отдельно проверить/исправить foreign-authority обработку
на изолированном стенде и обновить read-only container evidence после AWS login.
Новый deploy и изменения production требуют отдельного разрешения. Issue #79
автоматически не закрывается. **Безусловная рекомендация технически закрыть M6
и перейти к M7 пока не дана; M7 не начинался.** Полное соответствие официальному
DoD преподавателя не подтверждено независимо от исправления нового отклонения.
