# O-04 — Expense API equal/custom

Контракт принят [Тимуром 28.10.2026](https://github.com/inte11ectua1/skinulis/issues/36#issuecomment-6469818682)
для Q-06–Q-09, UQ-03/04/05/07/09. Это техническое решение; персональный
APPROVED-review Леры/независимая приёмка проверяются отдельно в [PR #41](https://github.com/inte11ectua1/skinulis/pull/41).
Реализация доступна в этом PR; факт merge смотреть в GitHub. Примеры O-01 не
заменяют этот контракт. Живые схемы/примеры: `/openapi.json`, `/docs`.

## Actor и маршруты

Публичный канал — существующий Bearer JWT/get_current_user. `/internal` mirrors
используют get_bot_user T-06: X-Bot-Service-Token + X-Telegram-ID из проверенного
Telegram sender update, без JWT/пароля пользователя. Смешанные каналы запрещены.
Существующая production-изоляция `/internal` остаётся задачей T-09; здесь deployment нет.
Все ответы расходных маршрутов имеют Cache-Control: no-store.

| Метод/путь (те же с `/internal`) | Вход | Успех |
|---|---|---|
| POST /groups/{group_id}/expenses/preview | Business union без UUID/версии | 200 PreviewProfile, без записи/резервации |
| POST /groups/{group_id}/expenses | Business union + client_request_id UUID | 201 Mutation; 200 первоначальный Mutation при replay |
| GET /groups/{group_id}/expenses | limit1..100 default20, offset≥0 | 200 Page[ExpenseProfile] |
| GET /expenses/{expense_id} | Проверенный member | 200 ExpenseProfile |
| PUT /expenses/{expense_id} | Полный business body + expected_version≥1 | 200 Mutation |
| DELETE /expenses/{expense_id}?expected_version=N | Обязательная положительная целая версия | 200 Mutation, включая повтор автора |

Создание и чтение доступны участникам группы; payer/автор — только actor.
PUT/DELETE только автору: владелец группы не получает исключения. Payer может не
быть потребителем. Неизвестные/чужие expense скрываются одинаковым 404.

## JSON

Вход — Pydantic v2 discriminated union по `split_mode`, extra=forbid на каждом уровне.
Позитивные signed BIGINT user IDs — строгие JSON integers, не bool/float/строка.
Название: NFC → Unicode strip → 1..120 code points → reject category C, включая ZWJ.
Внутренние пробелы/регистр сохраняются. Денежный вход — каноническая ASCII RUB
строка с двумя знаками: без знака, пробелов, leading zero, exponent и coercion.
Стоимость расхода 1..100000000 коп. Размер строки расхода/его доли ограничен 10
символами: из положительности и exact sum каждая допустимая доля не превышает
расхода. Это не лимит generic parser, компенсации или накопленного баланса.

```json
{"title":"Обед","split_mode":"equal","amount":"100.00","participants":[2,5,10],"client_request_id":"00000000-0000-4000-8000-000000000004"}
```

```json
{"title":"Обед","split_mode":"custom","amount":"100.00","shares":[{"user_id":2,"amount":"0.00"},{"user_id":5,"amount":"40.00"},{"user_id":10,"amount":"60.00"}],"client_request_id":"00000000-0000-4000-8000-000000000005"}
```

participants только equal, shares только custom, 1..30 уникальных потребителей
той же группы. Equal-остаток по numeric user_id ASC; custom sum совпадает точно,
без исправления ±1 копейки. Явно выбранные нули хранятся и возвращаются.
`payer_id/author_id/telegram_id/group_id` и другие extra fields во входе запрещены.
by_items/items — O-05 после merge O-04; он расширит эту же union/поверхность.

Preview body = тот же business body без client_request_id/expected_version.
PUT body = полный business body без UUID, с обязательным expected_version (JSON int).
Смена equal↔custom разрешена; group/payer/UUID/created_at неизменны. Существующую
детализацию receipt O-04 не заменяет/не удаляет.

ExpenseProfile: `{id,group_id,payer_id,client_request_id,split_mode,title,amount,
shares:[{user_id,amount}],created_at,deleted_at,version}`. Shares ASC user_id,
включая нули; даты aware UTC ISO8601 `Z`, deleted_at nullable. Email/Telegram ID
не выдаются. PreviewProfile: `{group_id,payer_id,split_mode,title,amount,shares}`.

Page: `{items,limit,offset}`, ASC(created_at,id), только active, пустые items[];
без total/has_next. GET deleted — 404. Читаются сохранённые historical shares,
новый член группы не получает доли старых расходов. Metadata+shares читаются одним
SQL snapshot; LIMIT применяется к расходам до join shares, N+1 отсутствует.

Mutation (POST/PUT/DELETE): `{expense:ExpenseProfile,balances:[{user_id,balance}]|null}`.
Без confirmed в группе допустим null. При наличии confirmed сервер до commit/ответа
считает **актуальные** балансы под той же group lock: paid active expenses − active
final shares + sent confirmed − received confirmed. Все участники, включая нули,
ASC user_id; balance — точная подписанная RUB-строка, сумма строго 0. Детали items
не вычитаются второй раз. При испорченном snapshot — безопасный 500 и rollback.
Это read-only агрегация для envelope, без balance cache, GET /balances, plan или O-07.

## POST replay / timeout

Scope UUID — (group_id,client_request_id) в expenses. Нормализованное намерение:
group+actor+normalized title+mode+integer kopecks+sorted participants либо sorted
custom pairs, со всеми явными нулями. Перестановка элементов не меняет намерение;
equal и custom — разные намерения даже при одинаковых итоговых долях.

Первое создание atomically сохраняет expense/shares/version1 и неизменяемые
initial_create_intent/result JSONB. Result — **полная исходная mutation envelope**,
без request-id/секретов. Тот же actor/ключ/намерение возвращает исходный result
с HTTP200, даже после PUT/soft-delete и последующих изменений балансов. Это не
актуальная карточка: для текущего состояния требуется GET/list. Другой actor/тело —
409 request_conflict без исходных DTO; сначала membership. Legacy NULL-history —
409 request_history_unavailable владельцу, историю не восстанавливаем из текущих долей.

После неоднозначного POST timeout повторять прежние UUID и неизменённое намерение.
Не создавать автоматически новый UUID. History хранится весь срок строки, включая
deleted. PUT/DELETE никогда не перезаписывают первоначальные JSONB; ORM assignment
guard запрещает менять/очищать уже записанные значения. Это не защита от
привилегированного прямого SQL вне service layer.

## Версии, удаление, preview

Все мутации: groups FOR UPDATE → expense при необходимости → проверки → запись и
агрегация/валидация ответа → один commit; любое исключение откатывает всё.
PUT сравнивает expected_version, заменяет снимок и version+1. Stale —409 без изменений.
Первый DELETE active также проверяет версию, ставит deleted_at, version+1. Повтор
автора уже deleted записи возвращает прежний tombstone/version даже со старым N;
balances при повторе отражает текущее состояние и может измениться после других операций.
Все shares/items и confirmed остаются. PUT deleted невозможен, воскресить расход нельзя.

После PUT timeout сначала GET и сравнение server version/snapshot, без слепого retry
stale тела. После DELETE timeout повтор того же пути/старого N безопасен для автора.
Preview не пишет expense, UUID или временный объект, ничего не резервирует.
Любая правка черновика инвалидирует preview/подтверждение в клиенте; финальный POST
повторно проверяет membership/суммы под lock. Бот не считает split/total локально.

## Ошибки

Оболочка строго `{error:{code,message,request_id}}` и X-Request-ID, без loc/details,
payload/SQL/внутренних аргументов. 401 сохраняет существующий WWW-Authenticate.

| HTTP | code | Причина |
|---|---|---|
| 400 | validation_error | Body/деньги/Unicode/режим/UUID/version/pagination/custom sum |
| 400 | invalid_participants | Consumer вне доступной группы, без раскрытия чужого user |
| 400 | ambiguous_actor | Смешаны public/service каналы |
| 401 | invalid_token / invalid_service_token | Существующая проверка credentials |
| 403 | expense_author_required | Member, включая owner, не автор |
| 404 | group_not_found / expense_not_found | Недоступный объект, deleted GET/PUT |
| 409 | request_conflict | Ключ другого actor/нормализованного намерения |
| 409 | request_history_unavailable | Нет доказанной первоначальной истории legacy POST |
| 409 | expense_version_conflict | Устаревший первый DELETE/PUT |
| 500 | internal_error | Повреждённый snapshot/неожиданный сбой, без частичной записи |

[Typed-model compatible JSON fixtures](../finance/fixtures/O-04_EXPENSES.json),
[реализация/проверки](../finance/O-04_CONTRACT_CHECKPOINT.md).
