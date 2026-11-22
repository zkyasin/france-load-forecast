import "@fontsource-variable/archivo/wdth.css";
import "./style.css";
import * as accuracy from "./accuracy";
import * as annual from "./annual";
import { byId } from "./chart";
import { latest, type Meta, publications } from "./data";
import * as forecast from "./forecast";
import { dayName, daysSince, NBSP, signed } from "./format";
import * as gaps from "./gaps";
import * as temperature from "./temperature";

// The bundle is published every Monday: an older one means that an update did not run.
const STALE_AFTER_DAYS = 8;

function notify(text: string): void {
  const notice = byId("notice");
  notice.textContent = text;
  notice.hidden = false;
}

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
  forecast.render(bundle, days);
  accuracy.render(bundle.accuracy);
  gaps.render(bundle.gaps);
  temperature.render(bundle.model);
  annual.render(bundle.history.years);
  method(bundle.meta);
}

main().catch((error: unknown) => {
  const reason = error instanceof Error ? error.message : String(error);
  notify(`Les données de la page n'ont pas pu être chargées : ${reason}.`);
});
