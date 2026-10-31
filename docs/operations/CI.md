# T-04 — CI и защита main

## M4 closeout / M5 Delivery (31.10.2026)

**M4 завершён по реализации:** [финальный T-08 PR #58](https://github.com/inte11ectua1/skinulis/pull/58) merged, Issue #45 closed. [CI его последнего head](https://github.com/inte11ectua1/skinulis/actions/runs/41213175596): lint/types/tests/docker-build/ci **5/5 success**. Предыдущие product PR также подтверждены на head: [O-06 #51](https://github.com/inte11ectua1/skinulis/actions/runs/41096303217) 1181 tests, [O-07 #53](https://github.com/inte11ectua1/skinulis/actions/runs/41195690077) 1283, [O-07N #57](https://github.com/inte11ectua1/skinulis/actions/runs/41208270181) 1311, [L-05 #54](https://github.com/inte11ectua1/skinulis/actions/runs/41210779152) 1460 tests/94,76%. Отдельные результаты **не суммировать**. На merge commit этих PR не обязаны существовать собственные checks: указан evidence final head. Несколько PR, включая #58, не имеют зарегистрированного independent human APPROVED; зелёный CI не является человеческим ревью.

**M5 delivery ещё не реализован:** [T-09 #59](https://github.com/inte11ectua1/skinulis/issues/59) должен добавить отдельную trustworthy GitHub Actions CD схему **после merge main** (GHCR immutable SHA, serialized SSH deploy/VPS, health/version SHA, private /internal); **не выдавать prod secrets в pull_request workflows**. [T-10 #60](https://github.com/inte11ectua1/skinulis/issues/60) — безопасные логи/rotation/runbook; [O-08 #61](https://github.com/inte11ectua1/skinulis/issues/61) — измерение 100 concurrent p95 только на одноразовой test DB; [L-06 #62](https://github.com/inte11ectua1/skinulis/issues/62) — mocked Telegram+real HTTP/PG. **Пока нет** GHCR deploy evidence, VPS HTTPS или live Telegram: G5 и live G2/G3/G4 остаются not verified. Инфраструктурные/production действия только по отдельному разрешению Тимура. [Handoff](M5_DELIVERY_HANDOFF.md).


Issue: [#13](https://github.com/inte11ectua1/skinulis/issues/13) — **closed после merged PR #19** (27.10.2026).

> **Срез после merge 27.10.2026:** M1/T-04 реализован в `main`; зелёный и намеренно красный CI runs опубликованы ниже. Административные настройки защиты, перечисленные в первоначальном отчёте T-04, — *исторические*. Повторное чтение GitHub ветки `main` после изменения владельцем показало required status check **`enforcement_level=non_admins`** для `lint`, `types`, `tests`, `docker-build`, `ci`: защита больше не гарантирует одинаковую обязательность проверок для администратора. PR #19 объединён без зарегистрированного независимого `APPROVED`-review. Факт красного CI и `mergeStateStatus=BLOCKED` на тестовом head не означает, что сейчас администратор не может обойти checks. Практическая блокировка direct push и визуальная причина запрета merge при failed required checks **не подтверждены**. G1 формально остаётся с оговорками; см. [STATUS](../STATUS.md).

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

## Настройки main и проверка администратором (историческая конфигурация при T-04)

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
5. **Целевая политика по первоначальному ADR**: no bypass / enforcement и для administrators, ruleset bypass list пуст. **Фактически позже владелец изменил режим:** текущий check enforcement_level=non_admins. Не выдавать прежний пункт за действующую настройку; вернуть полный enforcement только отдельным решением владельца.
6. Allow force pushes и Allow deletions выключены. Правило применяется к main,
   enforcement активно. Не включать Lock branch: это запретит и обычный merge.
7. Сохранить и заново открыть правило, проверить значения. Проверить красный PR
   под аккаунтом владельца: требуется именно блокировка, без возможности bypass.

Прямой push в main специально не выполняется: при ошибочной защите даже тестовый
push мог бы изменить общую ветку. Настройки защиты и фактический отказ push —
разные доказательства T-01; одно нельзя выдавать за другое.

## Доказательства (срез первоначального PR #19)

Первый [зелёный run #1](https://github.com/inte11ectua1/skinulis/actions/runs/40458001625)
на commit `b608a9d`: все пять jobs success. Linux Python 3.12.15 / uv 0.13.5;
343 unit passed, 4 PostgreSQL integration passed. Общее branch coverage app + bot:
97.79% (493 statements, 94 branches); coverage artifact загружен.
Dockerfile действительно собран на GitHub runner, без registry push.

Во время PR #19 административный PUT добавил пять required checks с источником
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

## Обновлённый статус после merge PR #19

- [PR #19](https://github.com/inte11ectua1/skinulis/pull/19) merged, [Issue #13](https://github.com/inte11ectua1/skinulis/issues/13) closed; CI присутствует в main.
- На момент первоначального тестового красного run GraphQL вернул BLOCKED и viewerCanMergeAsAdmin=false. Это исторический результат, а не повторная проверка после изменения branch protection.
- После изменения настроек в GitHub ответ `main.protection.required_status_checks.enforcement_level` равен **`non_admins`**, а пять required check names остаются перечисленными. Точные прочие параметры branch protection (после изменения) нужно перечитать авторизованным администратором; текущему коннектору детальный endpoint недоступен.
- Чтобы доказать реальную обязательность красного CI для **не-администратора**, нужно показать failed required checks в merge box. Для администратора с обходом проверка запрета должна отдельно документировать роль и режим bypass. Не отключать CI из workflow ради зелёного run.

## Безопасное повторение эксперимента

1. Открыть отдельную временную ветку от актуальной main (после принятия T-04)
   либо временный коммит рабочего PR до approval. Добавить только
   `tests/unit/test_ci_gate_probe.py` с функцией `def test_ci_gate() -> None:`
   и строкой `raise AssertionError("T-04 intentional probe")` внутри неё.
2. Открыть PR в main и дождаться красных `tests` и `ci` в Checks.
3. В Conversation прокрутить до merge box под аккаунтом **без admin bypass**. Сохранить
   скриншот с SHA/URL PR, failed checks с пометкой Required, текстом
   Merging is blocked и недоступной Merge. Для аккаунта `inte11ectua1` повторно
   проверить, включён ли разрешённый администраторский обход: при режиме
   `non_admins` нельзя обещать запрет Merge для самого владельца.
4. Зафиксировать, для каких ролей действует защита. **Сейчас для checks указан non_admins**, поэтому наличие bypass у владельца не считать ошибкой CI. Не нажимать Merge для тестового красного PR.
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
