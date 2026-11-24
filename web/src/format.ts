/** French formatting. Months are written YYYY-MM and days YYYY-MM-DD, both in UTC. */

const MINUS = "\u2212";
// Keeps a unit on the line of its number.
export const NBSP = "\u00a0";

const numbers = new Map<string, Intl.NumberFormat>();

function format(value: number, digits: number, signDisplay: "auto" | "exceptZero"): string {
  const key = `${digits}${signDisplay}`;
  let formatter = numbers.get(key);
  if (formatter === undefined) {
    formatter = new Intl.NumberFormat("fr-FR", {
      minimumFractionDigits: digits,
      maximumFractionDigits: digits,
      useGrouping: false,
      signDisplay,
    });
    numbers.set(key, formatter);
  }
  // Rounded first, so that a negative value that rounds to zero is written without a sign.
  // signDisplay "negative" would do it, but Firefox supports it only from version 116.
  const rounded = Number(value.toFixed(digits));
  return formatter.format(rounded === 0 ? 0 : rounded).replace("-", MINUS);
}

/** "1,5" with a decimal comma; negative values take a true minus sign, unless they round to zero. */
export const number = (value: number, digits = 1): string => format(value, digits, "auto");

/** "+1,5", "0,0" or a negative value with a true minus sign. */
export const signed = (value: number, digits = 1): string => format(value, digits, "exceptZero");

/** An axis label: whole values without a decimal, the others with one, so that close ticks differ. */
export const tick = (value: number): string => number(value, Number.isInteger(value) ? 0 : 1);

/** An axis label with its sign, as `signed` writes it. */
export const signedTick = (value: number): string => signed(value, Number.isInteger(value) ? 0 : 1);

export const twh = (value: number, digits = 1): string => `${number(value, digits)}${NBSP}TWh`;

export const percent = (value: number, digits = 1): string => `${number(value, digits)}${NBSP}%`;

export const celsius = (value: number, digits = 1): string => `${number(value, digits)}${NBSP}°C`;

/** A no-break space before ? ! : and ;, as French typography wants, so that none starts a line. */
export const frenchSpacing = (text: string): string => text.replace(/ (?=[?!:;])/g, NBSP);

/** "de mars", "d'avril": the preposition before a word, elided before a vowel. */
export const of = (word: string): string => (/^[aeiouéè]/i.test(word) ? `d'${word}` : `de ${word}`);

export const capitalize = (text: string): string => text.charAt(0).toUpperCase() + text.slice(1);

export const monthDate = (month: string): Date =>
  new Date(Date.UTC(Number(month.slice(0, 4)), Number(month.slice(5, 7)) - 1, 1));

export const dayDate = (day: string): Date =>
  new Date(
    Date.UTC(Number(day.slice(0, 4)), Number(day.slice(5, 7)) - 1, Number(day.slice(8, 10))),
  );

export function addMonths(month: string, count: number): string {
  const date = monthDate(month);
  date.setUTCMonth(date.getUTCMonth() + count);
  return date.toISOString().slice(0, 7);
}

const monthYear = new Intl.DateTimeFormat("fr-FR", {
  month: "long",
  year: "numeric",
  timeZone: "UTC",
});
const fullDay = new Intl.DateTimeFormat("fr-FR", {
  day: "numeric",
  month: "long",
  year: "numeric",
  timeZone: "UTC",
});
const shortMonth = new Intl.DateTimeFormat("fr-FR", { month: "short", timeZone: "UTC" });

/** "novembre 2026". */
export const monthName = (month: string): string => monthYear.format(monthDate(month));

/** "22 novembre 2026", "1er novembre 2026". */
export function dayName(day: string): string {
  const name = fullDay.format(dayDate(day));
  return name.startsWith("1 ") ? `1er ${name.slice(2)}` : name;
}

/** Tick of a time axis: "avr.", or "janv." over its year. */
export function monthTick(date: Date): string {
  const month = shortMonth.format(date);
  return date.getUTCMonth() === 0 ? `${month}\n${date.getUTCFullYear()}` : month;
}

/** Whole days from `day` to `now`. */
export const daysSince = (day: string, now: Date): number =>
  Math.floor((now.getTime() - dayDate(day).getTime()) / 86_400_000);
