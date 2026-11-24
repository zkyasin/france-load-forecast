/**
 * The hour-by-hour map in WebGL: the plants rise and fall with the hour. Each column is its capacity times the
 * output of its source at that hour over the source's highest hour of the two days.
 */

import * as THREE from "three";
import type { GridMap, Source } from "../../grid";
import { createStage, type Key } from "../stage";
import { columns, light, lineSegments, sourceColour, table } from "./map";

const SLAB = 0.08;
/** The background of the page: the frame of the map has no edge of its own colour. */
const BACKDROP = "#f6f7f9";
const HEIGHT = 0.00034;

export interface MixOptions {
  lite: boolean;
  layer: HTMLElement;
  /** The hour, across the two days, at a time in steps. */
  hour: (t: number) => number;
  /** Output of a source at a fractional hour over its highest hour. */
  share: (source: Source, hour: number) => number;
  onHour: (hour: number) => void;
}

export function createMix(canvas: HTMLCanvasElement, grid: GridMap, o: MixOptions) {
  const keys: Key[] = [
    { t: 0, position: [-3.5, 11, 10.5], target: [0.4, 0, 0.4] },
    { t: 0.7, position: [-5.5, 6.5, 8.5], target: [0.2, 0.3, 0.2] },
    { t: 1.7, position: [-1.2, 5.5, 9.5], target: [0.4, 0.4, 0.2] },
    { t: 2.7, position: [4.5, 6, 8.5], target: [0.4, 0.3, 0.4] },
    { t: 3.7, position: [5.5, 5, 6.5], target: [0.4, 0.3, 1.2] },
    { t: 4.7, position: [0.2, 10.5, 10], target: [0.3, 0.2, 0.3] },
  ];
  const plants = columns(grid.plants, sourceColour, SLAB);
  let last = Number.NaN;
  const stage = createStage(canvas, {
    lite: o.lite,
    background: BACKDROP,
    layer: o.layer,
    keys,
    narrowFov: 58,
    update: (t) => {
      const hour = o.hour(t);
      if (Math.abs(hour - last) < 0.01) return;
      last = hour;
      plants.update((plant) => plant.mw * HEIGHT * o.share(plant.s, hour));
      o.onHour(hour);
    },
  });
  const { scene } = stage;
  light(scene);
  table(scene, grid, { land: "#eef0f3", abroad: "#d5d9df", ground: BACKDROP }, SLAB);
  scene.add(
    lineSegments(
      grid,
      new THREE.LineBasicMaterial({ color: "#5c5f63", transparent: true, opacity: 0.3 }),
      SLAB + 0.004,
    ),
  );
  scene.add(plants.mesh);
  return stage;
}
