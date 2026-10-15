# Подготовка к Codex

## Тимур — один раз
1. Открыть PR с документацией; пригласить Олега, Леру и преподавателя.
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

Пока каркас отсутствует, Олег начинает O-01 (тест-матрица), Лера L-01 (UX), Тимур T-02 (uv).