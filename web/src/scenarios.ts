/** The energy of each year to 2031 under a trajectory of RTE's Bilan prévisionnel 2025 and a winter. */

import * as Plot from "@observablehq/plot";
import { byId, type Colors, drawIn, fillTable, frame, tipStyle } from "./chart";
import type { Scenarios } from "./data";
import { capitalize, NBSP, number, signed, twh } from "./format";

export interface Choice {
  trajectory: string;
  winter: string;
}

/** The case the others are compared with. */
const REFERENCE: Choice = { trajectory: "stagnation", winter: "normal" };

const WINTERS: Record<string, string> = { normal: "normal", cold: "froid", mild: "doux" };

const signedTwh = (value: number): string => `${signed(value)}${NBSP}TWh`;

/** "décarbonation lente": the label of a trajectory without its note, as inside a sentence. */
export function trajectoryName(scenarios: Scenarios, key: string): string {
  const label = (scenarios.trajectories[key]?.label ?? key).replace(/\s*\(.*\)$/, "");
  return label.charAt(0).toLowerCase() + label.slice(1);
}

export function energy(scenarios: Scenarios, year: number, choice: Choice): number {
  const found = scenarios.cases.find(
    (c) => c.year === year && c.trajectory === choice.trajectory && c.winter === choice.winter,
  );
  if (found === undefined) {
    throw new Error(`aucun scénario pour ${year}, ${choice.trajectory}, ${choice.winter}`);
  }
  return found.annual_energy;
}

/** The observed year whose weather a cold or mild winter replays, unless it changes with the year. */
export function weatherYear(scenarios: Scenarios, winter: string): number | undefined {
  const years = new Set(
    scenarios.replayed_winters.filter((r) => r.winter === winter).map((r) => r.weather_year),
  );
  const [only] = years;
  return years.size === 1 ? only : undefined;
}

/** "4,6 TWh", or "de 4,6 à 4,8 TWh" when the size of the effects differs once rounded. */
function size(values: number[]): string {
  const sizes = values.map(Math.abs);
  const [low, high] = [Math.min(...sizes), Math.max(...sizes)];
  return number(low) === number(high) ? twh(low) : `de ${number(low)} à ${twh(high)}`;
}

/** What a cold, then a mild winter does to the reference, and the years whose weather they replay. */
export function wintersText(scenarios: Scenarios): string {
  const [cold, mild] = (["cold", "mild"] as const).map((winter) => {
    const effects = scenarios.years.map(
      (year) =>
        energy(scenarios, year, { ...REFERENCE, winter }) - energy(scenarios, year, REFERENCE),
    );
    return {
      raises: (effects[0] ?? 0) >= 0,
      size: size(effects),
      year: weatherYear(scenarios, winter),
    };
  });
  if (cold === undefined || mild === undefined) return "";
  return (
    "Un hiver froid, qui revient environ une année sur dix, rejoue la météo de janvier, février " +
    `et décembre ${cold.year ?? "d'une année passée"} : il ${cold.raises ? "ajoute" : "retire"} ` +
    `${cold.size} à l'énergie de l'année. Un hiver doux, aussi rare, rejoue celle ` +
    `${mild.year === undefined ? "d'une autre année" : `de ${mild.year}`} : il ` +
    `${mild.raises ? "y ajoute" : "en retire"} ${mild.size}.`
  );
}

/** "+0,84 % de 2027 à 2030, puis +1,45 % en 2031". */
export function growth(rates: Record<string, number>): string {
  const runs: { from: string; to: string; rate: number }[] = [];
  for (const [year, rate] of Object.entries(rates)) {
    const last = runs.at(-1);
    if (last !== undefined && last.rate === rate) last.to = year;
    else runs.push({ from: year, to: year, rate });
  }
  return runs
    .map(
      ({ from, to, rate }) =>
        `${signed(rate, 2)}${NBSP}% ${from === to ? `en ${from}` : `de ${from} à ${to}`}`,
    )
    .join(", puis ");
}

/** The energy of the last year for `choice`, against the reference, and the growth it assumes. */
export function result(scenarios: Scenarios, choice: Choice): string {
  const year = scenarios.years.at(-1);
  if (year === undefined) return "";
  const value = energy(scenarios, year, choice);
  const start =
    `En ${trajectoryName(scenarios, choice.trajectory)}, avec un hiver ` +
    `${WINTERS[choice.winter] ?? choice.winter}, la consommation serait de ${twh(value)} en ${year}`;
  const compared =
    choice.trajectory === REFERENCE.trajectory && choice.winter === REFERENCE.winter
      ? " : c'est la référence des autres cas."
      : `, soit ${signedTwh(value - energy(scenarios, year, REFERENCE))} par rapport à la ` +
        `${trajectoryName(scenarios, REFERENCE.trajectory)}, avec un hiver normal.`;
  const rates = scenarios.trajectories[choice.trajectory]?.growth_pct;
  const assumed = rates === undefined ? "" : ` Croissance annuelle retenue : ${growth(rates)}.`;
  return start + compared + assumed;
}

export function tipText(scenarios: Scenarios, year: number, winter: string): string {
  return [
    `${year}, hiver ${WINTERS[winter] ?? winter}`,
    ...Object.keys(scenarios.trajectories).map(
      (trajectory) =>
        `${capitalize(trajectoryName(scenarios, trajectory))} : ` +
        twh(energy(scenarios, year, { trajectory, winter })),
    ),
  ].join("\n");
}

