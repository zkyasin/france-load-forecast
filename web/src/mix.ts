/** The hourly mix of two days, built by scripts/mix.py into public/grid/mix.json. */

import type { Source } from "./grid";

export type MixKey = Source | "consommation" | "pompage" | "ech_physiques";
export type MixHour = Record<MixKey, number>;

export interface MixDay {
  day: string;
  hours: MixHour[];
}

export interface MixData {
  source: string;
  unit: string;
  days: MixDay[];
}

export async function loadMix(): Promise<MixData> {
  const response = await fetch("grid/mix.json");
  if (!response.ok) throw new Error(`grid/mix.json : erreur HTTP ${response.status}`);
  return (await response.json()) as MixData;
}

/** Value of `key` at a fractional hour across the days laid end to end. */
export function mixAt(days: MixDay[], hour: number, key: MixKey): number {
  const hours = days.flatMap((d) => d.hours);
  const i = Math.max(0, Math.min(hours.length - 1, hour));
  const a = hours[Math.floor(i)] as MixHour;
  const b = hours[Math.min(hours.length - 1, Math.floor(i) + 1)] as MixHour;
  const f = i - Math.floor(i);
  return a[key] + (b[key] - a[key]) * f;
}

/** Piecewise-linear value between keys [t, value], held at the ends. */
export function track(keys: [number, number][], t: number): number {
  const first = keys[0] as [number, number];
  if (t <= first[0]) return first[1];
  for (let i = 0; i < keys.length - 1; i++) {
    const [t0, v0] = keys[i] as [number, number];
    const [t1, v1] = keys[i + 1] as [number, number];
    if (t <= t1) return t1 === t0 ? v1 : v0 + ((v1 - v0) * (t - t0)) / (t1 - t0);
  }
  return (keys.at(-1) as [number, number])[1];
}
