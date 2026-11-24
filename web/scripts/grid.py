"""Build public/grid/france.json, the map of the hour-by-hour chapter, from open data.

Inputs, downloaded by hand into a folder given as the first argument:
- ne_50m_admin_0_countries.geojson: Natural Earth 1:50m countries (public domain).
- lines.json: Overpass export of the 400 kV lines, `way["power"="line"]["voltage"~"400000"]`
  in the box 41.2,-5.3,51.2,9.7, `out geom` (OpenStreetMap, ODbL).
- plants.json: Overpass export of `nwr["power"="plant"]["plant:source"]` in the same box,
  `out center tags` (OpenStreetMap, ODbL).

Coordinates are rounded to 0.001 degree; lines are simplified to 0.004 degree (about 400 m).
"""

import itertools
import json
import math
import re
import sys
from pathlib import Path

BOX = (-5.6, 41.2, 9.8, 51.3)
NEIGHBOURS = {"BEL", "LUX", "DEU", "CHE", "ITA", "ESP", "AND", "MCO", "GBR", "NLD", "AUT"}
SOURCES = {
    "nuclear": "nucleaire",
    "hydro": "hydraulique",
    "gas": "gaz",
    "coal": "charbon",
    "oil": "fioul",
    "wind": "eolien",
    "solar": "solaire",
    "biomass": "bioenergies",
    "biogas": "bioenergies",
    "waste": "bioenergies",
}
# Smallest plant kept, in MW: below, a plant is a dot too small to see at the scale of France.
MIN_MW = {
    "nucleaire": 500,
    "hydraulique": 50,
    "gaz": 50,
    "charbon": 50,
    "fioul": 50,
    "eolien": 40,
    "solaire": 40,
    "bioenergies": 40,
}


def simplify(points, tolerance):
    """Douglas-Peucker."""
    if len(points) < 3:
        return points
    (x1, y1), (x2, y2) = points[0], points[-1]
    dx, dy = x2 - x1, y2 - y1
    norm = math.hypot(dx, dy) or 1e-12
    index, distance = 0, 0.0
    for i in range(1, len(points) - 1):
        x, y = points[i]
        d = abs(dy * x - dx * y + x2 * y1 - y2 * x1) / norm
        if d > distance:
            index, distance = i, d
    if distance <= tolerance:
        return [points[0], points[-1]]
    return simplify(points[: index + 1], tolerance)[:-1] + simplify(points[index:], tolerance)


def simplify_ring(ring, tolerance):
    """Douglas-Peucker on a closed ring, split at its farthest point from the first."""
    x0, y0 = ring[0]
    far = max(range(len(ring)), key=lambda i: math.hypot(ring[i][0] - x0, ring[i][1] - y0))
    return simplify(ring[: far + 1], tolerance)[:-1] + simplify(ring[far:], tolerance)


def inside(point, rings):
    x, y = point
    hit = False
    for ring in rings:
        for (x1, y1), (x2, y2) in zip(ring, ring[1:] + ring[:1], strict=False):
            if (y1 > y) != (y2 > y) and x < (x2 - x1) * (y - y1) / (y2 - y1) + x1:
                hit = not hit
    return hit


def distance(point, ring):
    """Distance in degrees from `point` to the nearest edge of `ring`."""
    x, y = point
    best = math.inf
    for (x1, y1), (x2, y2) in zip(ring, ring[1:] + ring[:1], strict=False):
        dx, dy = x2 - x1, y2 - y1
        t = max(0.0, min(1.0, ((x - x1) * dx + (y - y1) * dy) / ((dx * dx + dy * dy) or 1e-12)))
        best = min(best, math.hypot(x - x1 - t * dx, y - y1 - t * dy))
    return best


def short(name):
    """ "Centrale nucléaire de Flamanville" becomes "Flamanville"."""
    name = re.sub(
        r"^(Centre Nucléaire de Production d'Electricité|Centrale (nucléaire|hydroélectrique|"
        r"thermique|électrique)?)\s*(de la |de l'|du |des |de |d')?",
        "",
        name,
        flags=re.I,
    )
    return re.sub(r"^à cycle combiné gaz (de |du |d')?", "", name, flags=re.I).strip()


