# O-08 — финансовая безопасность и нагрузка M5

**Итоговая приёмка O-09 #76 (03.11.2026):** [PR #77](https://github.com/inte11ectua1/skinulis/pull/77) merged, задача закрыта владельцем. Минимальный auth-lifecycle fix устранил pool starvation (100-client HTTP500/pool timeouts=0), но **p95≤500ms остаётся FAIL** (mixed 956ms, contention 1098ms). Тимур явно принял эти остаточные задержки как допустимые для учебного проекта; это не performance PASS, не AWS benchmark и не изменение официального DoD. [Отдельный раздел O-09 ниже](#o-09-76--исправление-lifecycle-и-beforeafter-03112026),
[машинные агрегаты](O-09_LOAD_RESULTS.json). Исходные результаты Олега не заменены.

Исторический отчёт O-08: Issue #61 / PR #74 уже merged. Ниже сохранён срез
измерений Олега; изменения и отдельная оценка O-09 находятся в конце документа.

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
uv run python -m scripts.load_o08 --profile mixed --warmup 10 --duration 30 --output mixed.json
uv run python -m scripts.load_o08 --profile contention --warmup 10 --duration 30 --output contention.json
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

## Исходный finding O08-P01 — состояние на завершении O-08

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

## Новые проверки и доказательства O-08

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
Полный Linux suite проверяется GitHub CI. CI запускает Ruff/mypy/lock/audit отдельно
и только detect-secrets через pre-commit; full pre-commit на Linux не заявляется.
Для portable PG локально использован документированный direct TEST_DATABASE_URL
вариант: uv run pytest tests/integration -m integration. Существующий fixture
создаёт отдельную UUID database на каждый тест и не удаляет указанную admin DB.

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

## O-09 #76 — исправление lifecycle и before/after (03.11.2026)

Это отдельные измерения Тимура; исходные Windows результаты Олега выше сохранены.
[Машинные агрегаты O-09](O-09_LOAD_RESULTS.json) содержат четыре полных результата,
source hashes, условия и явный `overall_performance_pass=false`. Никаких AWS,
production DB/volumes/flags, CD или live Telegram действий в O-09 не выполнялось.

### Исправление и доказательство причины

Baseline — чистая main `f4a3a11b8f09160d781587b61164dddd921528ca` после PR74/75.
Measured fix — чистый `0bf9251aab0c04952ec340b97c08cc74095f44a8`.
На старом коде auth SELECT начинал request Session transaction; финансовый reader
пытался одновременно checkout второго connection из того же Engine. Новый PG
regression со строго одним pool slot воспроизвёл HTTP500 примерно через3s **до**
исправления; после него balances/plan работают через оба actor channels, в том
числе12 одновременных запросов к одному slot. Это детерминированный correctness
regression, его маленький pool не используется для benchmark.

JWT/get_bot_user теперь читают User в собственной короткой `database.sessions()`
Session. После успешного lookup полностью загруженный scalar User expunge-ится,
затем context manager закрывает только собственную read transaction и возвращает
lease. Endpoint получает detached User с загруженными id/email/telegram_id/created_at;
ему не нужны lazy/expired атрибуты. Сессия endpoint не закрывается и не rollback-ится
авторизацией. Неподписанный JWT/неверный service token/mixed channels остаются denied;
существование аккаунта проверяется каждым запросом, кэш не добавлялся.

Общая проверка охватывает все текущие consumers: business routes читают user.id,
а public/internal /users/me сериализуют загруженные scalar fields. Регрессии
проверяют DTO при занятом единственном pool slot, detached/unloaded/expired state,
отказ чужому/несуществующему actor, cleanup после auth-query exception и сохранность
незавершённой caller transaction. Unit fixtures получили отдельную override factory.

