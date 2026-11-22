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

export interface History {
  published: string;
  model_id: string;
  months: HistoryMonth[];
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

export interface Bundle {
  meta: Meta;
  forecast: Forecast;
  history: History;
  accuracy: Accuracy;
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
  const [meta, forecast, history, accuracy] = await Promise.all([
    get<Meta>("data/latest/meta.json"),
    get<Forecast>("data/latest/forecast.json"),
    get<History>("data/latest/history.json"),
    get<Accuracy>("data/latest/accuracy.json"),
  ]);
  return { meta, forecast, history, accuracy };
}

/** Dates of all publications, oldest first. */
export const publications = (): Promise<string[]> => get<string[]>("data/archive.json");

/** The forecast published on `day` (YYYY-MM-DD). */
export const archivedForecast = (day: string): Promise<Forecast> =>
  get<Forecast>(`data/archive/${day}/forecast.json`);
