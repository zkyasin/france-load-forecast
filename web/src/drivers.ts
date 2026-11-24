/** What changed climate-corrected consumption between the base year and the last twelve months:
 * large industry, electric cars and the rest. */

import * as Plot from "@observablehq/plot";
import { byId, type Colors, drawIn, fillTable, frame, tipStyle } from "./chart";
import type { DriverPeriod, Drivers } from "./data";
import { monthName, NBSP, number, of, signed, signedTick, twh } from "./format";

const NARROW = 600;

/** The change of consumption from the base year to the last twelve months, in TWh. */
export const change = (drivers: Drivers): number =>
  drivers.now.consumption - drivers.base.consumption;

const growth = (now: number, base: number): number => 100 * (now / base - 1);
const signedPercent = (value: number): string => `${signed(value)}${NBSP}%`;
const signedTwh = (value: number): string => `${signed(value)}${NBSP}TWh`;
const millions = (value: number): string =>
  `${number(value)}${NBSP}${value >= 2 ? "millions" : "million"}`;

export const title = (drivers: Drivers): string =>
  `Pourquoi la consommation a ${change(drivers) < 0 ? "baissé" : "augmenté"} depuis ${drivers.base_year}`;

/** "de septembre 2025 à août 2026": the twelve months compared with the base year. */
const months = (drivers: Drivers): string =>
  `${of(monthName(drivers.first_month))} à ${monthName(drivers.last_month)}`;

export function summary(drivers: Drivers): string {
  const delta = change(drivers);
  const { base, now, base_year: year } = drivers;
  return (
    `Corrigée de la météo, la consommation des douze mois ${months(drivers)} est ` +
    `${delta < 0 ? "inférieure" : "supérieure"} de ${twh(Math.abs(delta))} à celle de ${year}, ` +
    `soit ${signedPercent(growth(now.consumption, base.consumption))}. Avant 2020, elle était ` +
    "stable depuis 2014."
  );
}

/** What each part did, a paragraph each. */
export function parts(drivers: Drivers): string[] {
  const { base, now, contributions, cars, base_year: year } = drivers;
  const production = now.activity_index - 100;
  const industry =
    `La grande industrie raccordée au réseau de RTE a consommé ${twh(now.industry)}, contre ` +
    `${twh(base.industry)} en ${year}. Sa production a ${production < 0 ? "baissé" : "augmenté"} ` +
    `de ${number(Math.abs(production))}${NBSP}% : cela compte pour ` +
    `${signedTwh(contributions.industry_activity)}, et une énergie par unité produite ` +
    `${contributions.industry_intensity < 0 ? "plus faible" : "plus forte"} pour ` +
    `${signedTwh(contributions.industry_intensity)}.`;
  const added = contributions.electric_cars;
  const electric =
    `Les voitures rechargeables étaient ${millions(now.cars_millions)} en moyenne sur ces douze ` +
    `mois, contre ${millions(base.cars_millions)} en ${year}. À ${number(cars.mwh_per_car)}${NBSP}` +
    `MWh par voiture et par an, elles ont consommé ${twh(now.electric_cars)}, ` +
    `${twh(Math.abs(added))} de ${added < 0 ? "moins" : "plus"} qu'en ${year}. Ce chiffre est ` +
    `calé sur l'estimation de RTE pour ${cars.reference_year}, ${twh(cars.reference_twh)}.`;
  const lowest = drivers.years.reduce((low, next) => (next.rest < low.rest ? next : low));
  const dearest = drivers.years.reduce((high, next) =>
    next.real_price_index > high.real_price_index ? next : high,
  );
  const rest =
    `Le reste, ménages, entreprises et services, a ${contributions.rest < 0 ? "perdu" : "gagné"} ` +
    `${twh(Math.abs(contributions.rest))} (${signedPercent(growth(now.rest, base.rest))}). Il a ` +
    `touché son plus bas en ${lowest.year}. Les données publiques ne permettent pas d'y séparer ` +
    "les prix, la sobriété, l'efficacité énergétique et les pompes à chaleur. Corrigé de " +
    "l'inflation, le prix de l'électricité payé par les ménages était au plus haut en " +
    `${dearest.year} : ${signedPercent(dearest.real_price_index - 100)} par rapport à ${year}, ` +
    `contre ${signedPercent(now.real_price_index - 100)} sur ces douze mois.`;
  return [industry, electric, rest];
}

