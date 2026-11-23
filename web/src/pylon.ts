/**
 * The pylon that answers questions: a "tête de chat" pylon of the French grid, drawn in SVG.
 *
 * Its head turns about the neck (100, 108) and its body stands on (100, 188). At rest it breathes,
 * blinks, follows the pointer, fidgets, and a bird sometimes lands on its line. Each mood follows
 * what the page or the question API does.
 */

export type Mood = "idle" | "listen" | "think" | "answer" | "refuse" | "offline";

type Point = [number, number];
type Side = "L" | "R" | "C";
type Fidget = "look" | "ear" | "stretch" | "hum" | "spark";

export interface Pylon {
  readonly element: SVGSVGElement;
  /** Takes `mood` from `time`, in seconds. */
  setMood(mood: Mood, time: number): void;
  /** Draws the pose at `time`, `step` seconds after the previous drawing. */
  draw(time: number, step: number): void;
  /** Set while the pointer is over the pylon. */
  hovered: boolean;
}

export interface PylonOptions {
  /** "corner" stands on the edge of the screen with its line; "badge" is the small one. */
  view: "corner" | "badge";
  /** The side it leans to when listening: -1 left, 1 right. */
  towards: number;
}

const NS = "http://www.w3.org/2000/svg";
const FIDGETS: Record<Fidget, number> = { look: 2.4, ear: 0.8, stretch: 1.5, hum: 1.2, spark: 1.8 };
const MOUTHS: Record<Mood, string> = {
  idle: "M95.5 95 Q100 98 104.5 95",
  listen: "M97 95 Q100 99.5 103 95 Q100 93 97 95 Z",
  think: "M96 96.5 Q100 95.5 104 96.5",
  answer: "M92 93 Q100 101 108 93",
  refuse: "M94 97 L106 97",
  offline: "M97.5 96 Q100 97.5 102.5 96",
};

const lerp = (a: number, b: number, k: number): number => a + (b - a) * k;
const clamp = (value: number, low: number, high: number): number =>
  Math.max(low, Math.min(high, value));
const ease = (p: number): number => (p < 0.5 ? 2 * p * p : 1 - (-2 * p + 2) ** 2 / 2);
const between = (low: number, high: number): number => low + Math.random() * (high - low);
const fixed = (value: number): string => value.toFixed(2);

// Where the pointer last was, in the coordinates of the window, and when.
const pointer = { x: 0, y: 0, time: Number.NEGATIVE_INFINITY };
let tracking = false;
function trackPointer(): void {
  if (tracking) return;
  tracking = true;
  addEventListener(
    "pointermove",
    (event) => {
      pointer.x = event.clientX;
      pointer.y = event.clientY;
      pointer.time = performance.now() / 1000;
    },
    { passive: true },
  );
}

const legX = (y: number, side: -1 | 1): number =>
  side < 0 ? 72 + (188 - y) * 0.225 : 128 - (188 - y) * 0.225;

function lattice(): string {
  const levels = [188, 168, 148, 128, 108];
  let lines = "";
  for (let i = 0; i < levels.length - 1; i++) {
    const a = levels[i] ?? 0;
    const b = levels[i + 1] ?? 0;
    lines += `<line x1="${legX(a, -1)}" y1="${a}" x2="${legX(b, 1)}" y2="${b}"/>`;
    lines += `<line x1="${legX(a, 1)}" y1="${a}" x2="${legX(b, -1)}" y2="${b}"/>`;
    if (i > 0) lines += `<line x1="${legX(a, -1)}" y1="${a}" x2="${legX(a, 1)}" y2="${a}"/>`;
  }
  return lines;
}

function truss(): string {
  let path = "";
  for (let x = 52; x < 148; x += 12) path += `M${x} 60 L${x + 6} 54 L${x + 12} 60 `;
  return path;
}

let count = 0;

