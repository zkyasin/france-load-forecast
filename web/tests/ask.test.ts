import { expect, test } from "vitest";
import { AskError, ask, type Call, caption, failure, type Reply, readEvents } from "../src/ask";

const reply: Reply = {
  answer: "Environ 49,2 TWh en P50.",
  verified: true,
  tools: ["forecast", "forecast", "month_gap"],
  published: "2026-11-22",
};

/** A fetch that answers `status` with `body`, and records the request. */
function answering(status: number, body: unknown, requests: Request[] = []): typeof fetch {
  return async (input, init) => {
    requests.push(new Request(input, init));
    return new Response(JSON.stringify(body), { status });
  };
}

test("a verified answer names the date of its data and what the agent read", () => {
  expect(caption(reply)).toBe(
    "Chaque nombre vient des données publiées le 22 novembre 2026, lues dans la prévision et " +
      "les écarts d'un mois.",
  );
  expect(caption({ ...reply, tools: [] })).toBe("Cette réponse ne s'appuie sur aucune donnée.");
  expect(caption({ ...reply, verified: false })).toMatch(/^Un nombre de la réponse n'avait pas/);
});

/** A fetch that streams `events` as server-sent events, in chunks of `size` characters. */
function streaming(events: [string, unknown][], size = 7): typeof fetch {
  const text = events.map(([event, data]) => `event: ${event}\ndata: ${JSON.stringify(data)}\n\n`);
  const whole = text.join("");
  return async () =>
    new Response(
      new ReadableStream({
        start(controller) {
          const bytes = new TextEncoder().encode(whole);
          for (let at = 0; at < bytes.length; at += size) {
            controller.enqueue(bytes.slice(at, at + size));
          }
          controller.close();
        },
      }),
      { headers: { "Content-Type": "text/event-stream" } },
    );
}

test("the question and the exchange before it are posted to the stream of the API", async () => {
  const requests: Request[] = [];
  const previous = { question: "Et avril ?", answer: "Avril a fini sous la prévision." };

  const answer = await ask("Et janvier ?", {
    api: "https://api.test",
    fetcher: answering(200, reply, requests),
    previous,
  });

  expect(answer).toEqual(reply);
  const [request] = requests;
  expect(request?.url).toBe("https://api.test/ask/stream");
  expect(request?.method).toBe("POST");
  expect(await request?.json()).toEqual({ question: "Et janvier ?", previous });
});

test("each step comes before the answer, whatever the chunks of the stream", async () => {
  const steps: Call[] = [];
  const restarts: number[] = [];
  const events: [string, unknown][] = [
    ["step", { tool: "forecast", args: {} }],
    ["retry", {}],
    ["step", { tool: "month_gap", args: { month: "2026-04" } }],
    ["answer", reply],
  ];

  const answer = await ask("Et avril ?", {
    api: "https://api.test",
    fetcher: streaming(events),
    onStep: (call) => steps.push(call),
    onRetry: () => restarts.push(steps.length),
  });

  expect(answer).toEqual(reply);
  expect(steps).toEqual([
    { tool: "forecast", args: {} },
    { tool: "month_gap", args: { month: "2026-04" } },
  ]);
  expect(restarts).toEqual([1]);
});

test("a stream that ends on an error is a refusal of the API", async () => {
  const detail = "Le modèle ne répond pas pour le moment. Réessayez plus tard.";

  await expect(
    ask("Et avril ?", { api: "https://api.test", fetcher: streaming([["error", { detail }]]) }),
  ).rejects.toEqual(new AskError(503, detail));
});

test("an API without a stream is asked in one piece", async () => {
  const requests: Request[] = [];
  const older: typeof fetch = async (input, init) => {
    const request = new Request(input, init);
    requests.push(request);
    const found = request.url.endsWith("/ask");
    return new Response(JSON.stringify(found ? reply : { detail: "Not Found" }), {
      status: found ? 200 : 404,
    });
  };

  expect(await ask("Et janvier ?", { api: "https://api.test", fetcher: older })).toEqual(reply);
  expect(requests.map((request) => request.url)).toEqual([
    "https://api.test/ask/stream",
    "https://api.test/ask",
  ]);
});

test("events are read whole, and the rest waits for the next chunk", () => {
  expect(readEvents('event: step\ndata: {"tool": "accuracy"}\n\nevent: answ')).toEqual({
    events: [{ event: "step", data: '{"tool": "accuracy"}' }],
    rest: "event: answ",
  });
});

test("a refused question gives the status and the message of the API", async () => {
  const detail = "Vous avez posé beaucoup de questions. Réessayez plus tard.";
  const asking = (status: number, body: unknown) =>
    ask("Et janvier ?", { api: "https://api.test", fetcher: answering(status, body) });

  await expect(asking(429, { detail })).rejects.toEqual(new AskError(429, detail));
  await expect(asking(429, { detail })).rejects.toMatchObject({ status: 429 });
  await expect(asking(500, "oops")).rejects.toThrow(
    "Le service de questions a rencontré une erreur.",
  );
});

test("a question can be cancelled", async () => {
  const stop = new AbortController();
  const waiting: typeof fetch = (_, init) =>
    new Promise((_resolve, reject) => {
      init?.signal?.addEventListener("abort", () => reject(init.signal?.reason));
    });

  const asked = ask("Et janvier ?", {
    api: "https://api.test",
    fetcher: waiting,
    signal: stop.signal,
  });
  stop.abort();

  const error = await asked.catch((reason: unknown) => reason);
  expect(failure(error)).toBe("Question annulée.");
});

test("a network failure and a timeout are told apart", () => {
  expect(failure(new TypeError("Failed to fetch"))).toBe(
    "Le service de questions ne répond pas. Réessayez plus tard.",
  );
  expect(failure(new DOMException("The operation timed out.", "TimeoutError"))).toBe(
    "La réponse prend trop de temps. Réessayez plus tard.",
  );
  expect(failure(new Error("Le nombre de questions du jour est atteint."))).toBe(
    "Le nombre de questions du jour est atteint.",
  );
});
