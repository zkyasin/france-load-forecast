/** The peak of each month, its highest half-hour: measured, then forecast with its band. */

import * as Plot from "@observablehq/plot";
import { byId, type Colors, drawIn, fillTable, frame, tipStyle } from "./chart";
import type { ForecastMonth, MeasuredPeak, Peak } from "./data";
import {
  addMonths,
  dayName,
  monthDate,
  monthName,
  monthTick,
  NBSP,
  number,
  percent,
} from "./format";

/** Months measured before the current one, on wide and on narrow screens. */
const MONTHS_BEFORE = { wide: 24, narrow: 12 };
const NARROW = 600;

export const gw = (value: number, digits = 1): string => `${number(value, digits)}${NBSP}GW`;

/** The winter of a month, named by the year of its December; undefined from March to November. */
export function winterOf(month: string): number | undefined {
  const year = Number(month.slice(0, 4));
  const index = Number(month.slice(5, 7));
  if (index === 12) return year;
  return index <= 2 ? year - 1 : undefined;
}

const winterName = (winter: number): string => `${winter}-${winter + 1}`;

/** The month of the first winter of the forecast with the highest P50. */
export function winterPeak(
  months: ForecastMonth[],
): { winter: number; month: ForecastMonth } | undefined {
  const winter = months.map((month) => winterOf(month.month)).find((w) => w !== undefined);
  const candidates = months.filter((month) => winterOf(month.month) === winter);
  if (winter === undefined || candidates.length === 0) return undefined;
  const month = candidates.reduce((best, next) => (next.p50 > best.p50 ? next : best));
  return { winter, month };
}

/** The highest month of the last winter measured in full. */
export function lastWinter(
  history: MeasuredPeak[],
): { winter: number; month: MeasuredPeak } | undefined {
  const byWinter = new Map<number, MeasuredPeak[]>();
  for (const month of history) {
    const winter = winterOf(month.month);
    if (winter !== undefined) byWinter.set(winter, [...(byWinter.get(winter) ?? []), month]);
  }
  const whole = [...byWinter].filter(([, months]) => months.length === 3).at(-1);
  if (whole === undefined) return undefined;
  const [winter, months] = whole;
  return { winter, month: months.reduce((best, next) => (next.peak > best.peak ? next : best)) };
}

export function summary(peak: Peak): string {
  const sentences = ["La pointe d'un mois est sa demi-heure de plus forte consommation."];
  const coming = winterPeak(peak.months);
  if (coming !== undefined) {
    const { winter, month } = coming;
    sentences.push(
      `Pour l'hiver ${winterName(winter)}, la plus haute est attendue en ${monthName(month.month)} : ` +
        `${gw(month.p50)} en prévision médiane, entre ${number(month.p10)} et ${gw(month.p90)} ` +
        "dans la bande P10–P90.",
    );
  }
  const last = lastWinter(peak.history);
  if (last !== undefined) {
    sentences.push(
      `Pendant l'hiver ${winterName(last.winter)}, elle a atteint ${gw(last.month.peak)} le ` +
        `${dayName(last.month.day)}.`,
    );
  }
  sentences.push(`En hiver, un degré de moins la fait monter de ${gw(peak.winter_gw_per_c)}.`);
  return sentences.join(" ");
}

export function accuracyText(peak: Peak): string {
  const { mape, mape_naive, coverage, coverage_first_origin } = peak.accuracy;
  const model = mape["1 month"];
  const naive = mape_naive["1 month"];
  const all = coverage["all months"];
  const sentences = [];
  if (model !== undefined && naive !== undefined) {
    sentences.push(
      `Un mois à l'avance, la prévision médiane s'est trompée de ${percent(model)} en moyenne ` +
        `sur la pointe, contre ${percent(naive)} en reprenant celle du même mois un an plus tôt.`,
    );
  }
  if (all !== undefined) {
    sentences.push(
      `La bande P10–P90 a contenu ${percent(all, 0)} des pointes mensuelles depuis ` +
        `${monthName(coverage_first_origin)}, pour ${percent(80, 0)} visés.`,
    );
  }
  return sentences.join(" ");
}

/** All the chart says about one month. */
export interface Row {
  date: Date;
  month: string;
  measured?: MeasuredPeak;
  forecasted?: ForecastMonth;
}

