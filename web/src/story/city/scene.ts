/**
 * The city of days in WebGL: every building is a day since 2012 in glazed ceramic, as high as its
 * mean power and in its colour; the districts are navy plinths with streets between the months,
 * on a plain paper ground, under a high soft sun. The forecast is a district under scaffolding.
 */

import { ToneMappingEffect, ToneMappingMode, VignetteEffect } from "postprocessing";
import * as THREE from "three";
import { RoomEnvironment } from "three/addons/environments/RoomEnvironment.js";
import { RoundedBoxGeometry } from "three/addons/geometries/RoundedBoxGeometry.js";
import { postprocess } from "../post";
import { createStage } from "../stage";
import {
  CELL,
  type CityDay,
  type CityFocus,
  DISTRICT_D,
  DISTRICT_W,
  type Forecast,
  H,
  MONTH_D,
  MONTH_W,
  plan,
} from "./layout";
import { power } from "./palette";

export interface ColourOptions {
  lite: boolean;
  layer: HTMLElement;
  days: CityDay[];
  years: number[];
  forecast: Forecast[];
  focus: CityFocus[];
  monthNames: string[];
  zoom: number;
}

const WIDTH = CELL * 0.8;
const SUN = new THREE.Vector3(-0.45, 0.8, 0.35).normalize();

/** The top of a district: navy asphalt with pale dashes, and a paved block per month with a kerb. */
const PAVING = {
  street: "#30375e",
  line: "rgba(255,244,220,0.75)",
  kerb: "#e9dccb",
  block: "#fbf3e6",
};

function streets(paving = PAVING): THREE.CanvasTexture {
  const scale = 220;
  const w = Math.round((DISTRICT_W - 0.15) * scale);
  const d = Math.round((DISTRICT_D - 0.15) * scale);
  const canvas = document.createElement("canvas");
  canvas.width = w;
  canvas.height = d;
  const g = canvas.getContext("2d") as CanvasRenderingContext2D;
  g.fillStyle = paving.street;
  g.fillRect(0, 0, w, d);
  const ox = (w - 4 * MONTH_W * scale) / 2;
  const oz = (d - 3 * MONTH_D * scale) / 2;
  g.strokeStyle = paving.line;
  g.lineWidth = 2;
  g.setLineDash([10, 9]);
  for (let i = 0; i <= 4; i++) {
    const x = ox + i * MONTH_W * scale;
    g.beginPath();
    g.moveTo(x, 4);
    g.lineTo(x, d - 4);
    g.stroke();
  }
  for (let j = 0; j <= 3; j++) {
    const z = oz + j * MONTH_D * scale;
    g.beginPath();
    g.moveTo(4, z);
    g.lineTo(w - 4, z);
    g.stroke();
  }
  g.setLineDash([]);
  for (let m = 0; m < 12; m++) {
    const x = ox + (m % 4) * MONTH_W * scale + 0.035 * scale;
    const z = oz + Math.floor(m / 4) * MONTH_D * scale + 0.035 * scale;
    const bw = (MONTH_W - 0.07) * scale;
    const bd = (MONTH_D - 0.07) * scale;
    g.fillStyle = paving.kerb;
    g.beginPath();
    g.roundRect(x, z, bw, bd, 6);
    g.fill();
    g.fillStyle = paving.block;
    g.beginPath();
    g.roundRect(x + 3, z + 3, bw - 6, bd - 6, 4);
    g.fill();
  }
  const texture = new THREE.CanvasTexture(canvas);
  texture.colorSpace = THREE.SRGBColorSpace;
  texture.anisotropy = 8;
  return texture;
}

