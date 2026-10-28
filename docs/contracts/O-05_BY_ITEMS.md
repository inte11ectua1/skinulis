# O-05 — by_items Expense API

Принято [решением Тимура от 28.10.2026](https://github.com/inte11ectua1/skinulis/issues/39#issuecomment-6473059675).
Это решение tech lead, не персональный APPROVED Леры. Расширяет [O-04](O-04_EXPENSES.md).

## Запросы

Все public и /internal пути/actor/errors/pagination сохраняются из O-04.
Business body preview:

```json
{"title":"Ресторан","split_mode":"by_items","items":[{"title":"Пицца","amount":"900.00","participants":[10,20,30]}]}
```

POST /groups/{group_id}/expenses добавляет client_request_id UUID; full PUT
/expenses/{expense_id} добавляет expected_version strict int 1..BIGINT_MAX.
Preview POST /groups/{group_id}/expenses/preview не принимает UUID/version и не пишет.
POST повторно проверяет membership/суммы под group lock; preview не резервирует результат.

1..50 items; каждый содержит только title/amount/participants. Title: NFC → Unicode
strip → 1..120 codepoints без category C. Money: strict canonical nonnegative ASCII
RUB string, два знака, положительная сумма каждой позиции; total 1..100000000 коп.
Consumers: 1..30 unique strict positive BIGINT IDs, только участники этой группы.
Все модели extra=forbid. Root amount/participants/shares и actor/ID поля запрещены;
item position/item_id/group_id/author_id/payer_id также запрещены.

Сервер position = индекс массива +1. Для каждого блюда отдельно вызывается split_equal:
остаток получает меньший numeric user_id. Две позиции 0.01 на [10,20,30] дают final
{10:2,20:0,30:0}, а не деление общей суммы 2 коп. один раз. Final shares = union
выбранных consumers; выбранные нули сохраняются на обоих уровнях.

## Ответы

by_items имеет обязательный items в detail, page.items, preview, mutation.expense
и initial POST replay. Позиции ASC position; shares ASC numeric user_id:

```json
{"position":1,"title":"Пицца","amount":"900.00","shares":[{"user_id":10,"amount":"300.00"},{"user_id":20,"amount":"300.00"},{"user_id":30,"amount":"300.00"}]}
```

Нет DB item_id и отдельного participants: выбранные IDs следуют из shares с нулями.
Root amount вычисляется сервером. Equal/custom **не получают items вообще**, включая
items:null/[]; отдельные discriminated response DTO обеспечивают это и в JSONB replay.
Остальные поля Expense/Preview/Profile/Page/Mutation и ошибки — O-04 без изменений.
OpenAPI /openapi.json содержит третьи input ветки и discriminated response union на
обеих поверхностях. [Typed fixtures](../finance/fixtures/O-05_BY_ITEMS.json).

## PUT, DELETE и история

Разрешены все equal/custom/by_items переходы, включая by_items→by_items, как полный
PUT только автором. Сначала group FOR UPDATE, затем fresh expense FOR UPDATE,
expected_version; успешный PUT увеличивает version ровно один раз. Stale409 требует
перечитать карточку. Невалидный чек/ошибка БД откатывают все поля, детали и version.
Замена: удалить item shares → items → final shares, затем создать final shares →
items → item shares внутри одной транзакции. UUID/group/payer/created_at и immutable
initial intent/result не меняются. Аудит промежуточных PUT-версий MVP не требует.
Soft DELETE сохраняет все строки; повтор автора не меняет tombstone/version.
Confirmed settlements не меняются; mutation balances при confirmed пересчитываются,
вычитая только final shares. Item shares не являются вторым ledger.

Чтение — сохранённый snapshot, без перераспределения по текущим members. Один SQL
MVCC snapshot с page-ID CTE + UNION ALL, без N+1/final×item amplification. Несогласованные
item/final sums и selected unions вызывают safe500 без авторемонта. Foreign/deleted GET404.

## Original POST replay

Intention включает group/actor/normalized title/mode/derived total amount_kopecks и
**упорядоченный** items [{title,amount_kopecks,participants:sorted numeric IDs}].
Порядок consumers внутри блюда эквивалентен, порядок разных блюд значим: перестановка
с прежним UUID — request_conflict409 даже при одинаковых total/final sums.
Одинаковый UUID/actor/intent возвращает исходную полную envelope HTTP200, включая
исходные details/balances после PUT/DELETE. Другая суть/actor409. Первый POST201.
Старые equal/custom JSONB не дополняются и не переписываются. NULL legacy history409.
POST timeout: прежний UUID + исходное намерение. PUT timeout: GET/version; не слепой retry.

## L-04

Бот использует server preview; правка черновика инвалидирует preview. Edit — полный
мастер с историческими данными и предупреждением о confirmed/возможном обратном долге.
Смена режима заменяет прежние детали после preview/подтверждения. Stale409 обновляет
карточку и предлагает новый draft; отмена FSM не пишет расход. Bot-side math запрещена.
Реальная интеграция после merge; live G2 отложено. Backend не меняет FSM/handlers.

## Схема и границы

Новых миграций нет; единственный head0005_expense_replay_version. Существующие
четыре таблицы и composite FK/RESTRICT используются без изменений. O-02 правила,
identity/auth/groups, O-06/O-07 endpoints, deployment и live G2 не затронуты.
