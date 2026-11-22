import { expect, test } from "vitest";
import gapsFile from "../../tests/fixtures/bundle/gaps.json";
import type { Gaps } from "../src/data";
import { NBSP } from "../src/format";
import { monthGaps, shownTerms, summary, tipText } from "../src/gaps";

const gaps: Gaps = gapsFile;
const MINUS = String.fromCharCode(0x2212);

test("other effects are what the weather and the calendar leave of the gap", () => {
  const [october] = monthGaps(gaps, "against_year_before");
  expect(october?.others).toBeCloseTo(0.749 - 0.687 + 0.003, 9);
});

test("the calendar is left out against the forecast, which knew it", () => {
  const keys = (view: "against_forecast" | "against_year_before") =>
    shownTerms(monthGaps(gaps, view)).map((term) => term.key);
  expect(keys("against_forecast")).toEqual(["climate", "others"]);
  expect(keys("against_year_before")).toEqual(["climate", "calendar", "others"]);
});

test("against the year before, the summary splits the change of the twelve months", () => {
  expect(summary(monthGaps(gaps, "against_year_before"), "against_year_before")).toBe(
    `D'octobre 2025 à septembre 2026, la consommation a atteint 446,6${NBSP}TWh, soit ` +
      `+2,9${NBSP}TWh par rapport à la même période un an plus tôt : ${MINUS}1,6${NBSP}TWh dus ` +
      `à la météo, +0,1${NBSP}TWh au calendrier et +4,5${NBSP}TWh aux autres effets. Les ` +
      "données de septembre 2026 sont encore provisoires.",
  );
});

test("against the forecast, the summary compares the mean size of the terms", () => {
  expect(summary(monthGaps(gaps, "against_forecast"), "against_forecast")).toBe(
    "D'octobre 2025 à septembre 2026, la prévision faite au début de chaque mois s'est écartée " +
      `de la consommation de 1,2${NBSP}TWh en moyenne, dans un sens ou dans l'autre. L'effet de ` +
      `la météo a été de 0,9${NBSP}TWh en moyenne, celui des autres effets de 0,6${NBSP}TWh : la ` +
      "météo du mois est la première source d'écart. Les données de septembre 2026 sont encore " +
      "provisoires.",
  );
});

test("the tip of a month gives its gap, its terms and its temperatures", () => {
  const months = monthGaps(gaps, "against_year_before");
  const september = months.at(-1);
  if (september === undefined) throw new Error("no month");
  expect(tipText(september, "against_year_before", shownTerms(months))).toBe(
    [
      "septembre 2026, provisoire",
      `Mesuré : 31,2${NBSP}TWh`,
      `Un an plus tôt : 31,4${NBSP}TWh`,
      `Écart : ${MINUS}0,2${NBSP}TWh`,
      `Météo : ${MINUS}0,1${NBSP}TWh`,
      `Calendrier : 0,0${NBSP}TWh`,
      `Autres effets : ${MINUS}0,1${NBSP}TWh`,
      `Température : 19,9${NBSP}°C (un an plus tôt : 16,6${NBSP}°C)`,
    ].join("\n"),
  );
});
