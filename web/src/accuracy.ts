/** How far past forecasts were from the energy measured, by horizon. */

import * as Plot from "@observablehq/plot";
import { byId, type Colors, drawIn, fillTable, frame, tipStyle } from "./chart";
import type { Accuracy } from "./data";
import { monthName, number, percent } from "./format";

const HORIZONS: Record<string, string> = {
  "1 month": "1 mois",
  "2-3 months": "2 à 3 mois",
  "4-6 months": "4 à 6 mois",
  "7-12 months": "7 à 12 mois",
};

export const METHODS = [
  { key: "mape", label: "Ce modèle" },
  { key: "mape_naive_corrected", label: "Même mois un an plus tôt, corrigé du climat" },
  { key: "mape_naive", label: "Même mois un an plus tôt" },
] as const;

const ALL_MONTHS = "all months";

export interface Score {
  horizon: string;
  method: string;
  value: number;
}

export const horizonName = (key: string): string => HORIZONS[key] ?? key;

export const scores = (accuracy: Accuracy): Score[] =>
  METHODS.flatMap(({ key, label }) =>
    Object.entries(accuracy[key]).map(([horizon, value]) => ({
      horizon: horizonName(horizon),
      method: label,
      value,
    })),
  );

/** "de 3,6 %", or "de 3,5 à 3,6 %" when the values differ once rounded. */
function range(values: number[]): string {
  const [low, high] = [Math.min(...values), Math.max(...values)];
  return percent(low) === percent(high)
    ? `de ${percent(low)}`
    : `de ${number(low)} à ${percent(high)}`;
}

export function summary(accuracy: Accuracy): string {
  const model = Object.entries(accuracy.mape);
  const first = model[0];
  const last = model.at(-1);
  const text =
    `Le modèle a été rejoué au début de chaque mois, de ${monthName(accuracy.first_origin)} à ` +
    `${monthName(accuracy.last_origin)}, réestimé chaque 1er janvier sur les trois années ` +
    "précédentes.";
  if (first === undefined || last === undefined) return text;
  const naive = Object.values(accuracy.mape_naive_corrected);
  return (
    `${text} Son erreur moyenne sur l'énergie d'un mois va de ${percent(first[1])} ` +
    `(${horizonName(first[0])}) à ${percent(last[1])} (${horizonName(last[0])}). Reprendre le ` +
    `même mois de l'année précédente, corrigé du climat, donne une erreur ${range(naive)}.`
  );
}

export function coverage(accuracy: Accuracy): string {
  const recent = Object.entries(accuracy.mape_since_2023)[0];
  const sentences = [];
  if (recent !== undefined) {
    sentences.push(
      "Sur les prévisions faites depuis janvier 2023, l'erreur moyenne du modèle est de " +
        `${percent(recent[1])} (${horizonName(recent[0])}).`,
    );
  }
  const all = accuracy.coverage[ALL_MONTHS];
  const since2023 = accuracy.coverage_since_2023[ALL_MONTHS];
  if (all !== undefined && since2023 !== undefined) {
    sentences.push(
      `La bande P10–P90 a contenu ${percent(all, 0)} des mois depuis ` +
        `${monthName(accuracy.coverage_first_origin)} et ${percent(since2023, 0)} depuis ` +
        `janvier 2023, pour ${percent(80, 0)} visés.`,
    );
  }
  return sentences.join(" ");
}

function plot(data: Score[], width: number, colors: Colors) {
  const methods = METHODS.map((m) => m.label);
  const horizons = [...new Set(data.map((score) => score.horizon))];
  // The model is drawn last, over the naive forecasts it is close to.
  const ordered = [...data].reverse();
  return Plot.plot({
    ...frame(width, colors),
    height: 240,
    marginLeft: 32,
    marginRight: 12,
    marginBottom: 44,
    x: {
      type: "point",
      domain: horizons,
      padding: 0.4,
      label: "Horizon de la prévision",
      labelOffset: 40,
    },
    y: {
      grid: true,
      // Whole percents, from zero to above the largest error.
      domain: [0, Math.ceil(Math.max(...data.map((score) => score.value)))],
      tickSize: 0,
      label: "Erreur moyenne (%)",
      labelArrow: "none",
      tickFormat: (value: number) => number(value, 0),
    },
    color: { domain: methods, range: [colors.forecast, colors.measured, colors.third] },
    symbol: { domain: methods, range: ["circle", "square", "triangle"] },
    marks: [
      Plot.lineY(ordered, { x: "horizon", y: "value", stroke: "method", strokeWidth: 2 }),
      Plot.dot(ordered, {
        x: "horizon",
        y: "value",
        fill: "method",
        symbol: "method",
        r: 5,
        stroke: colors.paper,
        strokeWidth: 1.5,
      }),
      Plot.tip(
        data,
        Plot.pointer({
          x: "horizon",
          y: "value",
          title: (score: Score) => `${score.method}\n${score.horizon} : ${percent(score.value)}`,
          ...tipStyle(colors, width),
        }),
      ),
    ],
  });
}

export function render(accuracy: Accuracy): void {
  const data = scores(accuracy);
  byId("accuracy-summary").textContent = summary(accuracy);
  byId("accuracy-coverage").textContent = coverage(accuracy);
  drawIn(byId("accuracy-plot"), (width, colors) => plot(data, width, colors));
  const horizons = Object.keys(accuracy.mape);
  fillTable(
    byId<HTMLTableElement>("accuracy-table"),
    ["Horizon", ...METHODS.map((m) => m.label)],
    horizons.map((horizon) => [
      horizonName(horizon),
      ...METHODS.map(({ key }) => {
        const value = accuracy[key][horizon];
        return value === undefined ? "" : percent(value);
      }),
    ]),
  );
}
