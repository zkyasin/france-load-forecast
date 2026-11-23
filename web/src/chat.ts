/** The question panel: the pylon stands in the bottom-right corner and opens it. */

import "./chat.css";
import { API, ask, caption, failure, type Reply } from "./ask";
import { colors } from "./chart";
import {
  type Exchange,
  focus,
  followUps,
  KEPT,
  layout,
  leftText,
  moodOf,
  type Piece,
  previousOf,
  readExchanges,
  type Suggestion,
  sections,
  stepText,
  suggestions,
  verdict,
} from "./conversation";
import type { Bundle } from "./data";
import { figure } from "./minichart";
import { createPylon, type Mood, type Pylon } from "./pylon";

// What the visit keeps in the session: the exchanges, and whether the panel was opened.
const SAVED = "flf-questions";
const OPENED = "flf-questions-opened";
const LIMIT = 300;

const MOODS: Record<Mood, string> = {
  idle: "Répond à partir des données publiées",
  listen: "Vous écoute",
  think: "Lit les données…",
  answer: "Réponse vérifiée",
  refuse: "Pas de réponse chiffrée",
  offline: "Indisponible pour le moment",
};

const SKELETON = `
  <button class="chat-corner" type="button" aria-expanded="false" aria-controls="chat-panel"
    aria-label="Poser une question au pylône">
    <span class="chat-bubble" aria-hidden="true">Une question ?</span>
    <span class="chat-pylon"></span>
  </button>
  <section class="chat-panel" id="chat-panel" role="dialog" aria-labelledby="chat-title" hidden>
    <header class="chat-head">
      <span class="chat-badge"></span>
      <div class="chat-heading">
        <h2 id="chat-title">Questions sur la consommation</h2>
        <p class="chat-mood"></p>
      </div>
      <button class="chat-clear" type="button">Effacer</button>
      <button class="chat-close" type="button" aria-label="Fermer les questions">×</button>
    </header>
    <div class="chat-thread" aria-live="polite"></div>
    <p class="chat-left" aria-live="polite" hidden></p>
    <form class="chat-form">
      <label class="chat-label" for="chat-question">Votre question</label>
      <textarea id="chat-question" rows="1" maxlength="${LIMIT}"
        placeholder="Posez votre question…"></textarea>
      <span class="chat-count" hidden></span>
      <button class="chat-send" type="submit">Envoyer</button>
    </form>
  </section>`;

const reduce = matchMedia("(prefers-reduced-motion: reduce)");
const narrow = matchMedia("(max-width: 600px)");

function read(key: string): string | null {
  try {
    return sessionStorage.getItem(key);
  } catch {
    return null;
  }
}

function write(key: string, value: string | null): void {
  try {
    if (value === null) sessionStorage.removeItem(key);
    else sessionStorage.setItem(key, value);
  } catch {
    // Without storage, the exchanges last until the page is closed.
  }
}

function element<K extends keyof HTMLElementTagNameMap>(
  tag: K,
  className: string,
  text = "",
): HTMLElementTagNameMap[K] {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text) node.textContent = text;
  return node;
}

function fill(paragraph: HTMLElement, pieces: Piece[]): HTMLElement {
  paragraph.append(
    ...pieces.map((piece) =>
      piece.figure ? element("strong", "", piece.text) : document.createTextNode(piece.text),
    ),
  );
  return paragraph;
}

/** One loop draws the two pylons, and stops when the page is hidden or motion is reduced. */
function animate(corner: Pylon, badge: Pylon, panel: HTMLElement): () => void {
  let running = false;
  let last = 0;
  const still = (): void => {
    for (let i = 0; i < 3; i++) {
      corner.draw(1, 1);
      badge.draw(1, 1);
    }
  };
  const frame = (ms: number): void => {
    if (!running) return;
    const step = Math.min(0.05, (ms - last) / 1000);
    last = ms;
    corner.draw(ms / 1000, step);
    if (!panel.hidden) badge.draw(ms / 1000, step);
    requestAnimationFrame(frame);
  };
  const start = (): void => {
    if (running || reduce.matches || document.hidden) return;
    running = true;
    last = performance.now();
    requestAnimationFrame(frame);
  };
  document.addEventListener("visibilitychange", () => {
    if (document.hidden) running = false;
    else start();
  });
  reduce.addEventListener("change", () => {
    if (reduce.matches) {
      running = false;
      still();
    } else start();
  });
  still();
  start();
  return still;
}

