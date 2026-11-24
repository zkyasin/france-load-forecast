/**
 * Files written by `flf publish`, as the page reads them. Their schema is checked before they are
 * published: see src/france_load_forecast/bundle.py.
 */

export interface Meta {
  published: string;
  model_id: string;
  consolidated_until: string;
  temperature_until: string;
  measured_until: string;
  revision: { gw: number; days: number } | null;
}

export interface ForecastMonth {
  month: string;
  p10: number;
  p50: number;
  p90: number;
  // Energy already measured in the month.
  measured: number;
  horizon: number;
  provisional: boolean;
}

export interface Forecast {
  published: string;
  model_id: string;
  current_month: string;
  total_p50: number;
  months: ForecastMonth[];
}

export interface HistoryMonth {
  month: string;
  energy: number;
  provisional: boolean;
}

/** The energy of a complete year, in TWh, and RTE's monthly series summed over it. */
export interface HistoryYear {
  year: number;
  gross: number;
  gross_rte: number;
  gross_gap_pct: number;
  // Corrected for the weather.
  corrected: number;
  corrected_rte: number;
  corrected_gap_pct: number;
}

export interface History {
  published: string;
  model_id: string;
  months: HistoryMonth[];
  years: HistoryYear[];
}

export interface Accuracy {
  published: string;
  model_id: string;
  first_origin: string;
  last_origin: string;
  mape: Record<string, number>;
  mape_naive: Record<string, number>;
  mape_naive_corrected: Record<string, number>;
  mape_since_2023: Record<string, number>;
  coverage_first_origin: string;
  coverage: Record<string, number>;
  coverage_since_2023: Record<string, number>;
}

/** The gap between the energy of a month and a reference, and its terms, which add up to it. */
export interface GapView {
  actual: number;
  reference: number;
  gap: number;
  climate: number;
  calendar: number;
  lockdown: number;
  structural: number;
  residual: number;
}

export interface GapMonth {
  month: string;
  provisional: boolean;
  // Mean temperatures, in °C, of the month, of its reference, of the same month a year earlier and
  // of the past weather that the forecast made at its start assumed.
  temperature: { mean: number; reference: number; year_before: number; forecast: number };
  against_forecast: GapView;
  against_year_before: GapView;
}

export interface Gaps {
  published: string;
  model_id: string;
  months: GapMonth[];
}

export interface Gradient {
  temperature: number;
  // GW of daily load added by one degree less, at this smoothed temperature.
  gw_per_c: number;
}

export interface Model {
  published: string;
  model_id: string;
  fitted_from: string;
  fitted_until: string;
  // `winter` is the mean gradient over the days of December to February.
  thermosensitivity: { winter: number; by_temperature: Gradient[] };
}

/** A consumption trajectory of RTE's Bilan prévisionnel 2025. */
export interface Trajectory {
  label: string;
  pages: string;
  // Growth of each year, in %.
  growth_pct: Record<string, number>;
}

/** The energy of a year under a trajectory and a winter: normal, cold or mild. */
export interface Case {
  year: number;
  trajectory: string;
  winter: string;
  annual_energy: number;
  winter_energy: number;
  months: number[];
}

export interface Scenarios {
  published: string;
  model_id: string;
  source: string;
  years: number[];
  trajectories: Record<string, Trajectory>;
  // The observed year whose winter months a cold or mild winter replays, for each year.
  replayed_winters: { year: number; winter: string; weather_year: number }[];
  cases: Case[];
}

/** The highest half-hour of a whole month measured, in GW, and the day it fell on. */
export interface MeasuredPeak {
  month: string;
  peak: number;
  day: string;
  provisional: boolean;
}

/** The monthly peak forecast, in GW: the same fields as the energy forecast, `measured` being the
 * highest day so far. */
export interface Peak {
  published: string;
  model_id: string;
  current_month: string;
  months: ForecastMonth[];
  history: MeasuredPeak[];
  // Rise of the daily peak for one degree less, from December to February.
  winter_gw_per_c: number;
  accuracy: Omit<Accuracy, "published" | "model_id">;
}

export interface Bundle {
  meta: Meta;
  forecast: Forecast;
  history: History;
  accuracy: Accuracy;
  gaps: Gaps;
  model: Model;
  scenarios: Scenarios;
  // Missing from the bundles published before the peak was.
  peak: Peak | null;
}

async function get<T>(path: string): Promise<T> {
  const response = await fetch(path);
  if (!response.ok) {
    throw new Error(`${path} : erreur HTTP ${response.status}`);
  }
  return (await response.json()) as T;
}

/** The last published bundle. */
export async function latest(): Promise<Bundle> {
  const [meta, forecast, history, accuracy, gaps, model, scenarios, peak] = await Promise.all([
    get<Meta>("data/latest/meta.json"),
    get<Forecast>("data/latest/forecast.json"),
    get<History>("data/latest/history.json"),
    get<Accuracy>("data/latest/accuracy.json"),
    get<Gaps>("data/latest/gaps.json"),
    get<Model>("data/latest/model.json"),
    get<Scenarios>("data/latest/scenarios.json"),
    get<Peak>("data/latest/peak.json").catch(() => null),
  ]);
  return { meta, forecast, history, accuracy, gaps, model, scenarios, peak };
}

/** Dates of all publications, oldest first. */
export const publications = (): Promise<string[]> => get<string[]>("data/archive.json");

/** The forecast published on `day` (YYYY-MM-DD). */
export const archivedForecast = (day: string): Promise<Forecast> =>
  get<Forecast>(`data/archive/${day}/forecast.json`);
