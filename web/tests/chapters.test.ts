import { describe, expect, it } from "vitest";
import { step } from "../src/chapters";

describe("step", () => {
  it("enters the list from outside at either end", () => {
    expect(step(-1, 12, "ArrowDown")).toBe(0);
    expect(step(-1, 12, "ArrowUp")).toBe(11);
  });

  it("wraps around", () => {
    expect(step(11, 12, "ArrowDown")).toBe(0);
    expect(step(0, 12, "ArrowUp")).toBe(11);
  });

  it("jumps to the ends and ignores other keys", () => {
    expect(step(5, 12, "Home")).toBe(0);
    expect(step(5, 12, "End")).toBe(11);
    expect(step(5, 12, "Tab")).toBeNull();
    expect(step(0, 0, "ArrowDown")).toBeNull();
  });
});
