import { expect, test } from "vitest";
import forecastFile from "../../tests/fixtures/bundle/forecast.json";
import gapsFile from "../../tests/fixtures/bundle/gaps.json";
import { AskError, type Reply } from "../src/ask";
import {
  followUps,
  layout,
  moodOf,
  readExchanges,
  sections,
  suggestions,
  verdict,
} from "../src/conversation";
import type { Forecast, Gaps } from "../src/data";

const forecast: Forecast = forecastFile;
const gaps: Gaps = gapsFile;
const MINUS = String.fromCharCode(0x2212);

const reply: Reply = {
  answer: "Environ 49,2 TWh en P50.",
  verified: true,
  tools: ["forecast"],
  published: "2026-11-22",
};

test("the first questions come from the months the data cover", () => {
  expect(suggestions(forecast, gaps)).toEqual([
    { theme: "Prévision", question: "Quelle consommation prévoyez-vous pour janvier 2027 ?" },
    {
      theme: "Écarts",
      question: "Pourquoi la consommation d'avril 2026 a-t-elle été plus basse que prévu ?",
    },
    {
      theme: "Scénarios",
      question: "Que se passerait-il lors d'un hiver froid comme il en arrive un sur dix ?",
    },
    { theme: "Méthode", question: "Comment la prévision est-elle construite ?" },
  ]);
});

test("follow-ups depend on what was read and skip what was asked", () => {
  expect(followUps(["forecast"], new Set())).toEqual([
    "La prévision à six mois est-elle fiable ?",
    "Que se passerait-il lors d'un hiver froid comme il en arrive un sur dix ?",
  ]);
  expect(
    followUps(["forecast", "month_gap"], new Set(["La prévision à six mois est-elle fiable ?"])),
  ).toEqual([
    "Que se passerait-il lors d'un hiver froid comme il en arrive un sur dix ?",
    "De combien augmente la consommation quand il fait un degré de moins en hiver ?",
  ]);
  expect(followUps([], new Set())).toEqual([]);
});

test("an answer leads with its first sentence and its numbers stand out", () => {
  const { lead, paragraphs } = layout(
    `Février 2026 a consommé 39,95 TWh, soit ${MINUS}1,28 TWh de moins que prévu. Il faisait ` +
      "9,09 °C contre 7,12 °C supposés.\n\nLe résiduel a pesé +1,05 TWh.",
  );

  expect(lead.filter((piece) => piece.figure).map((piece) => piece.text)).toEqual([
    "39,95 TWh",
    `${MINUS}1,28 TWh`,
  ]);
  expect(lead.map((piece) => piece.text).join("")).toBe(
    `Février 2026 a consommé 39,95 TWh, soit ${MINUS}1,28 TWh de moins que prévu.`,
  );
  expect(paragraphs.map((paragraph) => paragraph.map((piece) => piece.text).join(""))).toEqual([
    "Il faisait 9,09 °C contre 7,12 °C supposés.",
    "Le résiduel a pesé +1,05 TWh.",
  ]);
  expect(layout("Hors sujet.")).toEqual({
    lead: [{ text: "Hors sujet.", figure: false }],
    paragraphs: [],
  });
});

test("an answer points to the sections of the page it read", () => {
  expect(sections(["forecast", "forecast", "month_gap", "unknown"])).toEqual([
    { anchor: "headline", label: "Voir la prévision" },
    { anchor: "gaps-title", label: "Voir les écarts" },
  ]);
});

test("each outcome has its label and its mood", () => {
  expect(verdict(reply)).toEqual({ label: "Vérifié", mood: "answer" });
  expect(verdict({ ...reply, verified: false })).toEqual({ label: "Sans source", mood: "refuse" });
  expect(verdict({ ...reply, tools: [] })).toEqual({ label: "Hors sujet", mood: "refuse" });
  expect(moodOf(new AskError(429, "Réessayez plus tard."))).toBe("offline");
  expect(moodOf(new AskError(422, "Posez une question de 1 à 300 caractères."))).toBe("idle");
  expect(moodOf(new DOMException("stopped", "AbortError"))).toBe("idle");
  expect(moodOf(new TypeError("Failed to fetch"))).toBe("offline");
});

test("only well-formed exchanges are read back from the session", () => {
  const kept = { question: "Et janvier ?", reply, error: null };
  const saved = JSON.stringify([kept, { question: 3 }, { question: "x", reply: {}, error: null }]);

  expect(readExchanges(saved)).toEqual([kept]);
  expect(readExchanges("not json")).toEqual([]);
  expect(readExchanges(null)).toEqual([]);
  const many = Array.from({ length: 30 }, (_, i) => ({
    question: `${i}`,
    reply: null,
    error: "x",
  }));
  expect(readExchanges(JSON.stringify(many))).toHaveLength(20);
});
