# T-04 — CI и защита main

Issue: [#13](https://github.com/inte11ectua1/skinulis/issues/13).
Конфигурация: [ci.yml](../../.github/workflows/ci.yml), команды:
[README](../../README.md#github-actions-ci). Версии Python/uv, lock-файл,
настройки Ruff/mypy/coverage не изменяются задачей T-04.

## Устройство проверки

`pull_request` в main проверяет merge ref текущего PR. События opened,
synchronize и reopened запускаются по умолчанию; path filters отсутствуют.
`workflow_dispatch` доступен после принятия workflow в default branch.
Concurrency отменяет устаревший запуск того же PR, но его cancelled результат
не считается зелёным. Используется GitHub-hosted Ubuntu 24.04, без личного `.env`.

`lint`, `types`, `tests`, `docker-build` выполняются независимо. Итоговый `ci`
имеет `always()` и явно требует ровно `success` от всех четырёх. `always()`
не скрывает ошибки: он позволяет запустить проверку результата даже после fail
или skip зависимости. Нет `continue-on-error` и privileged PR events.

Все run steps используют Bash с `-e -o pipefail`: например, `tee` не скрывает
отказ порога покрытия. `coverage run -m pytest` применяет существующий default
`not integration`; второй запуск `coverage run --append -m pytest -m integration`
переопределяет marker и дополняет тот же файл. Ненулевой код pytest, в том числе
отсутствие выбранных тестов, останавливает job. После обоих прогонов применяется
порог 60%, без промежуточного уменьшения настройки. Artifact содержит только
coverage.xml/coverage.txt, а не `.env`, БД или дампы окружения.

PostgreSQL 17.11 использует digest из Compose. Публичный тестовый пароль не даёт
доступа к постоянным данным: БД создаётся заново на каждый job, порт доступен на
loopback runner-а, production secrets не используются. Fixture дополнительно
проверяет major 17, драйвер psycopg и suffix `_test` у bootstrap БД; удаляет только
созданные ею UUID-БД. Локальный Compose runner сохранён без изменений.

Используются только actions/checkout, actions/upload-artifact и рекомендуемый
Astral setup-uv, все по commit SHA (аннотированный tag setup-uv разрешён до commit).
Cache setup-uv зависит от uv.lock и job suffix, не содержит `.venv`/секретов;
fork/PR cache ограничен правилами GitHub. Lock и frozen sync проверяются заново
независимо от cache hit. Docker job собирает существующий multi-stage/nonroot
Dockerfile; registry login, push и deployment отсутствуют.

## Настройки main и проверка администратором

На начало T-04 `main.protected=true`, rulesets API вернул пустой список, а GET
branch protection через GitHub-коннектор вернул 403 Resource not accessible by
integration. Это не подтверждает параметры и не означает, что защита отсутствует.
Для работы с административным API подготовлен GitHub CLI; нужен безопасный вход
в аккаунт владельца, без передачи токена в чат.

Если административный доступ недоступен, владелец открывает Settings → Branches
→ правило main → Edit (либо Settings → Rules → Rulesets → применяемое к main
активное правило). Существующие более строгие ограничения сохраняются:

1. Require a pull request before merging, минимум 1 approval другого участника.
2. Dismiss stale pull request approvals when new commits are pushed.
3. Require conversation resolution before merging.
4. Require status checks to pass before merging: точные check run names `lint`,
   `types`, `tests`, `docker-build`, `ci`, источник GitHub Actions. Выбирать после
   первого завершённого run. Require branches to be up to date before merging.
5. Do not allow bypassing the above settings / enforcement для administrators;
   в ruleset bypass list пуст. Не добавлять владельца и приложения как исключения.
6. Allow force pushes и Allow deletions выключены. Правило применяется к main,
   enforcement активно. Не включать Lock branch: это запретит и обычный merge.
7. Сохранить и заново открыть правило, проверить значения. Проверить красный PR
   под аккаунтом владельца: требуется именно блокировка, без возможности bypass.

Прямой push в main специально не выполняется: при ошибочной защите даже тестовый
push мог бы изменить общую ветку. Настройки защиты и фактический отказ push —
разные доказательства T-01; одно нельзя выдавать за другое.

## Доказательства

На этапе подготовки: локальные unit/quality checks и Docker build проходят.
GitHub run, required checks и красный/зелёный эксперимент подтверждаются ниже
после фактического выполнения; до этого T-04/G1 не считаются verified.

## Безопасное повторение эксперимента

После включения required checks создать временный тест в отдельной ветке/PR
либо временном коммите рабочего PR, например `assert False` с пояснением T-04.
Не менять финансовую логику или handlers. Дождаться failure у `tests` и `ci`.
Сохранить run URL, commit SHA и фактическое состояние merge box / API. Затем
удалить тест обычным коммитом, дождаться зелёного CI на новом head. Никогда не
merge тестовый PR и не force-push ради удаления доказательств.

`mergeStateStatus=BLOCKED` сам по себе недостаточен: причиной может быть также
отсутствующее approval. В UI нужно видеть указание именно на failed required
checks; если API/кнопка недоступны, этот пункт остаётся ручной проверкой.

## Диагностика

- Нет run: проверить Actions enabled, base=main, наличие workflow в PR, событие
  synchronize; fork workflow может ожидать разрешения владельца. Не использовать
  pull_request_target и не выдавать дополнительные permissions для обхода.
- Lock mismatch: исправить через uv в отдельном коммите, не редактировать lock
  вручную. Cache не является причиной пропуска lock check.
- Integration fail: открыть лог шага PostgreSQL/integration; проверить major 17,
  TEST_DATABASE_URL, доступность service и право CREATEDB. Обычный pytest БД
  не проверяет. Не заменять PostgreSQL на SQLite или mock.
- Coverage fail: смотреть общий отчёт app/bot и добавить значимые тесты, без
  omit сложного кода, изменения порога или skip/xfail.
- Docker fail: воспроизвести `docker build --pull --progress=plain .`, проверить
  доступ к публичным base images/индексу пакетов. Синтаксическая проверка не
  заменяет сборку.
- Expected check отсутствует: проверить имя job и branch rule; не удалять
  обязательную проверку ради merge, исправить workflow и повторить run.
- Сохранены предупреждения Starlette/httpx2 и experimental uv audit; текущий
  согласованный стек не меняется и предупреждения не подавляются.

Официальные основания: [события workflow](https://docs.github.com/en/actions/how-tos/write-workflows/choose-when-workflows-run/trigger-a-workflow),
[uv в GitHub Actions](https://docs.astral.sh/uv/guides/integration/github/),
[защищённые ветки](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-protected-branches/about-protected-branches).
