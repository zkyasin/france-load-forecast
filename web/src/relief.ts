/**
 * The relief of consumption: every hourly mean since 2012, from éCO2mix, built by
 * scripts/relief.py into public/relief/, and the daily figures the city of days reads from it.
 */

import { dayDate } from "./format";

export interface ReliefMeta {
  source: string;
  start: string;
  end: string;
  days: number;
  unit_mw: number;
  consolidated_until: string | null;
  peak: { day: string; hour: number; mw: number };
  last_day: {
    day: string;
    low: { hour: number; mw: number };
    high: { hour: number; mw: number };
    twh: number;
  };
  april_2020: { twh: number; mean_2015_2019: number };
  winter_2022: { twh: number; mean_2014_2018: number };
}

export interface Relief {
  meta: ReliefMeta;
  /** Hourly means in MW, 24 per day from `meta.start`; NaN where there is no value. */
  mw: Float32Array;
}

export const HOURS = 24;

const DAY = 86_400_000;

export function decode(meta: ReliefMeta, buffer: ArrayBuffer): Relief {
  const raw = new Uint16Array(buffer);
  const mw = new Float32Array(raw.length);
  for (let i = 0; i < raw.length; i++) {
    const value = raw[i] as number;
    mw[i] = value === 0 ? Number.NaN : value * meta.unit_mw;
  }
  return { meta, mw };
}

export async function loadRelief(): Promise<Relief> {
  const [meta, buffer] = await Promise.all([
    fetch("relief/relief.json").then((r) => {
      if (!r.ok) throw new Error(`relief.json : erreur HTTP ${r.status}`);
      return r.json() as Promise<ReliefMeta>;
    }),
    fetch("relief/relief.bin").then((r) => {
      if (!r.ok) throw new Error(`relief.bin : erreur HTTP ${r.status}`);
      return r.arrayBuffer();
    }),
  ]);
  return decode(meta, buffer);
}

export const dateOf = (relief: Relief, index: number): Date =>
  new Date(dayDate(relief.meta.start).getTime() + index * DAY);

export const isoDay = (date: Date): string => date.toISOString().slice(0, 10);

/** The last calendar year measured in full. */
export function lastFullYear(relief: Relief): number {
  const end = relief.meta.end;
  const year = Number(end.slice(0, 4));
  return end >= `${year}-12-31` ? year : year - 1;
}

/** Mean power of each day since the start, in GW; NaN for a day missing more than one hour. */
export function dailyMean(relief: Relief): Float32Array {
  const mean = new Float32Array(relief.meta.days).fill(Number.NaN);
  for (let d = 0; d < relief.meta.days; d++) {
    let sum = 0;
    let n = 0;
    for (let h = 0; h < HOURS; h++) {
      const v = relief.mw[d * HOURS + h] as number;
      if (Number.isNaN(v)) continue;
      sum += v;
      n += 1;
    }
    if (n >= HOURS - 1) mean[d] = sum / n / 1000;
  }
  return mean;
}

/** Mean power in GW of a month of `twh` terawatt-hours, `month` as "2027-01". */
export function monthGW(month: string, twh: number): number {
  const [y, m] = month.split("-").map(Number) as [number, number];
  const days = new Date(Date.UTC(y, m, 0)).getUTCDate();
  return (twh * 1000) / (days * 24);
}
