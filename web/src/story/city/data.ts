/**
 * The figures of the city of days: a day per building since 2012, the forecast months as mean
 * power, the two days the camera visits and the copy of the cards.
 */

import { capitalize, dayName, monthName, NBSP, number } from "../../format";
import { dailyMean, dateOf, isoDay, lastFullYear, loadRelief, monthGW } from "../../relief";
import type { Context } from "../types";
import type { CityDay, CityFocus, Forecast } from "./layout";

export const gw = (v: number) => `${number(v)}${NBSP}GW`;

const MONTHS = [
  "janv.",
  "févr.",
  "mars",
  "avr.",
  "mai",
  "juin",
  "juil.",
  "août",
  "sept.",
  "oct.",
  "nov.",
  "déc.",
];

export const CARD_TITLES = [
  "Un quartier, une année",
  "Le gratte-ciel de 2012",
  "Avril 2020",
  "Quinze quartiers",
  "Le chantier",
];

export async function cityData(ctx: Context) {
  const relief = await loadRelief();
  const mean = dailyMean(relief);
  const days: (CityDay & { day: string })[] = [];
  for (let i = 0; i < relief.meta.days; i++) {
    const v = mean[i] as number;
    if (Number.isNaN(v)) continue;
    const date = dateOf(relief, i);
    const first = new Date(Date.UTC(date.getUTCFullYear(), date.getUTCMonth(), 1));
    const offset = (first.getUTCDay() + 6) % 7;
    days.push({
      year: date.getUTCFullYear(),
      month: date.getUTCMonth(),
      weekday: (date.getUTCDay() + 6) % 7,
      row: Math.floor((date.getUTCDate() - 1 + offset) / 7),
      gw: v,
      day: isoDay(date),
    });
  }
  const years = [...new Set(days.map((d) => d.year))];
  const zoom = lastFullYear(relief);
  const top = days.reduce((a, b) => (b.gw > a.gw ? b : a));
  const april = days
    .filter((d) => d.year === 2020 && d.month === 3)
    .reduce((a, b) => (b.gw < a.gw ? b : a));
  const months = ctx.bundle.forecast.months.filter((m) => m.p90 > m.p10).slice(0, 12);
  const forecast: Forecast[] = months.map((m) => ({
    label: capitalize(monthName(m.month)),
    low: monthGW(m.month, m.p10),
    mid: monthGW(m.month, m.p50),
    high: monthGW(m.month, m.p90),
  }));
  const zoomDays = days.filter((d) => d.year === zoom);
  const avg = (v: { gw: number }[]) => v.reduce((a, b) => a + b.gw, 0) / (v.length || 1);
  const jan = avg(zoomDays.filter((d) => d.month === 0));
  const jul = avg(zoomDays.filter((d) => d.month === 6));
  const skyline = years
    .filter((y) => y <= zoom)
    .map((y) => ({ y, n: days.filter((d) => d.year === y && d.gw >= 75).length }));
  const tallest = skyline.reduce((a, b) => (b.n > a.n ? b : a));
  const peakMonth = forecast.reduce((a, b) => (b.mid > a.mid ? b : a));
  const focus: CityFocus[] = [
    { ...top, text: `${dayName(top.day)} · ${gw(top.gw)}`, when: [1.2, 2.2] },
    { ...april, text: `${dayName(april.day)} · ${gw(april.gw)}`, when: [2.2, 3.2] },
  ];
  const chantier =
    "en céramique à la couleur de sa médiane ; l'échafaudage vermillon monte jusqu'à la borne haute, un trait sombre marque la borne basse.";
  const texts = [
    `Le quartier ${zoom} : un pâté de maisons par mois, une colonne par jour de la semaine, une rangée par semaine, comme un calendrier. Chaque immeuble est un jour, haut de sa puissance moyenne : ${gw(jan)} en janvier, ${gw(jul)} en juillet.`,
    `Le plus haut immeuble de la ville : le ${dayName(top.day)}, ${gw(top.gw)} en moyenne sur 24 heures.`,
    `Au printemps 2020, pendant le premier confinement, le quartier s'abaisse : le ${dayName(april.day)}, ${gw(april.gw)}.`,
    `Vue d'ensemble : les gratte-ciel sont les hivers, les maisons basses les étés. Le quartier qui compte le plus de jours au-dessus de 75${NBSP}GW est ${tallest.y}, avec ${tallest.n}.`,
    `Le seizième quartier est en chantier : une tour par mois prévu, ${chantier} La plus haute : ${peakMonth.label.toLowerCase()}, ${gw(peakMonth.mid)}.`,
  ];
  return {
    days,
    years,
    zoom,
    forecast,
    focus,
    texts,
    monthNames: MONTHS,
  };
}

export type CityData = Awaited<ReturnType<typeof cityData>>;
