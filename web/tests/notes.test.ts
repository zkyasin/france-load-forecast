import { expect, test } from "vitest";
import septemberFile from "../../notes/2026-09.json";
import { NBSP } from "../src/format";
import { credit, dates, type Note, notes, summary } from "../src/notes";

const september: Note = septemberFile;
const MINUS = String.fromCharCode(0x2212);

test("the notes of notes/ reach the page, the latest month first", () => {
  expect(notes().map((note) => note.month)).toContain("2026-09");
  const months = notes([
    { ...september, month: "2026-08" },
    september,
    { ...september, month: "2025-12" },
  ]).map((note) => note.month);
  expect(months).toEqual(["2026-09", "2026-08", "2025-12"]);
});

test("the summary gives the energy of the month and both gaps", () => {
  expect(summary(september)).toBe(
    `La consommation a atteint 31,2${NBSP}TWh, soit ${MINUS}0,23${NBSP}TWh par rapport à la ` +
      `prévision faite au début du mois et ${MINUS}0,20${NBSP}TWh par rapport à septembre 2025.`,
  );
});

test("a provisional month says so", () => {
  expect(dates(september)).toBe(
    "D'après les données publiées le 22 novembre 2026. Mois provisoire, mesuré en temps réel.",
  );
});

test("the credit names the model that wrote the reading", () => {
  expect(credit(september)).toBe(
    "Lecture rédigée par ministral-3:14b, un modèle de langue exécuté en local, à partir de ces " +
      "données, puis relue avant publication. Chaque nombre a été vérifié contre les données.",
  );
  expect(credit({ ...september, model: "groq:llama-3.3-70b-versatile" })).toMatch(
    /^Lecture rédigée par le modèle de langue llama-3\.3-70b-versatile, /,
  );
});
