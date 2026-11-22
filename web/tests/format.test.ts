import { expect, test } from "vitest";
import {
  addMonths,
  dayName,
  daysSince,
  monthName,
  monthTick,
  number,
  percent,
  signed,
  signedTick,
  tick,
  twh,
} from "../src/format";

test("numbers take a decimal comma and a true minus sign", () => {
  expect(number(-1.25, 2)).toBe("\u22121,25");
  expect(number(447.018, 0)).toBe("447");
});

test("a value that rounds to zero has no sign", () => {
  expect(number(-0.01)).toBe("0,0");
  expect(signed(-0.001, 2)).toBe("0,00");
});

test("signed values show their sign", () => {
  expect(signed(0.758, 2)).toBe("+0,76");
  expect(signed(-1.5)).toBe("\u22121,5");
});

test("a unit stays on the line of its number", () => {
  expect(twh(40.46)).toBe("40,5\u00a0TWh");
  expect(percent(2.956)).toBe("3,0\u00a0%");
});

test("months are named in French and counted across years", () => {
  expect(monthName("2026-11")).toBe("novembre 2026");
  expect(addMonths("2026-11", 2)).toBe("2027-01");
  expect(addMonths("2026-11", -24)).toBe("2024-11");
});

test("days are named in French, the first of the month as 1er", () => {
  expect(dayName("2026-11-22")).toBe("22 novembre 2026");
  expect(dayName("2026-11-01")).toBe("1er novembre 2026");
});

test("days since a publication are whole days", () => {
  expect(daysSince("2026-11-22", new Date("2026-11-30T05:00:00Z"))).toBe(8);
});

test("time ticks show the year under January only", () => {
  expect(monthTick(new Date(Date.UTC(2027, 0, 1)))).toBe("janv.\n2027");
  expect(monthTick(new Date(Date.UTC(2026, 3, 1)))).toBe("avr.");
});

test("axis labels keep a decimal only where the step needs one", () => {
  expect([0, 0.5, 1, 1.5].map(tick)).toEqual(["0", "0,5", "1", "1,5"]);
  expect([-1, -0.5, 0, 0.5].map(signedTick)).toEqual(["\u22121", "\u22120,5", "0", "+0,5"]);
});
