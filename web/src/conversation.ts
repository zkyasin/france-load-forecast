/** What the question panel says around the answers of the API: none of it calls the model. */

import { AskError, type Call, type Reply } from "./ask";
import type { Forecast, Gaps } from "./data";
import { monthName, of } from "./format";
import type { Mood } from "./pylon";

export interface Suggestion {
  theme: string;
  question: string;
}

function largest<T>(items: T[], size: (item: T) => number): T | undefined {
  let best: T | undefined;
  for (const item of items) if (best === undefined || size(item) > size(best)) best = item;
  return best;
}

/** Questions to start with, one per theme, about the months the data cover now. */
export function suggestions(forecast: Forecast, gaps: Gaps): Suggestion[] {
  const list: Suggestion[] = [];
  const ahead = forecast.months.filter((month) => month.month >= forecast.current_month);
  const peak = largest(ahead, (month) => month.p50);
  if (peak !== undefined) {
    list.push({
      theme: "Prévision",
      question: `Quelle consommation prévoyez-vous pour ${monthName(peak.month)} ?`,
    });
  }
  const gap = largest(gaps.months, (month) => Math.abs(month.against_forecast.gap));
  if (gap !== undefined) {
    const direction = gap.against_forecast.gap < 0 ? "basse" : "haute";
    list.push({
      theme: "Écarts",
      question: `Pourquoi la consommation ${of(monthName(gap.month))} a-t-elle été plus ${direction} que prévu ?`,
    });
  }
  list.push(
    {
      theme: "Scénarios",
      question: "Que se passerait-il lors d'un hiver froid comme il en arrive un sur dix ?",
    },
    { theme: "Méthode", question: "Comment la prévision est-elle construite ?" },
  );
  return list;
}

// Questions that stand alone and follow well from what a tool returned.
const NEXT: Record<string, string[]> = {
  forecast: [
    "La prévision à six mois est-elle fiable ?",
    "Que se passerait-il lors d'un hiver froid comme il en arrive un sur dix ?",
  ],
  month_gap: [
    "De combien augmente la consommation quand il fait un degré de moins en hiver ?",
    "Comment la prévision est-elle construite ?",
  ],
  annual_energy: [
    "Corrigée du climat, la consommation augmente-t-elle depuis 2023 ?",
    "Quel serait l'effet d'une électrification rapide sur la consommation de l'an prochain ?",
  ],
  thermosensitivity: [
    "Que se passerait-il lors d'un hiver froid comme il en arrive un sur dix ?",
    "Comment la prévision est-elle construite ?",
  ],
  accuracy: ["Comment la prévision est-elle construite ?", "D'où viennent les données utilisées ?"],
  scenario: [
    "Quel serait l'effet d'une électrification rapide sur la consommation de l'an prochain ?",
    "La prévision à six mois est-elle fiable ?",
  ],
  fact: [
    "D'où viennent les données utilisées ?",
    "Pourquoi les données en temps réel sont-elles corrigées ?",
  ],
};

/** Up to two questions to ask next, after an answer read with `tools`, not asked yet. */
export function followUps(tools: string[], asked: Set<string>): string[] {
  const next: string[] = [];
  for (const tool of tools) {
    for (const question of NEXT[tool] ?? []) {
      if (!asked.has(question) && !next.includes(question)) next.push(question);
    }
  }
  return next.slice(0, 2);
}

export interface Piece {
  text: string;
  // A number with its unit, which the panel shows in bold.
  figure: boolean;
}

// A number with its unit, with its sign if it has one, as the agent writes it.
const FIGURE = /[+−‑-]?\d+(?:,\d+)?[   ]?(?:TWh|GWh|GW|MW|°C|%)/g;
// The end of a sentence: a full stop before a capital letter.
const SENTENCE = /(?<=[.!?])\s+(?=[A-ZÀ-ÖØ-Þ«])/u;

function pieces(text: string): Piece[] {
  const list: Piece[] = [];
  let start = 0;
  for (const match of text.matchAll(FIGURE)) {
    const at = match.index ?? 0;
    if (at > start) list.push({ text: text.slice(start, at), figure: false });
    list.push({ text: match[0], figure: true });
    start = at + match[0].length;
  }
  if (start < text.length) list.push({ text: text.slice(start), figure: false });
  return list;
}

/** The answer as the panel lays it out: its first sentence, which gives the answer, then the
 * rest in paragraphs, each split so that the numbers stand out. */
export function layout(answer: string): { lead: Piece[]; paragraphs: Piece[][] } {
  const blocks = answer
    .trim()
    .split(/\n\s*\n/)
    .map((block) => block.trim())
    .filter(Boolean);
  const [first = "", ...others] = blocks;
  const [lead = "", ...rest] = first.split(SENTENCE);
  const paragraphs = [rest.join(" "), ...others].filter(Boolean);
  return { lead: pieces(lead), paragraphs: paragraphs.map(pieces) };
}

