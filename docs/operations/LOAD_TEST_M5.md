# O-08 — финансовая безопасность и нагрузка M5

Issue #61; реализация в отдельной ветке, PR review, не merged и не release gate.

## Матрица до реализации и принятый профиль

| Риск | Уже покрыто в main | Усиление O-08 |
|---|---|---|
| Strict money, equal/custom/by_items, pennies, zeros, ресторан | test_money, test_splits, test_by_items_preparation/storage | 3 fixed seed × 60 неоднородных чеков, metamorphic перестановки, независимое сохранение суммы |
| Q-05, tie IDs, пустые/огромные векторы | test_settlement_plan | 3 seed × 100 векторов, отсутствие переплаты на каждом префиксе плана |
| Active final shares, confirmed only, NUMERIC > BIGINT, reverse debt, corrupt snapshots | test_balances_api/test_settlements_api | Генерируемая история из 24 HTTP расходов × 2 seeds с независимым покопеечным oracle, новые members, soft-delete, неизменность shares |
| Actor, foreign404, owner без исключений, validation/overpay | test_expense_api, test_settlements_api, test_notification_claim | Реальные финансовые 400/401/403/404/500 и коррелированные JSON-логи T-10 без payload/credentials |
| UUID overlap, double/full-debt confirm, expense PUT/DELETE, claim/confirm, DB-trigger rollback, MVCC | существующие PG tests с pg_blocking_pids и independent connections | Обратный порядок confirm против reject/cancel, независимые группы; прошлые доказательства повторно запускаются |
| Lost response после commit | раньше главным образом TestClient/ignored response | TCP proxy дожидается 201, обрывает ответ без HTTP headers; retry после PUT/delete/terminal, оба actor channels |
| 100 клиентов, latency и pool saturation | Не измерялось | Отдельный ограниченный real HTTP runner, два раздельных профиля и повтор при FAIL |

**До первого измерения зафиксировано:** seed6108, closed loop без think time,
100 независимых AsyncClient (по одному соединению), один запрос на клиента в полёте.
10-slot cycle: balances40%, plan20%, expenses list10%, settlements list10%, expense
create20%; индивидуальная перестановка цикла seeded. Длительность 30s после warmup10s,
не более10000 requests/phase, timeout15s/connect3s, без retries/redirects/proxy env.
Фактический mix при окончании окна может отличаться от цикла; counts приводятся.

Mixed: 20 групп ×5 участников =100 synthetic users, по10 исходных расходов в группе
(equal и by_items поровну). Contention: 1 группа ×5 участников, все100 клиентов
обращаются к ней. Новые расходы equal1.01, unique UUID, сохранённые данные растут.
Это интенсивный профиль экрана группы и добавления расходов, не модель всех UX;
PUT/settlement lifecycle отдельно проверяются корректностными/race tests.

API: один Uvicorn worker, штатные AnyIO40 tokens, T-10 INFO JSON logging включено.
DB: штатный QueuePool size5/overflow10/timeout3s, pre_ping; connect/statement_timeout3s.
Настройки приложения, production Compose/workflows/логирование не меняются.

## Изоляция и воспроизведение

Runner не принимает внешний API target. Он создаёт свой Uvicorn только на127.0.0.1
и случайном порту, проверяет /version SHA. TEST_DATABASE_URL должен явно задавать
postgresql+psycopg, loopback127.0.0.1/localhost, порт, credentials и *_test, без URL
query options. До CREATE DATABASE проверяется PG17 и local/private server address
(для disposable Docker допускается private bridge). На указанном сервере создаётся
новая skinulis_o08_<32hex>_test. Удаляется только эта созданная здесь UUID database;
сервер, чужие БД/volumes не удаляются. Никакого fallback на иной URL.

Дочерний API получает очищенное окружение с новыми synthetic signing/service keys;
operator .env, Telegram/cloud/prod credentials не читаются. Synthetic users/members
seeded непосредственно через ORM/approved expense service после Alembic upgrade;
это не измерение регистрации/Argon2. Токены только в памяти.

```sh
# TEST_DATABASE_URL заранее настроен на разрешённый локальный тестовый PG17
uv run python scripts/load_o08.py --profile mixed --warmup 10 --duration 30 --output mixed.json
uv run python scripts/load_o08.py --profile contention --warmup 10 --duration 30 --output contention.json
```

Нагрузочный runner не входит в обычный pytest. CI проверяет guards/процентили и
короткий HTTP/PG smoke на2 клиентах; это не evidence100 клиентов. Полные прогоны
выполняются отдельно. После закрытия API удаляются только собственные временные
логи/diagnostics и UUID database. Safe JSON агрегаты не содержат тела запросов,
токенов, ID, паролей или raw logs.

## Методика

perf_counter (monotonic, high resolution); wall time одного HTTP request от вызова
клиента до полного ответа/ошибки включает сеть, очередь, SQL, JSON. HTTP client
создаётся до barrier; все100 workers ждут общего старта. Измеряются peak in-flight,
число начавших/завершивших клиентов, samples каждые20ms и минимум requests/client.
Window закрывает запуск новых requests; уже начатые дожидаются timeout. RPS = все
завершённые requests / elapsed с drain. Percentile nearest rank: sorted[ceil(p*n)-1],
без interpolation. Основная latency включает ошибки, отдельно success latency.
Warmup выполняется отдельно и исключён из основной latency; SQL/pool diagnostics
включают warmup и явно так помечены. Observer PG каждые100ms считает active/Lock/
wait_event, не сохраняет SQL/payload. SQL observers хранят только durations по
категориям group FOR UPDATE/other; итог — агрегаты. Instrumentation overhead
существует и не отключается между повторами. PASS требует p95<=500ms и0 errors.

## Фактические результаты

Измерения ещё не выполнены; этот раздел будет заполнен только реальными evidence.
