import { expect, test } from "vitest";
import modelFile from "../../tests/fixtures/bundle/model.json";
import type { Model } from "../src/data";
import { NBSP } from "../src/format";
import { fitted, signChange, summary, tipText } from "../src/temperature";

const model: Model = modelFile;
const MINUS = String.fromCharCode(0x2212);

test("one degree less stops raising consumption between 15 and 20 °C", () => {
  expect(signChange(model.thermosensitivity.by_temperature)).toEqual([15, 20]);
  expect(signChange([{ temperature: 0, gw_per_c: 2 }])).toBeUndefined();
});

test("the summary gives the winter gradient, the coldest one and where the sign changes", () => {
  expect(summary(model)).toBe(
    "En hiver, de décembre à février, un degré de moins fait monter la consommation de " +
      `2,0${NBSP}GW en moyenne sur la journée. L'effet croît avec le froid : 2,5${NBSP}GW par degré à ` +
      `${MINUS}5${NBSP}°C. Entre 15 et 20${NBSP}°C, il change de signe : au-delà, la ` +
      "consommation augmente avec la chaleur, du fait de la climatisation.",
  );
});

test("the days of the fit are told under the chart", () => {
  expect(fitted(model)).toBe(
    "Modèle estimé sur les jours du 1er octobre 2023 au 30 septembre 2026.",
  );
});

test("the tip says whether one degree less adds or removes load", () => {
  expect(tipText({ temperature: 25, gw_per_c: -0.703 })).toBe(
    `À 25${NBSP}°C, un degré de moins retire 0,7${NBSP}GW`,
  );
  expect(tipText({ temperature: 0, gw_per_c: 2.38 })).toBe(
    `À 0${NBSP}°C, un degré de moins ajoute 2,4${NBSP}GW`,
  );
});