export function createColourCity(canvas: HTMLCanvasElement, o: ColourOptions) {
  const { slots, districtAt, monthAt, cellAt, focus, keys, forecastAt } = plan(
    o.years,
    o.zoom,
    o.focus,
  );
  const [fx, fz] = forecastAt;
  // The ground, the fog and the background are one grey that the vignette and the tone curve
  // bring to the paper of the page.
  const stage = createStage(canvas, {
    lite: o.lite,
    background: "#e2dfd8",
    layer: o.layer,
    keys,
    fov: 38,
    narrowFov: 62,
  });
  const { scene, renderer } = stage;
  // A neutral studio for the glaze's reflections.
  scene.fog = new THREE.Fog("#e2dfd8", 16, 44);
  const pmrem = new THREE.PMREMGenerator(renderer);
  const environment = pmrem.fromScene(new RoomEnvironment(), 0.04).texture;
  pmrem.dispose();
  scene.environmentIntensity = 0.45;
  scene.environment = environment;
  renderer.shadowMap.enabled = true;
  renderer.shadowMap.type = THREE.PCFShadowMap;
  scene.add(new THREE.HemisphereLight("#ffffff", "#a9a59c", 1.8));
  const sun = new THREE.DirectionalLight("#fff3e3", 2.2);
  sun.position.copy(SUN).multiplyScalar(22);
  // Soft shadows, as on paper.
  sun.shadow.intensity = 0.5;
  sun.castShadow = true;
  sun.shadow.mapSize.set(o.lite ? 1024 : 2048, o.lite ? 1024 : 2048);
  const reach = 2.3 * DISTRICT_W;
  Object.assign(sun.shadow.camera, {
    left: -reach,
    right: reach,
    top: reach,
    bottom: -reach,
    near: 1,
    far: 60,
  });
  sun.shadow.camera.updateProjectionMatrix();
  sun.shadow.bias = -0.0005;
  sun.shadow.normalBias = 0.01;
  scene.add(sun);

  const ground = new THREE.Mesh(
    new THREE.PlaneGeometry(300, 300),
    new THREE.MeshStandardMaterial({ color: "#d3cfc7", roughness: 1 }),
  );
  ground.rotation.x = -Math.PI / 2;
  ground.position.y = -0.22;
  ground.receiveShadow = true;
  scene.add(ground);

  // A plinth per district, sandstone under navy streets.
  const islandW = DISTRICT_W - 0.15;
  const islandD = DISTRICT_D - 0.15;
  const plinth = new RoundedBoxGeometry(islandW, 0.22, islandD, 3, 0.05);
  plinth.translate(0, -0.11, 0);
  const sandstone = new THREE.MeshStandardMaterial({
    color: "#f0c79a",
    roughness: 0.7,
  });
  const top = new THREE.MeshStandardMaterial({
    map: streets(),
    roughness: 0.75,
  });
  const deck = new THREE.PlaneGeometry(islandW - 0.06, islandD - 0.06);
  deck.rotateX(-Math.PI / 2);
  slots.forEach((year, k) => {
    const [dx, dz] = districtAt(k);
    const island = new THREE.Mesh(plinth, sandstone);
    island.position.set(dx, 0, dz);
    island.receiveShadow = true;
    island.castShadow = true;
    const paving = new THREE.Mesh(deck, top);
    paving.position.set(dx, 0.002, dz);
    paving.receiveShadow = true;
    scene.add(island, paving);
    // The year on a navy tab on the front rim of its plinth, over the street in front of the
    // first row of months, so that no tower stands on it.
    stage.label(
      year === 0 ? "prévision" : String(year),
      new THREE.Vector3(dx - islandW / 2 + 0.06, 0, dz + islandD / 2 - 0.03),
      [-1, 9],
      "v-tab",
    );
  });

  // The buildings: glazed ceramic, coloured by power.
  const box = new RoundedBoxGeometry(WIDTH, 1, WIDTH, 2, 0.012);
  box.translate(0, 0.5, 0);
  const glaze = new THREE.MeshPhysicalMaterial({
    roughness: 0.42,
    metalness: 0,
    clearcoat: 1,
    clearcoatRoughness: 0.18,
  });
  const count = o.days.length + o.forecast.length;
  const buildings = new THREE.InstancedMesh(box, glaze, count);
  buildings.castShadow = true;
  buildings.receiveShadow = true;
  const matrix = new THREE.Matrix4();
  const colour = new THREE.Color();
  const scale = new THREE.Vector3();
  const quaternion = new THREE.Quaternion();
  const put = (i: number, p: THREE.Vector3, sx: number, gw: number, sz: number) => {
    matrix.compose(p, quaternion, scale.set(sx, Math.max(0.001, gw * H), sz));
    buildings.setMatrixAt(i, matrix);
    const [r, g, b] = power(gw);
    buildings.setColorAt(i, colour.setRGB(r, g, b));
  };
  o.days.forEach((d, i) => {
    put(i, cellAt(d.year, d.month, d.weekday, d.row), 1, d.gw, 1);
  });
  // The forecast: a ceramic tower at the median, vermilion scaffolding to the high bound, a dark
  // band at the low bound.
  const poles: number[] = [];
  const bands: number[] = [];
  const square = (x: number, z: number, w: number, d: number, y: number, out: number[]) => {
    const c = [
      [x - w / 2, z - d / 2],
      [x + w / 2, z - d / 2],
      [x + w / 2, z + d / 2],
      [x - w / 2, z + d / 2],
    ] as const;
    for (let i = 0; i < 4; i++) {
      const p = c[i] as readonly [number, number];
      const q = c[(i + 1) % 4] as readonly [number, number];
      out.push(p[0], y, p[1], q[0], y, q[1]);
    }
  };
  o.forecast.forEach((f, m) => {
    const [mx, mz] = monthAt(m);
    const p = new THREE.Vector3(fx + mx, 0, fz + mz);
    const w = MONTH_W * 0.55;
    const d = MONTH_D * 0.55;
    put(o.days.length + m, p, w / WIDTH, f.mid, d / WIDTH);
    const sw = w + 0.06;
    const sd = d + 0.06;
    const high = f.high * H;
    for (const [sx, sz] of [
      [-1, -1],
      [1, -1],
      [1, 1],
      [-1, 1],
    ] as const) {
      poles.push(
        p.x + (sx * sw) / 2,
        0,
        p.z + (sz * sd) / 2,
        p.x + (sx * sw) / 2,
        high,
        p.z + (sz * sd) / 2,
      );
    }
    for (let y = 0.08; y < high; y += 0.08) square(p.x, p.z, sw, sd, y, poles);
    square(p.x, p.z, sw, sd, high, poles);
    square(p.x, p.z, w + 0.1, d + 0.1, f.low * H, bands);
    stage.label(f.label, new THREE.Vector3(p.x, high, p.z), [4.3, 9], "v-name");
  });
  scene.add(buildings);
  const scaffold = new THREE.BufferGeometry();
  scaffold.setAttribute("position", new THREE.Float32BufferAttribute(poles, 3));
  scene.add(new THREE.LineSegments(scaffold, new THREE.LineBasicMaterial({ color: "#d1401f" })));
  const band = new THREE.BufferGeometry();
  band.setAttribute("position", new THREE.Float32BufferAttribute(bands, 3));
  scene.add(new THREE.LineSegments(band, new THREE.LineBasicMaterial({ color: "#1d1b45" })));

  o.monthNames.forEach((name, m) => {
    const p = cellAt(o.zoom, m, 0, 0);
    stage.label(
      name,
      new THREE.Vector3(p.x - CELL / 2, 0.02, p.z - CELL / 2 - 0.02),
      [0.3, 1.3],
      "v-name",
    );
  });
  o.focus.forEach((f, k) => {
    const p = focus[k] as THREE.Vector3;
    const d = o.days.find(
      (x) => x.year === f.year && x.month === f.month && x.weekday === f.weekday && x.row === f.row,
    );
    stage.label(f.text, new THREE.Vector3(p.x, (d?.gw ?? 0) * H, p.z), f.when);
  });

  // No blur and no glare: a neutral tone curve that keeps the paper and the colour scale.
  postprocess(stage, {
    lite: o.lite,
    effects: [
      new VignetteEffect({ offset: 0.55, darkness: 0.1 }),
      new ToneMappingEffect({ mode: ToneMappingMode.NEUTRAL }),
    ],
  });
  const destroy = stage.destroy;
  return {
    ...stage,
    destroy() {
      destroy();
      environment.dispose();
    },
  };
}