`read_balances` и финансовые модули не менялись: membership + integrity + ledger
читаются в одной READ ONLY REPEATABLE READ transaction без group FOR UPDATE.
Новый PG test проверяет isolation/read-only/одинаковую transaction + pg_current_snapshot
на membership и ledger SELECTs; прежние MVCC writer-overlap/race/security/UUID tests
и L-06 запускаются полным suite. Записи по-прежнему берут group lock и явно
commit/rollback в сервисе. В transactions.py исправлен только устаревший комментарий.
ORM-модели, миграции, публичные DTO, финансовая математика и бот не изменялись.
[SQLAlchemy Session close](https://docs.sqlalchemy.org/en/20/orm/session_basics.html#closing),
[detached objects](https://docs.sqlalchemy.org/en/20/orm/session_state_management.html#quickie-intro-to-object-states).

### Стенд и воспроизведение

Один Mac: macOS15.3.2, Apple M1 Pro10logical CPU,16GiB RAM; Python3.12.15/uv0.13.5.
PostgreSQL17.11-bookworm pinned digest в Docker Desktop4.19/Engine23.0.5/Compose2.17.3,
linux/arm64 VM5vCPU/~7.67GiB RAM. Свой UUID Compose test project из compose.test.yaml,
PGDATA tmpfs, только127.0.0.1:random-port, без persistent volumes; project штатно
остановлен после четырёх runs. fsync/synchronous_commit/full_page_writes ON;
прочие SHOW-параметры записаны в JSON. Docker tmpfs/VM и macOS отличаются от исходного
Windows portable PG стенда Олега: сравнение before/after здесь только внутри Mac,
а не сравнение абсолютных результатов двух компьютеров и не оценка AWS.

Тот же100-client O-08 runner, seed6108, mixed20groups×5members/contention1×5,
исходные10расходов/group,80%reads/20%writes, warmup10s/measurement30s, один worker,
AnyIO40, INFO JSON logs; QueuePool5+10/timeout3s/pre_ping/connect+statement_timeout3s.
Конструктор Database.__init__ AST и hashes runner/support/RR reader совпали между
before/after. Параметры, duration, pool, worker, isolation и guards не подгонялись.
В каждом run100clients started/completed, peak_inflight100; ошибки включены в latency,
RPS включает drain; diagnostics/checkout/SQL/CPU включают warmup. Под нагрузкой
pytest/build не выполнялись. Каждый run создаёт и удаляет только собственную UUID DB.

```sh
# Только явная разрешённая loopback TEST_DATABASE_URL c *_test, PostgreSQL17.
uv run python -m scripts.load_o08 --profile mixed --warmup 10 --duration 30 --output /absolute/path/mixed.json
uv run python -m scripts.load_o08 --profile contention --warmup 10 --duration 30 --output /absolute/path/contention.json
```

Запуск через `-m scripts.load_o08` нужен для корректного repository import path на
чистом Mac; direct `python scripts/load_o08.py` дал ModuleNotFoundError до любых
измерений. Workload code не изменялся. Для нового сравнения checkout baseline/fix
commit в чистой ветке, тот же test server/settings и отсутствие параллельной нагрузки;
runner сам проверяет clean tree и exact /version. Результаты сохранять вне Git tree,
затем добавлять агрегаты отдельным документационным коммитом.

### Результат: pool starvation устранён, p95 цель пока FAIL

Все latency в ms; каждое значение — отдельный полный run, одна пара на профиль.

| Run | Requests | 2xx | HTTP500 | RPS | p50 | p95 | p99 | Pool timeouts* | Checkout p95 ms* |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| before mixed | 463 | 95 | 368 | 13.72 | 6130.38 | 12075.14 | 12169.41 | 533 | 3017.34 |
| before contention | 441 | 88 | 353 | 13.11 | 6159.25 | 12071.87 | 12164.67 | 517 | 3010.86 |
| after mixed | 3876 | 3876 | 0 | 126.92 | 777.41 | 956.05 | 1067.57 | 0 | 208.40 |
| after contention | 3680 | 3680 | 0 | 120.24 | 796.96 | 1098.46 | 1215.00 | 0 | 222.96 |

*Pool metrics включают warmup, поэтому before timeouts533/517 не следует сравнивать
только с measured500368/353. Они точно совпали с **всеми** server500 вместе с warmup.
After zero timeouts и zero HTTP500 — и в warmup, и в measurement. Нет client timeout,
network error или409. Во всех четырёх runs overall target_pass=false: threshold
500ms не уменьшался, никакого PASS по ускорению относительно baseline не вводилось.

### Остаточное ограничение и следующий шаг

Double checkout больше не объясняет latency: одно-slot regression проходит, pool
returns to0 после success/error, в full100-client runs timeouts исчезли. Но pool
по-прежнему достигает15/15; checkout p95 after≈208/223ms, API CPU≈52.38/50.48s
за startup+warmup+run (это не CPU utilization profiler). SQL other p95≈21.42/13.36ms.
В contention group-lock p95 вырос до≈336.05ms, observer видел до10 Lock waiters:
после устранения starvation стало возможно значительно больше настоящих записей
в одной группе. Ledger растёт по прежнему workload; успешных creates теперь больше.
В mixed group-lock p95≈45.92ms, поэтому одним group lock mixed latency не объясняется.

Наблюдаются измеримая очередь к ограниченному пулу и реальная сериализация writer
на hot group; точный вклад AnyIO scheduling, Python/ORM, количества SQL round trips,
Docker bridge и клиентского event loop этим агрегатным harness **не разделён**.
Нельзя объявлять CPU/GIL/PG hardware единственной доказанной причиной.
Следующий шаг — отдельный phase/CPU/SQL-roundtrip профиль при том же100-client
workload, затем оценка сокращения round trips/объёма validated ledger в рамках
согласованного RR snapshot и group-lock semantics. Не увеличивать pool/timeout/workers,
не ослаблять integrity/изоляцию, не вводить cache и не переносить расчёты в бот.

Issue76 остаётся open, PR использует **Refs #76**, поскольку p95≤500ms не достигнут.
Независимое review Олега/Леры требуется. Fix ещё не merged и не deployed;
готовность production по этим локальным измерениям не объявляется.


## Формальное решение по O-09 #76 / M5 closeout (03.11.2026)

[PR #77](https://github.com/inte11ectua1/skinulis/pull/77) merged в `main`; [Issue #76](https://github.com/inte11ectua1/skinulis/issues/76) закрыта `completed` после явного решения Тимура. Устранены HTTP500/QueuePool timeouts при зафиксированной нагрузке 100 клиентов. **p95≤500ms всё ещё FAIL**: mixed 956.05ms, contention 1098.46ms. Владелец принял этот ограниченный результат и не требует дальнейшей оптимизации в O-09; дальнейшее профилирование — отдельный будущий scope только по новой задаче. Принятие по внутренней планке **не** заменяет DoD audit и не доказывает latency на production. [M5 closeout](M5_CLOSEOUT_M6_HANDOFF.md).
