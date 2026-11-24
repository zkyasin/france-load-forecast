/**
 * Une journée, heure par heure: a chapter before Historique whose stage holds still in a frame
 * while its five cards scroll past, the hours and the camera following the scroll, and then lets
 * the page go on. It loads when it nears the screen and draws only while it is on it.
 */

import type { Card } from "../kit";
import { activeSteps, type Scope, stageCanvas, whileVisible } from "../scope";
import type { Context } from "../types";
import "./day.css";
import { CARDS, CREDIT, LABEL, tellMix } from "./mix";

/** With reduced motion, the hour shown before a card is reached: the autumn evening peak. */
const STILL = 1.7;

export function mountDay(s: Scope, ctx: Context): void {
  const section = document.getElementById("journee");
  const story = section?.querySelector<HTMLElement>(".v-day-story");
  const stage = story?.querySelector<HTMLElement>(".v-day-stage");
  const steps = story?.querySelector<HTMLElement>(".v-day-steps");
  if (!section || !story || !stage || !steps) return;
  const canvas = stageCanvas(s, stage, LABEL);
  const layer = s.element(stage, "div", "stage-labels v-labels");
  layer.setAttribute("aria-hidden", "true");
  s.element(stage, "p", "stage-credit", CREDIT);
  const cards: Card[] = CARDS.map((spec) => {
    const step = s.element(steps, "article", "step");
    const card = s.element(step, "div", "step-card");
    s.element(card, "h3", "step-title").textContent = spec.title;
    const text = s.element(card, "p");
    return { step, inner: card, text };
  });
  activeSteps(s, steps);

  // The frame sits below the masthead, whose height changes with the width of the screen.
  const masthead = document.querySelector<HTMLElement>(".masthead");
  if (masthead) {
    const sized = new ResizeObserver(() =>
      section.style.setProperty("--v-masthead", `${masthead.offsetHeight}px`),
    );
    sized.observe(masthead);
    s.add(() => sized.disconnect());
  }

  const day: Context = { ...ctx, story, stage, steps };
  const load = async () => {
    const told = await tellMix(s, day, { canvas, layer, cards });
    if (!told) return;
    story.classList.add("is-ready");
    whileVisible(s, story, told.scene.setRunning);
    if (!ctx.reducedMotion) {
      // Card k holds the time k + 0.7 when its step reaches the top of the screen.
      told.scene.setProgress(0);
      told.onTime(0);
      s.trigger({
        trigger: steps,
        start: "top 80%",
        end: "bottom 80%",
        scrub: 0.8,
        onUpdate: (self) => {
          const t = self.progress * cards.length;
          told.scene.setProgress(t);
          told.onTime(t);
        },
      });
      return;
    }
    // With reduced motion, each card shows its own still hour, without the scroll between.
    const still = (t: number) => {
      told.scene.setProgress(t);
      told.onTime(t);
    };
    still(STILL);
    cards.forEach((card, k) => {
      s.trigger({
        trigger: card.step,
        start: "top 70%",
        end: "bottom 60%",
        onToggle: (self) => {
          if (self.isActive) still(k + 0.7);
        },
      });
    });
  };
  const near = new IntersectionObserver(
    (entries) => {
      if (!entries.some((e) => e.isIntersecting)) return;
      near.disconnect();
      void load();
    },
    { rootMargin: "600px 0px" },
  );
  near.observe(story);
  s.add(() => near.disconnect());
}
