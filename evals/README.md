# Evaluation of the agent

[`questions.toml`](questions.toml) holds 40 questions frozen before the answers: forecasts, gaps
of a month, years, the model, scenarios, the data, and questions the agent must turn down. Each
question in scope names the tool the agent must call, its arguments and the figures of the tool
result that the answer must state. One question follows the exchange before it, as a visitor's
next question does.

`flf eval` asks them to a model and scores each answer without a judge:

- the expected tool is called with the expected arguments;
- each expected figure is stated, rounded to one decimal or within 1 %;
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
