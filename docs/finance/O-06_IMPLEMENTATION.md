# O-06 — точные балансы и план

Основание: [принятый T-08](../contracts/T-08_M4_BALANCES_SETTLEMENTS.md), PR50.
Статус: реализация для PR review, не merged/verified. O-07 не выполняется.

Один authoritative calculate_balances в expense_balances.py: paid active expenses
минус active final shares плюс sent confirmed минус received confirmed. SQL cast
в NUMERIC до unary arithmetic/SUM, Python int без BIGINT/expense cap для агрегата.
Вектор включает всех текущих members numeric ID ASC, в том числе нули.
mutation_balances сохраняет balances=null без confirmed; иначе использует тот же
calculate_balances. Snapshot validation и T07-01/T07-02 не удалены, replay не меняется.

GET /groups/{group_id}/balances и /settlement-plan, плюс /internal mirrors, используют
прежние JWT/service actor, no-store/error envelope и hidden group404. GET не пишет,
не создаёт pending/plan/cache, не вызывает FOR UPDATE. Typed JSON:
[fixtures](fixtures/O-06_BALANCES.json); Swagger /openapi.json содержит модели/примеры.

## MVCC

Auth dependency может уже начать READ COMMITTED transaction. Сервис её изоляцию
не переключает и не меняет общую Session dependency. Берётся отдельное connection
того же Engine с REPEATABLE READ **до begin**, первым SQL SET TRANSACTION READ ONLY.
Затем membership, snapshot integrity, members и NUMERIC ledger reads идут через
локальную Session, привязанную к этому connection, в одной транзакции/одном MVCC
snapshot. Session/connection гарантированно закрываются и при ошибке. Это требует
дополнительного pool checkout на GET; нагрузочная приёмка O-08 отдельно. Caller
write transaction не используется для такого GET; mutation envelope по-прежнему
считает прямо внутри штатной групповой write transaction под group lock.

В concurrency test reader останавливается после первого финансового SELECT,
независимый writer реально commits PUT либо DELETE, затем reader продолжает и
возвращает весь старый вектор/план. Следующий GET видит новое состояние. SHOW проверяет
repeatable read/read_only=on; SQL trace подтверждает отсутствие FOR UPDATE и N+1.
Это реальное перекрытие транзакций, не последовательная имитация двух GET.

## Q-05

Один раз сортируются исходные долги/кредиты по убыванию величины, ties numeric ID ASC.
Два указателя переводят min оставшихся сумм. Динамической пересортировки нет.
{10:800,20:700,30:-700,40:-500,50:-300} →30→10:700;40→10:100;40→20:400;50→20:300.
Это стабильный план погашения общего баланса, не доказательство прямого попарного
исторического долга и не глобально минимальное количество переводов. План — совет,
не факт отправки/получения, он не сохраняется и не резервирует долг.

| Случай | Результат |
|---|---|
| Пустые расходы/нулевой вектор | Все members с 0.00, transfers[] |
| Новый member | 0.00; старые shares не перераспределяются |
| Payer не consumer | Полная оплата в credit, выбранные shares в debit |
| by_items | Только final shares списываются, selected zeros сохраняются |
| Pending/rejected/cancelled | Эффект0 |
| Confirmed | Sender плюс, receiver минус, ровно один учёт записи |
| Deleted expense с confirmed | Confirmed остаётся, возможен обратный долг |
| Несогласованные final/item snapshots/вектор | Safe500, без авторемонта |
| Aggregate больше BIGINT | NUMERIC/Python int, exact signed RUB |

Финальные команды/числа/CI и SHA публикуются в PR. Человеческие независимые reviews
Тимура/Леры обязательны; O-07, банк, Telegram handlers/deploy/live tests не входят.
