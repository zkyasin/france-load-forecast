/**
 * The open-data map of the grid: the outline of France and its neighbours, the 400 kV lines and
 * the plants of at least 40 MW, built by scripts/grid.py into public/grid/france.json.
 */

export type Source =
  | "nucleaire"
  | "hydraulique"
  | "gaz"
  | "charbon"
  | "fioul"
  | "eolien"
  | "solaire"
  | "bioenergies";

export interface Plant {
  // Name, source, capacity in MW and [longitude, latitude].
  n: string;
  s: Source;
  mw: number;
  c: [number, number];
}

export interface GridMap {
  source: string;
  lines_km: number;
  france: [number, number][][];
  neighbours: [number, number][][];
  // A 400 kV line, and whether one of its ends is outside France.
  lines: { p: [number, number][]; b: 0 | 1 }[];
  plants: Plant[];
}

/** Names and colors of the sources, as in RTE's éCO2mix, in the order of the key. */
export const SOURCES: { key: Source; label: string; color: string }[] = [
  { key: "nucleaire", label: "Nucléaire", color: "#f2b705" },
  { key: "hydraulique", label: "Hydraulique", color: "#2772b2" },
  { key: "gaz", label: "Gaz", color: "#e8352a" },
  { key: "eolien", label: "Éolien", color: "#5cc5b0" },
  { key: "solaire", label: "Solaire", color: "#f28705" },
  { key: "bioenergies", label: "Bioénergies", color: "#2f8a5b" },
  { key: "charbon", label: "Charbon", color: "#8c6d3f" },
  { key: "fioul", label: "Fioul", color: "#7d4f8a" },
];

export const loadGrid = async (): Promise<GridMap> => {
  const response = await fetch("grid/france.json");
  if (!response.ok) throw new Error(`grid/france.json : erreur HTTP ${response.status}`);
  return (await response.json()) as GridMap;
};
