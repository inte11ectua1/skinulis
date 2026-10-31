# Подготовка к Codex

> **Исторический чек-лист первоначальной настройки (M0)**, не повторная команда. На 31.10.2026 **M1–M4 завершены по реализации**; M4 [PR #51/#53/#57/#54/#58](https://github.com/inte11ectua1/skinulis/pull/58) merged, Issues #45/#46/#47/#48/#55 closed. **Текущий M5 назначен:** Тимуру [T-09 #59](https://github.com/inte11ectua1/skinulis/issues/59) → [T-10 #60](https://github.com/inte11ectua1/skinulis/issues/60), Олегу [O-08 #61](https://github.com/inte11ectua1/skinulis/issues/61), Лере [L-06 #62](https://github.com/inte11ectua1/skinulis/issues/62). [M5 handoff](M5_DELIVERY_HANDOFF.md). T-01/G1 ещё открыта, live Telegram QA G2/G3/G4 отложено, G5 требует реального deploy/evidence. Преподавателя пока не приглашать; GitHub main — актуальный источник.

## Ниже — исходные инструкции первоначальной настройки

## Тимур — один раз
1. Стартовый PR и приглашения Олега/Леры уже выполнены. **Приглашение преподавателя перенесено на заключительный этап по решению Тимура**.
2. В Settings → Rules → Rulesets настроить protection main: PR, минимум один approval, dismiss stale approvals, resolved conversations, запрет force-push/deletion, без bypass. Как только появится CI — обязательные status checks.
3. Создать Issues T-01, O-01, L-01 и назначить владельцев по GitHub usernames.
4. Решения GitHub Flow и uv оформить ADR001/ADR002.

## Каждый
1. Принять приглашение в GitHub; настроить Git username/email, SSH либо HTTPS auth.
2. Установить Git, Docker/Compose, Python 3.12, uv, доступ к Codex.
3. Клонировать репозиторий, открыть его корень в Codex.
4. Прочитать START_HERE.md, AGENTS.md, PRODUCT_RULES, TECHNICAL_DECISIONS, свой SPEC/ROADMAP.
5. Создать свою ветку feat/T-xx, feat/O-xx или feat/L-xx. Не работать в main.
6. Codex получает одну issue и обязан отчитаться о тестах, изменениях и ограничениях.
7. Проверить diff и секреты; коммит под своим аккаунтом; создать PR; запросить review.

## Особенности
Тимур — администрирование репозитория, VPS и secrets; Олег — PostgreSQL для интеграционных тестов; Лера — тестовый Telegram-бот, токен только в окружении.

**Актуально после M4:** завершённые M4 Issues #45/#46/#47/#48/#55 не переоткрывать. M5 Issues #59/#60/#61/#62 назначены, Codex читает **свою** новую Issue и свежую main перед работой. T-09 critical path инфраструктуры и network isolation, без разрешённых VPS credentials допускается только код/dry-run/partial PR (Refs, не Closes); O-08 реальный load только на изолированной test DB, L-06 mocked Telegram+HTTP/PG без настоящего polling. Финальный PR `Closes #N` только когда acceptance выполнен, CI 5/5 и независимый review. Никаких production secrets в PR и никаких несанкционированных SSH/live Telegram/production stress действий.
