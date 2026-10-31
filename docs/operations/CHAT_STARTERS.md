# Стартовые сообщения для чатов

## Тимур — M5 / T-09 #59, затем T-10 #60

Я Тимур, Tech Lead проекта «Скинулись». Перед ответом актуализируй GitHub main, START_HERE, AGENTS, STATUS, мои SPEC/ROADMAP и [Issue #59](https://github.com/inte11ectua1/skinulis/issues/59). M1–M4 завершены; подготовь Codex промпт на T-09: GHCR SHA CD, VPS Compose/Caddy HTTPS, private /internal, migrations/version/rollback. **Не запускай SSH/VPS deploy и не работай с настоящими secret без моего явного разрешения**. T-10 #60 — после схемы T-09. Проверь незакрытую T-01 #2 и не называй G1/G5 verified без evidence.

## Олег — M5 / O-08 #61

Я Олег, Financial Backend Engineer проекта «Скинулись». Сверь GitHub main, PRODUCT_RULES, TECHNICAL_DECISIONS, OLEG_SPEC/ROADMAP, STATUS, [Issue #61](https://github.com/inte11ectua1/skinulis/issues/61). O-06/O-07/O-07N уже merged. Дай конкретный Codex промпт для O-08: настоящие PostgreSQL17 security/concurrency regressions и reproducible load 100 concurrent, p95 с измерениями. Тестовую БД делать изолированной, не бить production, не трогать авторизацию/Telegram без согласования.

## Лера — M5 / L-06 #62

Я Лера, Telegram Developer/QA проекта «Скинулись». Сверь GitHub main, AGENTS, LERA_SPEC/ROADMAP, STATUS, [Issue #62](https://github.com/inte11ectua1/skinulis/issues/62). L-05 merged/closed, pending notifications реализованы. Составь Codex промпт для L-06: mock Telegram FSM → real HTTP/PostgreSQL regressions, UX ошибки/таймауты, UUID replay и отсутствие duplicate send. **Не запускать live Telegram polling или реальные аккаунты** без разрешения Тимура.

## Перед каждым PR
Прочитай актуальный STATUS.md, назови следующую незаблокированную issue, критерии приёмки, файлы и тесты, затем составь точный промпт Codex.