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

Прогоны выполнены02.11.2026, последовательно, без параллельных pytest/PG tests.
Windows11 Home10.0.26200, AMD Ryzen7 8845HS,8cores/16threads,
RAM25 009 496 064 bytes(~23.29GiB). API/client/PG на одном компьютере, TCP loopback.
Python3.12.15/uv0.13.5; PostgreSQL17.11 portable из
[официального EDB ZIP](https://www.enterprisedb.com/download-postgresql-binaries),
HTTPS/ZIP CRC validation выбранных bin/lib/share. postgres.exe SHA256:
4125c1e963072d929f6468a449ad184b26d3be7d97cae3181c3d613dace49c8d.
Другого подходящего portable/локального PG17 на доступных дисках не обнаружено.
Создан отдельный ASCII UUID-каталог C:/Temp: initdb в кириллическом пути не прошёл.
Без установки системной службы. Docker Desktop недоступен(missing Linux Engine
pipe); reset/prune/удаление чужих данных не выполнялись.

PG: max_connections100/shared_buffers128MB, fsync/synchronous_commit/full_page_writes
on, track_io_timing on, timezoneEurope/Moscow. Никаких durability shortcuts.

Четыре диагностических прогона: **9f2f75b948d7f964c32f5e80c7315af1bc44cad9**,
clean worktree, /version SHA проверен. Два исходных прогона:
**f3a69288f0119f26aeddeb725caa8111c86ed540**. Между ними добавлена только
диагностическая обёртка настоящего pool.connect(duration/SQLAlchemy TimeoutError),
делегирующая оригиналу без изменения pool/SQL/исключений/нагрузки. Код приложения
везде совпадает с main6132f990da4dedc287d3865fdc633d2a601edc8c. После измерений
меняются только документы с результатами; executable files идентичны измеренным.
Byte SHA256 ключевых файлов(sha256:<hex>) и commit permalinks каждого run есть в
[машинных агрегатах](O-08_LOAD_RESULTS.json), без самоссылки документа на свой SHA.

Все latency ниже — **ms**, каждый ряд отдельный прогон. Во всех случаях **FAIL**
относительно p95<=500ms. HTTP500=internal_error. Ни одного409/network error/client
timeout. Errors включены в latency, а success latency также сохранена отдельно.

| Run | Requests | 2xx | HTTP500 | RPS с drain | p50 | p95 | p99 | min / max | elapsed s |
|---|---:|---:|---:|---:|---:|---:|---:|---|---:|

| mixed-1 | 491 | 151 | 340 | 14.01 | 6264.84 | 9501.48 | 12273.16 | 581.42 / 12436.60 | 35.05 |
| mixed-2 | 445 | 112 | 333 | 11.92 | 6727.01 | 12032.45 | 12241.44 | 589.05 / 12637.47 | 37.32 |
| mixed-diagnostic-1 | 468 | 117 | 351 | 12.44 | 6342.40 | 9601.00 | 12202.62 | 518.92 / 12280.76 | 37.62 |
| mixed-diagnostic-2 | 474 | 130 | 344 | 12.59 | 6291.01 | 9579.86 | 12189.12 | 507.04 / 12426.18 | 37.64 |
| contention-diagnostic-1 | 444 | 106 | 338 | 12.82 | 6523.11 | 12097.86 | 12291.59 | 613.27 / 12732.59 | 34.64 |
| contention-diagnostic-2 | 442 | 104 | 338 | 11.83 | 6601.43 | 12050.72 | 12242.70 | 517.51 / 12518.25 | 37.36 |

Во всех100 клиентов начали и завершили requests, peak in-flight100; среднее
sampled in-flight в launch window99.893..99.895, минимум3..4requests/client.
Первый sample может поймать1request при выпуске barrier до следующей итерации
loop(все workers уже готовы); после окна начинается drain. Это100 работающих
loops, а не100 последовательных requests.

Фактические create attempts: mixed diagnostic93/468(19.87%)/97/474(20.46%),
contention90/444(20.27%)/87/442(19.68%). Все counts/warmup в JSON. Clients между
фазами создаются заново до barrier: измерение включает reconnect после warmup,
но не создание объектов/JWT до barrier. Данные warmup остаются, каждый run начинает
новую БД. Success-p95 diagnostic mixed=9572.86/12150.87ms,
contention=12250.63/12172.06ms; вывод не является следствием включения500.

## Finding O08-P01 — исчерпание connection pool, OPEN

[Передан Тимуру](https://github.com/inte11ectua1/skinulis/issues/61#issuecomment-6584139938).

| Diagnostic run | Pool peak | Pool timeouts* | checkout p95 ms | SQL other p95 ms | group lock p95 ms | Max PG Lock waiters | API CPU seconds* |
|---|---:|---:|---:|---:|---:|---:|---:|
| mixed-diagnostic-1 | 15 | 511 | 3017.28 | 11.94 | 5.95 | 0 | 5.58 |
| mixed-diagnostic-2 | 15 | 506 | 3029.25 | 12.38 | 9.33 | 1 | 5.45 |
| contention-diagnostic-1 | 15 | 491 | 3024.82 | 11.00 | 95.21 | 2 | 5.53 |
| contention-diagnostic-2 | 15 | 487 | 3025.11 | 9.37 | 110.78 | 2 | 5.36 |

*Diagnostics включают warmup, CPU также startup/health/version/shutdown. Pool
TimeoutError точно совпал со всеми server500 включаяwarmup:511/506/491/487,
а не только measured500. В JSON sql.pool_connect — получение соединения,
**не SQL statement**. SQL categories:other/group_lock.

Наблюдения: pool15/15, checkout p50/p95 около штатных3s, PG преимущественно
ClientRead, максимум active1..5, SQL other p95<13ms. Contention повышает group lock
p95до95/111ms(max2waiters), но checkout остаётся около3s. API CPU5.36..5.58s за
startup+warmup+run не свидетельствует о CPU saturation. Один внешний Win32_Process
sample baseline: API peak working set128200KiB(~125.2MiB), это sample, не memory
profiler. RSS PG процессов не суммируется как physical RAM из-за shared pages;
disk/host CPU time series детально не профилированы.

Код объясняет наблюдения: get_current_user начинает request Session transaction
и удерживает auth connection до конца запроса; read_balances берёт второе
соединение Engine для read-only REPEATABLE READ. Concurrent readers могут занять
pool auth-соединениями и ждать ещё одно; очередь sync workers усиливает задержки.
На этом стенде pool TimeoutError объясняет все500. Дополнительный checkout был
явно указан в O-06 как residual risk для O-08. Нет evidence, что главным фактором
является PG CPU или T-10 logging.

Минимальная рекомендация для отдельного согласования Тимура/O-09: сократить
удержание auth connection перед получением financial snapshot, сохранив actor,
membership и MVCC, либо согласовать один snapshot SQL statement. Простое увеличение
pool не доказывает исправление: двойной checkout остаётся, PG connections ограничены.
После fix повторить **тот же** seed/mix/groups/100clients/warmup/duration и zero-error
критерий. Кеш/Redis/смена isolation/auth/архитектурная переделка здесь не выполнены.
Finding не закрыт,500ms не достигнуты; O-08 поставляет аудит/измерения, не обещание
готовности к production.

## Новые проверки и доказательства

23 новых unit и11 PG/HTTP cases. Property loops:3seeds×60 чеков и3seeds×100 больших
векторов(не отдельные pytest cases). Две HTTP ledger истории по24расхода сравниваются
с независимым penny-by-penny oracle; нули, новый member и soft-delete сохраняют
исторические shares.

Новые confirm-first vs reject/cancel races используют прежний contend helper:
первый настоящий HTTP writer остановлен после groups FOR UPDATE, второй идёт на
другом connection, observer требует wait_event_type=Lock и конкретный ownerPID в
pg_blocking_pids **до release**. Terminal retry сохраняет resolved_at. Отдельный
writer другой группы commits, пока первая locked. Старые duplicateUUID, full-debt/
double confirm, expense PUT/DELETE, claims, trigger rollback и MVCC tests заново
выполняются полным suite; они не выданы за новые.

Новые TCP tests: локальный proxy получает полный upstream201 после DB commit,
закрывает downstream socket без HTTP headers; клиент получает RemoteProtocolError.
Повтор прежнего UUID возвращает original history после PUT/delete/terminal;
другой actor/intent409, одна DB row. Оба actor channels, настоящий Uvicorn/HTTP.
Это потерянный ответ после commit, не mock математики или ASGI transport.

Privacy: реальные financial400/401/403/404/500, no-store/X-Request-ID и matching
JSON logs. Нет JWT/service credential, TelegramID, financial title/amount,
SQL/binds/traceback. Только synthetic markers; logging Тимура не менялся.

Найдена timezone-зависимость старого restaurant expected. Исправлена только
saved.created_at.astimezone(UTC), потому что DB timezoneEurope/Moscow корректно
возвращает aware+03:00, а API уже отдавал Z. Денежная семантика/история не менялись.

## Проверки и границы результата

Frozen/lock/Ruff lint+format/pip check/audit72(no known vulnerabilities)/secret scan/
diff check выполнены. Linux-target mypy142 Python files прошёл. Точный mypy . и
pre-commit на Windows имеют15 существующих POSIX-only type errors в backup/deploy
модулях; общий pytest останавливается на3 fcntl collection errors. Не использованы
skip/xfail и не переписана чужая инфраструктура. Local unit subset без3 POSIX files:
1173passed; новые unit23passed. Временная локальная pre-commit config сохраняет
все5hooks, явно добавляя mypy --platform linux; repo config/CI не изменены.
Полный Linux suite и штатный pre-commit проверяются GitHub CI.

Первый полный local PG:412passed/2failed по timezone expected. Исправленные2кейса
прошли; полный повтор: **414passed**,462.68s, без skip/xfail. Disposable Docker runner и Docker build локально
недоступны из-за Engine и не считаются passed. Один Alembic head0006; clean/repeated
upgrade/schema drift/0006backfill/downgrade/reupgrade входят в полный PG suite.
Новых миграций нет. На измеренном implementation SHA9f2f75b:
[CI41494219268](https://github.com/inte11ectua1/skinulis/actions/runs/41494219268)
**5/5success**,1243unit+414PG=1657passed, combined branch coverage**95.00%**
(3836statements/844branches). Docker build и disposable production-routing image
smoke прошли только в GitHub CI; это не production deploy. Checks окончательного
документационного head проверяются отдельно и публикуются в PR evidence.

Ограничения: локальная нагрузка без TLS/reverse proxy/production network и live
Telegram; closed-loop без think time — интенсивный профиль, не модель всех UX.
100clients contention используют5actors.30s не soak test. Pool errors ограничили
рост ledger; bottlenecks большой исторической БД ещё не оценены. Результат нельзя
переносить на AWS или объявлять G4/G5 verified. Remediation/новая оценка500ms открыты.
