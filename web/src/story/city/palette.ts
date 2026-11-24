/**
 * A bold colour scale for power, from indigo through teal, lime and gold to coral and rose,
 * interpolated in Oklab so that equal steps of power look like equal steps of colour.
 */

export const STOPS = ["#33288f", "#2477c8", "#19b3a6", "#9fd545", "#ffd23f", "#ff7a38", "#e8245c"];
export const LOW = 30;
export const HIGH = 85;

type Lab = [number, number, number];

const toLinear = (c: number) => (c <= 0.04045 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4);
const toSrgb = (c: number) => (c <= 0.0031308 ? 12.92 * c : 1.055 * c ** (1 / 2.4) - 0.055);

function hexToLab(hex: string): Lab {
  const n = Number.parseInt(hex.slice(1), 16);
  const r = toLinear(((n >> 16) & 255) / 255);
  const g = toLinear(((n >> 8) & 255) / 255);
  const b = toLinear((n & 255) / 255);
  const l = Math.cbrt(0.4122214708 * r + 0.5363325363 * g + 0.0514459929 * b);
  const m = Math.cbrt(0.2119034982 * r + 0.6806995451 * g + 0.1073969566 * b);
  const s = Math.cbrt(0.0883024619 * r + 0.2817188376 * g + 0.6299787005 * b);
  return [
    0.2104542553 * l + 0.793617785 * m - 0.0040720468 * s,
    1.9779984951 * l - 2.428592205 * m + 0.4505937099 * s,
    0.0259040371 * l + 0.7827717662 * m - 0.808675766 * s,
  ];
}

/** Linear sRGB of an Oklab colour, clamped to the gamut. */
function labToLinear([L, a, b]: Lab): [number, number, number] {
  const l = (L + 0.3963377774 * a + 0.2158037573 * b) ** 3;
  const m = (L - 0.1055613458 * a - 0.0638541728 * b) ** 3;
  const s = (L - 0.0894841775 * a - 1.291485548 * b) ** 3;
  const clamp = (v: number) => Math.min(1, Math.max(0, v));
  return [
    clamp(4.0767416621 * l - 3.3077115913 * m + 0.2309699292 * s),
    clamp(-1.2684380046 * l + 2.6097574011 * m - 0.3413193965 * s),
    clamp(-0.0041960863 * l - 0.7034186147 * m + 1.707614701 * s),
  ];
}

const LABS = STOPS.map(hexToLab);

/** The colour of a power in GW, as linear RGB for three.js. */
export function power(gw: number): [number, number, number] {
  const f = Math.min(1, Math.max(0, (gw - LOW) / (HIGH - LOW))) * (LABS.length - 1);
  const k = Math.min(LABS.length - 2, Math.floor(f));
  const a = LABS[k] as Lab;
  const b = LABS[k + 1] as Lab;
  const t = f - k;
  return labToLinear([
    a[0] + (b[0] - a[0]) * t,
    a[1] + (b[1] - a[1]) * t,
    a[2] + (b[2] - a[2]) * t,
  ]);
}

/** The same colour as a CSS hex, for the key. */
export function powerHex(gw: number): string {
  return `#${power(gw)
    .map((c) =>
      Math.round(toSrgb(c) * 255)
        .toString(16)
        .padStart(2, "0"),
    )
    .join("")}`;
}
