import { expect, test } from "vitest";
import driversFile from "../../tests/fixtures/bundle/drivers.json";
import type { Drivers } from "../src/data";
import { bars, change, parts, summary, tableRows, tipText, title } from "../src/drivers";
import { NBSP } from "../src/format";

const drivers: Drivers = driversFile;
const MINUS = String.fromCharCode(0x2212);
const TWH = `${NBSP}TWh`;
const PCT = `${NBSP}%`;

test("the title says which way consumption moved since the base year", () => {
  expect(title(drivers)).toBe("Pourquoi la consommation a baissé depuis 2019");
  const higher = { ...drivers, now: { ...drivers.now, consumption: 470 } };
  expect(title(higher)).toBe("Pourquoi la consommation a augmenté depuis 2019");
});

test("the summary compares the last twelve months with the base year", () => {
  expect(summary(drivers)).toBe(
    "Corrigée de la météo, la consommation des douze mois de septembre 2025 à août 2026 est " +
      `inférieure de 20,5${TWH} à celle de 2019, soit ${MINUS}4,4${PCT}. Avant 2020, elle était ` +
      "stable depuis 2014.",
  );
});

test("each part gets its paragraph, with what the data can and cannot tell", () => {
  const [industry, cars, rest] = parts(drivers);

  expect(industry).toBe(
    `La grande industrie raccordée au réseau de RTE a consommé 33,9${TWH}, contre 39,4${TWH} en ` +
      `2019. Sa production a baissé de 11,1${PCT} : cela compte pour ${MINUS}4,3${TWH}, et une ` +
      `énergie par unité produite plus faible pour ${MINUS}1,1${TWH}.`,
  );
  expect(cars).toBe(
    `Les voitures rechargeables étaient 2,4${NBSP}millions en moyenne sur ces douze mois, contre ` +
      `0,2${NBSP}million en 2019. À 2,3${NBSP}MWh par voiture et par an, elles ont consommé ` +
      `5,6${TWH}, 5,2${TWH} de plus qu'en 2019. Ce chiffre est calé sur l'estimation de RTE pour ` +
      `2025, 4,9${TWH}.`,
  );
  expect(rest).toBe(
    `Le reste, ménages, entreprises et services, a perdu 20,2${TWH} (${MINUS}4,7${PCT}). Il a ` +
      "touché son plus bas en 2023. Les données publiques ne permettent pas d'y séparer les prix, " +
      "la sobriété, l'efficacité énergétique et les pompes à chaleur. Corrigé de l'inflation, le " +
      `prix de l'électricité payé par les ménages était au plus haut en 2024 : +33,1${PCT} par ` +
      `rapport à 2019, contre +12,4${PCT} sur ces douze mois.`,
  );
});

test("the parts add up to the change, drawn last", () => {
  const drawn = bars(drivers);
  const total = drawn.at(-1);
  const sum = drawn.filter((bar) => !bar.total).reduce((all, bar) => all + bar.value, 0);

  expect(drawn.map((bar) => bar.label)).toEqual([
    "Industrie : production",
    "Industrie : intensité",
    "Voitures électriques",
    "Reste",
    "Total",
  ]);
  expect(total?.value).toBeCloseTo(change(drivers), 3);
  expect(sum).toBeCloseTo(change(drivers), 2);
  expect(drawn.map(tipText)[2]).toBe(
    `Voitures rechargeables, estimées d'après leur nombre\n+5,2${TWH}`,
  );
});

test("the table gives each whole year, then the last twelve months", () => {
  const rows = tableRows(drivers);

  expect(rows[0]).toEqual(["2018", "470,6", "40,6", "0,2", "429,8"]);
  expect(rows.at(-1)).toEqual(["Douze mois jusqu'à août 2026", "447,0", "33,9", "5,6", "407,4"]);
  expect(rows).toHaveLength(drivers.years.length + 1);
});
