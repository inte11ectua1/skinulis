# Post-release аудит «Скинулись» — 04.11.2026

**Итог: production API RELEASE VERIFIED; M6/G6 PARTIALLY / NOT READY для полного
официального закрытия.** Новый интерфейс и команды подтверждены владельцем;
свежая внутренняя диагностика AWS **NOT VERIFIED**. M7 можно готовить с раскрытыми
ограничениями, утверждать завершение защиты нельзя.

[Машинное evidence](POST_RELEASE_EVIDENCE_2026-11-04.json) ·
[Инвентаризация всей документации](DOCUMENTATION_AUDIT_2026-11-04.md).
В JSON публичные commit SHA имеют маркер `git:` для secret scanner; HTTP /version
возвращает сам полный SHA без этого маркера.
Проверки выполнены с Mac. GET/read-only GitHub/GHCR и безопасные raw HTTP-пробы;
без Telegram API, финансовых POST/PUT/DELETE, нагрузки, SSH-обхода, deployment,
миграций, остановки polling или изменения AWS/Environment/данных.
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
**Actual running Docker image ID/RepoDigests пока NOT VERIFIED** — нельзя подменять
его workflow input или HTTP-ответом. Deployment job success не доказывает нынешнюю
долговременную устойчивость контейнеров.

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

## 3. Внутренний runtime: границы доступа

`aws sts get-caller-identity --profile skinulis-new-admin --region ap-southeast-2`
вернул session expired. Обхода через иной account/direct public SSH не делалось.

| Пункт | Что есть | Свежая проверка |
|---|---|---|
| AWS account/instance/SSM | Ожидаемые621150878773 / i-0c920378dd242af2b / Sydney | NOT VERIFIED |
| API/db/Caddy healthy, restart/OOM | Старый runtime03.11 и успешный deployment job04.11 | NOT VERIFIED сейчас |
| Ровно один polling process | Release input=true; fixed Compose name/replicas1; владелец видит ответы | **NOT VERIFIED count**, нельзя утверждать OFF |
| Миграция | В коде единственный ожидаемый head0007_user_display_name; migrator штатного deploy прошёл | SQL actual revision NOT VERIFIED |
| PostgreSQL volume | Compose external existing volume, reset/down-v не выполнялись этим аудитом | Mount/identity/данные NOT VERIFIED сейчас |
| Приватные порты и сети | В принятом Compose только Caddy80/443, bot без DB/ports | AWS SG/actual bindings NOT VERIFIED сейчас |
| JSON logs/privacy/rotation | Код/Compose5m×3 и CI; историческое runtime evidence | Свежие логи/rotation NOT VERIFIED |
| Backup/restore | Исторический M5 backup evidence сохранён | Новый backup/restore не выполнялся и не подтверждён |

Для снятия пробела нужен штатный интерактивный вход владельца:
`aws login --profile skinulis-new-admin --region ap-southeast-2`, затем только
документированный pinned SSH-over-SSM read-only audit. Пароли/MFA/токены в чат не
присылать. Эта команда — следующий безопасный шаг, она здесь не запускалась.
Исторические [POST_DEPLOY_REPORT](POST_DEPLOY_REPORT.md) и
[runtime evidence03.11](POST_DEPLOY_RUNTIME_EVIDENCE.json) не переносятся на новый SHA.

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

1. Восстановить AWS login и повторить свежую read-only runtime проверку: digest,
   один bot process, health/restarts/OOM, actual0007, старый volume, bounded safe logs.
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
