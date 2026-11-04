# Общая память ChatGPT + Codex

**Источник истины — GitHub main:** docs, ADR, Issues, PR и docs/STATUS.md. ChatGPT-чаты и Codex могут расходиться и не синхронизируют память автоматически.

**Актуальный handoff 04.11.2026:** PR85 merged, main/release `c9ec9ce`;
protected deploy41836839608 с polling=true успешен. Владелец подтвердил UI и меню
production через BotFather. #84/#79/#80 open; M6 не принят полностью, M7 не пройден.
[Свежий аудит](../reviews/POST_RELEASE_AUDIT_2026-11-04.md) / [STATUS](../STATUS.md)
заменяют старые текущие срезы. Общие M6 задачи у Тимура, не создавать новые L-07/O-09.
Есть routing FAIL (пустой200 foreign-authority без доказанной утечки), p95>500ms,
исторические missing approvals/admin bypass; runtime AWS login expired, NOT VERIFIED.
Owner acceptance и зелёный CI не заменяют исключение преподавателя или независимое review.
Любые новые production/AWS/polling изменения требуют отдельного разрешения.

## Цикл
1. В начале задачи прочитать latest main, STATUS.md, issue, AGENTS.md и персональные документы.
2. Обсудить решение в отдельном чате участника; код поручить Codex с конкретными acceptance criteria.
3. Зафиксировать изменения через PR и человеческое ревью.
4. После merge обновить STATUS.md, закрыть issue, создать ADR при изменении архитектуры.
5. Если ChatGPT использует ранее загруженные файлы, обновить источники либо перечитать GitHub через подключение.

Не вести параллельный несинхронизированный «источник истины» в Notion. Notion допустим для заметок, но не канонической архитектуры.