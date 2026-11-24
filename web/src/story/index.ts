/**
 * The scroll story over the page: the progress bar, the masthead that takes a background once the
 * page scrolls, and the city of days in the stage of the hero, loaded on its own with three.js.
 */

import type { Bundle } from "../data";
import { ScrollTrigger } from "./scope";

function byId(id: string): HTMLElement {
  const element = document.getElementById(id);
  if (!element) throw new Error(`#${id} manquant`);
  return element;
}

function chrome(): void {
  const bar = byId("progress");
  ScrollTrigger.create({
    start: 0,
    end: "max",
    onUpdate: (self) => bar.style.setProperty("transform", `scaleX(${self.progress})`),
  });
  const masthead = byId("masthead");
  ScrollTrigger.create({
    start: 8,
    end: "max",
    onToggle: (self) => masthead.toggleAttribute("data-scrolled", self.isActive),
  });
}

/** Mounts the story once the chapters are drawn, since its scroll measures them. */
export async function boot(bundle: Bundle): Promise<void> {
  chrome();
  const { mount } = await import("./city");
  await mount({
    bundle,
    story: byId("story"),
    stage: byId("stage"),
    steps: byId("steps"),
    reducedMotion: matchMedia("(prefers-reduced-motion: reduce)").matches,
    lite: matchMedia("(max-width: 700px), (pointer: coarse)").matches,
  });
  ScrollTrigger.refresh();
}
