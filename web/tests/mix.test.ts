import { describe, expect, it } from "vitest";
import { type MixDay, type MixHour, mixAt, track } from "../src/mix";

const hour = (consommation: number) => ({ consommation }) as MixHour;

describe("track", () => {
  const keys: [number, number][] = [
    [0, 10],
    [1, 20],
    [2, 20],
    [3, 0],
  ];

  it("holds the first and last values beyond the keys", () => {
    expect(track(keys, -1)).toBe(10);
    expect(track(keys, 5)).toBe(0);
  });

  it("interpolates between keys", () => {
    expect(track(keys, 0.5)).toBe(15);
    expect(track(keys, 1.5)).toBe(20);
    expect(track(keys, 2.25)).toBe(15);
  });
});

describe("mixAt", () => {
  const days: MixDay[] = [
    { day: "2026-11-21", hours: [hour(40), hour(50)] },
    { day: "2026-06-21", hours: [hour(30), hour(34)] },
  ];

  it("reads the hours of the days laid end to end", () => {
    expect(mixAt(days, 1, "consommation")).toBe(50);
    expect(mixAt(days, 2, "consommation")).toBe(30);
  });

  it("interpolates fractional hours and clamps at the ends", () => {
    expect(mixAt(days, 0.5, "consommation")).toBe(45);
    expect(mixAt(days, 2.5, "consommation")).toBe(32);
    expect(mixAt(days, -3, "consommation")).toBe(40);
    expect(mixAt(days, 9, "consommation")).toBe(34);
  });
});
