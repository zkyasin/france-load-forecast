/** The map of France in WebGL: the projection, the slabs of land, the lines and the plants. */

import * as THREE from "three";
import { type GridMap, type Plant, SOURCES, type Source } from "../../grid";

// Equirectangular, scaled by the cosine of the mean latitude.
const LON0 = 2.45;
const LAT0 = 46.6;
const COS = Math.cos((LAT0 * Math.PI) / 180);

const project = ([lon, lat]: [number, number]): [number, number] => [
  (lon - LON0) * COS,
  -(lat - LAT0),
];

export function slab(
  rings: [number, number][][],
  depth: number,
  material: THREE.Material,
): THREE.Mesh {
  const shapes = rings.map(
    (ring) =>
      new THREE.Shape(
        ring.map((c) => {
          const [x, z] = project(c);
          return new THREE.Vector2(x, -z);
        }),
      ),
  );
  const geometry = new THREE.ExtrudeGeometry(shapes, { depth, bevelEnabled: false });
  geometry.rotateX(-Math.PI / 2);
  return new THREE.Mesh(geometry, material);
}

/** The 400 kV lines as segments, at height `y`; `pick` keeps some of them. */
export function lineSegments(
  grid: GridMap,
  material: THREE.Material,
  y: number,
  pick: (line: GridMap["lines"][number]) => boolean = () => true,
): THREE.LineSegments {
  const positions: number[] = [];
  for (const line of grid.lines) {
    if (!pick(line)) continue;
    const points = line.p.map(project);
    for (let i = 0; i < points.length - 1; i++) {
      const [x0, z0] = points[i] as [number, number];
      const [x1, z1] = points[i + 1] as [number, number];
      positions.push(x0, y, z0, x1, y, z1);
    }
  }
  const geometry = new THREE.BufferGeometry();
  geometry.setAttribute("position", new THREE.Float32BufferAttribute(positions, 3));
  return new THREE.LineSegments(geometry, material);
}

/** One column per plant, of height `height(plant)`, set again by `update`. */
export function columns(plants: Plant[], color: (source: Source) => string, base: number) {
  const geometry = new THREE.CylinderGeometry(1, 1, 1, 16);
  geometry.translate(0, 0.5, 0);
  const mesh = new THREE.InstancedMesh(
    geometry,
    new THREE.MeshStandardMaterial({ roughness: 0.6, metalness: 0 }),
    plants.length,
  );
  const tint = new THREE.Color();
  plants.forEach((plant, i) => {
    mesh.setColorAt(i, tint.set(color(plant.s)));
  });
  const matrix = new THREE.Matrix4();
  const radius = (plant: Plant) => 0.025 + Math.sqrt(plant.mw) * 0.0011;
  const update = (height: (plant: Plant, i: number) => number) => {
    plants.forEach((plant, i) => {
      const [x, z] = project(plant.c);
      const h = Math.max(0.0001, height(plant, i));
      const r = radius(plant);
      matrix.makeScale(r, h, r).setPosition(x, base, z);
      mesh.setMatrixAt(i, matrix);
    });
    mesh.instanceMatrix.needsUpdate = true;
  };
  return { mesh, update };
}

/** Lights for a model on a table. */
export function light(scene: THREE.Scene, intensity = 1) {
  scene.add(new THREE.HemisphereLight("#ffffff", "#9a9c96", 2 * intensity));
  const sun = new THREE.DirectionalLight("#fff8ee", 1.6 * intensity);
  sun.position.set(-5, 10, 4);
  scene.add(sun);
}

/** France and its neighbours on a table, the base of the map. */
export function table(
  scene: THREE.Scene,
  grid: GridMap,
  colours: { land: string; abroad: string; ground?: string },
  depth = 0.08,
) {
  const land = new THREE.MeshLambertMaterial({ color: colours.land });
  const abroad = new THREE.MeshLambertMaterial({ color: colours.abroad });
  const france = slab(grid.france, depth, land);
  const neighbours = slab(grid.neighbours, 0.03, abroad);
  scene.add(france, neighbours);
  if (colours.ground) {
    const ground = new THREE.Mesh(
      new THREE.PlaneGeometry(60, 60),
      new THREE.MeshBasicMaterial({ color: colours.ground }),
    );
    ground.rotation.x = -Math.PI / 2;
    ground.position.y = -0.002;
    scene.add(ground);
  }
  return { france, neighbours, land, abroad };
}

/** The colour of a source, as in éCO2mix. */
export const sourceColour = (source: Source): string => SOURCE_COLOURS.get(source) ?? "#888888";
const SOURCE_COLOURS = new Map(SOURCES.map((s) => [s.key, s.color]));
