# M6: аудит каждого Pull Request

Срез03.11.2026, baseline main `638a976`. Источник — REST `/pulls?state=all`
и `/pulls/{number}/reviews`, все страницы.49PR:48merged, один закрыт без merge.
Засчитывается submitted **APPROVED** до `merged_at` от другого участника
(Timur/Oleg/Lera, GitHub User, не bot/автор). COMMENTED/CI/устное разрешение не approval.
На11засчитанных PR проверен порядок: нет позднейшего CHANGES_REQUESTED до merge.
Это не утверждение, что каждый approval относится к последнему push:
`require_last_push_approval=false`, исторический snapshot правил не восстановлен.

**11PASS /37FAIL среди merged.** Недостающие исторические approvals нельзя
создать задним числом. Новое ревью может оценить код сейчас, но formal решение
об этом несоответствии курса принимает преподаватель. PR #65 не вошёл в main.

| PR | Автор | Merge | Pre-merge independent APPROVED | Статус |
|---|---|---|---|---|
| [#1](https://github.com/inte11ectua1/skinulis/pull/1) | inte11ectua1 | 2026-10-15T21:23:36Z | нет | FAIL |
| [#6](https://github.com/inte11ectua1/skinulis/pull/6) | inte11ectua1 | 2026-10-16T17:00:07Z | [Valeria18-new](https://github.com/inte11ectua1/skinulis/pull/6#pullrequestreview-5551027724) | PASS |
| [#7](https://github.com/inte11ectua1/skinulis/pull/7) | inte11ectua1 | 2026-10-26T17:20:01Z | [pylinolg-max](https://github.com/inte11ectua1/skinulis/pull/7#pullrequestreview-5656157751) | PASS |
| [#8](https://github.com/inte11ectua1/skinulis/pull/8) | pylinolg-max | 2026-10-26T17:33:42Z | [inte11ectua1](https://github.com/inte11ectua1/skinulis/pull/8#pullrequestreview-5656332473) | PASS |
| [#9](https://github.com/inte11ectua1/skinulis/pull/9) | Valeria18-new | 2026-10-26T18:20:44Z | [inte11ectua1](https://github.com/inte11ectua1/skinulis/pull/9#pullrequestreview-5656791131) | PASS |
| [#14](https://github.com/inte11ectua1/skinulis/pull/14) | inte11ectua1 | 2026-10-26T18:40:33Z | [pylinolg-max](https://github.com/inte11ectua1/skinulis/pull/14#pullrequestreview-5657215967) | PASS |
| [#15](https://github.com/inte11ectua1/skinulis/pull/15) | inte11ectua1 | 2026-10-26T19:14:09Z | [pylinolg-max](https://github.com/inte11ectua1/skinulis/pull/15#pullrequestreview-5657642557) | PASS |
| [#16](https://github.com/inte11ectua1/skinulis/pull/16) | pylinolg-max | 2026-10-26T19:46:17Z | [inte11ectua1](https://github.com/inte11ectua1/skinulis/pull/16#pullrequestreview-5658027298) | PASS |
| [#17](https://github.com/inte11ectua1/skinulis/pull/17) | pylinolg-max | 2026-10-26T20:18:42Z | [inte11ectua1](https://github.com/inte11ectua1/skinulis/pull/17#pullrequestreview-5658362424) | PASS |
| [#18](https://github.com/inte11ectua1/skinulis/pull/18) | Valeria18-new | 2026-10-26T22:03:41Z | [inte11ectua1](https://github.com/inte11ectua1/skinulis/pull/18#pullrequestreview-5659722090) | PASS |
| [#19](https://github.com/inte11ectua1/skinulis/pull/19) | inte11ectua1 | 2026-10-27T06:35:22Z | нет | FAIL |
| [#20](https://github.com/inte11ectua1/skinulis/pull/20) | inte11ectua1 | 2026-10-27T06:50:11Z | нет | FAIL |
| [#25](https://github.com/inte11ectua1/skinulis/pull/25) | inte11ectua1 | 2026-10-27T07:03:07Z | нет | FAIL |
| [#26](https://github.com/inte11ectua1/skinulis/pull/26) | inte11ectua1 | 2026-10-27T07:50:43Z | нет | FAIL |
| [#27](https://github.com/inte11ectua1/skinulis/pull/27) | inte11ectua1 | 2026-10-27T09:23:08Z | нет | FAIL |
| [#28](https://github.com/inte11ectua1/skinulis/pull/28) | Valeria18-new | 2026-10-28T09:18:44Z | [inte11ectua1](https://github.com/inte11ectua1/skinulis/pull/28#pullrequestreview-5680211421) | PASS |
| [#30](https://github.com/inte11ectua1/skinulis/pull/30) | inte11ectua1 | 2026-10-28T09:37:01Z | нет | FAIL |
| [#31](https://github.com/inte11ectua1/skinulis/pull/31) | pylinolg-max | 2026-10-28T11:21:34Z | нет | FAIL |
| [#33](https://github.com/inte11ectua1/skinulis/pull/33) | inte11ectua1 | 2026-10-28T11:12:48Z | нет | FAIL |
| [#34](https://github.com/inte11ectua1/skinulis/pull/34) | inte11ectua1 | 2026-10-28T11:35:25Z | нет | FAIL |
| [#40](https://github.com/inte11ectua1/skinulis/pull/40) | inte11ectua1 | 2026-10-28T12:24:33Z | нет | FAIL |
| [#41](https://github.com/inte11ectua1/skinulis/pull/41) | pylinolg-max | 2026-10-28T14:09:36Z | нет | FAIL |
| [#42](https://github.com/inte11ectua1/skinulis/pull/42) | pylinolg-max | 2026-10-28T16:47:09Z | нет | FAIL |
| [#43](https://github.com/inte11ectua1/skinulis/pull/43) | Valeria18-new | 2026-10-30T13:05:52Z | нет | FAIL |
| [#44](https://github.com/inte11ectua1/skinulis/pull/44) | inte11ectua1 | 2026-10-30T13:42:27Z | нет | FAIL |
| [#49](https://github.com/inte11ectua1/skinulis/pull/49) | inte11ectua1 | 2026-10-30T15:51:05Z | нет | FAIL |
| [#50](https://github.com/inte11ectua1/skinulis/pull/50) | inte11ectua1 | 2026-10-30T16:45:35Z | нет | FAIL |
| [#51](https://github.com/inte11ectua1/skinulis/pull/51) | pylinolg-max | 2026-10-30T17:21:28Z | нет | FAIL |
| [#52](https://github.com/inte11ectua1/skinulis/pull/52) | inte11ectua1 | 2026-10-31T10:08:15Z | нет | FAIL |
| [#53](https://github.com/inte11ectua1/skinulis/pull/53) | pylinolg-max | 2026-10-31T11:59:55Z | нет | FAIL |
| [#54](https://github.com/inte11ectua1/skinulis/pull/54) | Valeria18-new | 2026-10-31T14:59:09Z | нет | FAIL |
| [#56](https://github.com/inte11ectua1/skinulis/pull/56) | inte11ectua1 | 2026-10-31T13:45:41Z | нет | FAIL |
| [#57](https://github.com/inte11ectua1/skinulis/pull/57) | pylinolg-max | 2026-10-31T14:19:00Z | нет | FAIL |
| [#58](https://github.com/inte11ectua1/skinulis/pull/58) | inte11ectua1 | 2026-10-31T15:31:13Z | нет | FAIL |
| [#63](https://github.com/inte11ectua1/skinulis/pull/63) | inte11ectua1 | 2026-10-31T15:57:14Z | нет | FAIL |
| [#64](https://github.com/inte11ectua1/skinulis/pull/64) | inte11ectua1 | 2026-10-31T19:48:35Z | нет | FAIL |
| [#65](https://github.com/inte11ectua1/skinulis/pull/65) | inte11ectua1 | — | нет | NOT VERIFIED (closed без merge) |
| [#66](https://github.com/inte11ectua1/skinulis/pull/66) | inte11ectua1 | 2026-11-01T17:11:36Z | нет | FAIL |
| [#67](https://github.com/inte11ectua1/skinulis/pull/67) | inte11ectua1 | 2026-11-01T17:32:13Z | нет | FAIL |
| [#68](https://github.com/inte11ectua1/skinulis/pull/68) | inte11ectua1 | 2026-11-01T17:51:34Z | нет | FAIL |
| [#69](https://github.com/inte11ectua1/skinulis/pull/69) | inte11ectua1 | 2026-11-02T05:56:27Z | нет | FAIL |
| [#70](https://github.com/inte11ectua1/skinulis/pull/70) | inte11ectua1 | 2026-11-02T06:17:40Z | нет | FAIL |
| [#71](https://github.com/inte11ectua1/skinulis/pull/71) | inte11ectua1 | 2026-11-02T07:03:02Z | [pylinolg-max](https://github.com/inte11ectua1/skinulis/pull/71#pullrequestreview-5732883323) | PASS |
| [#72](https://github.com/inte11ectua1/skinulis/pull/72) | inte11ectua1 | 2026-11-02T06:27:33Z | нет | FAIL |
| [#73](https://github.com/inte11ectua1/skinulis/pull/73) | inte11ectua1 | 2026-11-02T13:51:27Z | нет | FAIL |
| [#74](https://github.com/inte11ectua1/skinulis/pull/74) | pylinolg-max | 2026-11-02T20:12:15Z | нет | FAIL |
| [#75](https://github.com/inte11ectua1/skinulis/pull/75) | Valeria18-new | 2026-11-02T20:41:00Z | нет | FAIL |
| [#77](https://github.com/inte11ectua1/skinulis/pull/77) | inte11ectua1 | 2026-11-02T22:18:09Z | нет | FAIL |
| [#78](https://github.com/inte11ectua1/skinulis/pull/78) | inte11ectua1 | 2026-11-02T22:56:50Z | нет | FAIL |

Новый M6 PR отсутствует в историческом baseline49PR. Его собственный human
review должен быть получен **перед** merge; запросы review и CI не означают APPROVED.
Кода main этот аудит не меняет и PR не мержит.

First-parent main:48коммитов — initial seed +47изменений, каждое из47сопоставлено
merge_commit_sha соответствующего merged PR.48merged PR в репозитории не обязаны
давать48first-parent merges (PR может войти через другую ветку). Никакого доказанного
позднего direct-push в доступной истории не обнаружено; возможность admin push
и фактический прошлый direct-push — разные утверждения.
