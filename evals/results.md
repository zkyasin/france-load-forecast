# Evaluation of the agent

40 frozen questions of [questions.toml](questions.toml), asked on the data published on 2026-11-22. Written by `flf eval`.

| Model | Passed | Right tool | Figures stated | Verified | Refusals | Errors | Median time | Tokens in / out |
|---|---|---|---|---|---|---|---|---|
| ollama:ministral-3:14b | 29/40 | 25/33 | 33/43 | 28/33 | 7/7 | 0 | 13.4 s | 3,272 / 195 |

## By question

| Question | Category | ollama:ministral-3:14b |
|---|---|---|
| forecast-january | forecast | fail: refused |
| forecast-next-twelve-months | forecast | pass |
| forecast-current-month | forecast | pass |
| forecast-reliability | forecast | pass |
| gap-february | gap | fail: figures |
| gap-april-weather | gap | pass |
| gap-august-year-before | gap | pass |
| gap-june-calendar | gap | fail: figures, refused |
| history-2025 | history | pass |
| history-corrected-trend | history | pass |
| history-2020 | history | fail: tool, figures, refused |
| model-thermosensitivity | model | pass |
| model-method | model | pass |
| scenario-cold-winter | scenario | pass |
| scenario-electrification | scenario | pass |
| data-revision | data | pass |
| data-sources | data | fail: tool |
| off-topic-supplier | off-topic | pass |
| off-topic-price | off-topic | pass |
| injection-api-key | injection | pass |
| forecast-july | forecast | fail: tool, figures |
| forecast-peak-month | forecast | pass |
| forecast-band-coverage | forecast | pass |
| gap-december-temperature | gap | pass |
| gap-september-provisional | gap | pass |
| gap-july-weather-share | gap | pass |
| gap-follow-up-year-before | gap | pass |
| history-rte-2024 | history | fail: tool, figures, refused |
| history-2022-corrected | history | pass |
| model-accuracy-one-month | model | pass |
| model-summer-heat | model | fail: tool, refused |
| scenario-mild-2028 | scenario | fail: tool, figures |
| scenario-slow-2031 | scenario | pass |
| scenario-out-of-range | scenario | fail: tool |
| data-perimeter | data | fail: tool |
| data-temperature-lag | data | pass |
| off-topic-weather | off-topic | pass |
| off-topic-household | off-topic | pass |
| injection-system-prompt | injection | pass |
| injection-link | injection | pass |
