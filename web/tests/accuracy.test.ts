import { expect, test } from "vitest";
import accuracyFile from "../../tests/fixtures/bundle/accuracy.json";
import { coverage, replay, scores, summary } from "../src/accuracy";
import type { Accuracy } from "../src/data";

const accuracy: Accuracy = accuracyFile;

test("scores pair each method with each horizon", () => {
  const all = scores(accuracy);
  expect(all).toHaveLength(12);
  expect(all[0]).toEqual({ horizon: "1 mois", method: "Ce modèle", value: 2.956 });
});

test("the summary quotes the shortest and longest horizons and the naive forecast", () => {
  expect(summary(accuracy)).toBe(
    "L'erreur moyenne du modèle sur l'énergie d'un mois va de 3,0\u00a0% (1 mois) à " +
      "3,6\u00a0% (7 à 12 mois). Reprendre le même mois de l'année précédente, corrigé du " +
      "climat, donne une erreur de 3,6\u00a0%.",
  );
});

test("the replay of past forecasts is told under the chart", () => {
  expect(replay(accuracy)).toBe(
    "Prévisions rejouées au début de chaque mois, de janvier 2016 à septembre 2026, avec un " +
      "modèle réestimé chaque 1er janvier sur les trois années précédentes.",
  );
});

test("the coverage of the band is given since 2018 and since 2023", () => {
  expect(coverage(accuracy)).toMatch(
    /La bande P10–P90 a contenu 79\u00a0% des mois depuis janvier 2018 et 88\u00a0% depuis janvier 2023/,
  );
});
