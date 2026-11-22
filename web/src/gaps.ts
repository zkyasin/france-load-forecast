/** What made the energy of each of the last twelve months differ from a reference. */

import * as Plot from "@observablehq/plot";
import { byId, type Colors, drawIn, fillTable, frame, tipStyle } from "./chart";
import type { Gaps } from "./data";
import {
  capitalize,
  celsius,
  monthDate,
  monthName,
  monthTick,
  NBSP,
  number,
  of,
  signed,
  signedTick,
  twh,
} from "./format";

/** The reference of each month: the same month a year earlier, or the forecast made on its first day. */
export type View = "against_year_before" | "against_forecast";

const NARROW = 600;

/**
 * The terms drawn, in the order they are stacked. The model splits the other effects into a
 * structural term and a residual, but a change that lasts a few months first shows in the
 * residual, so they are read together.
 */
const TERMS = [
  { key: "climate", label: "Météo" },
  { key: "calendar", label: "Calendrier" },
  { key: "others", label: "Autres effets" },
] as const;

export type Term = (typeof TERMS)[number];

export interface MonthGap {
  month: string;
  provisional: boolean;
  actual: number;
  reference: number;
  gap: number;
  climate: number;
  calendar: number;
  others: number;
  temperature: number;
  referenceTemperature: number;
}

export const monthGaps = (gaps: Gaps, view: View): MonthGap[] =>
  gaps.months.map((month) => {
    const terms = month[view];
    return {
      month: month.month,
      provisional: month.provisional,
      actual: terms.actual,
      reference: terms.reference,
      gap: terms.gap,
      climate: terms.climate,
      calendar: terms.calendar,
      others: terms.gap - terms.climate - terms.calendar,
      temperature: month.temperature.mean,
      referenceTemperature:
        view === "against_forecast" ? month.temperature.reference : month.temperature.year_before,
    };
  });

/** The terms that are not zero in every month. The calendar is known when the forecast is made. */
export const shownTerms = (months: MonthGap[]): Term[] =>
  TERMS.filter(({ key }) => months.some((month) => month[key] !== 0));

const sum = (values: number[]): number => values.reduce((total, value) => total + value, 0);

const meanAbsolute = (values: number[]): number => sum(values.map(Math.abs)) / values.length;

const signedTwh = (value: number): string => `${signed(value)}${NBSP}TWh`;

function provisionalNote(months: MonthGap[]): string {
  const provisional = months.filter((month) => month.provisional);
  const [only] = provisional;
  if (only === undefined) return "";
  if (provisional.length > 1) {
    return ` Les données des ${provisional.length} derniers mois sont encore provisoires.`;
  }
  return ` Les données ${of(monthName(only.month))} sont encore provisoires.`;
}

export function summary(months: MonthGap[], view: View): string {
  const first = months[0];
  const last = months.at(-1);
  if (first === undefined || last === undefined) return "";
  const period = `${capitalize(of(monthName(first.month)))} à ${monthName(last.month)}`;
  const note = provisionalNote(months);
  if (view === "against_year_before") {
    return (
      `${period}, la consommation a atteint ${twh(sum(months.map((m) => m.actual)))}, soit ` +
      `${signedTwh(sum(months.map((m) => m.gap)))} par rapport à la même période un an plus tôt : ` +
      `${signedTwh(sum(months.map((m) => m.climate)))} dus à la météo, ` +
      `${signedTwh(sum(months.map((m) => m.calendar)))} au calendrier et ` +
      `${signedTwh(sum(months.map((m) => m.others)))} aux autres effets.${note}`
    );
  }
  const climate = meanAbsolute(months.map((m) => m.climate));
  const others = meanAbsolute(months.map((m) => m.others));
  const cause = climate > others ? " : la météo du mois est la première source d'écart" : "";
  return (
    `${period}, la prévision faite au début de chaque mois s'est écartée de la consommation de ` +
    `${twh(meanAbsolute(months.map((m) => m.gap)))} en moyenne, dans un sens ou dans l'autre. ` +
    `L'effet de la météo a été de ${twh(climate)} en moyenne, celui des autres effets de ` +
    `${twh(others)}${cause}.${note}`
  );
}

/** The text of the tip on a month. */
export function tipText(month: MonthGap, view: View, terms: Term[]): string {
  const forecast = view === "against_forecast";
  return [
    `${monthName(month.month)}${month.provisional ? ", provisoire" : ""}`,
    `Mesuré : ${twh(month.actual)}`,
    `${forecast ? "Prévu au début du mois" : "Un an plus tôt"} : ${twh(month.reference)}`,
    `Écart : ${signedTwh(month.gap)}`,
    ...terms.map(({ key, label }) => `${label} : ${signedTwh(month[key])}`),
    `Température : ${celsius(month.temperature)} (${forecast ? "référence" : "un an plus tôt"} : ` +
      `${celsius(month.referenceTemperature)})`,
  ].join("\n");
}

