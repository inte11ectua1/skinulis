# Командный процесс

Каждый работает в отдельной ветке и под своим GitHub-аккаунтом. Все изменения проходят Pull Request. **Нормальный процесс**: минимум одно approval другого участника и зелёный CI (`lint`, `types`, `tests`, `docker-build`, `ci`). Стратегия — GitHub Flow, Conventional Commits. **Фактическое исключение:** на 27.10.2026 GitHub возвращает required checks enforcement `non_admins`; администратор может обойти часть защиты. Обход не является независимым review и должен быть явно зафиксирован в PR. [Подробности](operations/CI.md).

## Владение
- Тимур: auth, groups, Docker, workflows, deploy, конфигурация.
- Олег: expenses, splits, balances, settlements, миграции финансового домена.
- Лера: bot, API client, UX, end-to-end сценарии.

Согласовывать общий API до реализации, не изменять чужие модели без ревью. Ревью по кругу: Тимур → Олег → Лера → Тимур. Изменения финансов дополнительно проверяет Тимур, безопасности — Олег.

## Текущая очередь (04.11.2026)

M5 closed; #84 UX merged PR85 и production release `c9ec9ce`. M6 остаётся единой
[#79](https://github.com/inte11ectua1/skinulis/issues/79), ответственный Тимур,
консультации/review Олега и Леры без дублирующих задач. M7 — #80, open.
[Аудит](reviews/POST_RELEASE_AUDIT_2026-11-04.md) отделяет owner live-подтверждение
от полной независимой учебной приёмки. 41/52 merged PR без APPROVED, включая #85;
Environment approval deploy не является code review. Main enforce_admins=false;
Environment can_admins_bypass=false. Правила не ослаблялись.
Trusted CI/publish не означают deploy: новый rollout требует разрешения владельца,
production Environment approval и rollout flag. Выполненный Release41836839608
имел polling=true; flag снова false. Не запускать второй бот/новый deploy/DB writes
ради документационной проверки. Удаление групп и Mini App вне MVP.

## Перед каждым PR
Прочитать AGENTS.md, docs/PRODUCT_RULES.md, свой SPEC и ROADMAP, выполнить одну issue, добавить тесты, указать проверки, риски, ссылку на issue. После merge обновить docs/STATUS.md.

Две короткие синхронизации в неделю, еженедельный end-to-end demo. Не коммитить токены/пароли.