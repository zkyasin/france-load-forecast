/**
 * A small 3D stage: a renderer drawn only when something moves, a camera that eases
 * between keys along the scroll, and HTML labels pinned to points of the scene.
 */

import * as THREE from "three";
import { disposeScene } from "./dispose";

export type Vec = [number, number, number];

/** A camera key, at a time `t` counted in steps: 0 is the headline, k + 0.7 the step k. */
export interface Key {
  t: number;
  position: Vec;
  target: Vec;
}

export interface Label {
  element: HTMLElement;
  at: THREE.Vector3 | (() => THREE.Vector3 | null);
  /** Shown from `t[0]` to `t[1]`. */
  when: [number, number];
}

/** A renderer of the scene through passes, sized with the canvas and freed with the stage. */
export interface Pipeline {
  render: () => void;
  resize?: (width: number, height: number) => void;
  dispose?: () => void;
}

export interface StageOptions {
  lite: boolean;
  background: THREE.ColorRepresentation;
  keys: Key[];
  /** A narrow screen keeps the same keys, seen from further away. */
  narrowFov?: number;
  /** On a narrow screen, keys of its own, such as a headline framed under its title. */
  narrowKeys?: Key[];
  /** On a narrow screen, the camera stands this many times as far from its target. */
  narrowDistance?: number;
  /** On a narrow screen, the scene moves up by this share of the height, above the cards. */
  narrowLift?: number;
  fov?: number;
  layer: HTMLElement;
  /** Called before each frame with the time in steps. */
  update?: (t: number) => void;
  /** On a wide screen the scene moves right by this share of the width, beside the cards. */
  shift?: number;
  /** Keeps drawing every frame, for a scene that moves by itself. */
  animate?: boolean;
}

const smooth = (x: number) => x * x * (3 - 2 * x);

export function at(keys: Key[], t: number): { position: THREE.Vector3; target: THREE.Vector3 } {
  const first = keys[0] as Key;
  const last = keys.at(-1) as Key;
  let a = first;
  let b = last;
  if (t <= first.t) b = first;
  else if (t >= last.t) a = last;
  else {
    for (let i = 0; i < keys.length - 1; i++) {
      const k0 = keys[i] as Key;
      const k1 = keys[i + 1] as Key;
      if (t >= k0.t && t <= k1.t) {
        a = k0;
        b = k1;
        break;
      }
    }
  }
  const f = b.t === a.t ? 0 : smooth((t - a.t) / (b.t - a.t));
  const mix = (p: Vec, q: Vec) =>
    new THREE.Vector3(p[0] + (q[0] - p[0]) * f, p[1] + (q[1] - p[1]) * f, p[2] + (q[2] - p[2]) * f);
  return { position: mix(a.position, b.position), target: mix(a.target, b.target) };
}

export function createStage(canvas: HTMLCanvasElement, options: StageOptions) {
  const renderer = new THREE.WebGLRenderer({ canvas, antialias: !options.lite, alpha: false });
  renderer.setPixelRatio(Math.min(window.devicePixelRatio, options.lite ? 1.25 : 1.75));
  renderer.outputColorSpace = THREE.SRGBColorSpace;
  const scene = new THREE.Scene();
  scene.background = new THREE.Color(options.background);
  const camera = new THREE.PerspectiveCamera(options.fov ?? 32, 1, 0.05, 400);
  const labels: Label[] = [];
  let t = 0;
  let dirty = true;
  let width = 1;
  let height = 1;
  let pipeline: Pipeline | null = null;
  let narrow = false;
  const target = new THREE.Vector3();

  const resize = () => {
    width = canvas.clientWidth;
    height = canvas.clientHeight;
    if (!width || !height) return;
    renderer.setSize(width, height, false);
    camera.aspect = width / height;
    narrow = width < height;
    camera.fov = narrow ? (options.narrowFov ?? 52) : (options.fov ?? 32);
    // On a screen as low as a phone on its side, the text beside takes more of the width.
    const reach = height < 480 ? Math.min(2, 3.5 / (width / height)) : 1;
    const shift = !narrow && width / height > 1.15 ? (options.shift ?? 0.17) * reach : 0;
    const lift = narrow ? height * (options.narrowLift ?? 0) : 0;
    camera.setViewOffset(width, height, -width * shift, lift, width, height);
    camera.updateProjectionMatrix();
    pipeline?.resize?.(width, height);
    dirty = true;
  };
  const observer = new ResizeObserver(resize);
  observer.observe(canvas);

  const v = new THREE.Vector3();
  const place = () => {
    for (const label of labels) {
      const point = typeof label.at === "function" ? label.at() : label.at;
      const on = point !== null && t >= label.when[0] && t <= label.when[1];
      if (!on || point === null) {
        label.element.style.opacity = "0";
        continue;
      }
      v.copy(point).project(camera);
      const shown = v.z < 1 && Math.abs(v.x) < 1.2 && Math.abs(v.y) < 1.2;
      label.element.style.opacity = shown ? "1" : "0";
      label.element.style.transform = `translate(${((v.x + 1) / 2) * width}px, ${((1 - v.y) / 2) * height}px)`;
    }
  };
  const draw = () => {
    const keys = narrow && options.narrowKeys ? options.narrowKeys : options.keys;
    const { position, target: aim } = at(keys, t);
    target.copy(aim);
    options.update?.(t);
    const distance = narrow ? (options.narrowDistance ?? 1) : 1;
    camera.position.copy(position.sub(aim).multiplyScalar(distance).add(aim));
    camera.lookAt(target);
    camera.updateMatrixWorld();
    if (pipeline) pipeline.render();
    else renderer.render(scene, camera);
    place();
  };

  let running = true;
  let frame = 0;
  const loop = () => {
    frame = 0;
    if (!running) return;
    if (dirty || options.animate) {
      draw();
      dirty = false;
    }
    frame = requestAnimationFrame(loop);
  };
  resize();
  // The first frame waits for the caller to fill the scene.
  frame = requestAnimationFrame(loop);

  return {
    scene,
    camera,
    renderer,
    get time() {
      return t;
    },
    /** Where the camera looks at the current time. */
    target,
    /** Renders through a post-processing pipeline instead of straight to the canvas. */
    use(next: Pipeline) {
      pipeline = next;
      if (width && height) next.resize?.(width, height);
      dirty = true;
    },
    label(text: string, point: Label["at"], when: [number, number], className = "v-call") {
      const element = document.createElement("span");
      element.className = className;
      element.textContent = text;
      element.style.opacity = "0";
      options.layer.append(element);
      labels.push({ element, at: point, when });
      return element;
    },
    invalidate() {
      dirty = true;
    },
    setProgress(value: number) {
      t = value;
      dirty = true;
      if (!running) draw();
    },
    setRunning(value: boolean) {
      if (value === running) return;
      running = value;
      if (running && frame === 0) loop();
    },
    destroy() {
      running = false;
      cancelAnimationFrame(frame);
      observer.disconnect();
      for (const label of labels) label.element.remove();
      pipeline?.dispose?.();
      disposeScene(renderer, scene);
    },
  };
}

export type Stage = ReturnType<typeof createStage>;

/** Points of a line as a mesh of thin segments, in one colour. */
export function polyline(points: THREE.Vector3[], color: string, opacity = 1): THREE.Line {
  const geometry = new THREE.BufferGeometry().setFromPoints(points);
  const material = new THREE.LineBasicMaterial({ color, transparent: opacity < 1, opacity });
  return new THREE.Line(geometry, material);
}
