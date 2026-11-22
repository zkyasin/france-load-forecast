/** What the charts share: colors from the page's CSS, and redrawing at the width of their box. */

export interface Colors {
  paper: string;
  ink: string;
  muted: string;
  rule: string;
  forecast: string;
  measured: string;
  third: string;
  fourth: string;
}

/** The colors of the current color scheme, set in style.css. */
export function colors(): Colors {
  const style = getComputedStyle(document.documentElement);
  const read = (name: string) => style.getPropertyValue(`--${name}`).trim();
  return {
    paper: read("paper"),
    ink: read("ink"),
    muted: read("muted"),
    rule: read("rule"),
    forecast: read("forecast"),
    measured: read("measured"),
    third: read("third"),
    fourth: read("fourth"),
  };
}

/** Options shared by every plot. */
export const frame = (width: number, colors: Colors) => ({
  width,
  style: {
    background: "transparent",
    color: colors.muted,
    fontFamily: "inherit",
    fontSize: "13px",
    overflow: "visible",
  },
});

/**
 * Options of the hover tip, in the colors of the page. A tip with no y hangs from the top of the
 * frame, where Plot turns it left or right near the edges; on a phone its lines wrap sooner. Both
 * keep it whole on a small screen.
 */
export const tipStyle = (colors: Colors, width: number) => ({
  fill: colors.paper,
  stroke: colors.rule,
  textPadding: 8,
  pathFilter: "none",
  frameAnchor: "top" as const,
  preferredAnchor: "top" as const,
  lineWidth: width < 480 ? 13 : 20,
});

/**
 * Draws `draw` in `box` at the width of the box, and again whenever that width or the color scheme
 * changes. Returns a function that draws it again, after its data changed.
 */
export function drawIn(box: HTMLElement, draw: (width: number, colors: Colors) => Element) {
  let width = 0;
  const redraw = () => {
    width = box.clientWidth;
    box.replaceChildren(draw(width, colors()));
  };
  new ResizeObserver(() => {
    if (box.clientWidth !== width) redraw();
  }).observe(box);
  matchMedia("(prefers-color-scheme: dark)").addEventListener("change", redraw);
  redraw();
  return redraw;
}

/** Replaces the content of `table`: one row per entry of `body`, its first cells as row headers. */
export function fillTable(
  table: HTMLTableElement,
  header: string[],
  body: string[][],
  rowHeaders = 1,
): void {
  table.replaceChildren();
  const head = table.createTHead().insertRow();
  for (const text of header) {
    const cell = document.createElement("th");
    cell.scope = "col";
    cell.textContent = text;
    head.append(cell);
  }
  const rows = table.createTBody();
  for (const values of body) {
    const row = rows.insertRow();
    values.forEach((text, index) => {
      const cell = document.createElement(index < rowHeaders ? "th" : "td");
      if (index < rowHeaders) cell.setAttribute("scope", "row");
      cell.textContent = text;
      row.append(cell);
    });
  }
}

/** The element with this id, which the page must have. */
export function byId<T extends HTMLElement = HTMLElement>(id: string): T {
  const element = document.getElementById(id);
  if (element === null) throw new Error(`#${id} is missing from the page`);
  return element as T;
}
