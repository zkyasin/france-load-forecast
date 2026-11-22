/** The forecast of the next twelve months, against the months measured before. */

import * as Plot from "@observablehq/plot";
import { byId, type Colors, drawIn, fillTable, frame, tipStyle } from "./chart";
import { archivedForecast, type Bundle, type Forecast, type HistoryMonth, type Meta } from "./data";
import { addMonths, dayName, monthDate, monthName, monthTick, number, twh } from "./format";

/** Months measured before the current one, on wide and on narrow screens. */
const MONTHS_BEFORE = { wide: 24, narrow: 12 };
const NARROW = 600;

export interface Measured {
  date: Date;
  month: string;
  energy: number;
  provisional: boolean;
}

export interface Forecasted {
  date: Date;
  month: string;
  p10: number;
  p50: number;
  p90: number;
  measured: number;
  // Days of the month were still to come when the forecast was published.
  open: boolean;
}

/** All the chart says about one month. */
export interface Row {
  date: Date;
  month: string;
  measured?: Measured;
  forecasted?: Forecasted;
}

export const measuredMonths = (months: HistoryMonth[], from: string): Measured[] =>
  months.filter((m) => m.month >= from).map((m) => ({ ...m, date: monthDate(m.month) }));

export const forecastMonths = (forecast: Forecast): Forecasted[] =>
  forecast.months.map((m) => ({
    date: monthDate(m.month),
    month: m.month,
    p10: m.p10,
    p50: m.p50,
    p90: m.p90,
    measured: m.measured,
    open: m.p90 > m.p10,
  }));

export function rows(measured: Measured[], forecasted: Forecasted[]): Row[] {
  const byMonth = new Map<string, Row>();
  for (const m of measured) byMonth.set(m.month, { date: m.date, month: m.month, measured: m });
  for (const f of forecasted) {
    const row = byMonth.get(f.month) ?? { date: f.date, month: f.month };
    byMonth.set(f.month, { ...row, forecasted: f });
  }
  return [...byMonth.values()].sort((a, b) => a.date.getTime() - b.date.getTime());
}

/** The text of the tip on a month. */
export function tipText(row: Row): string {
  const { measured, forecasted } = row;
  const lines = [monthName(row.month)];
  if (measured) {
    lines.push(`Mesuré : ${twh(measured.energy)}${measured.provisional ? ", provisoire" : ""}`);
  }
  if (forecasted?.open) {
    lines.push(
      `Prévision : ${twh(forecasted.p50)}`,
      `Bande P10–P90 : ${number(forecasted.p10)} à ${twh(forecasted.p90)}`,
    );
    if (!measured && forecasted.measured > 0) {
      lines.push(`Déjà mesuré : ${twh(forecasted.measured)}`);
    }
  }
  return lines.join("\n");
}

/** "447 TWh de novembre 2026 à octobre 2027". */
export function headline(forecast: Forecast): string {
  const last = forecast.months.at(-1)?.month ?? forecast.current_month;
  return `${twh(forecast.total_p50, 0)} de ${monthName(forecast.current_month)} à ${monthName(last)}`;
}

export function lead(forecast: Forecast, meta: Meta): string {
  const text =
    "C'est la consommation d'électricité attendue en France continentale, hors Corse, sur ces " +
    "douze mois : la somme des prévisions médianes de chaque mois.";
  const current = forecast.months.find((m) => m.month === forecast.current_month);
  if (current === undefined || current.measured === 0) return text;
  return `${text} Du 1er au ${dayName(meta.measured_until)}, ${twh(current.measured)} ont déjà été consommés.`;
}