/** The months measured from `from` and the months forecast, one row per month. */
export function rows(peak: Peak, from: string): Row[] {
  const byMonth = new Map<string, Row>();
  for (const measured of peak.history.filter((m) => m.month >= from)) {
    byMonth.set(measured.month, {
      date: monthDate(measured.month),
      month: measured.month,
      measured,
    });
  }
  for (const forecasted of peak.months) {
    const row = byMonth.get(forecasted.month) ?? {
      date: monthDate(forecasted.month),
      month: forecasted.month,
    };
    byMonth.set(forecasted.month, { ...row, forecasted });
  }
  return [...byMonth.values()].sort((a, b) => a.date.getTime() - b.date.getTime());
}

/** Whether days of a forecast month were still to come when it was published. */
const open = (month: ForecastMonth): boolean => month.p90 > month.p10;

/** The text of the tip on a month. */
export function tipText({ month, measured, forecasted }: Row): string {
  const lines = [monthName(month)];
  if (measured) {
    lines.push(
      `Mesurée : ${gw(measured.peak)}, le ${dayName(measured.day)}` +
        `${measured.provisional ? ", provisoire" : ""}`,
    );
  }
  if (forecasted && open(forecasted)) {
    lines.push(
      `Prévision : ${gw(forecasted.p50)}`,
      `Bande P10–P90 : ${number(forecasted.p10)} à ${gw(forecasted.p90)}`,
    );
    if (!measured && forecasted.measured > 0) {
      lines.push(`Déjà atteinte : ${gw(forecasted.measured)}`);
    }
  }
  return lines.join("\n");
}

/** The table of the chart: the band of the months forecast, then the peak measured and its day. */
export const tableRows = (months: Row[]): string[][] =>
  months.map(({ month, measured, forecasted }) => {
    const band =
      forecasted && open(forecasted)
        ? [number(forecasted.p10), number(forecasted.p50), number(forecasted.p90)]
        : ["", "", ""];
    let peak = "";
    if (measured) {
      peak = `${number(measured.peak)}${measured.provisional ? " (provisoire)" : ""}`;
    } else if (forecasted && open(forecasted) && forecasted.measured > 0) {
      peak = `${number(forecasted.measured)} (partielle)`;
    }
    return [monthName(month), ...band, peak, measured ? dayName(measured.day) : ""];
  });

function plot(peak: Peak, width: number, colors: Colors) {
  const narrow = width < NARROW;
  const before = narrow ? MONTHS_BEFORE.narrow : MONTHS_BEFORE.wide;
  const months = rows(peak, addMonths(peak.current_month, -before));
  const measured = months.flatMap((row) =>
    row.measured ? [{ ...row.measured, date: row.date }] : [],
  );
  const forecasted = peak.months.map((month) => ({ ...month, date: monthDate(month.month) }));
  const dot = { x: "date", y: "peak", r: 4, stroke: colors.paper, strokeWidth: 2 };
  return Plot.plot({
    ...frame(width, colors),
    height: narrow ? 280 : 340,
    marginLeft: 32,
    marginRight: 12,
    marginBottom: 40,
    x: { type: "utc", ticks: narrow ? "6 months" : "3 months", tickFormat: monthTick, label: null },
    y: {
      grid: true,
      nice: true,
      ticks: 5,
      tickSize: 0,
      label: "GW",
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
      Plot.lineY(measured, { x: "date", y: "peak", stroke: colors.measured, strokeWidth: 2 }),
      Plot.dot(
        measured.filter((m) => !m.provisional),
        { ...dot, fill: colors.measured },
      ),
      // Provisional months are hollow.
      Plot.dot(
        measured.filter((m) => m.provisional),
        { ...dot, r: 3.5, fill: colors.paper, stroke: colors.measured },
      ),
      Plot.ruleX(months, Plot.pointerX({ x: "date", stroke: colors.muted, strokeOpacity: 0.5 })),
      Plot.tip(months, Plot.pointerX({ x: "date", title: tipText, ...tipStyle(colors, width) })),
    ],
  });
}

/** Shows the peak section, which the page keeps hidden for bundles published without it. */
export function render(peak: Peak | null): void {
  if (peak === null) return;
  byId("peak").hidden = false;
  byId("peak-nav").hidden = false;
  byId("peak-summary").textContent = summary(peak);
  byId("peak-accuracy").textContent = accuracyText(peak);
  drawIn(byId("peak-plot"), (width, colors) => plot(peak, width, colors));
  fillTable(
    byId<HTMLTableElement>("peak-table"),
    ["Mois", "P10", "P50", "P90", "Mesurée", "Jour de la pointe"],
    tableRows(rows(peak, addMonths(peak.current_month, -MONTHS_BEFORE.wide))),
  );
}
