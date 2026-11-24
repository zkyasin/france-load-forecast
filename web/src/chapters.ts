/**
 * The menu of chapters in the masthead: a button that shows every chapter, closed by Escape, by a
 * click outside or by the choice of a link, and the chapter in the middle of the screen marked in
 * the masthead as the page scrolls.
 */

/** The index that a key moves the focus to in a list of `count` links, or null for other keys. */
export function step(index: number, count: number, key: string): number | null {
  if (count === 0) return null;
  switch (key) {
    case "ArrowDown":
      return index < 0 ? 0 : (index + 1) % count;
    case "ArrowUp":
      return index < 0 ? count - 1 : (index - 1 + count) % count;
    case "Home":
      return 0;
    case "End":
      return count - 1;
    default:
      return null;
  }
}

function menu(root: HTMLElement, toggle: HTMLButtonElement, list: HTMLElement): void {
  // Pointe, Évolution and Questions may be hidden: only the links shown take the focus.
  const links = () => [...list.querySelectorAll<HTMLAnchorElement>("li:not([hidden]) > a")];
  const isOpen = () => toggle.getAttribute("aria-expanded") === "true";
  function show(open: boolean, focus?: "toggle" | number): void {
    toggle.setAttribute("aria-expanded", String(open));
    list.hidden = !open;
    if (focus === "toggle") toggle.focus();
    else if (typeof focus === "number") links()[focus]?.focus();
  }

  toggle.addEventListener("click", () => show(!isOpen()));
  root.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && isOpen()) {
      event.stopPropagation();
      show(false, "toggle");
      return;
    }
    const shown = links();
    const index = shown.indexOf(document.activeElement as HTMLAnchorElement);
    const next = step(index, shown.length, event.key);
    if (next === null || (event.target === toggle && !event.key.startsWith("Arrow"))) return;
    event.preventDefault();
    show(true, next);
  });
  list.addEventListener("click", (event) => {
    if ((event.target as Element).closest("a")) show(false);
  });
  document.addEventListener("pointerdown", (event) => {
    if (isOpen() && !root.contains(event.target as Node)) show(false);
  });
  root.addEventListener("focusout", (event) => {
    if (isOpen() && !root.contains(event.relatedTarget as Node | null)) show(false);
  });
}

/** Marks with aria-current the links of the masthead that lead to the chapter in view. */
function follow(masthead: HTMLElement): void {
  const links = [...masthead.querySelectorAll<HTMLAnchorElement>('a[href^="#"]:not(.brand)')];
  const byChapter = new Map<Element, HTMLAnchorElement[]>();
  for (const link of links) {
    const target = link.hash ? document.querySelector(link.hash) : null;
    const chapter = target?.closest("section") ?? target;
    if (!chapter) continue;
    byChapter.set(chapter, [...(byChapter.get(chapter) ?? []), link]);
  }
  const mark = (chapter: Element | null) => {
    for (const link of links) link.removeAttribute("aria-current");
    for (const link of (chapter && byChapter.get(chapter)) ?? []) {
      link.setAttribute("aria-current", "location");
    }
  };
  const current = () => {
    const link = links.find((each) => each.hasAttribute("aria-current"));
    return link ? [...byChapter].find(([, each]) => each.includes(link))?.[0] : undefined;
  };
  // A chapter is in view when it crosses a thin band at 40% of the height of the screen.
  const seen = new IntersectionObserver(
    (entries) => {
      for (const entry of entries) {
        if (entry.isIntersecting) mark(entry.target);
        else if (entry.target === current()) mark(null);
      }
    },
    { rootMargin: "-40% 0px -59% 0px" },
  );
  for (const chapter of byChapter.keys()) seen.observe(chapter);
}

export function render(): void {
  const masthead = document.getElementById("masthead");
  const root = masthead?.querySelector<HTMLElement>(".chapters");
  const toggle = root?.querySelector<HTMLButtonElement>(".chapters-toggle");
  const list = root?.querySelector<HTMLElement>(".chapters-menu");
  if (!masthead || !root || !toggle || !list) return;
  menu(root, toggle, list);
  follow(masthead);
}
