import "@fontsource-variable/archivo/wdth.css";
import "./style.css";
import * as accuracy from "./accuracy";
import * as annual from "./annual";
import { byId } from "./chart";
import * as chat from "./chat";
import { latest, type Meta, publications } from "./data";
import * as forecast from "./forecast";
import { dayName, daysSince, NBSP, signed } from "./format";
import * as gaps from "./gaps";
import * as notes from "./notes";
import * as peak from "./peak";
import * as scenarios from "./scenarios";
import * as temperature from "./temperature";

// The bundle is published every Monday: an older one means that an update did not run.
const STALE_AFTER_DAYS = 8;

/** Shows `text` in the notice, after what it already says. */
function notify(text: string): void {
  const notice = byId("notice");
  notice.textContent = notice.hidden ? text : `${notice.textContent} ${text}`;
  notice.hidden = false;
}

const reason = (error: unknown): string => (error instanceof Error ? error.message : String(error));

function masthead(meta: Meta, now: Date): void {
  byId("issue").textContent = `Publication du ${dayName(meta.published)}`;
  const age = daysSince(meta.published, now);
  if (age > STALE_AFTER_DAYS) {
    notify(
      `Dernière publication il y a ${age} jours, le ${dayName(meta.published)} : la mise à jour ` +
        "du lundi n'a pas eu lieu.",
    );
  }
}

function method(meta: Meta): void {
  byId("model-id").textContent = meta.model_id;
  if (meta.revision === null) {
    byId("realtime").hidden = true;
  } else {
    byId("revision").textContent = `${signed(meta.revision.gw, 2)}${NBSP}GW`;
  }
}

async function main(): Promise<void> {
  const bundle = await latest();
  // Without the list of publications, the page shows the latest forecast only.
  const days = await publications().catch(() => [bundle.meta.published]);
  masthead(bundle.meta, new Date());
  method(bundle.meta);
  // A section that fails leaves the others in place.
  const sections: [string, () => void][] = [
    ["Prévision", () => forecast.render(bundle, days)],
    ["Fiabilité", () => accuracy.render(bundle.accuracy)],
    ["Pointe", () => peak.render(bundle.peak)],
    ["Écarts", () => gaps.render(bundle.gaps)],
    ["Note du mois", () => notes.render()],
    ["Questions", () => chat.render(bundle)],
    ["Température", () => temperature.render(bundle.model)],
    ["Historique", () => annual.render(bundle.history.years)],
    ["Scénarios", () => scenarios.render(bundle.scenarios)],
  ];
  for (const [name, render] of sections) {
    try {
      render();
    } catch (error) {
      notify(`La section « ${name} » n'a pas pu être affichée : ${reason(error)}.`);
    }
  }
}

main().catch((error: unknown) => {
  notify(`Les données de la page n'ont pas pu être chargées : ${reason(error)}.`);
});
