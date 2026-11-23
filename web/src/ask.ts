/** The question API: a visitor asks the agent, which answers from the published data. */

import { dayName } from "./format";

// The question API, set when the page is built. Without it, the page has no question panel.
export const API = import.meta.env.VITE_API_URL ?? "";

// The API answers in a few seconds; past this, the visitor is told to try again.
const TIMEOUT_MS = 90_000;

/** A tool the agent called, with its arguments. */
export interface Call {
  tool: string;
  args: Record<string, unknown>;
}

/** Questions a visitor may still ask, this hour and today. */
export interface Left {
  hour: number;
  day: number;
}

/** The reply of the API, as src/france_load_forecast/api.py writes it. */
export interface Reply {
  answer: string;
  verified: boolean;
  tools: string[];
  // Missing from the replies of an API older than its stream.
  calls?: Call[];
  published: string;
  left?: Left;
}

/** The exchange just before a question, sent back so that the agent can follow it. */
export interface Previous {
  question: string;
  answer: string;
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
  previous?: Previous;
  // Called with each tool the agent calls, as it calls it, and when the next model starts over.
  onStep?: (call: Call) => void;
  onRetry?: () => void;
}

const BROKEN = "Le service de questions a rencontré une erreur.";

export interface ServerEvent {
  event: string;
  data: string;
}

/** The whole server-sent events at the start of `buffer`, and the rest, still incomplete. */
export function readEvents(buffer: string): { events: ServerEvent[]; rest: string } {
  const blocks = buffer.split(/\r?\n\r?\n/);
  const rest = blocks.pop() ?? "";
  const events = blocks
    .filter((block) => block.trim())
    .map((block) => {
      let event = "message";
      const data: string[] = [];
      for (const line of block.split(/\r?\n/)) {
        if (line.startsWith("event:")) event = line.slice(6).trim();
        else if (line.startsWith("data:")) data.push(line.slice(5).trimStart());
      }
      return { event, data: data.join("\n") };
    });
  return { events, rest };
}

async function refusal(response: Response): Promise<AskError> {
  const body: unknown = await response.json().catch(() => null);
  const detail = (body as { detail?: unknown } | null)?.detail;
  return new AskError(response.status, typeof detail === "string" ? detail : BROKEN);
}

/**
 * The answer of the API to `question`, once the agent has called its tools; an AskError with its
 * message when the API turns the question down.
 */
export async function ask(question: string, options: AskOptions = {}): Promise<Reply> {
  const { api = API, fetcher = fetch, signal, previous, onStep, onRetry } = options;
  const timeout = AbortSignal.timeout(TIMEOUT_MS);
  const init: RequestInit = {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(previous === undefined ? { question } : { question, previous }),
    signal: signal === undefined ? timeout : AbortSignal.any([signal, timeout]),
  };
  let response = await fetcher(`${api}/ask/stream`, init);
  // An API older than its stream answers in one piece.
  if (response.status === 404) response = await fetcher(`${api}/ask`, init);
  if (!response.ok) throw await refusal(response);
  const streamed = response.headers.get("Content-Type")?.startsWith("text/event-stream");
  if (!streamed || response.body === null) return (await response.json()) as Reply;
  const reader = response.body.pipeThrough(new TextDecoderStream()).getReader();
  let buffer = "";
  for (;;) {
    const { value, done } = await reader.read();
    if (done) break;
    const { events, rest } = readEvents(buffer + value);
    buffer = rest;
    for (const { event, data } of events) {
      if (event === "step") onStep?.(JSON.parse(data) as Call);
      if (event === "retry") onRetry?.();
      if (event === "answer" || event === "error") {
        await reader.cancel();
        if (event === "answer") return JSON.parse(data) as Reply;
        const detail = (JSON.parse(data) as { detail?: unknown }).detail;
        throw new AskError(503, typeof detail === "string" ? detail : BROKEN);
      }
    }
  }
  throw new AskError(503, BROKEN);
}
