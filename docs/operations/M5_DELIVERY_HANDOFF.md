# Handoff M4 → M5 Delivery (31.10.2026)

**Источник фактов:** GitHub `main` на старте этого handoff `eb3ae2880348b30df852ba653f0ac977d7ad007e` после merged [T-08 PR #58](https://github.com/inte11ectua1/skinulis/pull/58), Issue [#45](https://github.com/inte11ectua1/skinulis/issues/45) closed completed. Это **закрытие объёма M4 по коду и техническому аудиту**, не формальная проверка релизных G1/G2/G3/G4 и не обещание production готовности.

## 1. Что уже принято по M4

| Workstream | Issue | PR | Доказательство |
|---|---|---|---|
| O-06 balances + Q-05 plan | [#46](https://github.com/inte11ectua1/skinulis/issues/46) | [#51](https://github.com/inte11ectua1/skinulis/pull/51) | [CI 5/5, 1181 tests, 95,58%](https://github.com/inte11ectua1/skinulis/actions/runs/41096303217) |
| O-07 manual settlements + locks | [#47](https://github.com/inte11ectua1/skinulis/issues/47) | [#53](https://github.com/inte11ectua1/skinulis/pull/53) | [CI 5/5, 1283 tests, 95,71%](https://github.com/inte11ectua1/skinulis/actions/runs/41195690077) |
| O-07N notification claim | [#55](https://github.com/inte11ectua1/skinulis/issues/55) | [#57](https://github.com/inte11ectua1/skinulis/pull/57) | [CI 5/5, 1311 tests, 95,76%](https://github.com/inte11ectua1/skinulis/actions/runs/41208270181) |
| L-05 Telegram balances/transfer UX | [#48](https://github.com/inte11ectua1/skinulis/issues/48) | [#54](https://github.com/inte11ectua1/skinulis/pull/54) | [CI 5/5, 1460 tests, 94,76%](https://github.com/inte11ectua1/skinulis/actions/runs/41210779152) |
| T-08 финальный security audit | [#45](https://github.com/inte11ectua1/skinulis/issues/45) | [#58](https://github.com/inte11ectua1/skinulis/pull/58) | [Итоговый отчёт](../reviews/T-08_M4_FINAL_SECURITY_REVIEW.md), [CI 5/5](https://github.com/inte11ectua1/skinulis/actions/runs/41213175596) |

**Не складывать тесты разных CI runs**: каждый PR включает накопленный regression suite. PR #58 содержит документацию/аудит, не новый денежный функционал. Real Telegram тесты по решению Тимура не проводились. На нескольких завершённых M4 PR не зарегистрирован independent human APPROVED; PR #58 тоже объединён без зарегистрированного APPROVED. Не задним числом оформлять чужое одобрение; это отдельное процессное ограничение [T08-01](../reviews/T-08_M4_FINAL_SECURITY_REVIEW.md).

## 2. Назначенные задачи M5

| Приоритет | Участник | Issue | Цель | Что реально может делаться сейчас |
|---|---|---|---|---|
| **Критический путь 1** | Тимур | [T-09 #59](https://github.com/inte11ectua1/skinulis/issues/59) | GHCR immutable SHA, main-only CD, VPS Compose, HTTPS Caddy, публичный блок /internal, migrations, rollback | Проектирование, workflow, конфиг, тесты без prod secrets; реальный deploy только после отдельной команды и доступов |
| **После контракта T-09** | Тимур | [T-10 #60](https://github.com/inte11ectua1/skinulis/issues/60) | Структурированные JSON-логи, request_id, ротация, эксплуатационный rollback/runbook | Код/документация в параллельном workstream, финальная Compose integration после T-09 |
| **Параллельно T-09** | Олег | [O-08 #61](https://github.com/inte11ectua1/skinulis/issues/61) | PostgreSQL invariants/security/races + реальная воспроизводимая нагрузка 100 concurrent/p95 | От fresh main, отдельная disposable PG DB, без prod load |
| **Параллельно T-09** | Лера | [L-06 #62](https://github.com/inte11ectua1/skinulis/issues/62) | UI retry/timeout/error regression, mocked Telegram → real HTTP/PostgreSQL E2E | От fresh main, **без** live Telegram |

**Порядок:** начать с архитектуры T-09, O-08 и L-06 независимы и могут кодиться параллельно. T-10 может готовить JSON logging/runbook, но финальные Docker-настройки после согласованного T-09. T-09 реальный deploy блокируется отсутствующим разрешением/данными VPS, не должен мешать остальным тестовым задачам. Если команда выберет строго последовательную работу: T-09 design → O-08 → L-06 → T-09 integration/deploy по разрешению → T-10 operational finish. Это порядок зависимости, а не обязательный порядок людей.

**PR/Issue:** отдельная feature branch, green `lint/types/tests/docker-build/ci`, независимый human review без обхода защиты, `Closes #N` **только для полного acceptance**, промежуточное `Refs #N` не закрывает Issue. На реальном deploy только одобренный main и отдельные GitHub Secrets, без токенов в PR.

## 3. Gate / запреты

- **G1 / [T-01 #2](https://github.com/inte11ectua1/skinulis/issues/2):** main protected, но admin bypass/current enforcement и практический отказ прямому push не верифицированы; Issue остаётся open.
- **G2/G3/G4:** scoped реализация и реальные PostgreSQL/HTTP+mock Telegram tests готовы, но live Telegram QA специально отложено по решению Тимура ([#38](https://github.com/inte11ectua1/skinulis/issues/38) not_planned). **Не запускать live polling/настоящие Telegram аккаунты**, не объявлять gates verified.
- **G5 / M5:** не verified до реального GHCR image:SHA, HTTPS /health (DB healthy), /version exact SHA, private PostgreSQL и недоступного снаружи /internal; фактический SSH deploy требует explicit approval и предоставленных безопасных credentials.
- O-08 latency target p95 ≤500 ms при **описанной нагрузке**, 100 одновременно активных клиента — пока только критерий; **нет** выполненных M5 замеров. Не выдумывать результаты.
- Не менять PRODUCT_RULES/TECHNICAL_DECISIONS/ADR или API-схемы без отдельного согласованного Issue. Нет банка/Redis/Celery/новой БД или новых live демо.

## 4. Источники для Codex

Перед задачей перечитать свежие `START_HERE.md`, `AGENTS.md`, `docs/STATUS.md`, `docs/roadmaps/MASTER_ROADMAP.md`, персональные SPEC/ROADMAP и соответствующую **назначенную** GitHub Issue. Старые файловые вложения ChatGPT и исторические главы документации не заменяют `main`; считать этот файл M5 handoff до следующего документированного этапа. 