/** Whole TWh from below the lowest stack or total to above the highest. */
function extent(months: MonthGap[], terms: Term[]): [number, number] {
  const ends = months.flatMap((month) => {
    const values = terms.map(({ key }) => month[key]);
    const below = sum(values.filter((value) => value < 0));
    const above = sum(values.filter((value) => value > 0));
    return [below, above, month.gap];
  });
  return [Math.floor(Math.min(0, ...ends)), Math.ceil(Math.max(0, ...ends))];
}

function plot(months: MonthGap[], terms: Term[], view: View, width: number, colors: Colors) {
  const narrow = width < NARROW;
  const domain = months.map((month) => month.month);
  // On a phone, odd months are labelled, so that January, which carries the year, always is.
  const ticks = narrow ? domain.filter((month) => Number(month.slice(5, 7)) % 2 === 1) : domain;
  const fills = { climate: colors.measured, calendar: colors.third, others: colors.fourth };
  const stacked = terms.flatMap(({ key, label }) =>
    months.map((month) => ({ month: month.month, term: label, value: month[key] })),
  );
  const total = { x: "month", y: "gap", strokeWidth: 1.5 };
  return Plot.plot({
    ...frame(width, colors),
    height: narrow ? 240 : 280,
    marginLeft: 36,
    marginRight: 12,
    marginBottom: 40,
    x: {
      type: "band",
      domain,
      ticks,
      tickFormat: (month: string) => monthTick(monthDate(month)),
      tickSize: 0,
      padding: 0.3,
      label: null,
    },
    y: {
      grid: true,
      domain: extent(months, terms),
      ticks: 5,
      tickSize: 0,
      label: "TWh",
      labelArrow: "none",
      tickFormat: signedTick,
    },
    color: { domain: terms.map((term) => term.label), range: terms.map((term) => fills[term.key]) },
    marks: [
      Plot.barY(
        stacked,
        Plot.stackY({
          x: "month",
          y: "value",
          fill: "term",
          order: terms.map((term) => term.label),
          stroke: colors.paper,
          strokeWidth: 1,
        }),
      ),
      Plot.ruleY([0], { stroke: colors.ink, strokeOpacity: 0.6 }),
      Plot.dot(
        months.filter((month) => !month.provisional),
        { ...total, r: 4.5, fill: colors.ink, stroke: colors.paper },
      ),
      // Provisional months are hollow, as in the forecast chart.
      Plot.dot(
        months.filter((month) => month.provisional),
        { ...total, r: 4, fill: colors.paper, stroke: colors.ink },
      ),
      Plot.tip(
        months,
        Plot.pointerX({
          x: "month",
          title: (month: MonthGap) => tipText(month, view, terms),
          ...tipStyle(colors, width),
        }),
      ),
    ],
  });
}

function showTable(months: MonthGap[], terms: Term[], view: View): void {
  const forecast = view === "against_forecast";
  fillTable(
    byId<HTMLTableElement>("gaps-table"),
    [
      "Mois",
      "Mesuré",
      forecast ? "Prévu" : "Un an plus tôt",
      "Écart",
      ...terms.map((term) => term.label),
      "Température",
      forecast ? "Température de référence" : "Température un an plus tôt",
    ],
    months.map((month) => [
      `${monthName(month.month)}${month.provisional ? " (provisoire)" : ""}`,
      number(month.actual),
      number(month.reference),
      signed(month.gap),
      ...terms.map(({ key }) => signed(month[key])),
      number(month.temperature),
      number(month.referenceTemperature),
    ]),
  );
}

/** "météo, calendrier et autres effets". */
function listOf(terms: Term[]): string {
  const names = terms.map((term) => term.label.toLowerCase());
  const last = names.pop();
  return names.length === 0 ? (last ?? "") : `${names.join(", ")} et ${last}`;
}

/** Fills the section of the gaps, compared with the year before or with the forecast. */
export function render(gaps: Gaps): void {
  // The browser may restore the button chosen before a reload or a return to the page.
  const checked = byId("gaps-view").querySelector<HTMLInputElement>("input:checked")?.value;
  let view: View = checked === "against_forecast" ? checked : "against_year_before";
  let months = monthGaps(gaps, view);
  let terms = shownTerms(months);
  const redraw = drawIn(byId("gaps-plot"), (width, colors) =>
    plot(months, terms, view, width, colors),
  );
  const describe = () => {
    byId("gaps-summary").textContent = summary(months, view);
    const reference =
      view === "against_forecast" ? "à sa prévision" : "au même mois un an plus tôt";
    byId("gaps-plot").setAttribute(
      "aria-label",
      `Écart de chaque mois ${reference}, décomposé en ${listOf(terms)}`,
    );
    const shown = new Set<string>(terms.map((term) => term.key));
    for (const item of byId("gaps-legend").querySelectorAll<HTMLElement>("[data-term]")) {
      item.hidden = !shown.has(item.dataset.term ?? "");
    }
    byId("gaps-provisional").hidden = !months.some((month) => month.provisional);
    showTable(months, terms, view);
  };
  describe();

  byId("gaps-view").addEventListener("change", (event) => {
    const { value } = event.target as HTMLInputElement;
    if (value !== "against_year_before" && value !== "against_forecast") return;
    view = value;
    months = monthGaps(gaps, view);
    terms = shownTerms(months);
    redraw();
    describe();
  });
}