const TOPICS: Record<string, string> = {
  method: "la méthode",
  sources: "les sources des données",
  perimeter: "le périmètre des données",
  revision: "la révision des données en temps réel",
  temperature: "la publication des températures",
};
const TRAJECTORIES: Record<string, string> = {
  slow: "une décarbonation lente",
  rapid: "une décarbonation rapide",
};
const WINTERS: Record<string, string> = { cold: "un hiver froid", mild: "un hiver doux" };

export const isMonth = (value: unknown): value is string =>
  typeof value === "string" && /^\d{4}-(0[1-9]|1[0-2])$/.test(value);
const word = (value: unknown): string => (typeof value === "string" ? value : "");

/** What the agent reads with `call`, in a few words: "les écarts d'avril 2026". */
export function stepText({ tool, args }: Call): string {
  switch (tool) {
    case "forecast":
      return isMonth(args.month)
        ? `la prévision ${of(monthName(args.month))}`
        : "la prévision des mois à venir";
    case "month_gap":
      return isMonth(args.month)
        ? `les écarts ${of(monthName(args.month))}`
        : "les écarts d'un mois";
    case "annual_energy": {
      const { first, last } = args;
      if (!Number.isInteger(first) || !Number.isInteger(last)) return "l'énergie des années";
      return first === last ? `l'énergie de ${first}` : `l'énergie de ${first} à ${last}`;
    }
    case "thermosensitivity":
      return "la réponse à la température";
    case "accuracy":
      return "la fiabilité des prévisions passées";
    case "fact":
      return TOPICS[word(args.topic)] ?? "la méthode";
    case "scenario": {
      const cases = [TRAJECTORIES[word(args.trajectory)], WINTERS[word(args.winter)]].filter(
        Boolean,
      );
      const year = Number.isInteger(args.year) ? ` en ${args.year}` : "";
      return cases.length > 0
        ? `le scénario avec ${cases.join(" et ")}${year}`
        : `les scénarios${year}`;
    }
    default:
      return "les données publiées";
  }
}

// The section of the page that shows what each tool reads.
const SECTIONS: Record<string, { anchor: string; label: string }> = {
  forecast: { anchor: "headline", label: "Voir la prévision" },
  month_gap: { anchor: "gaps-title", label: "Voir les écarts" },
  annual_energy: { anchor: "history-title", label: "Voir l'historique" },
  thermosensitivity: { anchor: "temperature-title", label: "Voir la température" },
  accuracy: { anchor: "accuracy-title", label: "Voir la fiabilité" },
  scenario: { anchor: "scenarios-title", label: "Voir les scénarios" },
  fact: { anchor: "method-title", label: "Voir la méthode" },
};

/** The sections of the page where the data of an answer are drawn, once each. */
export function sections(tools: string[]): { anchor: string; label: string }[] {
  const anchors = new Set<string>();
  const list: { anchor: string; label: string }[] = [];
  for (const tool of tools) {
    const section = SECTIONS[tool];
    if (section !== undefined && !anchors.has(section.anchor)) {
      anchors.add(section.anchor);
      list.push(section);
    }
  }
  return list;
}

/** The label of an answer: checked against the data, refused, or out of the tool's scope. */
export function verdict(reply: Reply): { label: string; mood: Mood } {
  if (reply.tools.length === 0) return { label: "Hors sujet", mood: "refuse" };
  return reply.verified
    ? { label: "Vérifié", mood: "answer" }
    : { label: "Sans source", mood: "refuse" };
}

/** The mood of the pylon when a question gets no answer. */
export function moodOf(error: unknown): Mood {
  if (error instanceof DOMException && error.name === "AbortError") return "idle";
  if (error instanceof AskError && error.status === 422) return "idle";
  return "offline";
}

export interface Exchange {
  question: string;
  // The reply of the API, or what the visitor was told instead.
  reply: Reply | null;
  error: string | null;
}

// The panel keeps the last exchanges of the visit.
export const KEPT = 20;

const isReply = (value: unknown): value is Reply => {
  const reply = value as Partial<Reply> | null;
  return (
    typeof reply?.answer === "string" &&
    typeof reply.verified === "boolean" &&
    Array.isArray(reply.tools) &&
    reply.tools.every((tool) => typeof tool === "string") &&
    typeof reply.published === "string"
  );
};

/** The exchanges kept in the session, or none if what was kept cannot be read. */
export function readExchanges(saved: string | null): Exchange[] {
  if (saved === null) return [];
  try {
    const value: unknown = JSON.parse(saved);
    if (!Array.isArray(value)) return [];
    return value
      .filter(
        (item): item is Exchange =>
          typeof item?.question === "string" &&
          (item.reply === null || isReply(item.reply)) &&
          (item.error === null || typeof item.error === "string"),
      )
      .slice(-KEPT);
  } catch {
    return [];
  }
}
