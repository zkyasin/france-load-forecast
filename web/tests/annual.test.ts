import { expect, test } from "vitest";
import historyFile from "../../tests/fixtures/bundle/history.json";
import { againstRte, summary, tipText } from "../src/annual";
import type { History } from "../src/data";
import { NBSP } from "../src/format";

const { years }: History = historyFile;
const MINUS = String.fromCharCode(0x2212);

test("the summary gives the change corrected for the weather", () => {
  expect(summary(years)).toBe(
    `En 2025, la consommation a été de 443,9${NBSP}TWh. Corrigée de la météo, elle est passée ` +
      `de 468,6${NBSP}TWh en 2014 à 442,8${NBSP}TWh en 2025, soit ${MINUS}5,5${NBSP}%.`,
  );
});

test("the caption gives the gap to RTE's series", () => {
  expect(againstRte(years)).toBe(
    "Comme celle de RTE, la série corrigée laisse de côté le 29 février des années " +
      "bissextiles. La série de RTE, Corse et pertes comprises, s'en écarte de " +
      `0,4${NBSP}% en moyenne et de 1,1${NBSP}% au plus, en 2022.`,
  );
});

test("the tip of a year adds RTE's corrected energy", () => {
  const year = years.find((y) => y.year === 2022);
  if (year === undefined) throw new Error("no 2022");
  expect(tipText(year)).toBe(
    [
      "2022",
      `Mesurée : 450,1${NBSP}TWh`,
      `Corrigée de la météo : 449,3${NBSP}TWh`,
      `Corrigée par RTE : 454,3${NBSP}TWh`,
    ].join("\n"),
  );
});
