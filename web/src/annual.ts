/** The energy of each complete year, measured and corrected for the weather. */

import * as Plot from "@observablehq/plot";
import { byId, type Colors, drawIn, fillTable, frame, tipStyle } from "./chart";
import type { HistoryYear } from "./data";
import { NBSP, number, percent, signed, twh } from "./format";

const NARROW = 600;

export function summary(years: HistoryYear[]): string {
  const first = years[0];
  const last = years.at(-1);
  if (first === undefined || last === undefined) return "";
  const change = 100 * (last.corrected / first.corrected - 1);
  return (
    `En ${last.year}, la consommation a été de ${twh(last.gross)}. Corrigée de la météo, elle ` +
    `est passée de ${twh(first.corrected)} en ${first.year} à ${twh(last.corrected)} en ` +
    `${last.year}, soit ${signed(change)}${NBSP}%.`
  );
}

/** How the corrected series compares with RTE's, under the chart. */
export function againstRte(years: HistoryYear[]): string {
  if (years.length === 0) return "";
  const gaps = years.map((year) => Math.abs(year.corrected_gap_pct));
  const widest = years.reduce((worst, year) =>
    Math.abs(year.corrected_gap_pct) > Math.abs(worst.corrected_gap_pct) ? year : worst,
  );
  return (
    "Comme celle de RTE, la série corrigée laisse de côté le 29 février des années bissextiles. " +
    "La série de RTE, Corse et pertes comprises, s'en écarte de " +
    `${percent(gaps.reduce((a, b) => a + b, 0) / gaps.length)} en moyenne et de ` +
    `${percent(Math.abs(widest.corrected_gap_pct))} au plus, en ${widest.year}.`
  );
}

export const tipText = (year: HistoryYear): string =>
  [
    String(year.year),
    `Mesurée : ${twh(year.gross)}`,
    `Corrigée de la météo : ${twh(year.corrected)}`,
    `Corrigée par RTE : ${twh(year.corrected_rte)}`,
  ].join("\n");

/** Tens of TWh from below the lowest energy to above the highest. */
function extent(years: HistoryYear[]): [number, number] {
  const energies = years.flatMap((year) => [year.gross, year.corrected]);
  return [10 * Math.floor(Math.min(...energies) / 10), 10 * Math.ceil(Math.max(...energies) / 10)];
}

function plot(years: HistoryYear[], width: number, colors: Colors) {
  const all = years.map((year) => year.year);
  // On a phone, every other year is labelled, ending with the last one.
  const ticks = width < NARROW ? all.filter((_, index) => (all.length - 1 - index) % 2 === 0) : all;
  const series = { x: "year", strokeWidth: 2 };
  const dot = { x: "year", r: 4, stroke: colors.paper, strokeWidth: 2 };
  return Plot.plot({
    ...frame(width, colors),
    height: 260,
    marginLeft: 36,
    marginRight: 12,
    x: { inset: 12, ticks, tickFormat: String, tickSize: 0, label: null },
    y: {
      grid: true,
      domain: extent(years),
      ticks: 5,
      tickSize: 0,
      label: "TWh",
      labelArrow: "none",
      tickFormat: (value: number) => number(value, 0),
    },
    marks: [
      Plot.lineY(years, { ...series, y: "gross", stroke: colors.measured }),
      Plot.dot(years, { ...dot, y: "gross", fill: colors.measured }),
      Plot.lineY(years, { ...series, y: "corrected", stroke: colors.third }),
      Plot.dot(years, { ...dot, y: "corrected", symbol: "square", fill: colors.third }),
      Plot.ruleX(years, Plot.pointerX({ x: "year", stroke: colors.muted, strokeOpacity: 0.5 })),
      Plot.tip(years, Plot.pointerX({ x: "year", title: tipText, ...tipStyle(colors, width) })),
    ],
  });
}

export function render(years: HistoryYear[]): void {
  byId("history-summary").textContent = summary(years);
  byId("history-caption").textContent = againstRte(years);
  drawIn(byId("history-plot"), (width, colors) => plot(years, width, colors));
  fillTable(
    byId<HTMLTableElement>("history-table"),
    ["Année", "Mesurée", "Corrigée de la météo", "Corrigée par RTE", "Écart à RTE"],
    years.map((year) => [
      String(year.year),
      number(year.gross),
      number(year.corrected),
      number(year.corrected_rte),
      `${signed(year.corrected_gap_pct)}${NBSP}%`,
    ]),
  );
}