/** A bar of the chart: a part of the change, or the change itself. */
export interface Bar {
  label: string;
  detail: string;
  value: number;
  total: boolean;
}

export function bars(drivers: Drivers): Bar[] {
  const { contributions } = drivers;
  const part = (label: string, detail: string, value: number): Bar => ({
    label,
    detail,
    value,
    total: false,
  });
  return [
    part(
      "Industrie : production",
      "Grande industrie, effet de sa production",
      contributions.industry_activity,
    ),
    part(
      "Industrie : intensité",
      "Grande industrie, effet de son énergie par unité produite",
      contributions.industry_intensity,
    ),
    part(
      "Voitures électriques",
      "Voitures rechargeables, estimées d'après leur nombre",
      contributions.electric_cars,
    ),
    part("Reste", "Ménages, entreprises et services", contributions.rest),
    {
      label: "Total",
      detail: "Consommation corrigée de la météo",
      value: change(drivers),
      total: true,
    },
  ];
}

export const tipText = (bar: Bar): string => `${bar.detail}\n${signedTwh(bar.value)}`;

function plot(drivers: Drivers, width: number, colors: Colors) {
  const narrow = width < NARROW;
  const data = bars(drivers);
  const value = { x: () => 0, y: "label", text: (bar: Bar) => signed(bar.value), fill: colors.ink };
  return Plot.plot({
    ...frame(width, colors),
    height: 40 * data.length + 40,
    marginLeft: narrow ? 136 : 168,
    marginRight: 12,
    marginBottom: 36,
    x: {
      grid: true,
      nice: true,
      ticks: narrow ? 4 : 6,
      tickSize: 0,
      label: "TWh",
      labelArrow: "none",
      tickFormat: signedTick,
    },
    y: { domain: data.map((bar) => bar.label), tickSize: 0, padding: 0.3, label: null },
    marks: [
      Plot.barX(
        data.filter((bar) => !bar.total),
        { x: "value", y: "label", fill: colors.third },
      ),
      Plot.barX(
        data.filter((bar) => bar.total),
        { x: "value", y: "label", fill: colors.ink },
      ),
      Plot.ruleX([0], { stroke: colors.ink, strokeOpacity: 0.6 }),
      // Each value stands on the other side of zero from its bar, where there is room for it.
      Plot.text(
        data.filter((bar) => bar.value < 0),
        { ...value, dx: 6, textAnchor: "start" },
      ),
      Plot.text(
        data.filter((bar) => bar.value >= 0),
        { ...value, dx: -6, textAnchor: "end" },
      ),
      Plot.tip(
        data,
        Plot.pointerY({ x: "value", y: "label", title: tipText, ...tipStyle(colors, width) }),
      ),
    ],
  });
}

const values = (period: DriverPeriod): string[] =>
  [period.consumption, period.industry, period.electric_cars, period.rest].map((v) => number(v));

/** Each whole year, then the last twelve months. */
export const tableRows = (drivers: Drivers): string[][] => [
  ...drivers.years.map((year) => [String(year.year), ...values(year)]),
  [`Douze mois jusqu'à ${monthName(drivers.last_month)}`, ...values(drivers.now)],
];

/** Shows the section, which the page keeps hidden for bundles published without it. */
export function render(drivers: Drivers | null): void {
  if (drivers === null) return;
  byId("drivers").hidden = false;
  byId("drivers-nav").hidden = false;
  byId("drivers-title").textContent = title(drivers);
  byId("drivers-summary").textContent = summary(drivers);
  byId("drivers-parts").replaceChildren(
    ...parts(drivers).map((text) => {
      const paragraph = document.createElement("p");
      paragraph.textContent = text;
      return paragraph;
    }),
  );
  byId("drivers-caption").textContent =
    `Variation de la consommation corrigée de la météo entre ${drivers.base_year} et les douze ` +
    `mois ${months(drivers)}, en TWh, par partie. Les parties s'additionnent au total.`;
  drawIn(byId("drivers-plot"), (width, colors) => plot(drivers, width, colors));
  fillTable(
    byId<HTMLTableElement>("drivers-table"),
    ["Période", "Consommation", "Grande industrie", "Voitures électriques", "Reste"],
    tableRows(drivers),
  );
}
