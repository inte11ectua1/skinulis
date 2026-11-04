> **Дополнение после аудита, 04.11.2026 (решение владельца).** #84 закрыта `completed` как принятая UX-реализация с открыто задокументированными исключениями; #80 закрыта `not_planned`, отдельный этап M7 исключён из текущего roadmap. Упоминания планируемой M7 и открытых #84/#80 **ниже — датированный исторический срез**, не активные задачи. M6 #79 остаётся открыта; формальный DoD преподавателя не отменён. См. [текущий STATUS](../STATUS.md) и [roadmap](../roadmaps/MASTER_ROADMAP.md).

# Post-release аудит «Скинулись» — 04.11.2026

**Итог: production API RELEASE VERIFIED; M6/G6 PARTIALLY / NOT READY для полного
официального закрытия.** Новый интерфейс и команды подтверждены владельцем;
read-only runtime follow-up04.11 после browser login **VERIFIED**. M7 можно готовить с раскрытыми
ограничениями, утверждать завершение защиты нельзя.

[Машинное evidence](POST_RELEASE_EVIDENCE_2026-11-04.json) ·
[Инвентаризация всей документации](DOCUMENTATION_AUDIT_2026-11-04.md).
В JSON публичные commit SHA имеют маркер `git:` для secret scanner; HTTP /version
возвращает сам полный SHA без этого маркера.
Проверки выполнены с Mac. GET/read-only GitHub/GHCR и безопасные raw HTTP-пробы;
без Telegram API, финансовых POST/PUT/DELETE, нагрузки, SSH-обхода, deployment,
миграций, остановки polling или изменения AWS/Environment/данных.
Дополнительное разрешение владельца на browser login позволило закрыть
первоначальный runtime gap в14:37UTC (17:37МСК) через pinned SSH-over-SSM.
Дата —04.11.2026; внешние пробы начаты **13:55:25 UTC** (16:55МСК).

## 1. Main, CI, образ и protected release