function drawing(view: PylonOptions["view"]): string {
  const id = `pylon-fade-${++count}`;
  const left = view === "corner" ? 8 : -12;
  const leftWire = view === "corner" ? `stroke="url(#${id})"` : 'class="pylon-wire"';
  return `
    <defs>
      <linearGradient id="${id}" gradientUnits="userSpaceOnUse" x1="${left}" y1="0" x2="44" y2="0">
        <stop offset="0" class="pylon-fade" stop-opacity="0"/>
        <stop offset="1" class="pylon-fade" stop-opacity="1"/>
      </linearGradient>
    </defs>
    <ellipse data-part="shadow" class="pylon-fill" cx="100" cy="190" rx="36" ry="3.4" opacity="0.12"/>
    <path data-part="wireL" ${leftWire} fill="none" stroke-width="1.7"/>
    <path data-part="wireR" class="pylon-wire" fill="none" stroke-width="1.7"/>
    <path data-part="pulseL" class="pylon-current" fill="none" stroke-width="3.4" stroke-linecap="round" stroke-dasharray="1.2 16" opacity="0"/>
    <path data-part="pulseR" class="pylon-current" fill="none" stroke-width="3.4" stroke-linecap="round" stroke-dasharray="1.2 16" opacity="0"/>
    <circle data-part="spark" class="pylon-current-fill" r="2.8" opacity="0"/>
    <g data-part="bird" opacity="0">
      <g data-part="perched">
        <path class="pylon-fill" d="M5 -5 L10.5 -8.5 L9.8 -4 Z"/>
        <ellipse class="pylon-fill" cx="0" cy="-5" rx="5.6" ry="4"/>
        <g data-part="birdHead">
          <circle class="pylon-fill" cx="-4.6" cy="-9.2" r="2.9"/>
          <path class="pylon-current-fill" d="M-7.3 -9.7 L-10 -8.8 L-7.3 -8.1 Z"/>
          <circle class="pylon-light" cx="-5.4" cy="-9.8" r="0.75"/>
        </g>
        <path class="pylon-line" stroke-width="0.9" d="M-1 -1.5 L-1 0 M1.2 -1.5 L1.2 0"/>
      </g>
      <g data-part="flying" opacity="0">
        <ellipse class="pylon-fill" cx="0" cy="-5" rx="5" ry="3"/>
        <circle class="pylon-fill" cx="-4.8" cy="-6.4" r="2.5"/>
        <path data-part="wings" class="pylon-line" fill="none" stroke-width="1.8" stroke-linecap="round"/>
      </g>
    </g>
    <g data-part="body">
      <g class="pylon-line" stroke-width="1.3">${lattice()}</g>
      <path class="pylon-line" fill="none" stroke-width="3" stroke-linejoin="round" d="M72 188 L90 108 M128 188 L110 108"/>
      <g data-part="head">
        <path class="pylon-line" fill="none" stroke-width="3" stroke-linejoin="round" d="M90 108 L60 60 M110 108 L140 60 M38 60 L162 60 M46 54 L154 54"/>
        <path class="pylon-line" fill="none" stroke-width="1.2" d="${truss()} M96 100 L71 60 M104 100 L129 60"/>
        <g data-part="earL"><path class="pylon-fill" d="M36 61 L42 39 L53 55 Z"/></g>
        <g data-part="earR"><path class="pylon-fill" d="M164 61 L158 39 L147 55 Z"/></g>
        <g data-part="insulatorL"><line class="pylon-line" x1="44" y1="60" x2="44" y2="74" stroke-width="2.2" stroke-linecap="round"/><circle data-part="beadL" class="pylon-fill" cx="44" cy="75" r="2.7"/></g>
        <g data-part="insulatorR"><line class="pylon-line" x1="156" y1="60" x2="156" y2="74" stroke-width="2.2" stroke-linecap="round"/><circle data-part="beadR" class="pylon-fill" cx="156" cy="75" r="2.7"/></g>
        <g data-part="insulatorC"><line class="pylon-line" x1="100" y1="60" x2="100" y2="68" stroke-width="2.2" stroke-linecap="round"/><circle data-part="beadC" class="pylon-fill" cx="100" cy="69.5" r="2.4"/></g>
        <g data-part="eyes">
          <g data-part="eyeL"><circle class="pylon-light pylon-line" cx="87" cy="82" r="7.2" stroke-width="1.6"/><circle data-part="pupilL" class="pylon-fill" cx="87" cy="82" r="3.5"/><circle data-part="glintL" class="pylon-light" cx="86" cy="80.6" r="1.15"/></g>
          <g data-part="eyeR"><circle class="pylon-light pylon-line" cx="113" cy="82" r="7.2" stroke-width="1.6"/><circle data-part="pupilR" class="pylon-fill" cx="113" cy="82" r="3.5"/><circle data-part="glintR" class="pylon-light" cx="112" cy="80.6" r="1.15"/></g>
        </g>
        <path data-part="happy" class="pylon-line" fill="none" stroke-width="2.4" stroke-linecap="round" d="M80.5 84 Q87 76 93.5 84 M106.5 84 Q113 76 119.5 84" opacity="0"/>
        <path data-part="asleep" class="pylon-line" fill="none" stroke-width="2.4" stroke-linecap="round" d="M80.5 81 Q87 87 93.5 81 M106.5 81 Q113 87 119.5 81" opacity="0"/>
        <path data-part="mouth" class="pylon-line" fill="none" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
        <path data-part="burst" class="pylon-current" fill="none" stroke-width="2" stroke-linecap="round" opacity="0" d="M42 34 L40 27 M36 38 L30 34 M48 36 L52 30 M158 34 L160 27 M164 38 L170 34 M152 36 L148 30"/>
      </g>
    </g>
    <g data-part="badge" opacity="0">
      <circle data-part="badgeDisc" class="pylon-good" cx="100" cy="22" r="11"/>
      <path data-part="badgeMark" class="pylon-light-line" fill="none" stroke-width="2.6" stroke-linecap="round" stroke-linejoin="round"/>
    </g>
    <g data-part="sleep" class="pylon-muted" font-weight="800" opacity="0">
      <text x="126" y="38" font-size="15">z</text>
      <text x="138" y="26" font-size="11">z</text>
    </g>`;
}