export function render(bundle: Bundle): void {
  const link = document.querySelector<HTMLAnchorElement>('.masthead a[href="#questions"]');
  if (!API) {
    if (link?.parentElement) link.parentElement.hidden = true;
    return;
  }
  const root = element("div", "chat");
  root.innerHTML = SKELETON;
  document.body.append(root);
  const part = <T extends HTMLElement>(selector: string): T => {
    const node = root.querySelector<T>(selector);
    if (node === null) throw new Error(`${selector} is missing from the question panel`);
    return node;
  };
  const corner = part<HTMLButtonElement>(".chat-corner");
  const bubble = part(".chat-bubble");
  const panel = part(".chat-panel");
  const mood = part(".chat-mood");
  const thread = part(".chat-thread");
  const form = part<HTMLFormElement>(".chat-form");
  const field = part<HTMLTextAreaElement>("#chat-question");
  const counter = part(".chat-count");
  const left = part(".chat-left");
  const send = part<HTMLButtonElement>(".chat-send");

  const pylon = createPylon({ view: "corner", towards: -1 });
  const badge = createPylon({ view: "badge", towards: -1 });
  part(".chat-pylon").append(pylon.element);
  part(".chat-badge").append(badge.element);
  const still = animate(pylon, badge, panel);

  let moodTimer = 0;
  function feel(next: Mood, backToRest = 0): void {
    clearTimeout(moodTimer);
    const time = reduce.matches ? 1 : performance.now() / 1000;
    pylon.setMood(next, time);
    badge.setMood(next, time);
    if (reduce.matches) still();
    mood.textContent = MOODS[next];
    if (backToRest > 0) moodTimer = window.setTimeout(() => feel("idle"), backToRest);
  }
  feel("idle");

  let opened = read(OPENED) !== null;
  bubble.hidden = opened;
  function toggle(open: boolean): void {
    panel.hidden = !open;
    corner.setAttribute("aria-expanded", String(open));
    corner.classList.remove("chat-ducked");
    if (open) {
      opened = true;
      write(OPENED, "1");
      bubble.hidden = true;
      // The greeting first; the last exchange once there are some.
      thread.scrollTop = exchanges.length > 0 ? thread.scrollHeight : 0;
      field.focus();
    } else {
      corner.focus();
    }
  }
  corner.addEventListener("click", () => toggle(panel.hidden !== false));
  corner.addEventListener("pointerenter", () => {
    pylon.hovered = true;
  });
  corner.addEventListener("pointerleave", () => {
    pylon.hovered = false;
  });
  part(".chat-close").addEventListener("click", () => toggle(false));
  link?.addEventListener("click", (event) => {
    event.preventDefault();
    toggle(true);
  });
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && !panel.hidden) toggle(false);
  });
  // The pylon crouches while the page scrolls, so that it hides less of it.
  let settle = 0;
  addEventListener(
    "scroll",
    () => {
      if (!panel.hidden) return;
      corner.classList.add("chat-ducked");
      clearTimeout(settle);
      settle = window.setTimeout(() => corner.classList.remove("chat-ducked"), 900);
    },
    { passive: true },
  );

  let exchanges = readExchanges(read(SAVED));
  const asked = (): Set<string> => new Set(exchanges.map((exchange) => exchange.question));

  function show(node: HTMLElement): HTMLElement {
    thread.append(node);
    thread.scrollTop = thread.scrollHeight;
    return node;
  }

  function chips(list: Suggestion[], title: string): void {
    const box = element("div", "chat-chips");
    box.append(element("p", "chat-chips-title", title));
    for (const { theme, question } of list) {
      const chip = element("button", "chat-chip");
      chip.type = "button";
      if (theme) chip.append(element("small", "", theme));
      chip.append(element("span", "", question));
      chip.addEventListener("click", () => void submit(question));
      box.append(chip);
    }
    show(box);
  }

  /** The chart of the month an answer read, drawn from the data of the page when they are the
   * data of the answer. */
  function chart(reply: Reply, question: string): HTMLElement | null {
    const spot = focus(reply, question);
    if (spot === null || !reply.verified || reply.published !== bundle.meta.published) return null;
    const width = thread.clientWidth > 0 ? thread.clientWidth - 28 : 340;
    const drawn = figure(spot, bundle.forecast, bundle.gaps, width, colors());
    if (drawn === null) return null;
    const box = element("figure", "chat-figure");
    box.append(drawn.chart, element("figcaption", "", drawn.caption));
    return box;
  }

  function answer(reply: Reply, entering: boolean, question: string): void {
    const card = element("article", "chat-answer");
    const { lead, paragraphs } = layout(reply.answer);
    const blocks = [fill(element("p", "chat-lead"), lead)];
    const drawn = chart(reply, question);
    if (drawn !== null) blocks.push(drawn);
    for (const paragraph of paragraphs) blocks.push(fill(element("p", ""), paragraph));
    const { label, mood: tone } = verdict(reply);
    const proof = element("footer", "chat-proof");
    proof.append(element("span", `chat-verdict chat-verdict-${tone}`, label));
    proof.append(element("span", "chat-caption", caption(reply)));
    if (reply.verified) {
      for (const { anchor, label: text } of sections(reply.tools)) {
        const go = element("button", "chat-link", text);
        go.type = "button";
        go.addEventListener("click", () => {
          if (narrow.matches) toggle(false);
          document
            .getElementById(anchor)
            ?.scrollIntoView({ behavior: reduce.matches ? "auto" : "smooth", block: "start" });
        });
        proof.append(go);
      }
    }
    const copy = element("button", "chat-link", "Copier");
    copy.type = "button";
    copy.addEventListener("click", () => {
      const copied = navigator.clipboard?.writeText(`${reply.answer}\n\n${caption(reply)}`);
      (copied ?? Promise.reject(new Error("no clipboard")))
        .then(() => {
          copy.textContent = "Copié";
        })
        .catch(() => {
          copy.textContent = "Copie impossible";
        })
        .finally(() => {
          window.setTimeout(() => {
            copy.textContent = "Copier";
          }, 1600);
        });
    });
    proof.append(copy);
    blocks.push(proof);
    blocks.forEach((block, order) => {
      if (entering) block.style.setProperty("--order", String(order));
    });
    if (entering) card.classList.add("chat-entering");
    card.append(...blocks);
    show(card);
  }

  function exchange({ question, reply, error }: Exchange, entering: boolean): void {
    show(element("p", "chat-question", question));
    if (reply !== null) answer(reply, entering, question);
    if (error !== null) show(element("p", "chat-error", error));
  }

  function next(): void {
    const latest = exchanges.at(-1);
    const list = latest?.reply ? followUps(latest.reply.tools, asked()) : [];
    if (list.length > 0) {
      chips(
        list.map((question) => ({ theme: "", question })),
        "Pour continuer",
      );
    }
  }

  function greet(): void {
    show(
      element(
        "p",
        "chat-greeting",
        "Posez une question sur la consommation d'électricité en France. Chaque nombre de la " +
          "réponse vient des données publiées.",
      ),
    );
    chips(suggestions(bundle.forecast, bundle.gaps), "Pour commencer");
  }

  greet();
  for (const kept of exchanges) exchange(kept, false);
  next();

  part(".chat-clear").addEventListener("click", () => {
    exchanges = [];
    write(SAVED, null);
    thread.replaceChildren();
    greet();
    field.focus();
  });

  let pending: AbortController | null = null;
  function busy(on: boolean): void {
    send.textContent = on ? "Arrêter" : "Envoyer";
    send.type = on ? "button" : "submit";
    field.readOnly = on;
  }
  send.addEventListener("click", () => {
    if (pending !== null) pending.abort();
  });

  async function submit(text: string): Promise<void> {
    const question = text.trim();
    if (!question || pending !== null) return;
    for (const box of thread.querySelectorAll(".chat-chips")) box.remove();
    const kept: Exchange = { question, reply: null, error: null };
    show(element("p", "chat-question", question));
    // What the agent reads, step by step, as the API streams it.
    const waiting = show(element("div", "chat-steps"));
    const status = element("p", "chat-thinking", "Le pylône lit les données publiées");
    const steps = element("ul", "chat-step-list");
    waiting.append(status, steps);
    const slow = window.setTimeout(() => {
      status.textContent = "Encore quelques secondes";
    }, 8000);
    feel("think");
    pending = new AbortController();
    busy(true);
    try {
      const reply = await ask(question, {
        signal: pending.signal,
        previous: previousOf(exchanges),
        onStep: (call) => {
          steps.append(element("li", "", `Lit ${stepText(call)}`));
          thread.scrollTop = thread.scrollHeight;
        },
        onRetry: () => {
          steps.replaceChildren();
          status.textContent = "Un autre modèle reprend la question";
        },
      });
      kept.reply = reply;
      waiting.remove();
      left.textContent = leftText(reply.left);
      left.hidden = left.textContent === "";
      answer(reply, !reduce.matches, question);
      feel(verdict(reply).mood, 2600);
    } catch (error) {
      kept.error = failure(error);
      waiting.remove();
      show(element("p", "chat-error", kept.error));
      const after = moodOf(error);
      feel(after, after === "offline" ? 30_000 : 1500);
    } finally {
      clearTimeout(slow);
      pending = null;
      busy(false);
      exchanges = [...exchanges, kept].slice(-KEPT);
      write(SAVED, JSON.stringify(exchanges));
      next();
    }
  }

  form.addEventListener("submit", (event) => {
    event.preventDefault();
    const text = field.value;
    field.value = "";
    resize();
    void submit(text);
  });
  field.addEventListener("keydown", (event) => {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      if (pending === null) form.requestSubmit();
    }
  });
  function resize(): void {
    field.style.height = "auto";
    field.style.height = `${Math.min(field.scrollHeight, 132)}px`;
    const length = field.value.length;
    counter.hidden = length < LIMIT - 60;
    counter.textContent = `${length}/${LIMIT}`;
  }
  let quiet = 0;
  field.addEventListener("input", () => {
    resize();
    if (pending !== null) return;
    clearTimeout(quiet);
    if (field.value.trim()) {
      feel("listen");
      quiet = window.setTimeout(() => {
        if (pending === null) feel("idle");
      }, 1800);
    } else {
      feel("idle");
    }
  });
}
