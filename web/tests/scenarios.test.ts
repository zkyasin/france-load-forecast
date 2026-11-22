import { expect, test } from "vitest";
import scenariosFile from "../../tests/fixtures/bundle/scenarios.json";
import type { Scenarios } from "../src/data";
import { NBSP } from "../src/format";
import {
  growth,
  result,
  tipText,
  trajectoryName,
  weatherYear,
  wintersText,
} from "../src/scenarios";

const scenarios: Scenarios = scenariosFile;
const MINUS = String.fromCharCode(0x2212);

test("a trajectory is named without its note, as inside a sentence", () => {
  expect(trajectoryName(scenarios, "stagnation")).toBe("stagnation");
  expect(trajectoryName(scenarios, "rapid")).toBe("décarbonation rapide");
});

test("growth rates that repeat are grouped", () => {
  expect(growth({ "2027": 0.84, "2028": 0.84, "2029": 1.45 })).toBe(
    `+0,84${NBSP}% de 2027 à 2028, puis +1,45${NBSP}% en 2029`,
  );
});

test("the winters replay one observed year each, whose effect 29 February changes in 2028", () => {
  expect(weatherYear(scenarios, "cold")).toBe(2013);
  expect(weatherYear(scenarios, "mild")).toBe(2014);
  expect(wintersText(scenarios)).toBe(
    "Un hiver froid, qui revient environ une année sur dix, rejoue la météo de janvier, " +
      `février et décembre 2013 : il ajoute de 4,6 à 4,8${NBSP}TWh à l'énergie de l'année. Un ` +
      `hiver doux, aussi rare, rejoue celle de 2014 : il en retire 3,1${NBSP}TWh.`,
  );
});

test("a case is compared with the reference in the last year", () => {
  expect(result(scenarios, { trajectory: "rapid", winter: "cold" })).toBe(
    `En décarbonation rapide, avec un hiver froid, la consommation serait de 502,3${NBSP}TWh en ` +
      `2031, soit +59,7${NBSP}TWh par rapport à la stagnation, avec un hiver normal. Croissance ` +
      `annuelle retenue : +2,22${NBSP}% de 2027 à 2030, puis +2,61${NBSP}% en 2031.`,
  );
  expect(result(scenarios, { trajectory: "stagnation", winter: "normal" })).toBe(
    `En stagnation, avec un hiver normal, la consommation serait de 442,6${NBSP}TWh en 2031 : ` +
      "c'est la référence des autres cas. Croissance annuelle retenue : " +
      `${MINUS}0,07${NBSP}% de 2027 à 2031.`,
  );
});

test("the tip of a year gives the three trajectories for the winter chosen", () => {
  expect(tipText(scenarios, 2029, "normal")).toBe(
    [
      "2029, hiver normal",
      `Stagnation : 443,4${NBSP}TWh`,
      `Décarbonation lente : 455,6${NBSP}TWh`,
      `Décarbonation rapide : 474,6${NBSP}TWh`,
    ].join("\n"),
  );
});
