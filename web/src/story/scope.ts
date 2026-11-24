/**
 * The pieces of the scroll: a scope that collects what the story adds to the page, smooth
 * scrolling, chapter themes that follow the scroll, and chart lines drawn by the scroll.
 */

import { gsap } from "gsap";
import { ScrollTrigger } from "gsap/ScrollTrigger";
import type Lenis from "lenis";

gsap.registerPlugin(ScrollTrigger);

export { gsap, ScrollTrigger };

export interface Scope {
  /** Runs `cleanup` when the scope is disposed. */
  add(cleanup: () => void): void;
  on<K extends keyof WindowEventMap>(
    target: Window | Document | HTMLElement,
    type: K | string,
    listener: (event: Event) => void,
    options?: AddEventListenerOptions,
  ): void;
  trigger(vars: ScrollTrigger.Vars): ScrollTrigger;
  /** An element appended to `parent`, removed with the scope. */
  element<K extends keyof HTMLElementTagNameMap>(
    parent: Element,
    tag: K,
    className?: string,
    html?: string,
  ): HTMLElementTagNameMap[K];
  dispose(): void;
}

export function scope(): Scope {
  const cleanups: (() => void)[] = [];
  return {
    add: (cleanup) => cleanups.push(cleanup),
    on(target, type, listener, options) {
      target.addEventListener(type, listener, options);
      cleanups.push(() => target.removeEventListener(type, listener, options));
    },
    trigger(vars) {
      const trigger = ScrollTrigger.create(vars);
      cleanups.push(() => trigger.kill());
      return trigger;
    },
    element(parent, tag, className, html) {
      const element = document.createElement(tag);
      if (className) element.className = className;
      if (html !== undefined) element.innerHTML = html;
      parent.append(element);
      cleanups.push(() => element.remove());
      return element;
    },
    dispose() {
      for (const cleanup of cleanups.reverse()) {
        try {
          cleanup();
        } catch {
          // A failed cleanup must not keep the others from running.
        }
      }
      cleanups.length = 0;
    },
  };
}

/** Lenis smooth scrolling, wired to ScrollTrigger. Skipped with reduced motion. */
export async function smoothScroll(s: Scope, reducedMotion: boolean, lerp = 0.1): Promise<void> {
  if (reducedMotion) return;
  const { default: LenisClass } = await import("lenis");
  // The question panel scrolls its own thread.
  const lenis: Lenis = new LenisClass({ lerp, prevent: (node) => node.closest(".chat") !== null });
  lenis.on("scroll", ScrollTrigger.update);
  const tick = (time: number) => lenis.raf(time * 1000);
  gsap.ticker.add(tick);
  gsap.ticker.lagSmoothing(0);
  const onClick = (event: Event) => {
    const link = (event.target as Element).closest<HTMLAnchorElement>('a[href^="#"]');
    const target = link?.hash ? document.querySelector<HTMLElement>(link.hash) : null;
    if (!link || !target) return;
    event.preventDefault();
    const masthead = document.querySelector<HTMLElement>(".masthead")?.offsetHeight ?? 56;
    lenis.scrollTo(target, { offset: -masthead });
    history.replaceState(null, "", `${location.search}${link.hash}`);
  };
  s.on(document, "click", onClick);
  s.add(() => {
    gsap.ticker.remove(tick);
    lenis.destroy();
  });
}

/** The body takes the theme of the section in the middle of the screen. */
export function morphThemes(s: Scope, reducedMotion: boolean): void {
  const root = document.documentElement;
  if (!reducedMotion) root.classList.add("morph");
  for (const section of document.querySelectorAll<HTMLElement>("[data-theme]")) {
    s.trigger({
      trigger: section,
      start: "top 55%",
      end: "bottom 55%",
      onToggle: (self) => {
        if (self.isActive) document.body.dataset.theme = section.dataset.theme;
      },
    });
  }
  s.add(() => {
    root.classList.remove("morph");
    delete document.body.dataset.theme;
  });
}

/** Chart lines are drawn as their chart crosses the screen. */
export function drawCharts(s: Scope, reducedMotion: boolean): void {
  if (reducedMotion) return;
  for (const plot of document.querySelectorAll<HTMLElement>(".plot")) {
    plot.style.setProperty("--draw", "0");
    s.trigger({
      trigger: plot,
      start: "top 85%",
      end: "center 50%",
      scrub: 0.4,
      onUpdate: (self) => plot.style.setProperty("--draw", self.progress.toFixed(3)),
    });
    s.add(() => plot.style.removeProperty("--draw"));
  }
}

/** Steps: only the card of the step in view is shown, so that two cards never meet. */
export function activeSteps(s: Scope, steps: HTMLElement): void {
  steps.dataset.stepped = "";
  s.add(() => delete steps.dataset.stepped);
  for (const step of steps.querySelectorAll<HTMLElement>(".step:not(.step-hero)")) {
    s.trigger({
      trigger: step,
      start: "top 70%",
      end: "bottom 60%",
      onToggle: (self) => step.toggleAttribute("data-active", self.isActive),
    });
  }
}

/** Pauses `setRunning` when `element` is off screen or the tab is hidden. */
export function whileVisible(s: Scope, element: HTMLElement, setRunning: (on: boolean) => void) {
  let visible = true;
  const observer = new IntersectionObserver(([entry]) => {
    visible = Boolean(entry?.isIntersecting);
    setRunning(visible && !document.hidden);
  });
  observer.observe(element);
  s.add(() => observer.disconnect());
  s.on(document, "visibilitychange", () => setRunning(visible && !document.hidden));
}

/** A canvas filling the stage. */
export function stageCanvas(s: Scope, stage: HTMLElement, label: string): HTMLCanvasElement {
  const canvas = s.element(stage, "canvas", "stage-canvas");
  canvas.setAttribute("role", "img");
  canvas.setAttribute("aria-label", label);
  return canvas;
}
