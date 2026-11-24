/**
 * The story of the page: a miniature city whose buildings are the days since 2012, each as high
 * as its mean power and in its colour, from indigo (30 GW) to rose (85 GW), a district per year
 * on a navy plinth; the forecast is the last district, under scaffolding.
 */

import { colourKey, drive, frame } from "../kit";
import { scope } from "../scope";
import "../story.css";
import type { Context } from "../types";
import { CARD_TITLES, cityData } from "./data";
import { HIGH, LOW, powerHex } from "./palette";

export async function mount(ctx: Context): Promise<() => void> {
  const s = scope();
  const { canvas, layer, cards } = await frame(s, ctx, {
    theme: "paper",
    label:
      "Une ville miniature dont chaque immeuble est un jour depuis 2012, haut et coloré selon sa consommation moyenne, un quartier par année",
    credit: `RTE, éCO2mix (ODRÉ), Licence Ouverte 2.0 · hauteur et couleur : puissance moyenne du jour, de l'indigo (${LOW} GW) au rose (${HIGH} GW) · prévision du projet : médiane, échafaudage jusqu'à la borne haute`,
    cards: CARD_TITLES.map((title) => ({ title })),
  });
  const steps = Array.from({ length: 12 }, (_, k) => {
    const gw = LOW + ((HIGH - LOW) * k) / 11;
    return `${powerHex(gw)} ${((k / 11) * 100).toFixed(1)}%`;
  });
  const key = colourKey(s, ctx, {
    title: "Puissance moyenne du jour",
    gradient: `linear-gradient(90deg, ${steps.join(", ")})`,
    ends: [`${LOW} GW`, `${HIGH} GW`],
  });
  key(0);
  try {
    const data = await cityData(ctx);
    cards.forEach((c, k) => {
      c.text.textContent = data.texts[k] ?? "";
    });
    const { createColourCity } = await import("./scene");
    const scene = createColourCity(canvas, { lite: ctx.lite, layer, ...data });
    s.add(() => scene.destroy());
    drive(s, ctx, scene, cards.length, 3.7, key);
  } catch (error) {
    console.error(error);
    ctx.story.classList.add("no-model");
  }
  return () => s.dispose();
}
