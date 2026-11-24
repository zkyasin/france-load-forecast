import { expect, test } from "vitest";
import peakFile from "../../tests/fixtures/bundle/peak.json";
import type { Peak } from "../src/data";
import { NBSP } from "../src/format";
import {
  accuracyText,
  lastWinter,
  rows,
  summary,
  tableRows,
  tipText,
  winterOf,
  winterPeak,
} from "../src/peak";

const peak: Peak = peakFile;
const GW = `${NBSP}GW`;

test("a winter runs from December to February and is named by its December", () => {
  expect([winterOf("2026-12"), winterOf("2027-02"), winterOf("2026-11")]).toEqual([
    2026,
    2026,
    undefined,
  ]);
});

test("the coming winter peaks in its month with the highest median, the last one on its day", () => {
  expect(winterPeak(peak.months)).toMatchObject({
    winter: 2026,
    month: { month: "2027-01", p50: 82.09 },
  });
  expect(lastWinter(peak.history)).toMatchObject({
    winter: 2025,
    month: { month: "2026-01", peak: 90.236, day: "2026-01-06" },
  });
});

test("the summary gives the coming winter, the last one and the winter gradient", () => {
  expect(summary(peak)).toBe(
    "La pointe d'un mois est sa demi-heure de plus forte consommation. Pour l'hiver 2026-2027, " +
      `la plus haute est attendue en janvier 2027 : 82,1${GW} en prévision médiane, entre 76,8 et ` +
      `89,7${GW} dans la bande P10–P90. Pendant l'hiver 2025-2026, elle a atteint 90,2${GW} le ` +
      `6 janvier 2026. En hiver, un degré de moins la fait monter de 1,9${GW}.`,
  );
});

test("the accuracy gives the error a month ahead and the share of peaks inside the band", () => {
  expect(accuracyText(peak)).toBe(
    `Un mois à l'avance, la prévision médiane s'est trompée de 4,2${NBSP}% en moyenne sur la ` +
      `pointe, contre 5,7${NBSP}% en reprenant celle du même mois un an plus tôt. La bande ` +
      `P10–P90 a contenu 72${NBSP}% des pointes mensuelles depuis janvier 2018, pour 80${NBSP}% visés.`,
  );
});

test("a month measured in part shows its forecast and the highest day so far", () => {
  const tips = rows(peak, "2026-10").map(tipText);

  expect(tips.slice(0, 2)).toEqual([
    `octobre 2026\nMesurée : 59,0${GW}, le 23 octobre 2026, provisoire`,
    `novembre 2026\nPrévision : 73,2${GW}\nBande P10–P90 : 68,8 à 80,7${GW}\nDéjà atteinte : 68,0${GW}`,
  ]);
});

test("the table gives the band of the months to come and the day of each peak measured", () => {
  const table = tableRows(rows(peak, "2026-10"));

  expect(table.slice(0, 4)).toEqual([
    ["octobre 2026", "", "", "", "59,0 (provisoire)", "23 octobre 2026"],
    ["novembre 2026", "68,8", "73,2", "80,7", "68,0 (partielle)", ""],
    ["décembre 2026", "74,6", "79,5", "87,5", "", ""],
    ["janvier 2027", "76,8", "82,1", "89,7", "", ""],
  ]);
});
