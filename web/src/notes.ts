/** The monthly notes of notes/, written by the agent and reviewed before they are merged. */

import { byId } from "./chart";
import type { GapMonth } from "./data";
import { addMonths, capitalize, dayName, monthName, NBSP, signed, twh } from "./format";

const REPOSITORY = "https://github.com/zkyasin/france-load-forecast";

export interface Note extends GapMonth {
  published: string;
  // "provider:model", as in config/agent.toml.
  model: string;
  reading: string;
}

// Read when the page is built: a note reaches the page with the next deployment.
const files = import.meta.glob<Note>("../../notes/*.json", { eager: true, import: "default" });

/** The notes, the latest month first. */
export const notes = (all: Note[] = Object.values(files)): Note[] =>
  [...all].sort((a, b) => b.month.localeCompare(a.month));

const signedTwh = (value: number): string => `${signed(value, 2)}${NBSP}TWh`;

export function summary(note: Note): string {
  return (
    `La consommation a atteint ${twh(note.against_forecast.actual)}, soit ` +
    `${signedTwh(note.against_forecast.gap)} par rapport à la prévision faite au début du mois et ` +
    `${signedTwh(note.against_year_before.gap)} par rapport à ` +
    `${monthName(addMonths(note.month, -12))}.`
  );
}

export const dates = (note: Note): string =>
  `D'après les données publiées le ${dayName(note.published)}.` +
  (note.provisional ? " Mois provisoire, mesuré en temps réel." : "");

/** Who wrote the reading and how it was checked. */
export function credit(note: Note): string {
  const [provider, ...name] = note.model.split(":");
  const writer =
    provider === "ollama"
      ? `${name.join(":")}, un modèle de langue exécuté en local`
      : `le modèle de langue ${name.join(":") || provider}`;
  return (
    `Lecture rédigée par ${writer}, à partir de ces données, puis relue avant publication. ` +
    "Chaque nombre a été vérifié contre les données."
  );
}

export function render(): void {
  const [latest] = notes();
  if (latest === undefined) {
    // No note yet: the section and its link stay out of the page.
    byId("note").hidden = true;
    const link = document.querySelector('.masthead a[href="#note-title"]');
    if (link?.parentElement) link.parentElement.hidden = true;
    return;
  }
  byId("note-month").textContent = capitalize(monthName(latest.month));
  byId("note-dates").textContent = dates(latest);
  byId("note-summary").textContent = summary(latest);
  byId("note-reading").replaceChildren(
    ...latest.reading.split(/\n\s*\n/).map((text) => {
      const paragraph = document.createElement("p");
      paragraph.textContent = text.trim();
      return paragraph;
    }),
  );
  const link = document.createElement("a");
  link.href = `${REPOSITORY}/blob/main/notes/${latest.month}.md`;
  link.textContent = "La note complète, avec le détail des termes, est sur GitHub";
  byId("note-credit").replaceChildren(`${credit(latest)} `, link, ".");
}
