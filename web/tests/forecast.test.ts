import { expect, test } from "vitest";
import forecastFile from "../../tests/fixtures/bundle/forecast.json";
import historyFile from "../../tests/fixtures/bundle/history.json";
import metaFile from "../../tests/fixtures/bundle/meta.json";
import type { Forecast, History, Meta } from "../src/data";
import {
  forecastMonths,
  headline,
  lead,
  measuredMonths,
  rows,
  tableRows,
  tipText,
} from "../src/forecast";
import { addMonths } from "../src/format";

// The bundle published on 22 November 2026, also used by the Python tests.
const forecast: Forecast = forecastFile;
const history: History = historyFile;
const meta: Meta = metaFile;

test("the headline gives the total P50 of the twelve months from the current one", () => {
  expect(headline(forecast)).toBe("447\u00a0TWh de novembre 2026 à octobre 2027");
});

test("the lead gives the energy measured so far in the current month", () => {
  expect(lead(forecast, meta)).toMatch(
    /Du 1er au 21 novembre 2026, 27,6\u00a0TWh ont déjà été consommés\.$/,
  );
});

test("a month over before the forecast was published is not open", () => {
  const [october, november] = forecastMonths(forecast);
  expect(october?.open).toBe(false);
  expect(november?.open).toBe(true);
});

test("each month has one row, with what was measured and what was forecast", () => {
  const all = rows(measuredMonths(history.months, "2025-11"), forecastMonths(forecast));
  const expected = Array.from({ length: 24 }, (_, index) => addMonths("2025-11", index));
  expect(all.map((row) => row.month)).toEqual(expected);
  const october = all.find((row) => row.month === "2026-10");
  expect(october?.measured?.provisional).toBe(true);
  expect(october?.forecasted?.open).toBe(false);
});

test("the tip of a month shows only what is known about it", () => {
  const [october, november] = rows(
    measuredMonths(history.months, "2026-10"),
    forecastMonths(forecast),
  );
  if (october === undefined || november === undefined) throw new Error("rows are missing");
  expect(tipText(october)).toBe("octobre 2026\nMesuré : 34,4\u00a0TWh, provisoire");
  expect(tipText(november)).toBe(
    [
      "novembre 2026",
      "Prévision : 40,5\u00a0TWh",
      "Bande P10–P90 : 39,8 à 41,1\u00a0TWh",
      "Déjà mesuré : 27,6\u00a0TWh",
    ].join("\n"),
  );
});

test("the table gives the band of the months forecast, then the energy measured", () => {
  const [october, november] = tableRows(
    rows(measuredMonths(history.months, "2026-10"), forecastMonths(forecast)),
  );
  expect(october).toEqual(["octobre 2026", "", "", "", "34,4 (provisoire)"]);
  expect(november).toEqual(["novembre 2026", "39,8", "40,5", "41,1", "27,6 (partiel)"]);
});
