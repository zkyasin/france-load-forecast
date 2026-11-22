/** How much the consumption of the model rises for one degree less, by temperature. */

import * as Plot from "@observablehq/plot";
import { byId, type Colors, drawIn, fillTable, frame, tipStyle } from "./chart";
import type { Gradient, Model } from "./data";
import { celsius, dayName, NBSP, number, signed, tick } from "./format";

const gw = (value: number): string => `${number(value)}${NBSP}GW`;

/** The two temperatures between which one degree less stops raising consumption. */
export function signChange(gradients: Gradient[]): [number, number] | undefined {
  for (const [index, after] of gradients.entries()) {
    const before = gradients[index - 1];
    if (before !== undefined && before.gw_per_c > 0 && after.gw_per_c <= 0) {
      return [before.temperature, after.temperature];
    }
  }
  return undefined;
}

export function summary(model: Model): string {
  const { winter, by_temperature: gradients } = model.thermosensitivity;
  const sentences = [
    `Le modèle a été estimé sur les jours du ${dayName(model.fitted_from)} au ` +
      `${dayName(model.fitted_until)}. En hiver, de décembre à février, un degré de moins fait ` +
      `monter la consommation de ${gw(winter)} en moyenne sur la journée.`,
  ];
  const coldest = gradients[0];
  if (coldest !== undefined && coldest.gw_per_c > winter) {
    sentences.push(
      `L'effet croît avec le froid : ${gw(coldest.gw_per_c)} par degré à ` +
        `${celsius(coldest.temperature, 0)}.`,
    );
  }
  const change = signChange(gradients);
  if (change !== undefined) {
    sentences.push(
      `Entre ${number(change[0], 0)} et ${celsius(change[1], 0)}, il change de signe : au-delà, ` +
        "la consommation augmente avec la chaleur, du fait de la climatisation.",
    );
  }
  return sentences.join(" ");
}

export const tipText = ({ temperature, gw_per_c }: Gradient): string =>
  `À ${celsius(temperature, 0)}, un degré de moins ${gw_per_c < 0 ? "retire" : "ajoute"} ` +
  gw(Math.abs(gw_per_c));

function plot(gradients: Gradient[], width: number, colors: Colors) {
  return Plot.plot({
    ...frame(width, colors),
    height: 240,
    marginLeft: 36,
    marginRight: 12,
    marginBottom: 44,
    x: {
      inset: 12,
      ticks: gradients.map((gradient) => gradient.temperature),
      tickFormat: (value: number) => number(value, 0),
      tickSize: 0,
      label: "Température (°C)",
      labelAnchor: "center",
      labelArrow: "none",
      labelOffset: 40,
    },
    y: {
      grid: true,
      nice: true,
      ticks: 5,
      tickSize: 0,
      label: "GW par degré de moins",
      labelArrow: "none",
      tickFormat: tick,
    },
    marks: [
      Plot.ruleY([0], { stroke: colors.ink, strokeOpacity: 0.6 }),
      Plot.lineY(gradients, {
        x: "temperature",
        y: "gw_per_c",
        stroke: colors.forecast,
        strokeWidth: 2,
      }),
      Plot.dot(gradients, {
        x: "temperature",
        y: "gw_per_c",
        r: 4,
        fill: colors.forecast,
        stroke: colors.paper,
        strokeWidth: 2,
      }),
      Plot.tip(
        gradients,
        Plot.pointerX({ x: "temperature", y: "gw_per_c", title: tipText, ...tipStyle(colors) }),
      ),
    ],
  });
}

export function render(model: Model): void {
  const gradients = model.thermosensitivity.by_temperature;
  byId("temperature-summary").textContent = summary(model);
  drawIn(byId("temperature-plot"), (width, colors) => plot(gradients, width, colors));
  fillTable(
    byId<HTMLTableElement>("temperature-table"),
    ["Température", "Effet d'un degré de moins"],
    gradients.map((gradient) => [
      celsius(gradient.temperature, 0),
      `${signed(gradient.gw_per_c)}${NBSP}GW`,
    ]),
  );
}