def km(points):
    total = 0.0
    for (x1, y1), (x2, y2) in itertools.pairwise(points):
        mean = math.radians((y1 + y2) / 2)
        total += math.hypot((x2 - x1) * math.cos(mean), y2 - y1) * 111.2
    return total


def rnd(points):
    return [[round(x, 3), round(y, 3)] for x, y in points]


def mw(text):
    # A value without a unit is ambiguous in OpenStreetMap: it is left out.
    match = re.match(r"\s*([\d\s.,]+)\s*(GW|MW|kW|W)", text or "", re.I)
    if not match:
        return None
    try:
        value = float(match.group(1).replace(" ", "").replace(",", "."))
    except ValueError:
        return None
    unit = match.group(2).upper()
    return value * {"GW": 1000, "MW": 1, "KW": 0.001, "W": 1e-6}[unit]


def main(folder: Path, out: Path) -> None:
    countries = json.loads((folder / "ne_50m_admin_0_countries.geojson").read_text())
    france, neighbours = [], []
    for feature in countries["features"]:
        code = feature["properties"]["ADM0_A3"]
        if code != "FRA" and code not in NEIGHBOURS:
            continue
        geometry = feature["geometry"]
        multi = geometry["type"] == "MultiPolygon"
        polygons = geometry["coordinates"] if multi else [geometry["coordinates"]]
        for polygon in polygons:
            ring = polygon[0]
            xs, ys = [p[0] for p in ring], [p[1] for p in ring]
            if max(xs) < BOX[0] or min(xs) > BOX[2] or max(ys) < BOX[1] or min(ys) > BOX[3]:
                continue
            simple = rnd(simplify_ring(ring, 0.01))
            (france if code == "FRA" else neighbours).append(simple)

    lines, length, crossing = [], 0.0, 0
    for way in json.loads((folder / "lines.json").read_text())["elements"]:
        points = [(p["lon"], p["lat"]) for p in way.get("geometry", [])]
        if len(points) < 2 or way["tags"].get("operator") != "RTE":
            continue
        length += km(points)
        border = not all(inside(p, france) for p in (points[0], points[-1]))
        crossing += border
        lines.append({"p": rnd(simplify(points, 0.004)), "b": 1 if border else 0})

    plants = []
    for element in json.loads((folder / "plants.json").read_text())["elements"]:
        tags = element["tags"]
        source = SOURCES.get(tags.get("plant:source", "").split(";")[0])
        power = mw(tags.get("plant:output:electricity"))
        point = (
            (element["lon"], element["lat"])
            if "lon" in element
            else (element["center"]["lon"], element["center"]["lat"])
        )
        if source is None or power is None or power < MIN_MW[source]:
            continue
        # Above this, a value is a typing error: the largest plant that is not nuclear is 1.8 GW.
        if power > (6000 if source == "nucleaire" else 2000):
            continue
        # The coast is simplified: a plant on it, or offshore, may fall just outside France.
        near = min(distance(point, ring) for ring in france) < 0.35
        abroad = any(inside(point, [ring]) for ring in neighbours)
        if not (inside(point, france) or (near and not abroad)):
            continue
        plants.append(
            {
                "n": short(tags.get("name", "")),
                "s": source,
                "mw": round(power),
                "c": [round(point[0], 3), round(point[1], 3)],
            }
        )
    plants.sort(key=lambda p: -p["mw"])

    data = {
        "source": "OpenStreetMap (ODbL), Natural Earth (domaine public)",
        "lines_km": round(length),
        "lines_crossing": crossing,
        "france": france,
        "neighbours": neighbours,
        "lines": lines,
        "plants": plants,
    }
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(data, separators=(",", ":"), ensure_ascii=False))


if __name__ == "__main__":
    main(Path(sys.argv[1]), Path(__file__).parent.parent / "public" / "grid" / "france.json")
