/** The question box: a visitor asks the agent, which answers from the published data. */

import { byId } from "./chart";
import { dayName } from "./format";

// The question API, set when the page is built. Without it, the box stays out of the page.
const API = import.meta.env.VITE_API_URL ?? "";

// The API answers in a few seconds; past this, the visitor is told to try again.
const TIMEOUT_MS = 90_000;

/** The reply of the API, as src/france_load_forecast/api.py writes it. */
export interface Reply {
  answer: string;
  verified: boolean;
  tools: string[];
  published: string;
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
  if (error instanceof DOMException && error.name === "TimeoutError") {
    return "La réponse prend trop de temps. Réessayez plus tard.";
  }
  if (error instanceof TypeError)
    return "Le service de questions ne répond pas. Réessayez plus tard.";
  return error instanceof Error ? error.message : String(error);
}

/** The answer of the API to `question`; its message when it refuses the question. */
export async function ask(question: string, api = API, fetcher = fetch): Promise<Reply> {
  const response = await fetcher(`${api}/ask`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ question }),
    signal: AbortSignal.timeout(TIMEOUT_MS),
  });
  const body: unknown = await response.json().catch(() => null);
  if (!response.ok) {
    const detail = (body as { detail?: unknown } | null)?.detail;
    throw new Error(
      typeof detail === "string" ? detail : "Le service de questions a rencontré une erreur.",
    );
  }
  return body as Reply;
}

function paragraphs(box: HTMLElement, text: string): void {
  box.replaceChildren(
    ...text.split(/\n\s*\n/).map((part) => {
      const paragraph = document.createElement("p");
      paragraph.textContent = part.trim();
      return paragraph;
    }),
  );
}

export function render(): void {
  if (!API) {
    byId("ask").hidden = true;
    const link = document.querySelector('.masthead a[href="#ask-title"]');
    if (link?.parentElement) link.parentElement.hidden = true;
    return;
  }
  const form = byId<HTMLFormElement>("ask-form");
  const field = byId<HTMLTextAreaElement>("ask-question");
  const send = byId<HTMLButtonElement>("ask-send");
  const answer = byId("ask-answer");
  const origin = byId("ask-origin");
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const question = field.value.trim();
    if (!question) return;
    send.disabled = true;
    answer.textContent = "Réponse en cours…";
    origin.textContent = "";
    try {
      const reply = await ask(question);
      paragraphs(answer, reply.answer);
      origin.textContent = caption(reply);
    } catch (error) {
      answer.textContent = failure(error);
    } finally {
      send.disabled = false;
    }
  });
  // An example fills the field; the visitor sends it, as each question counts.
  for (const example of document.querySelectorAll<HTMLButtonElement>("#ask [data-question]")) {
    example.addEventListener("click", () => {
      field.value = example.dataset.question ?? "";
      field.focus();
    });
  }
}
