# Общая память ChatGPT + Codex

**Источник истины — GitHub main:** docs, ADR, Issues, PR и docs/STATUS.md. ChatGPT-чаты и Codex могут расходиться и не синхронизируют память автоматически.

**Актуальный handoff 03.11.2026:** M5 **принят по согласованному объёму**. T-09 #59 и T-10 #60 (Тимур), O-08 #61 (Олег), L-06 #62 (Лера), O-09 #76 (Тимур) — все **closed** и PR #74/#75/#77 merged. [Фактический closeout и M6-план](M5_CLOSEOUT_M6_HANDOFF.md); подробности [STATUS](../STATUS.md). G5 — evidence первого API production rollout (не новый `main`), Telegram polling off, live G2/G3/G4 not verified. O-09 устранила HTTP500 на 100-client local load; p95≈956/1098ms **выше внутреннего таргета 500ms**, но Тимур принял это отклонение. T-01 #2 закрыта `not_planned` и не fully accepted; недостающие GitHub human APPROVED — риск для DoD.

**Следом M6 Acceptance (ещё без Issues):** Тимур T-11 DoD/cold start, Олег финальный PG/finance audit, Лера L-07 user guide/demo. Утверждать, что новая задача назначена, можно только после создания GitHub Issue. Prod deploy/AWS/SSH/live Telegram/stress — только после явной новой команды Тимура.

## Цикл
1. В начале задачи прочитать latest main, STATUS.md, issue, AGENTS.md и персональные документы.
2. Обсудить решение в отдельном чате участника; код поручить Codex с конкретными acceptance criteria.
3. Зафиксировать изменения через PR и человеческое ревью.
4. После merge обновить STATUS.md, закрыть issue, создать ADR при изменении архитектуры.
5. Если ChatGPT использует ранее загруженные файлы, обновить источники либо перечитать GitHub через подключение.

Не вести параллельный несинхронизированный «источник истины» в Notion. Notion допустим для заметок, но не канонической архитектуры.