import { describe, expect, it } from "vitest";
import { dailyMean, dateOf, decode, lastFullYear, monthGW, type ReliefMeta } from "../src/relief";

const meta: ReliefMeta = {
  source: "test",
  start: "2024-02-28",
  end: "2024-03-01",
  days: 3,
  unit_mw: 50,
  consolidated_until: "2024-03-01",
  peak: { day: "2024-02-28", hour: 19, mw: 60_000 },
  last_day: {
    day: "2024-03-01",
    low: { hour: 4, mw: 40_000 },
    high: { hour: 19, mw: 55_000 },
    twh: 1.1,
  },
  april_2020: { twh: 30, mean_2015_2019: 37 },
  winter_2022: { twh: 170, mean_2014_2018: 190 },
};

function relief(missing: number[] = [5]) {
  const raw = new Uint16Array(3 * 24).map((_, i) => 800 + i);
  for (const i of missing) raw[i] = 0;
  return decode(meta, raw.buffer);
}

describe("relief", () => {
  it("decodes units of 50 MW and keeps missing hours empty", () => {
    const r = relief();
    expect(r.mw[0]).toBe(40_000);
    expect(Number.isNaN(r.mw[5])).toBe(true);
  });

  it("dates each day from the start", () => {
    expect(dateOf(relief(), 2).toISOString().slice(0, 10)).toBe("2024-03-01");
  });

  it("averages each day over its hours, and leaves out a day missing two", () => {
    const mean = dailyMean(relief([5, 30, 31]));
    const hours = Array.from({ length: 24 }, (_, h) => h).filter((h) => h !== 5);
    expect(mean[0]).toBeCloseTo((hours.reduce((a, h) => a + 800 + h, 0) / 23) * 0.05);
    expect(Number.isNaN(mean[1])).toBe(true);
  });

  it("takes the year before when the last one is not over", () => {
    expect(lastFullYear(relief())).toBe(2023);
  });

  it("turns the energy of a month into its mean power", () => {
    expect(monthGW("2027-01", 49.15)).toBeCloseTo(66.06, 2);
    expect(monthGW("2028-02", 0.696)).toBeCloseTo(1, 6);
  });
});