- Актуальный исследованный `origin/main`: `c9ec9cea388fd9282fadc437ff2ce1c7390d4a0c`.
- [PR #85](https://github.com/inte11ectua1/skinulis/pull/85) merged04.11 в11:51:15UTC.
- [Push-main CI41824303985](https://github.com/inte11ectua1/skinulis/actions/runs/41824303985):
  lint/types/tests/docker-build/ci **5/5 success**. Из самого лога: **1382 unit +458
  PostgreSQL17 integration**, combined branch coverage **94,10%** (порог60%).
  Это реальный CI на merge SHA, не перенесённый результат feature branch.
- [Publish41825912360](https://github.com/inte11ectua1/skinulis/actions/runs/41825912360)
  успешен, отдельно от [manual Release41836839608](https://github.com/inte11ectua1/skinulis/actions/runs/41836839608).
- Новый Release: **operation=deploy, enable_polling=true, rollback_compatible=false**;
  guard/publish/deploy success. REST approvals: **Valeria18-new**, production approved.
  Лог подтверждает `Approved remote release completed`04.11 в13:30:47UTC.
- Свежий REST Environment: independent reviewers, prevent_self_review=true,
  protected branches only, can_admins_bypass=false. Rollout flag прочитан **false**,
  updated_at13:40:18UTC. В рамках аудита ничего не менялось.
- Анонимно заново получены GHCR manifest/config; SHA256 обоих пересчитаны,
  linux/amd64, non-root skinulis, OCI source/revision и APP_COMMIT_SHA совпали.

```text
ghcr.io/inte11ectua1/skinulis@sha256:9deb582d78653dffac806d1c3304d51e419c0d79809e13a1c30c5f4251e97cbf
```

GHCR digest совпал с APP_IMAGE deployment job. Публичный /version совпал с release.
**Actual running Docker image ID/RepoDigests/OCI revision VERIFIED** свежим inspect
через pinned SSH-over-SSM после browser login: API и bot используют тот же immutable
digest. Само по себе workflow input/HTTP-ответ или deploy success не заменяет эту проверку.

## 2. Свежий внешний production smoke

URL: **https://3-25-53-31.sslip.io**. TLS1.3, default hostname/SNI/CA validation,
Let's Encrypt YE2, SAN совпал; сертификат02.11.2026–31.01.2027.
Первый запуск системного Python получил SSLCertVerificationError; финальный прогон выполнен
проектным Python3.12 с certifi CA и включённой полной проверкой. curl отдельно также
прошёл обычную TLS-проверку. `-k`/verify=false не применялись.

| Проверка | Фактический результат | Статус |
|---|---|---|
| HTTPS и сертификат | Доверенная цепочка/SAN/срок, TLS1.3 | PASS |
| HTTP /health | 308 в точный HTTPS URL | PASS |
| GET /health | 200, status=ok, database=ok | PASS |
| Подключение DB | Реальный SELECT1 handler app/api/system.py; HTTP database=ok | PASS для соединения, не Docker health |
| GET /version | 200, exact release SHA `c9ec9cea388fd9282fadc437ff2ce1c7390d4a0c` | PASS |
| GET /docs, /redoc, /openapi.json | 200; OpenAPI paths и schemas получены | PASS |
| /users/me, /groups без JWT | 401, единый error envelope и request_id | PASS |
| Origin-form /internal и encoding/traversal/method-варианты | Включая double encoding, backslash, dot segments: 404/400/405 | PASS в проверенном наборе |
| X-Original-URL/X-Rewrite-URL/query | /health остаётся health; внутренний ответ не получен | PASS |
| Foreign-authority absolute-form | GET request-target https://localhost/internal/users/me →200, body0bytes | **FAIL** |

Итого **35 HTTP probes: 34 PASS /1 FAIL**, отдельно TLS и redirect PASS.
Из25 negative routing probes24PASS/1FAIL. Точный список/методы/коды — в JSON evidence.
Foreign-authority повторён curl --request-target с обычным TLS:200/0bytes.
Это прежний routing FAIL, **не доказанная утечка /internal и не доказанный обход auth**.
Не «починен» документированием и не закрыт зелёным isolated delivery smoke в CI.
Исправление Caddy/request-target поведения — отдельный кодовый Issue/PR после
разрешения владельца, с regression и защищённым rollout; здесь код не менялся.

## 3. Внутренний runtime: read-only follow-up после browser login

Первоначальная попытка STS вернула session expired. После отдельной команды
владельца выполнен штатный `aws login --profile skinulis-new-admin --region ap-southeast-2`
через браузер; постоянные access keys не создавались. STS подтвердил account621150878773.
Использовано существующее pinned SSH-over-SSM: StrictHostKeyChecking=yes,
отдельный deployment key/known_hosts; без direct fallback/изменения host key.
В14:37UTC выполнен новый metadata/SQL/log audit, **не повторный deploy**.

| Пункт | Фактический результат | Статус |
|---|---|---|
| AWS/EC2/SSM | Account621150878773, Sydney, i-0c920378dd242af2b Running/SSM Online, IPv43.25.53.31, AMD64 | VERIFIED |
| API/db/Caddy/bot | Все running/healthy; restart_count0/OOM=false | VERIFIED на момент проверки |
| Polling | Один Python -m bot.main на host и внутри одного bot container; иных running containers0 | VERIFIED на этой EC2 |
| Docker init | Отдельный docker-init только передаёт команду дочернему Python; исключён из count | Не второй polling |
| Миграция | SQL SELECT alembic_version →0007_user_display_name; migrate exited0, в bounded startup logs started1/completed1 | VERIFIED, миграции аудит не запускал |
| PostgreSQL volume | skinulis-production-postgres, CreatedAt2026-11-01T20:22:25Z, подключён к /var/lib/postgresql/data | Имя/дата/mount совпали с прежним evidence; пользовательские записи не читались |
| Runtime роль | LOGIN=true; SUPERUSER/CREATEDB/CREATEROLE/REPLICATION/BYPASSRLS=false | VERIFIED через pg_roles |
| Read-only SQL | default_transaction_read_only=on, statement_timeout5s, только schema/role metadata | VERIFIED; без DDL/пользовательских SELECT |
| Сеть/порты | SG inbound только TCP80/443; только Caddy имеет bindings80/443; API/db/bot без ports, bot без DB network | VERIFIED, правил не меняли |
| Логи/rotation | json-file5m×3/compress=true на всех5 services; API200/200, bot25/25, migrate5/5, Caddy19/19 JSON | VERIFIED в ограниченной выборке |
| Privacy/errors | obvious sensitive fields/token shapes0, API/bot/migrate unexpected fields0, error/critical0; restart/oom/die events за30min0 | Не полный forensic-аудит всех логов |
| Ресурсы | RAM available≈1,00GiB, swap2GiB почти свободен; root disk free≈12,30GiB из18,33GiB; низкий load | Запаса достаточно для текущего scope, не нагрузочная гарантия |
| Backup/restore | Старые M5 evidence сохранены | Свежий backup/restore не выполнялся/не проверен |

Не выводились env, credentials, сырые command lines/logs или пользовательские данные.
Секреты приложения не читались; логи анализировались только в памяти, сохранены
агрегаты. Нулевые флаги privacy не доказывают отсутствия всех возможных утечек во
всей истории. Process-count относится к этой EC2, не всем возможным внешним хостам.
Два первоначальных отказа операторского скрипта были ошибками формата docker inspect/top;
после исправления read-only скрипта проверка завершилась. Это не ошибки production.

Исторические [POST_DEPLOY_REPORT](POST_DEPLOY_REPORT.md) и
[runtime evidence03.11](POST_DEPLOY_RUNTIME_EVIDENCE.json) сохранены; свежий результат
в текущем JSON evidence. Нового Telegram API getMe/getUpdates/тестовых сообщений,
контейнерных lifecycle-команд, миграций, rollback или DB writes не выполнялось.

## 4. Функционал по коду и текущему CI

Это audit реализации/тестов, **не новый write-E2E на production**.

| Область | Реализовано и документировано | Evidence |
|---|---|---|
| Identity | Telegram-only после согласия; email/API register/login JWT; одноразовый linking без merge | app/api/auth.py, telegram_identity.py; T-05/T-06 contracts |
| Профиль/имена | nullable display_name, PATCH своего профиля, согласие на initial Telegram name, различимые одноимённые участники | 0007, schemas, bot/presentation.py, tests display_names/ux84 |
| Группы | Create/list/read/members, owner/member access, одноразовые24h invites и отзыв | groups services/contracts и PG races |
| Расходы | equal/custom/by_items, server preview, versioned edit и soft-delete только автором | expense API/services, O-04/O-05 contracts, PG tests |
| Денежный ввод | 100/100,5/100.50 → strict100.00/100.50; zero только custom, без float/округления | bot/money_input.py; strict DTO и money_layout tests |
| Баланс/план | Серверные exact kopecks; pending без эффекта, план — рекомендация | O-06/O-07, существующие financial tests |
| Компенсации | Manual pending → receiver confirm/reject, sender cancel; повторная проверка долга | settlement tests/concurrency, USER_GUIDE |
| UI | Русские карточки, escaping, Unicode icons, primary/success/danger, contextual rows | bot/button_theme.py, keyboard_layout.py |
| Lifecycle | Edit одной карточки, retire перед новым текстом, nonce stale rejection/recovery | ui.py, screen_lifecycle.py; не обещаем очистку неизвестной истории после FSM reset |
| Локальное окружение | Отдельный skinulis_testing_bot, API/PG, сохраняемые volumes и безопасный runner | LOCAL_TELEGRAM_UX, scripts/local_ux.py |

Бот не переводит банковские деньги и не задаёт всем пользователям фон переписки.
Удаление групп, участников с историей и Mini App **отложены владельцем / вне MVP**.
Ограничения банковской проверки, mutable confirmed и merge аккаунтов не расширялись.

## 5. Команды production и owner evidence

Владелец04.11 явно сообщил: основной **@skinulis_expenses_bot** отвечает с новым
UI; через BotFather настроено рабочее меню:

| Команда | Описание |
|---|---|
| /start | Главное меню |
| /groups | Мои группы |
| /profile | Профиль |
| /help | Помощь |
| /cancel | Отмена ввода |

Это **OWNER REPORTED**, не getMyCommands/полный live-E2E аудит агентом.
Настройки команд хранятся Telegram и не требуют повторения при обычном restart;
[официальные команды/Menu Button](https://core.telegram.org/bots/features#commands).
Код configure_test_menu с identity guard автоматически обслуживает только
skinulis_testing_bot; production setup не добавлен. Автонастройка production —
необязательное будущее улучшение. Это команды бота, **не Mini App**.

## 6. GitHub process, Issues и учебная приёмка

Повторно проверены все52mergedPR (53closed всего, #65 не merged), REST reviews:
**11 имеют независимый submitted APPROVED до merge /41 не имеют**. Среди новых
#81/#82/#83/#85 — ни одного. [Дополнение полного PR-аудита](M6_PR_REVIEWS.md).
Проверялись записи GitHub других User до merged_at; личное чтение кода этим не
аттестуется. Environment approval Леры относится к deploy, не к code review PR85.
Main protection: strict=true, checks lint/types/tests/docker-build/ci, review1,
dismiss_stale=true, **enforce_admins=false**. Не доказана универсальная блокировка
red CI для администратора. Environment bypass=false — другое правило.

| Issue | GitHub04.11 | Решение по readiness |
|---|---|---|
| #84 UX | open; PR85 merged, CI/deploy зелёные, owner UI/menu подтверждены | По реализации и owner smoke готово; автоматического закрытия нет. Нет полного evidence трёх новых пользователей без подсказок и pre-merge независимого APPROVED. Финальное принятие/раскрытие этих gaps — Тимур |
| #79 M6 | open | PARTIALLY / NOT READY для полного DoD; routing FAIL, process/performance/logging/live/runtime gaps не закрыты |
| #80 M7 | open | Можно готовить материалы/честный fallback; нет evidence завершённой презентации/полной репетиции/защиты |

[DoD курса](https://github.com/andrey-limasov/app-conf/blob/main/definition-of-done.md)
требует PR review, CI/deployment/observability/docs и учебную приёмку;
[ТЗ](https://github.com/andrey-limasov/app-conf/blob/main/project-requirements.md)
содержит95%responses≤500ms/100connections. Исторический local p95≈956/1098ms — FAIL,
внутреннее принятие Тимуром не равно исключению преподавателя. Не запускалась новая
production load. Literal logging backend/user-context и red-check UI proof остаются
формальными gaps из M6, здесь не устранялись. Групповой delete и Mini App не являются
добавленными обязательными критериями курса.

## 7. Что осталось и готовность к защите

1. Runtime gap закрыт: browser login и свежие read-only проверки выполнены.
   Перед следующим релизом/защитой повторять диагностику по необходимости без lifecycle changes.
2. Отдельно согласовать кодовый fix routing FAIL с regression, review и rollout;
   не исправлять Caddy в docs PR и не называть200 доказанной утечкой.
3. Оформить полный3-user/new-user E2E checklist с фактическими результатами/датой
   и ролями, отдельно delivery best-effort notifications; owner smoke уже есть.
4. Раскрыть missing historical APPROVED/admin bypass и получить решение
   преподавателя по DoD deviations (performance/logging/process), а не задним числом
   рисовать approvals. Документационный PR тоже требует независимого review.
5. Для M7 #80 подготовить слайды/спикер-ноты7min, demo5min, Q&A8min и одну полную
   командную репетицию с измерением времени. Использовать существующий release,
   синтетические группу/записи и честно маркированный offline fallback.
   [План/ожидания курса](https://github.com/andrey-limasov/app-conf/blob/main/assessment.md),
   [готовый сценарий](M6_THREE_USER_DEMO.md); новый live запуск не выполняется этим аудитом.

**Показ существующего API/подтверждённого владельцем UI возможен, но полную
готовность к защите/DoD заявлять рано.** Начало подготовки M7 не равно закрытию M6.
Все Issues оставлены открытыми. Новый production deploy/polling/restart/DB writes
не выполнялись; runtime secrets не читались. Rollout flag осталсяfalse.

## 8. Документация и проверки этого PR

Проверены инвентаризацией все70 исходных Markdown-файлов: ссылки/структура/статусные
утверждения; семантически обновлены устаревшие точки входа, roadmap/контракты,
эксплуатация, user guide и UX. Датированные отчёты дополнены сверху; исходные SHA,
результаты/неудачи и ссылки сохранены. Стабильные финансовые контракты не переписаны.
Полный перечень каждого файла и решение — [documentation audit](DOCUMENTATION_AUDIT_2026-11-04.md).
Код приложения, tests, migrations, workflows, Compose и production config не менялись.
Применимые проверки и окончательный CI docs PR указываются в описании PR;
результаты main CI выше не выдаются за проверку нового документационного commit.
