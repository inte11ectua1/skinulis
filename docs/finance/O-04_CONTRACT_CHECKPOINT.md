# O-04 — внутренний срез и предложенный HTTP-контракт

**Draft / Refs #36. Финансовые HTTP endpoints не опубликованы.**
Q-06/Q-07/Q-08/Q-09 не имеют утверждённого решения в Issues #35/#36/#37
на момент подготовки этого среза. Код ниже не означает готовый Expense API,
возможность реальной интеграции L-04 или выполнение полного Acceptance #36.

База — main `51f2e82`, merged PR #31/#33, actual Alembic head
`0004_financial_domain`. Авторизация и модели T-05/T-06 не изменяются.
[Запрос согласования с JSON/ошибками/повторами](https://github.com/inte11ectua1/skinulis/issues/36#issuecomment-6469108140)
опубликован до реализации; обсуждение связано с
[T-07](https://github.com/inte11ectua1/skinulis/issues/35#issuecomment-6469114270)
и [L-04](https://github.com/inte11ectua1/skinulis/issues/37#issuecomment-6469114848).
Пока нет ответа Тимура и клиентского согласования Леры. Никакой новой миграции нет.

## Уже принятые основания

- Q-01/Q-02: строгая каноническая RUB-строка; Python int positive signed BIGINT,
  без bool/coercion, остатки в ascending numeric user_id. Используются функции
  O-02 без изменения `money.py`/`splits.py`.
- [Q-03 и storage Q-04/Q-10](https://github.com/inte11ectua1/skinulis/issues/23#issuecomment-6467181035):
  NFC → Unicode strip → 1..120 code points → отказ category C; внутренние пробелы
  и регистр сохраняются. Строки явно выбранных нулевых долей сохраняются.
  SQL CHECK O-03 проверяет только длину, а не всю Unicode-политику.
- Actor = плательщик/автор, создание/чтение только членом группы; изменение
  только автором, включая запрет owner изменять расход другого участника.
  Payer может отсутствовать среди потребителей.
- Group row lock первым, одна транзакция и один commit/rollback. Soft-delete
  сохраняет историю; подтверждённые компенсации не переписываются.

## Что реализовано в этом промежуточном срезе

`app/services/expenses.py` содержит Python-типы и операции без роутеров/DTO:

| Операция | Гарантия | Граница |
|---|---|---|
| normalize_title / prepare_expense | Принятая Q-03, parse_money → validate_expense_amount → split_equal/split_custom, строгая сумма и все нули | Не Pydantic и не JSON boundary; публичные ограничения длины денежного ввода требуют решения |
| create_once | Членство и payer=actor, group lock до insert, расход+полный снимок одним commit | Только первая вставка; **каждый** занятый UUID даёт внутренний ExpenseRequestExists без тела/ID/сравнения текущих долей |
| read_expense | Membership и активный расход; metadata+shares в одном SELECT | Внутренний ExpenseSnapshot в копейках, не HTTP response DTO |
| list_expenses | Пагинация расходов до join долей, limit default20, ASC(created_at,id), нули/история из БД | Формат страницы и внешний max limit требуют T-07; число SQL не зависит от размера страницы |
| locked_edit | Non-locking lookup group_id → groups FOR UPDATE → свежий expense FOR UPDATE → author | Внутренний transaction scope, **не** готовый PUT/DELETE endpoint |
| editor.replace_snapshot | Полная атомарная замена equal/custom; старые и новые доли не смешиваются; rollback возвращает старое состояние | Будущий адаптер обязан сначала выполнить утверждённую проверку stale-write; wrapper PUT отсутствует |
| editor.mark_deleted | deleted_at ставится один раз, позиции/доли/settlements остаются | Повторяемость примитива не утверждает HTTP-код/форму повторного DELETE |

Editor приватный, живёт только внутри исходной заблокированной транзакции;
после выхода или преждевременного ручного commit его методы отказывают.
Не создавать editor вручную и не использовать primitives как публичный API.
Передавать только отдельную request Session с уже проверенным actor из T-05/T-06;
не объединять write services/чужую незавершённую работу в одной Session.
Функции не проверяют JWT сами и не доказывают полномочия произвольного Python caller.
Исторический editor для повторного tombstone требует явного include_deleted=True;
обычный editor не открывает удалённый расход. Пустой или несбалансированный
сохранённый snapshot вызывает ExpenseSnapshotInvalid, без исправления денег.
Его HTTP-представление остаётся частью открытого Q-10/Q-07.

Чтение метаданных и долей одним SQL важно и для консистентности: два отдельных
SELECT под READ COMMITTED могут увидеть разные версии при конкурентной замене.
Список сначала выбирает страницу expense IDs, затем присоединяет shares в том же
SQL; LIMIT не обрезает доли многопользовательского расхода. Старые ORM-объекты
обновляются через populate_existing после lock/на чтении.

Замена by_items либо equal/custom с вложенными items отклоняется внутренним
ExpenseDetailsUnsupported; детализация не удаляется. Тест soft-delete исторического
receipt проверяет только сохранность существующих строк O-03, не реализует O-05.

## Предлагаемая внешняя поверхность — НЕ реализована

| Предложенный путь | Ответ по предложению |
|---|---|
| POST /groups/{id}/expenses | 201 впервые; 200 первоначальный результат при согласованном replay |
| GET /groups/{id}/expenses | 200 {items,limit,offset}; limit1..100 default20, offset≥0; только active, ASC(created_at,id) |
| GET /expenses/{id} | 200 Expense; deleted/чужой/неизвестный — безопасный 404 |
| PUT /expenses/{id} | 200 Expense после полного сохранения, обязательный expected_version по предложению Q-09 |
| DELETE /expenses/{id} | 200 tombstone; повтор автора — прежний tombstone |

Предлагаются отдельные `/internal` mirrors с существующим get_bot_user/service
credential + Telegram sender header; публичные — существующий get_current_user/JWT.
Новый actor из body не допускается. Internal mirrors тоже ждут согласования.
UQ-03 preview не реализуется, URL ему не назначен; бот не считает split и не создаёт
временный расход. Чтение current membership не заменяет будущую повторную проверку
сохранения после preview.

Предлагаемые JSON и ошибки для клиентского mock-first review находятся в
[fixtures/O-04_PROPOSED.json](fixtures/O-04_PROPOSED.json). Это **не OpenAPI
fixtures работающего API**, Pydantic HTTP schemas ещё не созданы. Суммы в будущем
DTO форматирует существующий format_money, даты — общий UTCDateTime (UTC Z).

Q-08: одна union по split_mode; participants только equal, shares только custom,
extra forbid; items добавит O-05 в ту же union. PUT — полная замена, без изменения
group/payer/client_request_id/created_at; возможность equal↔custom предложена,
но пока не принята. В read предлагаются shares ASC(user_id), включая нули.

| Случай (предложение Q-07/UQ-04) | HTTP / code |
|---|---|
| Невалидный body/сумма/Unicode/режим/пагинация | 400 validation_error |
| Посторонний consumer в доступной группе | 400 invalid_participants |
| JWT / смешанные каналы | Существующие 401 invalid_token / 400 ambiguous_actor |
| Чужая/неизвестная группа | 404 group_not_found |
| Чужой/неизвестный/deleted expense | 404 expense_not_found |
| Member или owner меняет чужой активный expense | 403 expense_author_required |
| Занятый UUID с другим actor/нормализованным намерением | 409 request_conflict |
| Устаревшая версия PUT | 409 expense_version_conflict |
| Нет доказанной первоначальной истории POST | 409 request_history_unavailable |
| Неожиданный сбой | Существующий 500 internal_error |

Оболочка остаётся error.code/message/request_id и X-Request-ID; поля loc/details
не добавляются. Ошибки не отражают payload/SQL/чужой исходный результат. Внутренние
исключения этого среза пока **не отображляются** в предложенные HTTP-коды.

## Почему replay и stale PUT остаются блокерами

ORM O-03 хранит актуальное состояние. После PUT сравнение POST с текущим title,
amount/shares не доказывает равенство **исходного** намерения; после DELETE ключ
также остаётся занятым. Snapshot текущих долей не превращаем в request history.
Одинаковый derived equal snapshot и custom snapshot также не означают один режим.

Предлагается отдельно согласовать изменение схемы: immutable service-managed
initial_create_intent JSONB + initial_create_result JSONB и version BIGINT DEFAULT1
в expenses. Это **только предложение**, columns/revision не создаются. Альтернатива
отдельной request-history table должна быть решена до реализации.
Для legacy rows нельзя достоверно восстановить исходный запрос из текущего состояния.

Предлагаемое нормализованное намерение: actor+group+title после Q-03+mode+integer
kopecks+sorted participants/custom pairs со всеми нулями. Сохранять intent/result
атомарно с первым expense, на весь срок хранения, включая soft-delete. Повтор
того же actor/ключа/намерения возвращает первоначальный result после PUT/DELETE,
но не меняет актуальный расход; клиент перечитывает GET для актуального экрана.
Другой actor/тело — безопасный конфликт без выдачи первоначального result.
После timeout повторять только прежний UUID и прежнее намерение, не новый UUID.

Предложение Q-09: expected_version под group lock, конфликт вместо молчаливого
last-write-wins, version+1 при полном успешном PUT. После PUT timeout перечитать
GET/сверить версию и данные, не обещать идемпотентный повтор PUT без отдельного
решения. Group lock сам по себе защищает от частичной записи, но не stale drafts.
Тест двух внутренних замен доказывает только последовательную атомарность
примитивов; это **не** тест или выбор публичной stale PUT политики.

Дополнительное сопряжение: PRODUCT_RULES §6 упоминает возвращение пересчитанных
балансов после изменений при confirmed, а O-04 исключает O-06. Нужно согласовать
форму/этап такого ответа с T-07; баланс и фиктивные значения здесь не добавляются.

## Приёмка и оставшаяся работа

Новые unit-тесты проверяют Q-03, RUB, equal/custom, нули и отсутствие новых expense
путей в действующем OpenAPI. PostgreSQL tests используют штатную UUID disposable
БД и неизменённый Database/session helper. Они проверяют реальные сохранённые
снимки, членство/авторство, пагинацию без N+1, group-first locks, независимые
overlapping transactions (ожидание видно в pg_stat_activity), первый insert с UUID,
полную замену, actual CHECK failure после DELETE старых shares с rollback,
soft-delete/историю/confirmed и независимость групп. Read во время uncommitted
замены возвращает целиком предыдущую версию и не блокируется group lock.

**Не выполнены и не объявляются выполненными:** публичные/internal CRUD маршруты,
Pydantic discriminated union/OpenAPI, HTTP spoofing/ошибки/страницы, успешный replay
и конфликт тела по первоначальной истории, approved stale PUT/concurrency/timeout,
реальная интеграция клиента Леры. Для этого нужны решения Q-06–Q-09 и разрешение
схемы, затем отдельные HTTP+PostgreSQL tests поверх этих primitives.
Issue #36 остаётся открытой; PR Draft с Refs #36, без merge и без старта O-05.

Ревью Тимура: согласование DTO/схемы, group locks, безопасное сокрытие, границы
транзакции, первоначальная история и политика stale-write. Ревью Леры: Q/UQ,
JSON fixtures/errors, нули, Unicode/emoji, страницы и повторы после timeout.
Ответы и даты решений добавлять ссылками, не считать молчание approval.

## Локальная проверка промежуточного среза — 28.10.2026

- 643 unit passed, включая 56 новых; 173 PostgreSQL 17 integration passed,
  включая 35 новых. После уточнения запроса lock повторены все 35 новых PG tests.
  Без skip/xfail. Это результаты внутренних primitives и существующей системы,
  **не** приёмка ещё отсутствующего expense HTTP API.
- Совокупное branch coverage app+bot — 96,59%; expenses.py — 96,28%.
- Sync frozen/lock, Ruff check/format, mypy . (77 файлов), pre-commit --all-files,
  pip check, audit --locked и diff check прошли; известных уязвимостей в 72 внешних
  пакетах нет. JSON fixture синтаксически проверен, пометка proposed сохранена.
- Docker build --pull успешен; запуск API/бота и production deploy не выполнялись.
  Head остаётся 0004_financial_domain; clean/repeat upgrade и alembic check
  проходят внутри прежних migration-тестов на disposable БД. Чужие контейнеры,
  volumes и пользовательская БД не очищались.
- Существующее предупреждение Starlette/httpx deprecation сохранено. Никаких
  изменений deps/lock/CI/Docker/auth/groups/бота/ORM/migrations/O-02 нет.
- GitHub Actions для коммита этого PR проверяется отдельно после публикации;
  локальная зелень не является доказательством remote CI или принятия контрактов.

```powershell
uv run pytest --cov=app --cov=bot --cov-report=term-missing --cov-report=xml
uv run python scripts/test_integration.py --cov=app --cov=bot --cov-append --cov-report=term-missing --cov-report=xml
uv run coverage report --include="app/services/expenses.py" --precision=2
```
