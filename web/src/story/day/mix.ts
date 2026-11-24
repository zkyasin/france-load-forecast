/**
 * The story of the hour-by-hour chapter: the words of its cards, the legend and the panel of
 * figures, and the scene they drive, from the hourly mix of two days.
 */

import { NBSP, number } from "../../format";
import { loadGrid, SOURCES, type Source } from "../../grid";
import { loadMix, type MixKey, mixAt, track } from "../../mix";
import { type Card, legend } from "../kit";
import type { Scope } from "../scope";
import type { Context } from "../types";

export const LABEL =
  "Carte des centrales dont la hauteur suit, heure par heure, la production de leur filière";
export const CREDIT =
  "Production : RTE, éCO2mix (ODRÉ), Licence Ouverte 2.0 · Carte : OpenStreetMap (ODbL)";
export const CARDS = [
  { title: "Un samedi d'automne, 4 h" },
  { title: "Le même jour, 19 h" },
  { title: "Le jour le plus long, 4 h" },
  { title: "Midi au soleil" },
  { title: "Deux jours, deux mix" },
];
const gw = (mw: number) => `${number(mw / 1000)}${NBSP}GW`;
const dayLabel = (day: string) =>
  new Date(`${day}T12:00:00Z`).toLocaleDateString("fr-FR", {
    day: "numeric",
    month: "long",
    year: "numeric",
    timeZone: "UTC",
  });

/**
 * Fills the cards, builds the legend and the panel on `ctx.stage`, and returns the scene with
 * what follows its time in steps, for the caller to drive; without its data, null, and the story
 * shows no model.
 */
export async function tellMix(
  s: Scope,
  ctx: Context,
  parts: { canvas: HTMLCanvasElement; layer: HTMLElement; cards: Card[] },
) {
  const key = legend(s, ctx, [
    {
      text: "Hauteur : puissance installée × production de la filière à cette heure ÷ son heure la plus haute des deux jours",
      swatch: "#15171a",
      from: -1,
    },
  ]);
  const panel = s.element(ctx.stage, "div", "v-panel");
  panel.setAttribute("aria-live", "off");
  const title = s.element(panel, "strong");
  const total = s.element(panel, "span");
  const list = s.element(panel, "ul");
  const shown = SOURCES.filter((x) => !["charbon", "fioul"].includes(x.key));
  const rows = shown.map((source) => {
    const li = document.createElement("li");
    li.style.setProperty("--swatch", source.color);
    const name = document.createElement("span");
    name.textContent = source.label;
    const value = document.createElement("b");
    li.append(name, value);
    list.append(li);
    return { key: source.key, value };
  });
  try {
    return await build(s, ctx, parts, { key, panel, title, total, rows });
  } catch (error) {
    console.error(error);
    ctx.story.classList.add("no-model");
    key(9);
    return null;
  }
}

async function build(
  s: Scope,
  ctx: Context,
  parts: { canvas: HTMLCanvasElement; layer: HTMLElement; cards: Card[] },
  ui: {
    key: (t: number) => void;
    panel: HTMLElement;
    title: HTMLElement;
    total: HTMLElement;
    rows: { key: MixKey; value: HTMLElement }[];
  },
) {
  const { key, panel, title, total, rows } = ui;
  const [grid, mix] = await Promise.all([loadGrid(), loadMix()]);
  // Laid end to end: the recent day first, then the longest day.
  const days = [...mix.days].sort((a, b) => b.day.localeCompare(a.day));
  const [autumn, june] = days;
  if (!autumn || !june) throw new Error("mix.json : deux jours attendus");
  const peak = new Map<MixKey, number>();
  for (const k of SOURCES.map((x) => x.key)) {
    peak.set(k, Math.max(...days.flatMap((d) => d.hours.map((h) => h[k]))));
  }
  const share = (source: Source, hour: number) =>
    Math.max(0, mixAt(days, hour, source)) / (peak.get(source) || 1);
  const hourAt = (t: number) =>
    track(
      [
        [0, 0],
        [0.7, 4],
        [1.7, 19],
        [2.3, 24],
        [2.7, 28],
        [3.7, 37],
        [4.7, 47],
      ],
      t,
    );
  const at = (h: number, k: MixKey) => mixAt(days, h, k);
  const t = parts.cards.map((c) => c.text);
  const exchange = (h: number) => {
    const v = at(h, "ech_physiques");
    return v < 0 ? `la France exporte ${gw(-v)}` : `la France importe ${gw(v)}`;
  };
  if (t[0])
    t[0].textContent = `Le ${dayLabel(autumn.day)}, à 4 h, la France consomme ${gw(at(4, "consommation"))}. Le nucléaire en produit ${gw(at(4, "nucleaire"))}, et ${exchange(4)}.`;
  if (t[1])
    t[1].textContent = `À 19 h, la consommation monte à ${gw(at(19, "consommation"))}. L'hydraulique passe de ${gw(at(4, "hydraulique"))} à ${gw(at(19, "hydraulique"))}, le gaz de ${gw(at(4, "gaz"))} à ${gw(at(19, "gaz"))} : ce sont eux qui suivent la pointe.`;
  if (t[2])
    t[2].textContent = `Le ${dayLabel(june.day)}, à 4 h : ${gw(at(28, "consommation"))} consommés, le solaire est à zéro, ${exchange(28)}.`;
  if (t[3])
    t[3].textContent = `À 13 h, le solaire donne ${gw(at(37, "solaire"))} : la plupart viennent de panneaux trop petits pour la carte, mais ses parcs y montent au plus haut. ${exchange(37).replace(/^l/, "L")}.`;
  if (t[4])
    t[4].textContent = `En novembre, le soir fait la pointe et l'eau et le gaz montent avec elle. En juin, le soleil fait la journée et le nucléaire recule : ${gw(at(28, "nucleaire"))} à 4 h, ${gw(at(37, "nucleaire"))} à 13 h.`;
  const onHour = (hour: number) => {
    const h = Math.round(hour);
    const day = h < 24 ? autumn : june;
    title.textContent = `${dayLabel(day.day)}, ${h % 24}${NBSP}h`;
    total.textContent = `Consommation : ${gw(at(h, "consommation"))} · ${exchange(h)}`;
    for (const row of rows) row.value.textContent = gw(Math.max(0, at(h, row.key)));
  };
  const { createMix } = await import("./scene");
  const scene = createMix(parts.canvas, grid, {
    lite: ctx.lite,
    layer: parts.layer,
    hour: hourAt,
    share,
    onHour,
  });
  s.add(() => scene.destroy());
  const onTime = (time: number) => {
    key(time);
    panel.toggleAttribute("data-off", time < 0.3);
  };
  return { scene, onTime };
}
