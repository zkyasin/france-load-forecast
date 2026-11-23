/** The question API: a visitor asks the agent, which answers from the published data. */

import { dayName } from "./format";

// The question API, set when the page is built. Without it, the page has no question panel.
export const API = import.meta.env.VITE_API_URL ?? "";

// The API answers in a few seconds; past this, the visitor is told to try again.
const TIMEOUT_MS = 90_000;

/** The reply of the API, as src/france_load_forecast/api.py writes it. */
export interface Reply {
  answer: string;
  verified: boolean;
  tools: string[];
  published: string;
}

/** A question the API turned down, with its HTTP status and its message. */
export class AskError extends Error {
  readonly status: number;

  constructor(status: number, message: string) {
    super(message);
    this.name = "AskError";
    this.status = status;
  }
}

const TOOLS: Record<string, string> = {
  forecast: "la prévision",
  month_gap: "les écarts d'un mois",
  annual_energy: "l'énergie des années",
  thermosensitivity: "la réponse à la température",
  accuracy: "la fiabilité",
  fact: "la méthode et les sources",
  scenario: "les scénarios",
};

/** "la prévision et les écarts d'un mois". */
function listOf(names: string[]): string {
  const last = names.at(-1) ?? "";
  return names.length < 2 ? last : `${names.slice(0, -1).join(", ")} et ${last}`;
}

/** Where the answer comes from, or why it is not shown. */
export function caption(reply: Reply): string {
  if (!reply.verified) {
    return "Un nombre de la réponse n'avait pas de source dans les données : elle n'est pas affichée.";
  }
  if (reply.tools.length === 0) return "Cette réponse ne s'appuie sur aucune donnée.";
  const read = [...new Set(reply.tools.map((tool) => TOOLS[tool] ?? tool))];
  return (
    `Chaque nombre vient des données publiées le ${dayName(reply.published)}, lues dans ` +
    `${listOf(read)}.`
  );
}

/** What to tell the visitor when the question gets no answer. */
export function failure(error: unknown): string {
  if (error instanceof DOMException && error.name === "AbortError") return "Question annulée.";
  if (error instanceof DOMException && error.name === "TimeoutError") {
    return "La réponse prend trop de temps. Réessayez plus tard.";
  }
  if (error instanceof TypeError)
    return "Le service de questions ne répond pas. Réessayez plus tard.";
  return error instanceof Error ? error.message : String(error);
}

export interface AskOptions {
  api?: string;
  fetcher?: typeof fetch;
  // Cancels the question, as the visitor's Stop button does.
  signal?: AbortSignal;
}

/** The answer of the API to `question`; an AskError with its message when it turns it down. */
export async function ask(question: string, options: AskOptions = {}): Promise<Reply> {
  const { api = API, fetcher = fetch, signal } = options;
  const timeout = AbortSignal.timeout(TIMEOUT_MS);
  const response = await fetcher(`${api}/ask`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ question }),
    signal: signal === undefined ? timeout : AbortSignal.any([signal, timeout]),
  });
  const body: unknown = await response.json().catch(() => null);
  if (!response.ok) {
    const detail = (body as { detail?: unknown } | null)?.detail;
    throw new AskError(
      response.status,
      typeof detail === "string" ? detail : "Le service de questions a rencontré une erreur.",
    );
  }
  return body as Reply;
}
