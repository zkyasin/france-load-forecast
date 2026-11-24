/**
 * The plan of the city of days: a district per year, four months across and three deep, a column
 * per weekday and a row per week in each month; the last district is the forecast, a tower per
 * month. The camera keys follow the cards of the story.
 */

import * as THREE from "three";
import type { Key } from "../stage";

/** The camera over the headline on a phone: its height, its depth, and the depth it aims at. */
const NARROW_HERO = { y: 16, z: 15, aim: -20 };

export const CELL = 0.08;
export const MONTH_W = 7 * CELL + 0.14;
export const MONTH_D = 6 * CELL + 0.14;
export const DISTRICT_W = 4 * MONTH_W + 0.5;
export const DISTRICT_D = 3 * MONTH_D + 0.5;
/** Height of a building per GW of mean power. */
export const H = 0.009;

export interface CityDay {
  year: number;
  month: number;
  /** Day of the week, Monday 0, and week row in the month. */
  weekday: number;
  row: number;
  gw: number;
}

export interface CityFocus {
  year: number;
  month: number;
  weekday: number;
  row: number;
  text: string;
  when: [number, number];
}

export interface Forecast {
  label: string;
  low: number;
  mid: number;
  high: number;
}

export function plan(years: number[], zoom: number, focusDays: CityFocus[]) {
  const slots = [...years, 0];
  const districtAt = (k: number): [number, number] => [
    ((k % 4) - 1.5) * DISTRICT_W,
    (Math.floor(k / 4) - 1.5) * DISTRICT_D,
  ];
  const slot = (year: number) => slots.indexOf(year);
  /** Centre of a month block, relative to its district. */
  const monthAt = (month: number): [number, number] => [
    (month % 4) * MONTH_W - (4 * MONTH_W) / 2 + MONTH_W / 2,
    Math.floor(month / 4) * MONTH_D - (3 * MONTH_D) / 2 + MONTH_D / 2,
  ];
  const cellAt = (year: number, month: number, weekday: number, row: number) => {
    const [dx, dz] = districtAt(slot(year));
    const mx = (month % 4) * MONTH_W - (4 * MONTH_W) / 2 + 0.07;
    const mz = Math.floor(month / 4) * MONTH_D - (3 * MONTH_D) / 2 + 0.07;
    return new THREE.Vector3(dx + mx + (weekday + 0.5) * CELL, 0, dz + mz + (row + 0.5) * CELL);
  };
  const [zx, zz] = districtAt(slot(zoom));
  const [fx, fz] = districtAt(slots.length - 1);
  const focus = focusDays.map((f) => cellAt(f.year, f.month, f.weekday, f.row));
  const keys: Key[] = [
    { t: 0, position: [1.5, 17, 10], target: [0, 0, 0.5] },
    { t: 0.7, position: [zx - 0.4, 3.6, zz + 2.8], target: [zx, 0.2, zz] },
    {
      t: 1.7,
      position: [(focus[0]?.x ?? 0) - 1.6, 1.6, (focus[0]?.z ?? 0) + 1.9],
      target: [focus[0]?.x ?? 0, 0.5, focus[0]?.z ?? 0],
    },
    {
      t: 2.7,
      position: [(focus[1]?.x ?? 0) + 1.5, 1.4, (focus[1]?.z ?? 0) + 1.8],
      target: [focus[1]?.x ?? 0, 0.25, focus[1]?.z ?? 0],
    },
    { t: 3.7, position: [-8, 4.5, 8.5], target: [0, 0.3, 0] },
    { t: 4.7, position: [fx + 2.4, 2.2, fz + 3.2], target: [fx, 0.4, fz] },
  ];
  // On a phone the headline holds the top of the screen: the city waits below it, seen from
  // further back, and rises into view with the first card.
  const narrowKeys: Key[] = [
    { t: 0, position: [1.5, NARROW_HERO.y, NARROW_HERO.z], target: [0, 0, NARROW_HERO.aim] },
    ...keys.slice(1),
  ];
  return {
    slots,
    districtAt,
    monthAt,
    cellAt,
    focus,
    keys,
    narrowKeys,
    forecastAt: [fx, fz] as const,
  };
}

export type Plan = ReturnType<typeof plan>;
