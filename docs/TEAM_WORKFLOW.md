# Командный процесс

Каждый работает в отдельной ветке и под своим GitHub-аккаунтом. Все изменения проходят Pull Request. **Нормальный процесс**: минимум одно approval другого участника и зелёный CI (`lint`, `types`, `tests`, `docker-build`, `ci`). Стратегия — GitHub Flow, Conventional Commits. **Фактическое исключение:** на 27.10.2026 GitHub возвращает required checks enforcement `non_admins`; администратор может обойти часть защиты. Обход не является независимым review и должен быть явно зафиксирован в PR. [Подробности](operations/CI.md).

## Владение
- Тимур: auth, groups, Docker, workflows, deploy, конфигурация.
- Олег: expenses, splits, balances, settlements, миграции финансового домена.
- Лера: bot, API client, UX, end-to-end сценарии.

Согласовывать общий API до реализации, не изменять чужие модели без ревью. Ревью по кругу: Тимур → Олег → Лера → Тимур. Изменения финансов дополнительно проверяет Тимур, безопасности — Олег.

## M5 Delivery — границы общего процесса (31.10.2026)

- **Задачи назначены:** Тимур T-09 #59 → T-10 #60, Олег O-08 #61, Лера L-06 #62; [полный handoff](operations/M5_DELIVERY_HANDOFF.md). O-08/L-06 могут начинаться параллельно с T-09, T-10 финальная эксплуатационная часть после T-09.
- В **pull_request** workflow только CI на недоверенном коде **без** SSH/prod DB/GHCR deploy secrets. CD/публикация/deploy — исключительно после одобренного merge в main; если настоящих серверных данных нет, сделать dry-run/static tests/partial PR, не утверждать G5 verified.
- T-09 публично закрывает `/internal` reverse proxy/не публикует PostgreSQL; O-08 грузит **только одноразовую приватную тестовую БД** (100 concurrent), L-06 использует **mock Telegram**, без реального polling. Настоящие SSH/VPS/live Telegram/load-production действия — только с явного разрешения Тимура.
- PR с завершённой Issue должен содержать **`Closes #N`**, частичный PR **`Refs #N`**, не закрывать незаконченный scope. **Independent human APPROVED обязателен по процессу**, даже если admin GitHub может обходить protection. Исторические PR без APPROVED не «одобрены задним числом».

**M5-L update 01.11.2026:** Тимур отказался от VPS для текущего хостинга. [ADR003](adr/003-laptop-as-demo-host.md), [инструкция](operations/LAPTOP_HOSTING.md). Теперь T-09 — ноутбук/Compose и проверенная main, T-10 — локальная диагностика; O-08/L-06 не меняют scope. **Не включать** из предыдущего workflow `operation=deploy` по SSH/production rollout; отдельные облачные/серверные секреты не нужны. PR CI и GHCR publication остаются. Telegram bot long polling только по явной команде пользователя; не выдавать laptop smoke за исходный G5 VPS/HTTPS или за независимое human APPROVED.

## Перед каждым PR
Прочитать AGENTS.md, docs/PRODUCT_RULES.md, свой SPEC и ROADMAP, выполнить одну issue, добавить тесты, указать проверки, риски, ссылку на issue. После merge обновить docs/STATUS.md.

Две короткие синхронизации в неделю, еженедельный end-to-end demo. Не коммитить токены/пароли.