interface Wire {
  from: Point;
  control: Point;
  to: Point;
}

/** A point of a wire, from its start (0) to its end (1). */
function along(wire: Wire, s: number): Point {
  const a = (1 - s) ** 2;
  const b = 2 * s * (1 - s);
  const c = s * s;
  return [
    a * wire.from[0] + b * wire.control[0] + c * wire.to[0],
    a * wire.from[1] + b * wire.control[1] + c * wire.to[1],
  ];
}

/** A wire from `from` to (`endX`, 70) that hangs by `sag` in its middle. */
function hang(from: Point, endX: number, sag: number): Wire {
  const to: Point = [endX, 70];
  return { from, control: [(from[0] + to[0]) / 2, (from[1] + to[1]) / 2 + 2 * sag], to };
}

const path = (wire: Wire): string =>
  `M${fixed(wire.from[0])} ${fixed(wire.from[1])} Q${fixed(wire.control[0])} ${fixed(wire.control[1])} ${fixed(wire.to[0])} ${fixed(wire.to[1])}`;

export function createPylon({ view, towards }: PylonOptions): Pylon {
  trackPointer();
  const frame =
    view === "corner"
      ? { box: "0 16 236 182", left: 8, right: 520, sag: [6, 26], perch: 198, bird: true }
      : { box: "0 4 200 196", left: -12, right: 212, sag: [10, 10], perch: 178, bird: false };
  const element = document.createElementNS(NS, "svg");
  element.setAttribute("viewBox", frame.box);
  element.setAttribute("aria-hidden", "true");
  element.classList.add("pylon");
  element.innerHTML = drawing(view);
  const parts = new Map<string, SVGElement>();
  for (const node of element.querySelectorAll<SVGElement>("[data-part]")) {
    parts.set(node.dataset.part ?? "", node);
  }
  const part = (name: string): SVGElement => {
    const node = parts.get(name);
    if (node === undefined) throw new Error(`the pylon has no ${name}`);
    return node;
  };

  let mood: Mood = "idle";
  let since = 0;
  let hovered = false;
  // The pose, eased towards its targets at each drawing.
  let tilt = 0;
  let headX = 0;
  let headY = 0;
  let scaleX = 1;
  let scaleY = 1;
  let hop = 0;
  let earL = 0;
  let earR = 0;
  let open = 1;
  let wide = 1;
  let gaze: Point = [0, 0];
  let dim = 1;
  let current = 0;
  let badge = 0;
  // Insulators swing on springs: angle and speed.
  const swing: Record<Side, Point> = { L: [0, 0], R: [0, 0], C: [0, 0] };
  let nextBlink = between(1, 3);
  let blinkEnd = -1;
  let fidget: { kind: Fidget; start: number; side: "L" | "R" } | null = null;
  let nextFidget = between(1.2, 2.5);
  let wander: Point = [0, 0];
  let nextWander = between(1, 3);
  let gust = Number.NEGATIVE_INFINITY;
  let nextGust = between(6, 11);
  let spark: { side: "L" | "R"; start: number } | null = null;
  let wires: Record<"L" | "R", Wire> | null = null;
  const bird = {
    mode: frame.bird ? "away" : "off",
    start: 0,
    next: between(6, 12),
    leave: 0,
    from: [0, 0] as Point,
  };

  function perch(): Point {
    if (wires === null) return [frame.perch, 70];
    const wire = wires.R;
    return along(wire, clamp((frame.perch - wire.from[0]) / (wire.to[0] - wire.from[0]), 0, 1));
  }
  function birdAt(time: number): Point {
    if (bird.mode === "perched") return perch();
    if (bird.mode === "in") {
      const p = ease(clamp((time - bird.start) / 1.8, 0, 1));
      const [x, y] = perch();
      return [lerp(frame.perch + 90, x, p), lerp(-10, y, p) - 22 * Math.sin(Math.PI * p)];
    }
    if (bird.mode === "out") {
      const p = clamp((time - bird.start) / 1.3, 0, 1);
      return [bird.from[0] + 120 * p, bird.from[1] - 90 * p * p];
    }
    return [0, -50];
  }
  function flyAway(time: number): void {
    bird.from = birdAt(time);
    bird.mode = "out";
    bird.start = time;
  }

  function rotate([x, y]: Point, degrees: number, [cx, cy]: Point): Point {
    const a = (degrees * Math.PI) / 180;
    const cos = Math.cos(a);
    const sin = Math.sin(a);
    return [cx + (x - cx) * cos - (y - cy) * sin, cy + (x - cx) * sin + (y - cy) * cos];
  }
  /** Where a point of the head is drawn, once the head and the body are posed. */
  function posed(point: Point): Point {
    const [x, y] = rotate(point, tilt, [100, 108]);
    return [100 + (x + headX - 100) * scaleX, 188 + (y + headY - 188) * scaleY + hop];
  }
  function bead(side: "L" | "R"): Point {
    const top = side === "L" ? 44 : 156;
    const angle = swing[side][0];
    return posed([top + 15 * Math.sin(angle), 60 + 15 * Math.cos(angle)]);
  }

  function setMood(next: Mood, time: number): void {
    if (next === mood) return;
    mood = next;
    since = time;
    fidget = null;
    if (next === "answer") {
      swing.L[1] += 2.2;
      swing.R[1] -= 2.2;
      swing.C[1] += 1.5;
    }
    if (next !== "idle" && (bird.mode === "in" || bird.mode === "perched")) flyAway(time);
  }

  function draw(time: number, step: number): void {
    const k = 1 - Math.exp(-step * 7);
    const s = time - since;
    const resting = mood === "idle";

    // Fidgets and gusts, at rest only.
    if (resting && fidget === null && time > nextFidget) {
      const kinds = Object.keys(FIDGETS) as Fidget[];
      const kind = kinds[Math.floor(Math.random() * kinds.length)] ?? "look";
      fidget = { kind, start: time, side: Math.random() < 0.5 ? "L" : "R" };
      if (kind === "spark") spark = { side: fidget.side, start: time };
    }
    const fp = fidget === null ? 0 : (time - fidget.start) / FIDGETS[fidget.kind];
    if (fidget !== null && fp >= 1) {
      fidget = null;
      nextFidget = time + between(2.5, 6);
    }
    if (resting && time > nextGust) {
      gust = time;
      nextGust = time + between(9, 16);
    }
    const wind = time - gust < 2.6 ? Math.sin((Math.PI * (time - gust)) / 2.6) : 0;

    // Targets of the pose.
    const breath = mood === "offline" ? Math.sin(time * 0.9) * 1.8 : Math.sin(time * 1.7);
    let toTilt = 0;
    let toHeadX = 0;
    let toHeadY = -0.8 * Math.sin(time * 1.7 + 0.6);
    let toEarL = 0;
    let toEarR = 0;
    let toWide = 1;
    let toDim = 1;
    let toCurrent = 0;
    let toBadge = 0;
    let sagBy = 0;
    let toScaleY = 1 + 0.012 * breath;
    const toScaleX = 1 - 0.004 * breath;
    if (hovered && resting) {
      toEarL = -9;
      toEarR = 9;
      toWide = 1.08;
    }
    if (mood === "listen") {
      toTilt = 7 * towards;
      toEarL = -12;
      toEarR = 12;
      toWide = 1.14;
      sagBy = -4;
    }
    if (mood === "think") {
      toTilt = -2 * towards;
      toHeadX = 0.4 * Math.sin(time * 37);
      toEarL = -6;
      toEarR = 6;
      toCurrent = 1;
    }
    if (mood === "answer") {
      toEarL = -10;
      toEarR = 10;
      toBadge = 1;
      sagBy = 6 * Math.sin(s * 9) * Math.exp(-s * 2.5);
    }
    if (mood === "refuse") {
      toTilt = 7 * Math.sin(s * 15) * Math.exp(-s * 2.6);
      toEarL = 16;
      toEarR = -16;
      toBadge = 1;
      sagBy = 5;
      toWide = 0.78;
    }
    if (mood === "offline") {
      toTilt = -6;
      toEarL = 20;
      toEarR = -20;
      toDim = 0.6;
      sagBy = 9;
    }
    if (fidget !== null && resting) {
      if (fidget.kind === "ear") {
        const flick = -18 * Math.sin(Math.PI * fp * 4) * (1 - fp);
        if (fidget.side === "L") toEarL += flick;
        else toEarR -= flick;
      }
      if (fidget.kind === "stretch") {
        const lift = Math.sin(Math.PI * fp);
        toHeadY -= 4 * lift;
        toScaleY += 0.025 * lift;
        toEarL -= 8 * lift;
        toEarR += 8 * lift;
      }
      if (fidget.kind === "hum") toTilt += 3 * Math.sin(fp * Math.PI * 6) * (1 - fp);
    }
    // A hop, then a squash on landing, when the answer is verified.
    const hopping = mood === "answer" && s < 0.5;
    if (mood === "answer" && s >= 0.5 && s < 0.75) {
      toScaleY -= 0.07 * Math.sin((Math.PI * (s - 0.5)) / 0.25);
    }

    const humming = fidget !== null && fidget.kind === "hum";
    tilt = mood === "refuse" || humming ? toTilt : lerp(tilt, toTilt, k);
    headX = mood === "think" ? toHeadX : lerp(headX, toHeadX, k);
    headY = lerp(headY, toHeadY, k);
    scaleX = lerp(scaleX, toScaleX, k);
    scaleY = mood === "answer" && s < 0.8 ? toScaleY : lerp(scaleY, toScaleY, k);
    hop = hopping ? -13 * Math.sin((Math.PI * s) / 0.5) : lerp(hop, 0, 1 - Math.exp(-step * 14));
    const flicking = fidget !== null && fidget.kind === "ear";
    const earK = flicking ? 1 : 1 - Math.exp(-step * 12);
    earL = lerp(earL, toEarL, earK);
    earR = lerp(earR, toEarR, earK);
    wide = lerp(wide, toWide, k);
    dim = lerp(dim, toDim, k);
    current = lerp(current, toCurrent, k);
    badge = lerp(badge, toBadge, 1 - Math.exp(-step * 9));

    // The insulators lag behind the head, and the wind pushes them.
    const push = 0.18 * wind * Math.sin(time * 5);
    const steps = Math.min(60, Math.ceil(step * 120));
    for (const side of ["L", "R", "C"] as const) {
      const target = (-tilt * Math.PI) / 180 + push;
      let [angle, speed] = swing[side];
      for (let i = 0; i < steps; i++) {
        speed += (-55 * (angle - target) - 3.2 * speed) * (step / steps);
        angle += speed * (step / steps);
      }
      swing[side] = [angle, speed];
    }

    // Blinks, now and then twice.
    if (time > nextBlink) {
      blinkEnd = time + 0.13;
      nextBlink = time + (Math.random() < 0.2 ? 0.28 : between(2.8, 6));
    }
    open = lerp(open, time < blinkEnd ? 0.08 : 1, Math.min(1, step * 30));

    // The eyes follow the pointer if it moved lately; otherwise each mood has its own look.
    if (time > nextWander) {
      wander = [between(-2.4, 2.4), between(-1.6, 1.2)];
      nextWander = time + between(1.2, 3.5);
    }
    let toGaze: Point = wander;
    if (fidget !== null && fidget.kind === "look") {
      toGaze = fp < 0.35 ? [-2.6, -0.4] : fp < 0.7 ? [2.6, -0.4] : [0, 0];
    }
    if (mood === "listen") toGaze = [2.2 * towards, 1.8];
    if (mood === "think") toGaze = [1.6 * towards + 0.6 * Math.sin(time * 2), -2.4];
    if (mood === "refuse") toGaze = [0, 2];
    if (performance.now() / 1000 - pointer.time < 3 && (resting || mood === "listen")) {
      const m = element.getScreenCTM();
      if (m !== null) {
        const [ex, ey] = posed([100, 82]);
        const dx = pointer.x - (m.a * ex + m.c * ey + m.e);
        const dy = pointer.y - (m.b * ex + m.d * ey + m.f);
        const distance = Math.hypot(dx, dy) || 1;
        const reach = Math.min(1, distance / 140) * 2.7;
        toGaze = [(dx / distance) * reach, (dy / distance) * reach * 0.8];
      }
    }
    const gazeK = 1 - Math.exp(-step * 10);
    gaze = [lerp(gaze[0], toGaze[0], gazeK), lerp(gaze[1], toGaze[1], gazeK)];

    // The pose.
    part("body").setAttribute(
      "transform",
      `translate(0 ${fixed(hop)}) translate(100 188) scale(${scaleX.toFixed(4)} ${scaleY.toFixed(4)}) translate(-100 -188)`,
    );
    part("head").setAttribute(
      "transform",
      `translate(${fixed(headX)} ${fixed(headY)}) rotate(${fixed(tilt)} 100 108)`,
    );
    part("earL").setAttribute("transform", `rotate(${fixed(earL)} 46 58)`);
    part("earR").setAttribute("transform", `rotate(${fixed(earR)} 154 58)`);
    for (const [side, top] of [
      ["L", "44 60"],
      ["R", "156 60"],
      ["C", "100 60"],
    ] as const) {
      const degrees = (swing[side][0] * 180) / Math.PI;
      part(`insulator${side}`).setAttribute("transform", `rotate(${fixed(degrees)} ${top})`);
    }
    const grounded = 1 - Math.min(1, -hop / 13);
    part("shadow").setAttribute("rx", fixed(36 * (0.7 + 0.3 * grounded)));
    part("shadow").setAttribute("opacity", (0.06 + 0.06 * grounded).toFixed(3));

    part("eyes").setAttribute("opacity", mood === "answer" || mood === "offline" ? "0" : "1");
    part("happy").setAttribute("opacity", mood === "answer" ? "1" : "0");
    part("asleep").setAttribute("opacity", mood === "offline" ? "1" : "0");
    const lid = Math.max(0, Math.min(1, open)) * wide;
    for (const [side, cx] of [
      ["L", 87],
      ["R", 113],
    ] as const) {
      part(`eye${side}`).setAttribute(
        "transform",
        `translate(${cx} 82) scale(${wide.toFixed(3)} ${Math.max(0.06, lid).toFixed(3)}) translate(${-cx} -82)`,
      );
      part(`pupil${side}`).setAttribute("cx", fixed(cx + gaze[0]));
      part(`pupil${side}`).setAttribute("cy", fixed(82 + gaze[1]));
      part(`glint${side}`).setAttribute("cx", fixed(cx + gaze[0] - 1));
      part(`glint${side}`).setAttribute("cy", fixed(82 + gaze[1] - 1.4));
    }
    const mouth = part("mouth");
    mouth.setAttribute("d", hovered && resting ? "M93 94 Q100 100 107 94" : MOUTHS[mood]);
    if (mood === "listen") {
      mouth.setAttribute("class", "pylon-line pylon-fill");
      mouth.removeAttribute("fill");
    } else {
      mouth.setAttribute("class", "pylon-line");
      mouth.setAttribute("fill", "none");
    }

    // The beads light up in turn while the API works.
    const lit = mood === "think" ? Math.floor(time * 5) % 3 : -1;
    ["beadL", "beadC", "beadR"].forEach((name, i) => {
      part(name).setAttribute("class", lit === i ? "pylon-current-fill" : "pylon-fill");
    });

    // The wires, and the current that runs along them.
    const sag = (i: 0 | 1): number =>
      (frame.sag[i] ?? 10) +
      2.5 * Math.sin(time * 1.3 + i * 1.7) +
      sagBy +
      7 * wind * Math.sin(time * 6 + i);
    wires = { L: hang(bead("L"), frame.left, sag(0)), R: hang(bead("R"), frame.right, sag(1)) };
    const left = path(wires.L);
    const right = path(wires.R);
    part("wireL").setAttribute("d", left);
    part("wireR").setAttribute("d", right);
    for (const [name, d] of [
      ["pulseL", left],
      ["pulseR", right],
    ] as const) {
      part(name).setAttribute("d", d);
      part(name).setAttribute("stroke-dashoffset", fixed((time * 42) % 17.2));
      part(name).setAttribute("opacity", current.toFixed(2));
    }

    // A spark comes in along a wire and lights the ears when it arrives.
    let burst = 0;
    if (spark !== null) {
      const p = (time - spark.start) / 1.1;
      if (p < 1) {
        const [x, y] = along(wires[spark.side], 1 - ease(p));
        part("spark").setAttribute("cx", fixed(x));
        part("spark").setAttribute("cy", fixed(y));
        part("spark").setAttribute("opacity", "1");
      } else {
        part("spark").setAttribute("opacity", "0");
        burst = Math.max(0, 1 - (p - 1) / 0.5);
        if (p > 1.5) spark = null;
      }
    } else {
      part("spark").setAttribute("opacity", "0");
    }
    if (mood === "answer" && s < 0.8) burst = Math.max(burst, 1 - s / 0.8);
    part("burst").setAttribute("opacity", burst.toFixed(2));

    // The badge over the head, and sleep.
    part("badge").setAttribute("opacity", badge.toFixed(2));
    part("badge").setAttribute(
      "transform",
      `translate(100 22) scale(${(0.5 + 0.5 * badge).toFixed(3)}) translate(-100 -22)`,
    );
    part("badgeDisc").setAttribute("class", mood === "refuse" ? "pylon-warn" : "pylon-good");
    part("badgeMark").setAttribute(
      "d",
      mood === "refuse" ? "M95 22 L105 22" : "M95 22 L99 26 L106 18",
    );
    if (mood === "offline") {
      const cycle = (time * 0.5) % 1;
      part("sleep").setAttribute("opacity", (Math.sin(Math.PI * cycle) * 0.9).toFixed(2));
      part("sleep").setAttribute(
        "transform",
        `translate(${fixed(4 * cycle)} ${fixed(-10 * cycle)})`,
      );
    } else {
      part("sleep").setAttribute("opacity", "0");
    }
    element.style.opacity = dim.toFixed(3);

    // The bird lands on the right wire at rest, and leaves when the mood changes.
    if (bird.mode !== "off") {
      if (bird.mode === "away" && resting && time > bird.next) {
        bird.mode = "in";
        bird.start = time;
      }
      if (bird.mode === "in" && time - bird.start > 1.8) {
        bird.mode = "perched";
        bird.start = time;
        bird.leave = time + between(7, 13);
      }
      if (bird.mode === "perched" && time > bird.leave) flyAway(time);
      if (bird.mode === "out" && time - bird.start > 1.3) {
        bird.mode = "away";
        bird.next = time + between(18, 34);
      }
      const flying = bird.mode === "in" || bird.mode === "out";
      const [x, y] = birdAt(time);
      part("bird").setAttribute("opacity", bird.mode === "away" ? "0" : "1");
      part("bird").setAttribute(
        "transform",
        `translate(${fixed(x)} ${fixed(y)}) scale(${bird.mode === "out" ? -1 : 1} 1)`,
      );
      part("perched").setAttribute("opacity", flying ? "0" : "1");
      part("flying").setAttribute("opacity", flying ? "1" : "0");
      part("wings").setAttribute(
        "d",
        Math.floor(time * 12) % 2 ? "M-1 -6 L-6 -13 M2 -6 L7 -13" : "M-1 -6 L-6 -2 M2 -6 L7 -2",
      );
      const peck =
        bird.mode === "perched" ? Math.max(0, Math.sin((time - bird.start) * 2.1)) ** 12 : 0;
      part("birdHead").setAttribute("transform", `rotate(${fixed(-28 * peck)} -2 -7)`);
    }
  }

  return {
    element,
    setMood,
    draw,
    get hovered() {
      return hovered;
    },
    set hovered(value: boolean) {
      hovered = value;
    },
  };
}
