# Подготовка к Codex

> **Исторический чек-лист первоначальной настройки (M0)**, не новая команда. На 30.10.2026 M1–M3 **завершены по реализации** (M3 PR #41–#44 merged, Issues #35/#36/#37/#39 closed). **Текущий этап M4 назначен:** [T-08 #45](https://github.com/inte11ectua1/skinulis/issues/45) Тимуру, [O-06 #46](https://github.com/inte11ectua1/skinulis/issues/46) → [O-07 #47](https://github.com/inte11ectua1/skinulis/issues/47) Олегу, [L-05 #48](https://github.com/inte11ectua1/skinulis/issues/48) Лере. До merge O-06 full O-07 implementation blocked; Лера начинает с mock UI, HTTP — после согласованных contract/merged backend. G1/G2/G3 не verified, T-01 открыта, live Telegram отложен до отдельного сигнала Тимура. Преподавателя пока не приглашать. Актуальные факты: [STATUS](../STATUS.md).

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

**Актуально после M3:** задачи M3 #35/#36/#37/#39 уже closed. Новые M4 Issues #45–#48 **созданы и назначены**; начинать от свежей `main` в отдельных ветках и PR, утверждать новые Q/UQ до публичного API. O-07 реализация — после O-06, L-05 HTTP — после backend; не переиспользовать старые Issues. Формальные доказательства T-01/G1 и живой Telegram G2/G3 остаются открытыми/отложенными по решению Тимура.