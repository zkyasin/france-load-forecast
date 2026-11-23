/** The small chart of an answer: the band of the month a forecast read, or the terms of a gap. */

import * as Plot from "@observablehq/plot";
import { type Colors, frame } from "./chart";
import type { Focus } from "./conversation";
import type { Forecast, Gaps } from "./data";
import { addMonths, monthName, NBSP, number, of, signed, twh } from "./format";
import { monthGaps, type View } from "./gaps";

export interface Figure {
  chart: Element;
  caption: string;
}

function band(forecast: Forecast, month: string, width: number, colors: Colors): Figure | null {
  const row = forecast.months.find((entry) => entry.month === month);
  if (row === undefined) return null;
  const pad = (row.p90 - row.p10) * 0.2;
  const at = { y: () => "band" };
  const chart = Plot.plot({
    ...frame(width, colors),
    height: 64,
    marginTop: 22,
    marginBottom: 22,
    marginLeft: 16,
    marginRight: 16,
    x: { domain: [row.p10 - pad, row.p90 + pad], axis: null },
    y: { domain: ["band"], axis: null },
    marks: [
      Plot.barX([row], { ...at, x1: "p10", x2: "p90", fill: colors.forecast, fillOpacity: 0.25 }),
      Plot.tickX([row], { ...at, x: "p50", stroke: colors.forecast, strokeWidth: 3 }),
      Plot.text([row], {
        ...at,
        x: "p50",
        text: (entry) => twh(entry.p50),
        dy: -20,
        fill: colors.ink,
        fontWeight: 700,
      }),
      Plot.text([row], { ...at, x: "p10", text: (entry) => number(entry.p10), dy: 19 }),
      Plot.text([row], { ...at, x: "p90", text: (entry) => number(entry.p90), dy: 19 }),
    ],
  });
  return {
    chart,
    caption: `Prévision ${of(monthName(month))} : la médiane, et la bande P10–P90 en TWh.`,
  };
}

const TERMS = [
  ["climate", "Météo"],
  ["calendar", "Calendrier"],
  ["others", "Autres effets"],
] as const;

function terms(
  gaps: Gaps,
  month: string,
  view: View,
  width: number,
  colors: Colors,
): Figure | null {
  const entry = monthGaps(gaps, view).find((gap) => gap.month === month);
  if (entry === undefined) return null;
  const fills = { climate: colors.measured, calendar: colors.third, others: colors.fourth };
  // The calendar was known when the forecast was made: against it, the term is always zero.
  const rows = TERMS.filter(([key]) => view === "against_year_before" || key !== "calendar").map(
    ([key, label]) => ({ label, value: entry[key], fill: fills[key] }),
  );
  const reach = Math.max(0.1, ...rows.map((row) => Math.abs(row.value)));
  const chart = Plot.plot({
    ...frame(width, colors),
    height: 24 * rows.length + 8,
    marginTop: 4,
    marginBottom: 4,
    marginLeft: 96,
    marginRight: 44,
    // Room past the longest bar for its value.
    x: { domain: [-reach * 1.45, reach * 1.45], axis: null },
    y: { domain: rows.map((row) => row.label), label: null, tickSize: 0 },
    color: { type: "identity" },
    marks: [
      Plot.barX(rows, { x: "value", y: "label", fill: "fill", insetTop: 4, insetBottom: 4 }),
      Plot.ruleX([0], { stroke: colors.ink, strokeOpacity: 0.6 }),
      Plot.text(
        rows.filter((row) => row.value >= 0),
        { x: "value", y: "label", text: (row) => signed(row.value), textAnchor: "start", dx: 4 },
      ),
      Plot.text(
        rows.filter((row) => row.value < 0),
        { x: "value", y: "label", text: (row) => signed(row.value), textAnchor: "end", dx: -4 },
      ),
    ],
  });
  const reference =
    view === "against_forecast" ? "à la prévision" : `à ${monthName(addMonths(month, -12))}`;
  return {
    chart,
    caption: `Écart ${of(monthName(month))} ${reference} : ${signed(entry.gap)}${NBSP}TWh, par effet.`,
  };
}

/** The chart of the month an answer read, if the page has its data. */
export function figure(
  focus: Focus,
  forecast: Forecast,
  gaps: Gaps,
  width: number,
  colors: Colors,
): Figure | null {
  return focus.kind === "forecast"
    ? band(forecast, focus.month, width, colors)
    : terms(gaps, focus.month, focus.view, width, colors);
}
