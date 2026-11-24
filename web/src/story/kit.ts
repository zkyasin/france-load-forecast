/** What the scenes share around them: the cards, the stage layers, the legends and the scroll. */

import {
  activeSteps,
  drawCharts,
  type Scope,
  smoothScroll,
  stageCanvas,
  whileVisible,
} from "./scope";
import type { Context } from "./types";

export interface CardSpec {
  title: string;
  text?: string;
}

export interface Card {
  step: HTMLElement;
  inner: HTMLElement;
  text: HTMLElement;
}

export async function frame(
  s: Scope,
  ctx: Context,
  options: {
    label: string;
    credit: string;
    cards: CardSpec[];
  },
) {
  await smoothScroll(s, ctx.reducedMotion);
  drawCharts(s, ctx.reducedMotion);
  const canvas = stageCanvas(s, ctx.stage, options.label);
  const layer = s.element(ctx.stage, "div", "stage-labels v-labels");
  layer.setAttribute("aria-hidden", "true");
  s.element(ctx.stage, "p", "stage-credit", options.credit);
  const cards: Card[] = options.cards.map((spec) => {
    const step = s.element(ctx.steps, "article", "step");
    const inner = s.element(step, "div", "step-card");
    s.element(inner, "h2", "step-title").textContent = spec.title;
    const text = s.element(inner, "p");
    text.textContent = spec.text ?? "";
    return { step, inner, text };
  });
  activeSteps(s, ctx.steps);
  return { canvas, layer, cards };
}

/** A legend in the corner of the stage, whose items appear one step after another. */
export function legend(
  s: Scope,
  ctx: Context,
  items: { text: string; swatch?: string; from: number }[],
) {
  const list = s.element(ctx.stage, "ol", "v-legend");
  const rows = items.map((item) => {
    const li = document.createElement("li");
    if (item.swatch) li.style.setProperty("--swatch", item.swatch);
    li.textContent = item.text;
    list.append(li);
    return { li, from: item.from };
  });
  return (t: number) => {
    for (const row of rows) row.li.toggleAttribute("data-on", t >= row.from);
  };
}

/**
 * A colour key in the corner of the stage, kept on a phone: a gradient with its two ends, or
 * a few swatches. It waits over the headline and shows from the first card.
 */
export function colourKey(
  s: Scope,
  ctx: Context,
  options: {
    title: string;
    gradient?: string;
    ends?: [string, string];
    swatches?: { swatch: string; text: string }[];
  },
) {
  const key = s.element(ctx.stage, "div", "v-key");
  key.setAttribute("aria-hidden", "true");
  s.element(key, "strong", "", options.title);
  if (options.gradient) {
    const bar = s.element(key, "i", "v-key-bar");
    bar.style.background = options.gradient;
    const ends = s.element(key, "span", "v-key-ends");
    s.element(ends, "span", "", options.ends?.[0] ?? "");
    s.element(ends, "span", "", options.ends?.[1] ?? "");
  }
  for (const item of options.swatches ?? []) {
    const row = s.element(key, "span", "v-key-row", item.text);
    row.style.setProperty("--swatch", item.swatch);
  }
  return (t: number) => key.toggleAttribute("data-off", t < 0.3);
}

/**
 * Drives a scene with the scroll, in steps: 0 at the headline, `cards` at the end. With reduced
 * motion the scene shows one still frame at `still`.
 */
export function drive(
  s: Scope,
  ctx: Context,
  scene: { setProgress: (t: number) => void; setRunning: (on: boolean) => void },
  cards: number,
  still: number,
  onTime?: (t: number) => void,
) {
  if (ctx.reducedMotion) {
    scene.setRunning(false);
    scene.setProgress(still);
    onTime?.(still);
    return;
  }
  scene.setProgress(0);
  onTime?.(0);
  s.trigger({
    trigger: ctx.story,
    start: "top top",
    end: "bottom bottom",
    scrub: 0.8,
    onUpdate: (self) => {
      const t = self.progress * cards;
      scene.setProgress(t);
      onTime?.(t);
    },
  });
  whileVisible(s, ctx.story, scene.setRunning);
}
