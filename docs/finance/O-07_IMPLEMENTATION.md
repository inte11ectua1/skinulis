# O-07 — ручные компенсации

Issue #47: реализация для независимого PR review, **не merged**. База — main после
PR #51 (O-06) и #52 (правила PR). Используется принятый
[T-08 контракт](../contracts/T-08_M4_BALANCES_SETTLEMENTS.md), без новых финансовых
решений, миграций, банковских операций или Telegram handlers.

## API и данные

Публичные маршруты используют прежний verified JWT actor. Все пять операций имеют
такие же `/internal` mirrors через T-06 verified bot-service actor:

| Метод / путь | Результат |
|---|---|
| POST /groups/{group_id}/settlements | 201 pending; 200 original pending replay |
| GET /groups/{group_id}/settlements | Актуальные записи, items/limit/offset |
| POST /settlements/{settlement_id}/confirm | Только receiver, confirmed |
| POST /settlements/{settlement_id}/reject | Только receiver, rejected |
| POST /settlements/{settlement_id}/cancel | Только sender, cancelled |

Sync routes: app/api/settlements.py; строгие Pydantic v2 DTO и OpenAPI examples:
app/schemas/settlements.py; бизнес-логика: app/services/settlements.py.
[Typed fixtures](fixtures/O-07_SETTLEMENTS.json) проверяются Pydantic в unit-тесте.
Body create: receiver_id, amount, client_request_id. Sender берётся из actor.
Action body отсутствует либо пустой объект; actor/status/server fields запрещены.
Mutation response — только settlement, без баланса и банка.

Деньги: прежние parse_money/format_money, integer копейки, canonical ASCII RUB
с двумя знаками. Одна компенсация 1..9223372036854775807 коп., без expense cap.
Максимальная каноническая строка занимает 20 символов. Агрегаты остаются точными
NUMERIC/Python int и могут превышать BIGINT. Даты aware UTC с Z. Все ответы имеют
no-store и X-Request-ID; 401 сохраняет WWW-Authenticate. Общие безопасные ошибки
переиспользованы, SQL/секреты в них не выдаются.

GET: текущие члены видят записи своей группы. created_at,id ASC, limit20/1..100,
offset>=0; optional status и direction=incoming/outgoing/all (default all).
Фильтрация до LIMIT/OFFSET, направления относятся к actor. Нет total/has_next,
N+1 или write locks. Чужой/неизвестный ресурс скрыт404.

## Состояния и права

| Текущее | Действие | Actor | Итог |
|---|---|---|---|
| pending | confirm | receiver | fresh balance check, confirmed, resolved_at |
| pending | reject | receiver | rejected, resolved_at, эффект0 |
| pending | cancel | sender | cancelled, resolved_at, эффект0 |
| terminal | тот же action | разрешённый actor | 200, тот же resolved_at, эффект0 |
| terminal | иной action | actor с правом этого action | 409 settlement_state_conflict |
| любое | wrong member, включая owner | нет нужной роли | 403 sender/receiver_required |

Роль проверяется до terminal retry. Owner не получает исключений. При первом
переходе меняются только status/resolved_at; group/sender/receiver/amount/UUID/
created_at никогда не редактируются сервисом. Terminal история не исправляется
после expense PUT/DELETE. Прямой административный SQL вне service layer.

Pending — уведомление о внешнем переводе, не банковский платёж и не резерв долга.
Балансы/greedy использованы из O-06: только confirmed даёт sender плюс, receiver
минус. Ресторан3200: 2200/-1400/-800; pending500 ничего не меняет; confirmed500
→1700/-900/-800; soft-delete расхода →-500/500/0 и обратный план.

## UUID и timeout recovery

UNIQUE(group_id,client_request_id) уже существует. Frozen Intent: group_id,
verified sender_id, receiver_id, amount_kopecks. После group lock и membership
сначала читается UUID, до проверки нового размера долга. Равное намерение →200
с исходными immutable полями, status=pending, resolved_at=null даже после terminal.
Иное намерение/actor →safe409 request_conflict без раскрытия оригинала.

Исходный результат однозначно восстанавливается, JSONB/new migration не нужны.
UUID может существовать в другой группе или таблице expenses. Group lock
сериализует дубликаты; UNIQUE — дополнительная защита. Первый POST →201.

После потерянного ответа повторять тот же UUID и body. Replay — история создания,
**не текущий статус**: затем GET settlements, после confirm GET balances/plan.
Это обязательный handoff для L-05 #48; нельзя показывать replay как current.

## Транзакции и гонки

write_transaction владеет единственным commit/rollback, включая auth autobegin.
Сначала require_member(...,lock=True): SELECT groups FOR UPDATE; затем settlement
FOR UPDATE с populate_existing. Для action исходный SELECT group_id по ID не
блокирует строку и не авторизует доступ. Settlement-first locks отсутствуют.

Confirm pending вызывает существующий calculate_balances **в текущей write Session
под group lock**. Он читает свежую историю после предыдущего writer commit,
проверяет expense snapshots, берёт только active final shares и confirmed;
T07-01/T07-02 сохранены. Проверка: sender<0, receiver>0, amount<=min(debt,credit).
Иначе409 settlement_balance_conflict и rollback: pending/resolved_at=null остаются.
Read-only RR Session O-06 тут не вызывается.

Расходные PUT/DELETE используют тот же group-first lock. Две pending на весь долг
допустимы; первый confirm исчерпывает долг, второй после lock wait получает409.
Same-row confirm →200 без второго эффекта. Последующий PUT/DELETE сохраняет
confirmed, допускает reverse debt. GET balances/plan сохраняет единый RR snapshot.

## Проверки и доказательство перекрытия

Unit: строгие ID/money/UUID/extra fields, intent/роли/пределы, fixtures/OpenAPI.
PostgreSQL17: настоящий API, независимые Sessions/connections, без mock математики:

- Restaurant, partial/full, terminal retries/replay, immutable UUID/timestamps,
  reverse debt, public/internal access, safe errors/no-store, filters/pagination.
- BIGINT maximum compensation и агрегат3×BIGINT, snapshot corruption safe500.
- AFTER INSERT/UPDATE PostgreSQL trigger вызывает настоящую ошибку БД; проверяются
  полный rollback, прежние status/history/balances.
- В восьми writer race случаях первый HTTP writer остановлен после group lock.
  Второй HTTP request начинает транзакцию. Observer через pg_stat_activity и
  pg_blocking_pids доказывает ожидание именно PID первого writer; оба futures ещё
  не завершены. Затем первый отпускается; проверяются результат и весь вектор.
  Это same/different UUID, same/different confirm row, confirm vs PUT/DELETE в
  обоих порядках. Последовательные вызовы не выдаются за overlap.
- Два reader/confirm overlaps: RR reader приостановлен после первого financial
  SELECT, confirm commits на другом соединении; reader возвращает целый старый
  результат, следующий GET — новый. Старые O-06 overlaps остаются.
- Список получает пять строк постоянным числом SELECT, без FOR UPDATE.

Точные результаты, CI/coverage/final SHA публикуются в PR. Если локальный Docker
Engine недоступен, реальные PG/migrations/build evidence берутся из нового CI на
PR head с явной оговоркой. Reset/prune/удаление Docker данных запрещены.

Остаются независимый security review Тимура #45, L-05 #48 client/HTTP integration
Леры после merge и будущая нагрузочная приёмка O-08. G4/live Telegram/production
не объявляются verified; O-08 здесь не начинается.
