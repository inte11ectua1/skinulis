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
fork/PR cache ограничен правилами GitHub. Две inline allowlist-пометки
detect-secrets относятся только к явно публичному тестовому паролю и его URL;
глобальные проверки секретов не отключены. Lock и frozen sync проверяются заново
независимо от cache hit. Docker job собирает существующий multi-stage/nonroot
Dockerfile; registry login, push и deployment отсутствуют.

## Настройки main и проверка администратором

На начало T-04 `main.protected=true`, rulesets API вернул пустой список, а GET
branch protection через GitHub-коннектор вернул 403 Resource not accessible by
integration. Это не подтверждает параметры и не означает, что защита отсутствует.
Административный API доступен через существующую Git-авторизацию владельца:
штатный `git credential` helper передаёт credential процессу gh в памяти,
без печати или записи токена в файлы. Дополнительный device login отменён.

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

Первый [зелёный run #1](https://github.com/inte11ectua1/skinulis/actions/runs/40458001625)
на commit `b608a9d`: все пять jobs success. Linux Python 3.12.15 / uv 0.13.5;
343 unit passed, 4 PostgreSQL integration passed. Общее branch coverage app + bot:
97.79% (493 statements, 94 branches); coverage artifact загружен.
Dockerfile действительно собран на GitHub runner, без registry push.

После этого административный PUT добавил пять required checks с источником
GitHub Actions (`app_id=15368`), strict=true. Повторный независимый GET подтвердил:

| Параметр classic branch protection main | Фактическое значение 27.10.2026 |
|---|---|
| Required checks | lint, types, tests, docker-build, ci; GitHub Actions |
| Branch up to date | strict=true |
| Required PR approval | 1, dismiss_stale_reviews=true |
| Admin enforcement | enforce_admins=true |
| Review bypass allowances | отсутствуют |
| Conversations | required_conversation_resolution=true |
| Force pushes / deletion | оба false |
| Rulesets | пустой список; действует classic branch protection |

Существующие настройки сохранены: code-owner review=false, last-push
approval=false, linear history=false, lock branch=false. Ни одна прежняя защита
не ослаблялась. Источник: GET /repos/inte11ectua1/skinulis/branches/main/protection
под административной Git-авторизацией; коннектор с ограниченными permissions
по-прежнему может получать 403. Это не отменяет проверку через CLI.

[Красный run #2](https://github.com/inte11ectua1/skinulis/actions/runs/40458200449),
commit `7f221c9`: временный `test_ci_gate_probe.py` даёт 1 failed / 343 passed.
`tests` и `ci` — failure, `lint`/`types`/`docker-build` — success. Integration и
coverage в этом run не запускались после ошибки unit-теста; их успех не заявляется.
На этом head GraphQL вернул statusCheckRollup=FAILURE, mergeStateStatus=BLOCKED,
reviewDecision=REVIEW_REQUIRED, viewerCanMergeAsAdmin=false. Проверки tests/ci
в этот момент уже обязательны по повторно прочитанной защите main.

Снимок API без credentials: [T-04_EVIDENCE.json](T-04_EVIDENCE.json).
Он содержит настройку защиты, точный отрицательный head и check conclusions.
**Ограничение доказательства:** состояние кнопки Merge/текст причины в UI не
прочитаны: Computer Use ожидал разрешения macOS Accessibility/Screen Recording.
BLOCKED мог одновременно объясняться отсутствующим approval; это не выдано за
визуальное подтверждение блокировки именно из-за CI. Для закрытия этого пункта
владелец повторяет описанный ниже временный тест и сохраняет merge box с failed
required checks / Merging is blocked, без возможности admin bypass. Пробовать
merge или отключать approval для эксперимента не нужно.

Намеренный тест удалён обычным коммитом `48a0471`; в итоговом diff его нет.
[Восстановленный run #3](https://github.com/inte11ectua1/skinulis/actions/runs/40458675107)
после удаления probe: все пять jobs success. Это подтверждает переход
зелёный → намеренно красный → зелёный на настоящем PR. Окончательный run текущего
head после документационного коммита также указан в PR #19. G1 остаётся
not verified до независимого review/merge T-04 и оставшейся визуальной проверки.

## Безопасное повторение эксперимента

1. Открыть отдельную временную ветку от актуальной main (после принятия T-04)
   либо временный коммит рабочего PR до approval. Добавить только
   `tests/unit/test_ci_gate_probe.py` с функцией `def test_ci_gate() -> None:`
   и строкой `raise AssertionError("T-04 intentional probe")` внутри неё.
2. Открыть PR в main и дождаться красных `tests` и `ci` в Checks.
3. В Conversation прокрутить до merge box под аккаунтом inte11ectua1. Сохранить
   скриншот с SHA/URL PR, failed checks с пометкой Required, текстом
   Merging is blocked и недоступной Merge. Отсутствие approval может отображаться
   одновременно: нужна также явная причина failed required status checks.
4. Проверить отсутствие обхода для владельца. Не нажимать Merge и не отключать
   требование approval, admin enforcement или status checks.
5. Удалить только временный тест обычным коммитом, дождаться всех пяти зелёных
   проверок. Сохранить обе run URLs; закрыть тестовый PR без merge.

Финансовую логику/handlers не менять; не force-push ради удаления доказательств.
Если явной причины failed required checks нет, сохранить наблюдение и проверить
имена checks/источник в защите main, не объявлять эксперимент завершённым.

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