function plot(scenarios: Scenarios, choice: Choice, width: number, colors: Colors) {
  const { years } = scenarios;
  const last = years.at(-1);
  const points = Object.keys(scenarios.trajectories).flatMap((trajectory) =>
    years.map((year) => ({
      year,
      trajectory,
      name: trajectoryName(scenarios, trajectory),
      energy: energy(scenarios, year, { trajectory, winter: choice.winter }),
    })),
  );
  const chosen = points.filter((point) => point.trajectory === choice.trajectory);
  const others = points.filter((point) => point.trajectory !== choice.trajectory);
  const winters = years.map((year) => ({
    year,
    mild: energy(scenarios, year, { ...choice, winter: "mild" }),
    cold: energy(scenarios, year, { ...choice, winter: "cold" }),
  }));
  const energies = scenarios.cases.map((c) => c.annual_energy);
  // A halo of the background keeps each name readable where it crosses the band.
  const label = {
    x: "year",
    y: "energy",
    text: "name",
    dy: -14,
    textAnchor: "end" as const,
    stroke: colors.paper,
    strokeWidth: 3,
    paintOrder: "stroke",
  };
  return Plot.plot({
    ...frame(width, colors),
    height: 280,
    marginLeft: 36,
    marginRight: 12,
    x: { inset: 16, ticks: years, tickFormat: String, tickSize: 0, label: null },
    y: {
      grid: true,
      domain: [
        10 * Math.floor(Math.min(...energies) / 10),
        10 * Math.ceil(Math.max(...energies) / 10),
      ],
      ticks: 5,
      tickSize: 0,
      label: "TWh",
      labelArrow: "none",
      tickFormat: (value: number) => number(value, 0),
    },
    marks: [
      Plot.areaY(winters, {
        x: "year",
        y1: "mild",
        y2: "cold",
        fill: colors.forecast,
        fillOpacity: 0.2,
      }),
      Plot.lineY(others, {
        x: "year",
        y: "energy",
        z: "trajectory",
        stroke: colors.muted,
        strokeWidth: 1.5,
      }),
      Plot.lineY(chosen, { x: "year", y: "energy", stroke: colors.forecast, strokeWidth: 2 }),
      Plot.dot(chosen, {
        x: "year",
        y: "energy",
        r: 4,
        fill: colors.forecast,
        stroke: colors.paper,
        strokeWidth: 2,
      }),
      // Each line is named at its end, in the colors of the text.
      Plot.text(
        others.filter((point) => point.year === last),
        { ...label, fill: colors.muted },
      ),
      Plot.text(
        chosen.filter((point) => point.year === last),
        { ...label, fill: colors.ink },
      ),
      Plot.ruleX(years, Plot.pointerX({ stroke: colors.muted, strokeOpacity: 0.5 })),
      Plot.tip(
        years,
        Plot.pointerX({
          x: (year: number) => year,
          title: (year: number) => tipText(scenarios, year, choice.winter),
          ...tipStyle(colors, width),
        }),
      ),
    ],
  });
}

/** Radio buttons for `options` in `fieldset`, the one of value `checked` chosen. */
function fillChoice(
  fieldset: HTMLElement,
  options: { value: string; label: string }[],
  checked: string,
): void {
  const box = fieldset.querySelector(".options");
  if (box === null) throw new Error(`#${fieldset.id} has no options`);
  box.replaceChildren(
    ...options.map(({ value, label }) => {
      const input = document.createElement("input");
      input.type = "radio";
      input.name = fieldset.id;
      input.value = value;
      input.checked = value === checked;
      const text = document.createElement("span");
      text.textContent = label;
      const wrapper = document.createElement("label");
      wrapper.append(input, text);
      return wrapper;
    }),
  );
}

function showTable(scenarios: Scenarios): void {
  const trajectories = Object.keys(scenarios.trajectories);
  fillTable(
    byId<HTMLTableElement>("scenarios-table"),
    ["Année", "Hiver", ...trajectories.map((key) => capitalize(trajectoryName(scenarios, key)))],
    scenarios.years.flatMap((year) =>
      Object.keys(WINTERS).map((winter) => [
        String(year),
        WINTERS[winter] ?? winter,
        ...trajectories.map((trajectory) =>
          number(energy(scenarios, year, { trajectory, winter })),
        ),
      ]),
    ),
    // The year and the winter both name a row: three rows share each year.
    2,
  );
}

export function render(scenarios: Scenarios): void {
  const choice: Choice = { ...REFERENCE };
  byId("scenarios-winters").textContent = wintersText(scenarios);
  fillChoice(
    byId("scenario-trajectory"),
    Object.keys(scenarios.trajectories).map((key) => ({
      value: key,
      label: trajectoryName(scenarios, key),
    })),
    choice.trajectory,
  );
  fillChoice(
    byId("scenario-winter"),
    Object.entries(WINTERS).map(([value, name]) => {
      const year = weatherYear(scenarios, value);
      return { value, label: year === undefined ? name : `${name}, comme ${year}` };
    }),
    choice.winter,
  );
  const redraw = drawIn(byId("scenarios-plot"), (width, colors) =>
    plot(scenarios, choice, width, colors),
  );
  const describe = () => {
    byId("scenarios-result").textContent = result(scenarios, choice);
  };
  describe();
  showTable(scenarios);

  for (const [id, key] of [
    ["scenario-trajectory", "trajectory"],
    ["scenario-winter", "winter"],
  ] as const) {
    byId(id).addEventListener("change", (event) => {
      choice[key] = (event.target as HTMLInputElement).value;
      redraw();
      describe();
    });
  }
}
