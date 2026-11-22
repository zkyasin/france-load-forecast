import { expect, test } from "vitest";
import { ask, caption, failure, type Reply } from "../src/ask";

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

test("the question is posted to the API and its reply returned", async () => {
  const requests: Request[] = [];

  const answer = await ask("Et janvier ?", "https://api.test", answering(200, reply, requests));

  expect(answer).toEqual(reply);
  const [request] = requests;
  expect(request?.url).toBe("https://api.test/ask");
  expect(request?.method).toBe("POST");
  expect(await request?.json()).toEqual({ question: "Et janvier ?" });
});

test("a refused question gives the message of the API", async () => {
  const detail = "Vous avez posé beaucoup de questions. Réessayez plus tard.";

  await expect(ask("Et janvier ?", "https://api.test", answering(429, { detail }))).rejects.toThrow(
    detail,
  );
  await expect(ask("Et janvier ?", "https://api.test", answering(500, "oops"))).rejects.toThrow(
    "Le service de questions a rencontré une erreur.",
  );
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
