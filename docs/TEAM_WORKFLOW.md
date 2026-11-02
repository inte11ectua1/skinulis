# Командный процесс

Каждый работает в отдельной ветке и под своим GitHub-аккаунтом. Все изменения проходят Pull Request. **Нормальный процесс**: минимум одно approval другого участника и зелёный CI (`lint`, `types`, `tests`, `docker-build`, `ci`). Стратегия — GitHub Flow, Conventional Commits. **Фактическое исключение:** на 27.10.2026 GitHub возвращает required checks enforcement `non_admins`; администратор может обойти часть защиты. Обход не является независимым review и должен быть явно зафиксирован в PR. [Подробности](operations/CI.md).

## Владение
- Тимур: auth, groups, Docker, workflows, deploy, конфигурация.
- Олег: expenses, splits, balances, settlements, миграции финансового домена.
- Лера: bot, API client, UX, end-to-end сценарии.

Согласовывать общий API до реализации, не изменять чужие модели без ревью. Ревью по кругу: Тимур → Олег → Лера → Тимур. Изменения финансов дополнительно проверяет Тимур, безопасности — Олег.

## M5 Delivery — принят (03.11.2026) / M6 Acceptance — план

- M5 T-09 #59, T-10 #60, O-08 #61, L-06 #62 и O-09 #76 **закрыты**; PR #74/#75/#77 merged, первый API HTTPS/CD G5 evidence есть. [Closeout](operations/M5_CLOSEOUT_M6_HANDOFF.md). O-09 100-client pool500 устранены, p95 956/1098ms — внутренний FAIL, явно принят Тимуром.
- **Следующий M6:** T-11 DoD audit/cold start у Тимура, финальный financial QA у Олега (O-09 ID уже использован), L-07 user guide/demo у Леры. Новые Issues ещё не созданы.
- По-прежнему обязательно независимое человеческое GitHub APPROVED до merge; исторические PR без APPROVED не выдавать за reviewed. T-01 #2 закрыта `not_planned`, но исходные branch-protection evidence не закрыты по DoD.
- `pull_request` не получает prod secrets; после merge trusted main может публиковать образ, **но автоматически не деплоит в AWS**: защищённый Environment approval и разрешённый rollout flag. Production SSH/AWS/DB/Telegram polling/live/production stress — только с новой явной командой Тимура.
- G2/G3/G4 live Telegram не проверены; G5 evidence относится к первому API rollout, а не актуальному `main`. `Closes #N` только после полного acceptance; при согласованной уступке фиксировать точное FAIL, как в O-09.

## Перед каждым PR
Прочитать AGENTS.md, docs/PRODUCT_RULES.md, свой SPEC и ROADMAP, выполнить одну issue, добавить тесты, указать проверки, риски, ссылку на issue. После merge обновить docs/STATUS.md.

Две короткие синхронизации в неделю, еженедельный end-to-end demo. Не коммитить токены/пароли.