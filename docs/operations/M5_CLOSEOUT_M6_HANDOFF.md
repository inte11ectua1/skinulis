# M5 Delivery → M6 Acceptance: закрытие и handoff (03.11.2026)

**Решение владельца (Тимур): M5 завершён и принят по согласованному объёму разработки и первичного deployment.** Это **не** означает, что полный DoD курса, все release gates или live Telegram demo приняты. Срез к GitHub `main` `0de89b3a5f47522fe4932551d746fe1eb839e463` (merge PR #77); [post-merge main CI #41536084636](https://github.com/inte11ectua1/skinulis/actions/runs/41536084636) **5/5 success**, [Release #41537783167](https://github.com/inte11ectua1/skinulis/actions/runs/41537783167) **success** (trusted publication, не deployment). [PR #77 CI 5/5](https://github.com/inte11ectua1/skinulis/actions/runs/41533351706).

## 1. Что завершено

| Участник/работа | Issue | PR / результат |
|---|---|---|
| Тимур T-09, production GHCR/CD/HTTPS | [#59](https://github.com/inte11ectua1/skinulis/issues/59), closed completed | [#64](https://github.com/inte11ectua1/skinulis/pull/64) и [первый approved rollout](T-09_FIRST_PRODUCTION_ROLLOUT.md); публичный API, Caddy TLS, private PG, запрет /internal, exact deployed /version |
| Тимур T-10, JSON logs / incident | [#60](https://github.com/inte11ectua1/skinulis/issues/60), closed completed | [#71](https://github.com/inte11ectua1/skinulis/pull/71), [#73](https://github.com/inte11ectua1/skinulis/pull/73); логи/ротация и operational runbook, фактические проверки API |
| Олег O-08, PG security/races/load | [#61](https://github.com/inte11ectua1/skinulis/issues/61), closed completed | [#74](https://github.com/inte11ectua1/skinulis/pull/74); PostgreSQL regression/real concurrent load, честный первоначальный performance FAIL |
| Лера L-06, Telegram UX/offline E2E | [#62](https://github.com/inte11ectua1/skinulis/issues/62), closed completed | [#75](https://github.com/inte11ectua1/skinulis/pull/75); mock Telegram → локальные HTTP/FastAPI/PostgreSQL17, recovery/error/UUID |
| Тимур O-09 follow-up, pool starvation | [#76](https://github.com/inte11ectua1/skinulis/issues/76), closed completed | [#77](https://github.com/inte11ectua1/skinulis/pull/77); освобождение auth connection до RR snapshot и повторный тест 100 клиентов |

На момент закрытия M5 **не было открытых Issues или PR по продуктовым задачам**; этот документ подготовлен в отдельном [документационном PR #78](https://github.com/inte11ectua1/skinulis/pull/78). Для задач M6 **новые Issues ещё не заведены**; они являются планом, а не уже назначенной работой. Исторический [M4 → M5 handoff](M5_DELIVERY_HANDOFF.md) хранится для аудита, но не отражает нынешнюю очередь задач.

## 2. Нагрузка и явно принятая уступка

Испытания [O-09](LOAD_TEST_M5.md) выполнены на одной локальной машине с отдельной тестовой PostgreSQL17, фиксированными seed6108, mixed/contention, 100 одновременными клиентами, 10 секунд warmup + 30 секунд нагрузки, прежними pool 5+10/timeout3s, worker и mix:

| Профиль | HTTP 500 до → после | Pool timeouts до → после (с warmup) | RPS до → после | p95 до → после |
|---|---|---|---|---|
| mixed | 368 → **0** | 533 → **0** | 13.72 → **126.92** | 12075 → **956 мс** |
| contention | 353 → **0** | 517 → **0** | 13.11 → **120.24** | 12072 → **1098 мс** |

[Исходные агрегаты O-09](O-09_LOAD_RESULTS.json). **Внутренний таргет p95≤500 мс не достигнут (FAIL)**. Тимур явно принял текущую latency и закрыл #76 как устранение критического исчерпания пула; это **исключение из внутренней цели**, а не ложный PASS и не изменение официального DoD преподавателя. Бенчмарк локальный; AWS с новым кодом не нагрузочно тестировался.

## 3. Production/G5 и границы приёмки

- Первый production rollout [Release #41428440222](https://github.com/inte11ectua1/skinulis/actions/runs/41428440222) успешен: **https://3-25-53-31.sslip.io**, SHA развернутого приложения `f7020cda3908d7e0c40c0b0f840e322b3d6cfda5`, SSL/Caddy, /health с БД, /version, /internal deny и private PostgreSQL проверены [в момент rollout](T-09_FIRST_PRODUCTION_ROLLOUT.md). Это техническое evidence G5 для **первого rollout**, а не повторная проверка текущей доступности сайта.
- Последний код `main` после PR #77 **не развёрнут автоматически**: merge ≠ production deploy; механизм release по умолчанию не разрешает rollout. Для нового deployment и отдельно для polling нужно явное разрешение владельца и protected Environment approval.
- **Бот polling выключен**; live G2/G3/G4 не подтверждены, даже если offline E2E зелёный. Производственный бот/реальные пользователи не тестировались.
- **G1 / T-01 #2** закрыта `not_planned` как административное решение, **не** как fully accepted: режим защиты допускает admin bypass, фактический direct-push rejection не доказан; приглашение преподавателя отложено.
- В ряде merged PR (включая #77) **нет независимого submitted GitHub APPROVED**. Это остаётся риском соответствия обязательному критерию курса; устное согласие и CI не подменяют formal human review.
- Нет подтверждённого production rollback с реальным outage; документация/изолированные тесты присутствуют. Автобэкапы, дополнительная offline key escrow, собственный домен и Elastic IP **не являются зафиксированными обязательными критериями официального DoD**; владелец отказался от дополнительных работ по ним для учебного проекта.

## 4. Следующая фаза M6 Acceptance (план, не созданные Issues)

**Тимур / T-11:** сверить актуальный [официальный DoD](https://github.com/andrey-limasov/app-conf/blob/main/definition-of-done.md) пункт за пунктом, отдельно зафиксировать исключения/факты GitHub reviews/protection, доказать чистый локальный запуск Docker Compose + миграции + test DB, проверить сценарий демонстрации и release evidence. Не объявлять обязательный DoD выполненным без доказательств или предварительного согласования с преподавателем.

**Олег / финальный QA:** проверить финансовые invariants, 100-client O-09 report, подготовить объяснение double checkout и residual p95, провести аудит PR/PG/concurrency; исходное roadmap имя O-09 **уже занято завершённой #76** — **не создавать новую задачу с тем же ID**. Новую M6 Issue/ID согласовать отдельно, если потребуется.

**Лера / L-07:** подготовить простую пользовательскую инструкцию /start → profile → group/invite → expense modes → balances → pending/confirm/reject/cancel; безопасные synthetic screenshots, 3-user test/demo script, список UX отказов. Live Telegram/E2E **только по отдельному решению Тимура**; до этого mock/HTTP/PG evidence, не выдавать за живой smoke.

**M7 Defense после M6:** 7-минутная презентация, 5-минутная демонстрация и ответы на вопросы по программе курса. Проверить заранее, что реально может работать с предоставленной сетью и разрешённым режимом запуска.

## 5. Операционный процесс

Новые задачи — отдельные issues и ветки от свежей `main`; 5/5 CI плюс **independent human APPROVED до merge**. Не делать direct push в `main`; не запускать production deploy, не изменять AWS/секреты, не проводить production stress/реальный Telegram polling без нового явного разрешения Тимура. Канонический статус: [STATUS](../STATUS.md), [roadmap](../roadmaps/MASTER_ROADMAP.md); этот документ — зафиксированный handoff, а не свидетельство уже проведённого M6 smoke.
