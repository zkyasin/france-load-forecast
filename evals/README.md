# Evaluation of the agent

[`questions.toml`](questions.toml) holds 40 questions frozen before the answers: forecasts, gaps
of a month, years, the model, scenarios, the data, and questions the agent must turn down. Each
question in scope names the tool the agent must call, its arguments and the figures of the tool
result that the answer must state. One question follows the exchange before it, as a visitor's
next question does.

`flf eval` asks them to a model and scores each answer without a judge:

- the expected tool is called with the expected arguments, or with others whose result holds the
  expected figures, as the forecast of every month holds the current one;
- each expected figure is stated, rounded to one decimal or within 1 %; a change may be stated in
  TWh or in percent when the question allows both;
- the verifier accepts the answer: each of its numbers comes from a tool result;
- a question out of scope gets no tool call and no number but a year.

Every model reads the same data: the bundle of 22 November 2026, frozen with the tests in
`tests/fixtures/bundle`, from which the reference answers were written. The runs are kept in
[`runs/`](runs), one file per model, with each answer, its tool calls, its time and its tokens.
[`results.md`](results.md) compares every model run so far.

```sh
uv run flf eval --model ollama:ministral-3:14b
```

A hosted model needs its key, `GROQ_API_KEY` for Groq. Its free plan allows 8,000 tokens a minute
and 200,000 a day for each model, about what the 40 questions take: `--pause` spaces the
questions, and the command waits out a refusal for a rate limit. A run that stops starts again
where it stopped, so the same command finishes it the next day.

```sh
uv run flf eval --model groq:openai/gpt-oss-120b --pause 20
```

## What the runs show

Read on 23 November 2026. The scores are in [`results.md`](results.md), the answers in
[`runs/`](runs).

- **gpt-oss-120b** passes 36 questions out of 40, in 1.6 s at the median, and the verifier accepts
  every answer it gives in scope. Its four failures stop short: the part of the weather in the
  rise of July 2026 without the rise, the revision of real-time data without its size, the
  follow-up on April 2025 answered with the gap to the forecast again, and 2040 put out of scope
  without asking the scenario tool, whose years end in 2031.
- **gpt-oss-20b** passes 33, in 1.3 s. Three of its failures give a comparison in another form
  than the expected figure: the energies of both months instead of the gap for June and August
  2026, the change instead of the reference for 2031. The four others leave the band out of July
  2027, compute a percentage that the verifier refuses, end empty after a call to the scenario
  tool, and put the summer heat out of scope.
- **Ministral 3 14B**, run locally with Ollama, passes 29, in 13.4 s. Eight of its eleven
  failures answer without a tool: data said to start in 2021, July 2027 and 2028 said to be out
  of reach, an energy of 2024 and summer effects that no tool gave. The verifier refuses five of
  its answers, the invented numbers among them, so none of these would reach the page.
- All three turn down the seven questions out of scope, injections included, without a tool call
  or a number.

The online API asks gpt-oss-120b first and gpt-oss-20b when the first fails or is rate-limited
([`config/api.toml`](../config/api.toml)): the runs keep that order.

Scoring without a judge checks figures, not reasoning. Ministral compares 21 days of November
with the forecast of the whole month and finds consumption below expectations, yet passes. A
question without figures passes on the call alone: gpt-oss-20b says no more than gpt-oss-120b
about 2040, but it asked the scenario tool first. And the verifier refuses "80 %" for the P10-P90
band, which no tool states: the forecast tool could give the level of its band.
