# Фактическое состояние проекта

## T-10 — JSON logging, rotation и runbook: реализация для review (02.11.2026)

В feature-ветке T-10 добавлены единый безопасный JSON stdout API/bot/migrate,
серверный request_id, allowlist events/fields, secret-negative тесты, Docker
rotation всех пяти services и [incident/rollback runbook](operations/INCIDENTS_AND_ROLLBACK.md).
Новые зависимости/миграции/финансовые изменения отсутствуют. Локально прошли
1219 unit +403 PostgreSQL integration tests; branch coverage app/bot94,80%,
с общим logging-модулем95,00% (порог60% сохранён), frozen/lock/Ruff/mypy/
pre-commit/secrets/pip check/audit, Docker build и реальный isolated delivery smoke.
Production validation пока **pending**: PR использует Refs #60, #60/G5 не закрываются.

Read-only аудит T-09 подтвердил new-account Environment/OIDC targets, SG только
80/443, активные Docker/SSM, RAM/swap/disk; подробное new-EC2 evidence уже в
[PR #70](https://github.com/inte11ectua1/skinulis/pull/70), не дублируется здесь.
[check-transport](https://github.com/inte11ectua1/skinulis/actions/runs/41346841056)
пока waiting independent approval. PRODUCTION_ROLLOUT_ENABLED=false;
production containers/migrations/polling не запускались. T-09 #59 остаётся open.
Нижележащие EC2/роль-срезы — исторические; активная конфигурация нового AWS описана
в #70, документационный #69 относится к отказу IAM в старом аккаунте.


## T-09 — EC2 preflight выполнен, публичный rollout ожидает (01.11.2026)

[PR #64](https://github.com/inte11ectua1/skinulis/pull/64) merged в `main`;
[PR #65](https://github.com/inte11ectua1/skinulis/pull/65) закрыт без merge;
[PR #66](https://github.com/inte11ectua1/skinulis/pull/66) merged и восстановил
серверный scope. [Полное evidence](operations/T-09_EC2_PREFLIGHT.md);
[PR #67](https://github.com/inte11ectua1/skinulis/pull/67) содержит backup helper
и проверенные результаты подготовки EC2.

На EC2 установлены официальный Docker 29.9.2, containerd 2.4.2,
Compose 5.6.1 и Buildx 0.38.1; Docker включён в автозапуск, TCP daemon
не опубликован. Созданы отдельный deployment user/key, private runtime env
и external volumes. Проверенный `main` image GHCR скачан по digest:
linux/amd64, non-root и revision SHA подтверждены. GitHub Environment
`production` настроен с независимыми reviewers, prevent self-review
и без admin bypass; `PRODUCTION_ROLLOUT_ENABLED=false`.

На EC2 прошли изолированные проверки PostgreSQL 17, TLS с тестовым CA,
private actor, 26 негативных routing cases и сохранности данных. Backup helper
проверен настоящим dump/restore в двух тестовых БД, перезапуском восстановленной
БД и off-host synthetic copy с SHA256; production DB не затрагивалась.
13 новых unit cases покрывают границы privacy/failure для backup.
Владелец также подтвердил EBS encryption (`aws/ebs`), закрытые входящие порты
8000/5432, работающую роль `skinulis-ec2-ssm-role`, SSM Agent Online
и успешное открытие реальной интерактивной SSM-сессии.

**Остаётся:** human review/merge PR #67 и
[PR #68](https://github.com/inte11ectua1/skinulis/pull/68),
настройка GitHub OIDC IAM-role и реальный `check-transport`,
домен/DNS, PUBLIC_DOMAIN, публичный ACME HTTPS и отдельное разрешение на
production rollout. Telegram token не настроен, polling выключен.
Реальный production API/DB/Caddy/bot не запускался; T-09 #59 и G5 **не verified**.

Ниже — восстановленный в PR #66 серверный scope и более ранние исторические
срезы. Они не отменяют приведённые выше результаты EC2 preflight.

## T-09 follow-up · 01.11.2026: AWS SSM CD transport

В [PR #68](https://github.com/inte11ectua1/skinulis/pull/68) подготовлен OIDC + SSH-over-SSM transport;
[Console setup, exact trust и permissions JSON](operations/AWS_SSM_CD.md).
Guard/protected production Environment/host-key pin/controller сохраняются;
добавлены recheck после approval и read-only `check-transport` с rollout=false.
Владелец подтвердил encrypted EBS, private SG ports8000/5432, EC2 SSM IAM role,
Online agent и успешную интерактивную session. Новая GitHub OIDC IAM role не
создавалась; реальный GitHub → SSM transport ещё pending после human review и
настройки владельцем. PR #66 и PR #67 уже merged; их изменения сохранены ниже.
PR #68 остаётся открытым; GitHub OIDC IAM role ещё не настроена,
production rollout и polling не выполнялись.
**T-09 #59 / G5 остаются незавершёнными**; DNS/TLS/public acceptance отдельно.

## M5 — серверный scope восстановлен, production acceptance открыт (01.11.2026)

**Текущее решение (01.11.2026):** [PR #64](https://github.com/inte11ectua1/skinulis/pull/64) с инфраструктурой GHCR/CD/VPS/Caddy **merged в `main` 31.10.2026** (merge SHA `3f67828c40be6e14786816ffbfbcb867fcc79a7f`). [PR #65](https://github.com/inte11ectua1/skinulis/pull/65) с заменой VPS на ноутбук **closed without merge** 01.11.2026; `compose.laptop.yaml`, laptop ADR003, отключение SSH rollout и связанные правки не попали в `main`. Возвращаем [T-09 #59](https://github.com/inte11ectua1/skinulis/issues/59) и [T-10 #60](https://github.com/inte11ectua1/skinulis/issues/60) к исходным требованиям: VPS/cloud, публичный URL, Caddy HTTPS, trusted-main SHA GHCR/SSH deployment, серверные JSON-логи/ротация/rollback runbook. Это соответствует [DoD преподавателя](https://github.com/andrey-limasov/app-conf/blob/main/definition-of-done.md); исключение для отсутствующего сервера возможно только по предварительному согласованию. Оба issue **open**, G5 **not verified**: реальный деплой/HTTPS не проводился; SSH/secrets/live Telegram — исключительно по отдельному разрешению Тимура.


В принятом [PR #64](https://github.com/inte11ectua1/skinulis/pull/64) из ветки `feat/T-09-ghcr-cd-vps` реализованы: общий non-root API/bot image, production Compose/Caddy,
trusted-main release policy, digest pinning, отключённый по умолчанию SSH rollout,
однократная миграция, health/SHA probes и image rollback без DB downgrade.
[Runbook и ручной checklist](operations/DEPLOYMENT.md),
[схема окружения](environment-schema.md#production-delivery--t-09).

Локально прошли75 новых unit cases release/deploy/SSH boundaries и Docker smoke:
реальные PostgreSQL17.11 + non-root Caddy, trusted local-CA TLS, DB restart с
сохранением профиля в своём UUID volume, exact /version и26 negative raw routes;
private service actor работает. Полный локальный набор: **1133 unit +402 настоящих
PostgreSQL integration =1535 passed**, combined branch coverage app+bot **94,76%**.
Frozen sync/lock, Ruff, strict mypy128 files, pre-commit/secrets, pip check,
audit72 packages и native/container actionlint прошли. Docker API/bot image собран
и проверен без polling. Единственный Alembic head0006 сохранён.
Обычный CI сохраняет пять required job names, добавляет main push, actionlint и
этот Docker smoke. Фактические GitHub CI evidence — в описании инфраструктурного PR.

**Не выполнены реальные GHCR publication/SSH/VPS/ACME/live Telegram.** Read-only
GitHub API при проверке не показал ни одного Environment: protected production
Environment/secrets ещё нужно создать вручную, не считать их настроенными.
Флаг rollout не включался, branch protection не менялась. Только `Refs #59`;
Issue #59 и G5 остаются открытыми. O-08 #61/L-06 #62/T-10 #60 не реализуются этой веткой.

Ниже сохранены исходный handoff и исторические срезы `main`; они относятся к более ранним датам и не отменяют текущий статус merged PR #64 / открытого T-09 #59.

**Актуальный статус 31.10.2026 · GitHub main `eb3ae2880348b30df852ba653f0ac977d7ad007e` после merged [T-08 PR #58](https://github.com/inte11ectua1/skinulis/pull/58):** этапы **M1/M2/M3/M4 завершены по реализации**. M4: [O-06 #46/PR #51](https://github.com/inte11ectua1/skinulis/pull/51), [O-07 #47/PR #53](https://github.com/inte11ectua1/skinulis/pull/53), [O-07N #55/PR #57](https://github.com/inte11ectua1/skinulis/pull/57), [L-05 #48/PR #54](https://github.com/inte11ectua1/skinulis/pull/54), [T-08 #45/PR #58](https://github.com/inte11ectua1/skinulis/pull/58) — **все merged, все Issues closed completed**. [T-08 финальный audit](reviews/T-08_M4_FINAL_SECURITY_REVIEW.md), [его CI 5/5](https://github.com/inte11ectua1/skinulis/actions/runs/41213175596), финальная кодовая [L-05 CI 5/5, 1460 tests/94,76%](https://github.com/inte11ectua1/skinulis/actions/runs/41210779152). Тесты подтверждены на **PR head**, не отдельным новым запуском после merge.

**M5 Delivery назначен, реализация впереди:** Тимур [T-09 #59](https://github.com/inte11ectua1/skinulis/issues/59) (main-only GHCR/CD/VPS/Caddy/private /internal) → [T-10 #60](https://github.com/inte11ectua1/skinulis/issues/60) (JSON logging/rotation/runbook), Олег [O-08 #61](https://github.com/inte11ectua1/skinulis/issues/61) (real PG load 100 clients/p95 и regressions), Лера [L-06 #62](https://github.com/inte11ectua1/skinulis/issues/62) (UX errors/retries, mocked Telegram + real HTTP/PG). [Полный handoff и зависимости](operations/M5_DELIVERY_HANDOFF.md). T-09 critical path; Олег и Лера могут начинать параллельно. **Ничего не деплоили и новую нагрузку 100 клиентов не измеряли**. Настоящие SSH/VPS/Telegram действия требуют отдельного разрешения Тимура.

**Незакрытые проверки:** [T-01 #2](https://github.com/inte11ectua1/skinulis/issues/2)/G1 остаётся открытой (admin bypass/негативные доказательства); **G2/G3/G4 не formally verified** из-за отложенного live Telegram QA ([#38](https://github.com/inte11ectua1/skinulis/issues/38) closed not_planned); G5 недоступен до GHCR+HTTPS+/version SHA+закрытого снаружи /internal. На PR #51/#53/#57/#54/#58 **не зарегистрированы independent human APPROVED**; это процессная оговорка T08-01, которую нельзя подменять AI-комментариями или зелёным CI. Исторические срезы ниже сохранены как хронология, не как текущие M5 статусы.

**Срез:** 30 октября 2026 года, проверен GitHub `main` `34074adf95d65760b3ba773999f55689ded738e6` после [merged PR #44](https://github.com/inte11ectua1/skinulis/pull/44). **M3 Expenses завершён по реализации:** [O-04 #36](https://github.com/inte11ectua1/skinulis/issues/36), [O-05 #39](https://github.com/inte11ectua1/skinulis/issues/39), [L-04 #37](https://github.com/inte11ectua1/skinulis/issues/37), [T-07 #35](https://github.com/inte11ectua1/skinulis/issues/35) все **closed (completed)**, PR #41/#42/#43/#44 merged. Последний [GitHub CI PR #44](https://github.com/inte11ectua1/skinulis/actions/runs/41064210033) на `124bbe5`: **5/5 success, 857 unit +290 PostgreSQL integration =1147 tests**, combined branch coverage **95,46%**. T-07 выявил и исправил Medium T07-01 (не заменять повреждённые простые snapshots) и Low T07-02 (error responses без `no-store`); [аудит](reviews/T-07_M3_SECURITY_REVIEW.md). **Независимого зарегистрированного APPROVED-review PR #44 нет**; это не отменяет merge/CI, но не следует приписывать его участникам.

**Исторический M4-срез на 30.10.2026 (до merge #53/#57/#54):** O-06 уже завершён PR #51 с [CI 5/5, 1181 tests, 95,58% coverage](https://github.com/inte11ectua1/skinulis/actions/runs/41096303217). Старые дальнейшие зависимости O-07 и L-05 **на 31.10 выполнены**, см. текущий M4-срез вверху. Отдельные незавершённые гейты G1/T-01, G2/G3 live Telegram, G4 и production `/internal` T-09 не смешивать с готовностью M4 кода.

**Этап M1 (Skeleton): завершён по объёму задач.** [T-03 #10](https://github.com/inte11ectua1/skinulis/issues/10), [O-02 #11](https://github.com/inte11ectua1/skinulis/issues/11), [L-02 #12](https://github.com/inte11ectua1/skinulis/issues/12) и [T-04 #13](https://github.com/inte11ectua1/skinulis/issues/13) закрыты, код находится в `main`. **G1 — не полностью подтверждён как формальный gate**: нужна доказательная проверка причины блокировки красного CI в интерфейсе и незавершённые защитные проверки T-01; у PR #19 не зарегистрировано независимого APPROVED-ревью. Это не отменяет успешную реализацию M1.

Статусы задач: `planned → in progress → PR review → merged → verified`. `merged` не равно `verified`: для последнего нужны соответствующие CI, тесты и/или работающий сервис.

## M0 — подготовка и документация

| Задача | Состояние | Ответственный | Подтверждение / оставшееся |
|---|---|---|---|
| [T-01](https://github.com/inte11ectua1/skinulis/issues/2) GitHub и ADR 001 | **in progress** | Тимур | [PR #1](https://github.com/inte11ectua1/skinulis/pull/1) и [PR #6](https://github.com/inte11ectua1/skinulis/pull/6) merged; ADR 001 принят. `main.protected=true`, auto-delete веток включён. Пять required CI checks настроены; текущий GitHub API сообщает enforcement checks **`non_admins`** — администраторский обход возможен, поэтому предыдущая запись `enforce_admins=true` из T-04 уже не является актуальным доказательством. Практический отказ прямому push и визуальная причина блокировки merge при красном CI не подтверждены. [Evidence](operations/CI.md). Приглашение преподавателя отложено решением Тимура. |
| [T-02](https://github.com/inte11ectua1/skinulis/issues/5) Python 3.12, uv | **merged** | Тимур | [PR #7](https://github.com/inte11ectua1/skinulis/pull/7) merged после `APPROVED` Олега и исправления уязвимостей; CPython 3.12.15, uv 0.13.5. Локальные macOS проверки в PR, Windows junction issue при `uv python install` остаётся не перепроверенным на обновлённом uv. |
| [O-01](https://github.com/inte11ectua1/skinulis/issues/3) инварианты | **merged** | Олег | [PR #8](https://github.com/inte11ectua1/skinulis/pull/8) approved Тимуром и merged; финансовые документы, 105 сценариев, вопросы Q-01–Q-10. Это документация, не реализация тестов. |
| [L-01](https://github.com/inte11ectua1/skinulis/issues/4) Telegram UX | **merged** | Лера | [PR #9](https://github.com/inte11ectua1/skinulis/pull/9) approved Тимуром и merged; сценарии, 42 будущих QA-проверки, вопросы UQ-01–UQ-09. Требующие контрактов пункты остаются открытыми. |

**ADR:** 001 (GitHub Flow) принят PR #6; 002 (uv) принят PR #7. Текстовые статусы приняты в main через [PR #14](https://github.com/inte11ectua1/skinulis/pull/14).

## M1 — Skeleton (вторая фаза; реализация завершена 27.10.2026)

| Задача | Состояние | Ответственный | Зависимости |
|---|---|---|---|
| [T-03](https://github.com/inte11ectua1/skinulis/issues/10) API/DB/Alembic/Compose | **merged** | Тимур | [PR #15](https://github.com/inte11ectua1/skinulis/pull/15) merged; PostgreSQL 17.11, Alembic, Compose, локальное cold-start evidence ниже |
| [O-02](https://github.com/inte11ectua1/skinulis/issues/11) pure splits и parser | **merged** | Олег | [PR #16](https://github.com/inte11ectua1/skinulis/pull/16) и [#17](https://github.com/inte11ectua1/skinulis/pull/17) merged; parser/splits, Q-01/Q-02 и часть Q-04 приняты; финансовых моделей/API пока нет |
| [L-02](https://github.com/inte11ectua1/skinulis/issues/12) bot skeleton и mock HTTP | **merged** | Лера | [PR #18](https://github.com/inte11ectua1/skinulis/pull/18) merged; навигация/typed health client/mock-тесты, без live Telegram и онбординга |
| [T-04](https://github.com/inte11ectua1/skinulis/issues/13) PR CI | **merged, Issue closed** | Тимур | [PR #19](https://github.com/inte11ectua1/skinulis/pull/19) merged 27.10.2026; GitHub Actions lint/types/tests/docker-build/ci, PostgreSQL integration и покрытие ≥60%; [успешный run](https://github.com/inte11ectua1/skinulis/actions/runs/40459119340), [красный run](https://github.com/inte11ectua1/skinulis/actions/runs/40458200449), [подробности](operations/CI.md). PR объединён без зарегистрированного независимого APPROVED review. |

Все T-03, O-02, L-02, T-04 завершены по M1, а **M2 также принят в `main`**: [T-05 #21](https://github.com/inte11ectua1/skinulis/issues/21), [T-06 #22](https://github.com/inte11ectua1/skinulis/issues/22), [O-03 #23](https://github.com/inte11ectua1/skinulis/issues/23), [L-03 #24](https://github.com/inte11ectua1/skinulis/issues/24) закрыты. Контракты T-05/T-06 и финансовые Q-03/Q-04/Q-10 согласованы решениями техлида с указанными границами; это не заменяет независимые ревью и проверку G2. Исторический M1-срез `d635398` сохранён в доказательствах ниже.

## M2 — Identity (реализация закрыта 28.10.2026, G2 pending)

| Задача | Состояние в GitHub | Ответственный | Реализовано и доказательства |
|---|---|---|---|
| [T-05 #21](https://github.com/inte11ectua1/skinulis/issues/21) Auth/users | **merged / Issue closed** | Тимур | [PR #26](https://github.com/inte11ectua1/skinulis/pull/26): `users`, Argon2id, email register/login, JWT `/users/me`, миграция `0002_users`. [Final CI](https://github.com/inte11ectua1/skinulis/actions/runs/40468385916) green; 422 unit +22 PostgreSQL integration, 98,31% coverage (срез T-05). |
| [T-06 #22](https://github.com/inte11ectua1/skinulis/issues/22) Groups/invites/actor | **merged / Issue closed** | Тимур | [PR #27](https://github.com/inte11ectua1/skinulis/pull/27) merged 27.10: `groups/group_members`, одноразовые invites, owner-only GET/DELETE и internal mirrors, service Telegram actor, bootstrap/link, `0003_groups_identity`. [Контракт](contracts/T-06_IDENTITY.md) принят техлидом, backend race/permission/smoke tests зафиксированы ниже. |
| [O-03 #23](https://github.com/inte11ectua1/skinulis/issues/23) Finance ORM/Alembic | **merged / Issue closed** | Олег | [PR #31](https://github.com/inte11ectua1/skinulis/pull/31) merged 28.10 после документационного [PR #33](https://github.com/inte11ectua1/skinulis/pull/33) в его ветку: пять таблиц `expenses/expense_items/expense_shares/expense_item_shares/settlements`, линейная `0004_financial_domain` после `0003`. [CI](https://github.com/inte11ectua1/skinulis/actions/runs/40678199167) на final PR head **5/5 success**. PR-отчёт: 587 unit +138 PostgreSQL integration, coverage 96,63%; **нет финансового CRUD/балансов/автомата компенсаций**. |
| [L-03 #24](https://github.com/inte11ectua1/skinulis/issues/24) Telegram onboarding/groups | **merged / Issue closed** | Лера | [PR #28](https://github.com/inte11ectua1/skinulis/pull/28) merged 28.10: aiogram FSM, explicit Create/Link, профиль/группы/приглашения, типизированный httpx internal API, safe timeout/retry, mock и API+PostgreSQL integration. [CI](https://github.com/inte11ectua1/skinulis/actions/runs/40658217735) **5/5 success**; 571 unit +70 integration по отчёту PR. **Не live Telegram E2E**. |

**M2 follow-ups закрыты:**
- [#29](https://github.com/inte11ectua1/skinulis/issues/29) / [PR #30](https://github.com/inte11ectua1/skinulis/pull/30) — каноническая сериализация datetime в UTC `Z` для T-05/T-06 API, regression на PostgreSQL с не-UTC timezone.
- [#32](https://github.com/inte11ectua1/skinulis/issues/32) / [PR #33](https://github.com/inte11ectua1/skinulis/pull/33) — финансовые контракты Q-03 (NFC/trim/Unicode category C **на будущей входной границе O-04/O-05**), Q-10 (явные нулевые доли), Q-04 (BIGINT/NUMERIC), `position` и `resolved_at`. PR #33 сначала объединён **в ветку Олега**, затем вместе с PR #31 оказался в `main`. Открытые аспекты Q-04/Q-10 для будущих API не считаются закрытыми.

**Факт против gate:** публичная JWT-аутентификация, группы, Telegram bot-service endpoints и клиент бота реализованы и покрыты CI/PostgreSQL tests. **G2 пока not verified**: нет подтверждённого сквозного *live Telegram* сценария на реальном боте с отдельными пользователями, а production reverse proxy для защиты `/internal` относится к T-09 и не развёрнут/не проверен. Независимое `APPROVED` для PR #31 не зарегистрировано; администраторский merge не заменяет review. Не приписывать этапу M2 работающие расходы, балансы, выплаты либо полный продуктовый E2E.

## M3 — Expenses (реализация завершена 30.10.2026; G3 pending)

| Issue | Ответственный | Принятая реализация и ссылки |
|---|---|---|
| [O-04 #36](https://github.com/inte11ectua1/skinulis/issues/36) | Олег | **merged/closed** [PR #41](https://github.com/inte11ectua1/skinulis/pull/41): equal/custom CRUD, actor/member/author, group-first transactions, exact UUID replay, optimistic versions, preview, historical snapshots, mutation balances при confirmed |
| [O-05 #39](https://github.com/inte11ectua1/skinulis/issues/39) | Олег | **merged/closed** [PR #42](https://github.com/inte11ectua1/skinulis/pull/42): by_items 1..50, selected zero shares, исторические позиции, режимные full PUT, original replay, public/internal HTTP |
| [L-04 #37](https://github.com/inte11ectua1/skinulis/issues/37) | Лера | **merged/closed** [PR #43](https://github.com/inte11ectua1/skinulis/pull/43): aiogram expense FSM, три режима, server preview, list/detail, stable UUID, timeout recovery, mock Telegram + real HTTP/PostgreSQL integration |
| [T-07 #35](https://github.com/inte11ectua1/skinulis/issues/35) | Тимур | **merged/closed** [PR #44](https://github.com/inte11ectua1/skinulis/pull/44): security review, T07-01/T07-02 fixed, 20 новых PostgreSQL tests; [отчёт](reviews/T-07_M3_SECURITY_REVIEW.md), [final CI](https://github.com/inte11ectua1/skinulis/actions/runs/41064210033) **5/5 success**, 1147 tests / 95,46% coverage |

Формальные **G2/G3 not verified**: серверные контрактные и PostgreSQL/HTTP проверки есть, но live Telegram delivery и реальный пользовательский E2E сознательно отложены по решению Тимура. Не заменять этой записью отдельную эксплуатационную приёмку. В M3 **не реализованы** отдельные GET balances/settlement-plan, POST settlements и terminal transitions — это M4; существующий internal mutation-balances O-04 только частичная переиспользуемая основа.

## Завершённый M4 — Balances, Settlements, Telegram (31.10.2026)

| Issue | Владелец | Состояние и доказательства |
|---|---|---|
| [O-06 #46](https://github.com/inte11ectua1/skinulis/issues/46) | Олег | **merged/closed**, [PR #51](https://github.com/inte11ectua1/skinulis/pull/51): balances, Q-05 greedy, repeatable-read; [CI 5/5](https://github.com/inte11ectua1/skinulis/actions/runs/41096303217), 1181 tests |
| [O-07 #47](https://github.com/inte11ectua1/skinulis/issues/47) | Олег | **merged/closed**, [PR #53](https://github.com/inte11ectua1/skinulis/pull/53): settlement pending/terminal, UUID replay, fresh balance checks under group-first locks; [CI 5/5](https://github.com/inte11ectua1/skinulis/actions/runs/41195690077), 1283 tests |
| [O-07N #55](https://github.com/inte11ectua1/skinulis/issues/55) | Олег | **merged/closed**, [PR #57](https://github.com/inte11ectua1/skinulis/pull/57): one-shot internal recipient claim, Alembic 0006, PG races; [CI 5/5](https://github.com/inte11ectua1/skinulis/actions/runs/41208270181), 1311 tests |
| [L-05 #48](https://github.com/inte11ectua1/skinulis/issues/48) | Лера | **merged/closed**, [PR #54](https://github.com/inte11ectua1/skinulis/pull/54): Telegram balances/settlement UI, best-effort notification, recovery; [CI 5/5](https://github.com/inte11ectua1/skinulis/actions/runs/41210779152), 1460 tests / 94,76% |
| [T-08 #45](https://github.com/inte11ectua1/skinulis/issues/45) | Тимур | **merged/closed**, [PR #58](https://github.com/inte11ectua1/skinulis/pull/58): [финальный security report](reviews/T-08_M4_FINAL_SECURITY_REVIEW.md); [CI 5/5](https://github.com/inte11ectua1/skinulis/actions/runs/41213175596) |

M4 реализован в коде и проверен PostgreSQL/HTTP/Telegram mocks, но **live Telegram gate G4 отдельно не подтверждён**. У PR есть процессный риск human review evidence; не ретроактивно приписывать APPROVED.

## Текущий M5 — Delivery (Issues созданы и назначены 31.10.2026)

| Issue | Владелец | Что делать и зависимость |
|---|---|---|
| [T-09 #59](https://github.com/inte11ectua1/skinulis/issues/59) | Тимур | **первый critical path**: GHCR SHA, trusted-main CD, Docker Compose/VPS, Caddy HTTPS, снаружи deny /internal, DB private, upgrade/health/version/rollback. Настоящий VPS deploy только после разрешения |
| [T-10 #60](https://github.com/inte11ectua1/skinulis/issues/60) | Тимур | JSON logs/request_id, Docker log rotation, runbook; разработка дизайна сразу, production integration **после T-09** |
| [O-08 #61](https://github.com/inte11ectua1/skinulis/issues/61) | Олег | **старт сейчас, параллельно**: PG financial/security/races, controlled 100 simultaneous clients, p50/p95/p99; без production load |
| [L-06 #62](https://github.com/inte11ectua1/skinulis/issues/62) | Лера | **старт сейчас, параллельно**: Telegram mocked UX error/timeout/replay + real HTTP/PostgreSQL E2E; live Telegram запрещён |

**G5 пока not verified.** Не открывать порты API/DB в Интернет, не передавать prod secrets в PR, не запускать SSH, реальные Telegram updates или стресс-тесты чужого VPS по умолчанию. [M5 handoff](operations/M5_DELIVERY_HANDOFF.md).

## Release gates

| Gate | Статус | Условие проверки |
|---|---|---|
| G1 — cold start / миграция / health / CI | **implementation complete; formal verification pending** | Cold start, миграции, /health 200/503 подтверждены в PR #15; CI зелёный и намеренно красный подтверждены в PR #19. Не завершена визуальная проверка failed-required-check причины блокировки; нет независимого approval PR #19; администраторский bypass требует отдельного решения об уровне защиты. |
| G2 — auth и группы | **implementation complete; formal verification pending** | M2 код merged и CI зелёный; live Telegram E2E и production-изоляция `/internal` не подтверждены |
| G3 — расходы | **not verified** | M3 PR #41–#44 merged и Issues closed, T-07 принята/закрыта; CI 5/5 и ресторанный HTTP/PostgreSQL test evidence есть. **Живой Telegram E2E отложен**, поэтому gate не объявлен verified. [Evidence](reviews/T-07_M3_SECURITY_REVIEW.md). |
| G4 — компенсации | **implementation complete; formal live gate pending** | M4 PR #51/#53/#57/#54/#58 merged/closed, PostgreSQL race/HTTP/mock Telegram tests и T-08 audit есть. Live Telegram QA отложено, independent approvals для ряда PR отсутствуют; не выдавать за verified |
| G5 — публикация и CD | **not verified** | M5 назначен #59/#60/#61/#62, GHCR/VPS/HTTPS/image SHA/приватный /internal ещё не доказаны |
| G6 — приёмка / демонстрация | **not verified** | M6 |

## Открытые вопросы и ограничения

- Последний доступный GitHub API подтверждает, что `main` защищена и перечислены required checks, но **enforcement_level=`non_admins`** (администратор не связан ими на тех же условиях). Это изменение после доказательств T-04; необходимо заново проверить фактические admin bypass settings. Визуальная причина блокировки Merge на красном CI и отказ direct push остаются непроверенными; см. [CI](operations/CI.md).
- Предпросмотр **UQ-03 принят** в O-04: POST /groups/{id}/expenses/preview и internal mirror; без записи/UUID/резервации, расчёты только на сервере. [Контракт](contracts/O-04_EXPENSES.md). Решения balances/settlements реализованы в O-06/O-07/O-07N, см. завершённый M4.
- Денежная грамматика/порядок ID **Q-01/Q-02** приняты в PR #17; прочие Q/UQ закрываются до соответствующих этапов по ответственным.
- API/PostgreSQL/Docker проверены локально в T-03 ([PR #15](https://github.com/inte11ectua1/skinulis/pull/15)); каркас бота принят PR #18, live Telegram и продуктовый E2E не проверены. CI реализован в merged [PR #19](https://github.com/inte11ectua1/skinulis/pull/19). G1 нельзя помечать формально verified до незакрытых доказательств и уточнения admin bypass.

## Локальные доказательства T-03 (26.10.2026)

- macOS arm64, Python 3.12.15, uv 0.13.5; Engine 23.0.5, Compose 2.17.3.
- Frozen-установка, lock check, Ruff lint/format, строгий mypy (19 файлов), все
  pre-commit hooks и проверка совместимости пакетов прошли. Аудит 54 зависимостей
  не обнаружил известных уязвимостей; исключения не добавлялись.
- Unit/T-02: 18 passed; отдельно реальная PostgreSQL 17.11: 4 integration passed.
  Объединённое branch coverage **существующего app/** — 98.69%, не покрытие будущего MVP.
- Холодный запуск на новом изолированном volume: db healthy → migrate exit 0 →
  api healthy; /, /health, /version, /docs, /redoc, /openapi.json — HTTP 200.
  При остановке DB /health → 503; после старта DB → 200 без перезапуска API.
- На чистой БД Alembic применяет 0001_baseline, повторный upgrade успешен,
  alembic check не находит drift. Намеренно ошибочная следующая ревизия в
  отдельном тестовом project: migrate exit 1, API не запущен.
- Runtime UID 10001, без .env/.git/tests/dev dependencies. Тестовые контейнеры
  остановлены, named volumes сохранены; другие проекты и .env не изменялись.
- Windows/Linux host отдельно не проверены; предупреждение Starlette о будущей
  смене httpx для TestClient не подавлено. Реализация T-04 принята, но формальная
  приёмка G1 остаётся отдельной.

## Проверки T-04 (27.10.2026)

[Merged PR #19](https://github.com/inte11ectua1/skinulis/pull/19) ([Issue #13 closed](https://github.com/inte11ectua1/skinulis/issues/13)),
[первый зелёный CI](https://github.com/inte11ectua1/skinulis/actions/runs/40458001625),
[намеренно красный CI](https://github.com/inte11ectua1/skinulis/actions/runs/40458200449).
На GitHub Linux: 343 unit + 4 PostgreSQL integration passed, branch coverage
app + bot 97.79%, Docker build success; frozen/lock/Ruff/mypy/secrets/audit прошли.
Локально macOS повторены эти проверки и Compose integration runner; actionlint
также прошёл. Бизнес-код, тесты владельцев и lock не менялись.

В ходе T-04 административным API были прочитаны required lint/types/tests/docker-build/ci,
strict up-to-date и правила PR/review; красный head имел API BLOCKED. После merge
защита **изменилась**: текущий ответ GitHub показывает enforcement_level=non_admins
для checks. Нельзя сохранять прежнее утверждение о запрете обхода администратором.
Визуальная конкретная причина блокировки merge box ещё не подтверждена.
Намеренная ошибка удалена; восстановленный run и снимок *исторических* настроек
в [CI evidence](operations/CI.md). Issue #13 закрыта после merge PR #19,
при этом в PR #19 не зарегистрировано чужого approval; G1 формально не verified.

## T-05 — merged PR #26

На базе merged PR #25 подготовлены users/BIGINT/Argon2id, register/login,
JWT dependency и /users/me; [предлагаемый контракт](contracts/T-05_IDENTITY.md)
вынесен на review Олегу и Лере через [Issue #21](https://github.com/inte11ectua1/skinulis/issues/21#issuecomment-6436016259).
Это не начало T-06 и не согласование всех Telegram DTO.

Локально macOS: 422 unit + 22 PostgreSQL integration passed; общее branch
coverage app + bot 98.31%. Ruff/mypy, frozen sync/lock, pip check и аудит
72 пакетов прошли. Docker Compose smoke на отдельной БД: healthy DB/API,
0002_users head, повтор upgrade/check без drift, register 201/login 200/me 200,
без токена 401. Проверен migrate без JWT в host/container; логи не содержат
сгенерированных credentials. Volume сохранён, чужие БД не затронуты.

[PR #26](https://github.com/inte11ectua1/skinulis/pull/26): первый [GitHub run](https://github.com/inte11ectua1/skinulis/actions/runs/40468232064)
на commit bf01c59 завершил lint/types/tests/docker-build/ci успешно. Linux: 422 unit,
22 PostgreSQL integration, общее branch coverage app + bot 98.31%, Docker build
успешен. Окончательный [run](https://github.com/inte11ectua1/skinulis/actions/runs/40468385916)
на fc5cd23 также успешен. PR #26 merged, Issue #21 closed. Независимого
APPROVED-review нет; на момент T-05 DTO/TTL/алгоритм/FK были вынесены как предложения. Часть identity-контрактов позже принята tech lead в T-06; это не заменяет независимый review и не закрывает G2.


## T-06 — PR #27, контракт утверждён tech lead

[PR #27](https://github.com/inte11ectua1/skinulis/pull/27), **merged 27.10.2026**. Последующие строки в этом разделе — исторический срез до merge; актуальное M2-резюме см. выше.
База main после [PR #26](https://github.com/inte11ectua1/skinulis/pull/26),
0002_users. Добавлены groups/members, hashed invites, service Telegram actor,
explicit bootstrap и одноразовая привязка; [контракт](contracts/T-06_IDENTITY.md).
Одна следующая ревизия 0003_groups_identity; без финансовых таблиц и изменений bot/**.
[Запрос согласования](https://github.com/inte11ectua1/skinulis/issues/22#issuecomment-6436799120),
[handoff O-03](https://github.com/inte11ectua1/skinulis/issues/23#issuecomment-6436883933),
[handoff L-03](https://github.com/inte11ectua1/skinulis/issues/24#issuecomment-6436885598).
Контракт, включая GET/DELETE и /internal mirrors, утверждён
[Тимуром как tech lead](https://github.com/inte11ectua1/skinulis/issues/22#issuecomment-6437632203). Это не
независимый APPROVED от Олега или Леры; их review по-прежнему запрошен.

Первый срез реализации (до GET/DELETE), macOS: **484 unit + 60 PostgreSQL17 integration passed**, включая независимые
конкурирующие транзакции (lock waits подтверждаются pg_stat_activity), миграции
с чистой и T-05 БД, owner/member FK, ограничения30, single-use и no merge.
Объединённое branch coverage app/ + bot/ **98,24%** (порог60%). [GitHub CI run](https://github.com/inte11ectua1/skinulis/actions/runs/40474060236)
на d23eb48: lint/types/tests/docker-build/ci **success**, Linux484 unit +60 integration,
coverage98,24%. Для текущего head смотрите checks PR #27. Review запрошен у обоих владельцев.
Frozen/lock, Ruff, strict mypy (59 Python files), pip check и audit72 packages без
известных уязвимостей прошли; зависимости/lock не изменялись.

Docker Compose smoke в отдельном project skinulis-t06-smoke-f21d8cd3e4 (первый local smoke, до GET/DELETE):
db/api healthy, migrate exit0, /health и /docs200, register201/login200/me200,
без JWT401, group201/replay без дубля, service bootstrap200, join200/reuse404,
link201/consume200/reuse404, bad service401, cross-group404. Alembic head/check
и повтор migrate без JWT/BOT secrets успешны; секретов в логах нет.
Контейнеры остановлены, named volume сохранён; пользовательские БД не трогались.

HTTP GET списка/DELETE отзыва и /internal mirrors включены по утверждённому
контракту. Результаты полного scope приведены ниже. **Issue #22 закрыта после merge PR #27**. G2 не verified: live Telegram E2E и production-изоляция остаются непроверенными.
Production reverse proxy/изоляция /internal относятся к T-09 и не развёрнуты.


### Завершение GET/DELETE по решению tech lead

[Утверждение контракта 27.10.2026](https://github.com/inte11ectua1/skinulis/issues/22#issuecomment-6437632203)
разрешило завершить backend без ожидания дополнительных решений по маршрутам.
Добавлены GET /groups/{id}/invites, DELETE /groups/{id}/invites/{invite_id} и
/internal mirrors; owner-only права, metadata без token/hash/consumed_by,
pagination20/max100/offset, все состояния, порядок(created_at,id), безопасные
403/404/409, повтор DELETE и отзыв expired unused приглашения. Схема и head
0003_groups_identity не изменялись.

После доработки локально: **511 unit + 68 PostgreSQL integration passed**;
branch coverage app/ + bot/ **98,40%**, порог60 сохранён. Frozen sync/lock, Ruff
lint/format, strict mypy (60 файлов), pre-commit --all-files, pip check и аудит
72 пакетов прошли, известных уязвимостей нет. Новые27 unit и8 integration проверяют
HTTP-контракты, все состояния, tie-break сортировки, empty pages, права и реальную
HTTP join-vs-revoke гонку с независимыми соединениями и подтверждёнными lock waits.

Финальный local Compose smoke: project skinulis-t06-smoke-31dfe6f4db, новые
credentials и отдельная БД. Build/config/up/ps успешны, DB/API healthy,
migrate exit0; старые auth/group/bootstrap/link сценарии работают. Public/internal
GET/DELETE200, повтор DELETE возвращает ту же metadata, member GET403,
consumed DELETE409, join после отзыва404. Ответы и логи без сгенерированных
секретов; повтор Alembic/check и migrate без JWT/BOT secrets успешны. Контейнеры
остановлены без -v, тестовый volume сохранён; пользовательские БД не затронуты.

[GitHub CI после завершения scope](https://github.com/inte11ectua1/skinulis/actions/runs/40478372227)
на a07b52c: lint/types/tests/docker-build/ci success, Linux511 unit +68 integration,
coverage98,40%. Последний head проверяется checks PR #27 перед Ready for review.
T-06 backend впоследствии merged через PR #27, Issue #22 закрыта.
Эти цифры — проверка на head до merge, не live Telegram E2E. Production-изоляция /internal
не проверена, G2 не помечается verified.

## O-05 — PR #42 (28.10.2026)

Новый by_items контракт принят Тимуром в #39/6473059675; HTTP preview/create/read/page/
PUT/DELETE и /internal mirrors реализованы в ветке feat/O-05-by-items-expenses.
Позиции/нули/ordered original replay/версии и все смены режимов покрыты тестами.
Контракт: contracts/O-05_BY_ITEMS.md, fixtures: finance/fixtures/O-05_BY_ITEMS.json.
PR42 merged 28.10.2026, Issue39 closed; это перепроверено при T-07 30.10.
Финальный CI исходного head: [40728353389](https://github.com/inte11ectua1/skinulis/actions/runs/40728353389).
Независимое человеческое review не подменяется решением tech lead; G2 отложено.

## O-06 — merged / Issue #46 closed (30.10.2026)

[PR #51](https://github.com/inte11ectua1/skinulis/pull/51) merged в `main` (`88df77d64deb1bd0dbd5702e91b648f954d45fb0`). JWT/verified bot public/internal GET balances/plan, exact SQL NUMERIC/zero shares, Q-05 greedy и согласованный read-only REPEATABLE READ snapshot. [CI 5/5](https://github.com/inte11ectua1/skinulis/actions/runs/41096303217): 871 unit + 310 PostgreSQL = **1181 tests**, coverage 95,58%. Issue #46 закрыта как completed после технической проверки; независимое human APPROVED в GitHub не зарегистрировано, это не формальная G4 verification. O-07 #47 **может начинаться**, живое Telegram тестирование по решению Тимура остаётся отложенным.
