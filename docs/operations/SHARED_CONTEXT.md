# Общая память ChatGPT + Codex

**Источник истины — GitHub main:** docs, ADR, Issues, PR и docs/STATUS.md. ChatGPT-чаты и Codex могут расходиться и не синхронизируют память автоматически.

**Исторический handoff 31.10.2026:** M4 **completed by implementation**: [T-08 #45/PR #58](https://github.com/inte11ectua1/skinulis/pull/58) и O-06/O-07/O-07N/L-05 в main, Issues closed; [финальный security report](../reviews/T-08_M4_FINAL_SECURITY_REVIEW.md). **M5 assigned:** Тимур [T-09 #59](https://github.com/inte11ectua1/skinulis/issues/59) → [T-10 #60](https://github.com/inte11ectua1/skinulis/issues/60), Олег [O-08 #61](https://github.com/inte11ectua1/skinulis/issues/61), Лера [L-06 #62](https://github.com/inte11ectua1/skinulis/issues/62). Источник подробностей — [M5 Delivery handoff](M5_DELIVERY_HANDOFF.md) и [STATUS](../STATUS.md). G1 T-01 #2, G2/G3/G4 live Telegram и G5 остаются отдельно не verified; реальный SSH/VPS/Telegram/stress без разрешения Тимура запрещён.

**Новое решение 01.11.2026:** VPS заменён ноутбуком Тимура. **Текущая T-09 #59** — локальный Compose (API/DB/migrate и opt-in bot polling) + CI/GHCR, без публичного SSH/Caddy/доменов; T-10 #60 — локальное логирование/восстановление. [ADR003](../adr/003-laptop-as-demo-host.md) и [runbook](LAPTOP_HOSTING.md). Исходный VPS/HTTPS G5 не выполнен и эквивалентность курсу не подтверждена. Не просить Codex создавать сервер/секреты и не запускать настоящий Telegram без разрешения.

## Цикл
1. В начале задачи прочитать latest main, STATUS.md, issue, AGENTS.md и персональные документы.
2. Обсудить решение в отдельном чате участника; код поручить Codex с конкретными acceptance criteria.
3. Зафиксировать изменения через PR и человеческое ревью.
4. После merge обновить STATUS.md, закрыть issue, создать ADR при изменении архитектуры.
5. Если ChatGPT использует ранее загруженные файлы, обновить источники либо перечитать GitHub через подключение.

Не вести параллельный несинхронизированный «источник истины» в Notion. Notion допустим для заметок, но не канонической архитектуры.