function plot(history: HistoryMonth[], forecast: Forecast, width: number, colors: Colors) {
  const narrow = width < NARROW;
  const before = narrow ? MONTHS_BEFORE.narrow : MONTHS_BEFORE.wide;
  const measured = measuredMonths(history, addMonths(forecast.current_month, -before));
  const forecasted = forecastMonths(forecast);
  const months = rows(measured, forecasted);
  const dot = { x: "date", r: 4, stroke: colors.paper, strokeWidth: 2 };
  return Plot.plot({
    ...frame(width, colors),
    height: narrow ? 300 : 380,
    marginLeft: 32,
    marginRight: 12,
    marginBottom: 40,
    x: { type: "utc", ticks: narrow ? "6 months" : "3 months", tickFormat: monthTick, label: null },
    y: {
      grid: true,
      nice: true,
      ticks: 5,
      tickSize: 0,
      label: "TWh",
      labelArrow: "none",
      tickFormat: (value: number) => number(value, 0),
    },
    marks: [
      Plot.areaY(forecasted, {
        x: "date",
        y1: "p10",
        y2: "p90",
        fill: colors.forecast,
        fillOpacity: 0.2,
      }),
      // Dashed and without dots, so that it is told from the measured line without its color.
      Plot.lineY(forecasted, {
        x: "date",
        y: "p50",
        stroke: colors.forecast,
        strokeWidth: 2,
        strokeDasharray: "4,5",
      }),
      Plot.lineY(measured, { x: "date", y: "energy", stroke: colors.measured, strokeWidth: 2 }),
      Plot.dot(
        measured.filter((m) => !m.provisional),
        { ...dot, y: "energy", fill: colors.measured },
      ),
      // Provisional months are hollow.
      Plot.dot(
        measured.filter((m) => m.provisional),
        { ...dot, y: "energy", r: 3.5, fill: colors.paper, stroke: colors.measured },
      ),
      Plot.ruleX(months, Plot.pointerX({ x: "date", stroke: colors.muted, strokeOpacity: 0.5 })),
      Plot.tip(
        months,
        Plot.pointerX({
          x: "date",
          title: tipText,
          ...tipStyle(colors, width),
        }),
      ),
    ],
  });
}

function caption(shown: Forecast, meta: Meta): string {
  if (shown.published !== meta.published) {
    return (
      `Énergie mensuelle en TWh. Prévision publiée le ${dayName(shown.published)}, ` +
      `mesures publiées le ${dayName(meta.published)}.`
    );
  }
  return (
    `Énergie mensuelle en TWh. Données consolidées jusqu'au ${dayName(meta.consolidated_until)}, ` +
    `puis temps réel jusqu'au ${dayName(meta.measured_until)} ; températures jusqu'au ` +
    `${dayName(meta.temperature_until)}.`
  );
}

function measuredText({ measured, forecasted }: Row): string {
  if (measured) {
    return `${number(measured.energy)}${measured.provisional ? " (provisoire)" : ""}`;
  }
  if (forecasted?.open && forecasted.measured > 0) {
    return `${number(forecasted.measured)} (partiel)`;
  }
  return "";
}

/** The table of the chart: the band of the months forecast, then the energy measured. */
export const tableRows = (months: Row[]): string[][] =>
  months.map((row) => {
    const { forecasted } = row;
    const band = forecasted?.open
      ? [number(forecasted.p10), number(forecasted.p50), number(forecasted.p90)]
      : ["", "", ""];
    return [monthName(row.month), ...band, measuredText(row)];
  });

function showTable(table: HTMLTableElement, history: HistoryMonth[], forecast: Forecast): void {
  const from = addMonths(forecast.current_month, -MONTHS_BEFORE.wide);
  const months = rows(measuredMonths(history, from), forecastMonths(forecast));
  fillTable(table, ["Mois", "P10", "P50", "P90", "Mesuré"], tableRows(months));
}

/** Fills the forecast section with the latest forecast, or one of `days` chosen in the archive. */
export function render(bundle: Bundle, days: string[]): void {
  const { meta, forecast, history } = bundle;
  byId("headline").textContent = headline(forecast);
  byId("lead").textContent = lead(forecast, meta);

  let shown = forecast;
  const redraw = drawIn(byId("forecast-plot"), (width, colors) =>
    plot(history.months, shown, width, colors),
  );
  const table = byId<HTMLTableElement>("forecast-table");
  const show = (chosen: Forecast) => {
    shown = chosen;
    redraw();
    byId("forecast-caption").textContent = caption(shown, meta);
    showTable(table, history.months, shown);
  };
  show(forecast);

  if (days.length < 2) return;
  const select = byId<HTMLSelectElement>("publication");
  for (const day of [...days].reverse()) select.add(new Option(dayName(day), day));
  select.value = meta.published;
  byId("archive").hidden = false;
  select.addEventListener("change", () => {
    const day = select.value;
    if (day === meta.published) return show(forecast);
    // Another date may have been chosen while this one was loading: its answer is then ignored.
    archivedForecast(day).then(
      (chosen) => {
        if (select.value === day) show(chosen);
      },
      () => {
        if (select.value !== day) return;
        select.value = shown.published;
        byId("forecast-caption").textContent =
          `La prévision du ${dayName(day)} n'a pas pu être chargée. ${caption(shown, meta)}`;
      },
    );
  });
}
