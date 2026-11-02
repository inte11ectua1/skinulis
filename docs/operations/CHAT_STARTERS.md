# Стартовые сообщения для чатов — M6 план (03.11.2026)

**Перед началом:** M5 закрыт [по согласованным критериям](M5_CLOSEOUT_M6_HANDOFF.md); новых M6 GitHub Issues пока нет. Сверять актуальные GitHub main, [STATUS](../STATUS.md), roadmap, AGENTS и реальные Issues. Не считать старые сообщения M5 актуальными заданиями.

## Тимур — M6 / T-11, DoD и демонстрация

Я Тимур, tech lead «Скинулись». Проверь свежий main, START_HERE, AGENTS, STATUS, TIMUR_SPEC/ROADMAP и [M5 closeout](M5_CLOSEOUT_M6_HANDOFF.md). Предложи критерии отдельной Issue T-11: обязательный DoD преподавателя, независимый PR approval, админские правила main, чистый Docker Compose setup, инфраструктурный evidence и готовность к защите. Не объявляй весь DoD закрытым без доказательств. Без явного разрешения не выполнять AWS deployment/live Telegram или менять secrets.

## Олег — M6 / финальный финансовый QA (ID ещё согласовать)

Я Олег, financial backend engineer. Изучи свежий main, PRODUCT_RULES, TECHNICAL_DECISIONS, OLEG_SPEC/ROADMAP, STATUS, [O-08 отчёт](LOAD_TEST_M5.md) и O-09 [#76](https://github.com/inte11ectua1/skinulis/issues/76). O-08 и O-09 уже закрыты. Подготовь проверяемый план финального финансового/PG QA для M6, включая честный p95 FAIL при принятом отказе от 500ms; **не создавай и не выполняй ещё одну O-09**. Перед кодом согласовать новую Issue/ID, не использовать production для тестов.

## Лера — M6 / L-07 user guide и demo script

Я Лера, Telegram Developer/QA. Прочитай свежий main, AGENTS, LERA_SPEC/ROADMAP, STATUS и [L-06 regression](../bot/L-06_UX_REGRESSION.md). M5 L-06 #62 merged/closed. Помоги сформировать отдельную L-07 Issue: user guide, три синтетических участника, demo script от /start до confirm, ошибки и безопасные скриншоты. Live Telegram без явного разрешения Тимура запрещён; offline HTTP/PG не является live E2E.

## Перед новым PR

Сначала оформите отдельную Issue и acceptance; отдельная ветка от свежего main, 5/5 CI, independent human APPROVED, `Closes` только при полном scope. Не мержить без review и не выдавать архивные статусы за текущие.
