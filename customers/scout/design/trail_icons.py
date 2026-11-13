#!/usr/bin/env python3
"""Scout "Trail" cloud icons, drawn as clean vector geometry (light and dark variants).

Usage: python3 trail_icons.py OUTDIR
Writes QField theme icon overrides (same file names as QField's) plus *_dark.svg variants.
Shapes follow the "Scout Cloud icons - Trail style" sheet: cloud, map with dotted trail, pin,
arrows and "!" are cut out of the shapes, so they read on any background and when tinted.
"""
import math
import os
import sys

from shapely import affinity
from shapely.geometry import LineString, Point, Polygon, box
from shapely.ops import unary_union

Q = 32  # circle smoothness

LIGHT = dict(cloud="#22324A", map="#22324A", trail="#5FA732", pin="#5FA732", grey="#9AA4B2",
             red="#D64545", hub_pin="#7CC24A", white="#FFFFFF")
DARK = dict(cloud="#7CC24A", map="#DCE3EC", trail="#7CC24A", pin="#7CC24A", grey="#5E6878",
            red="#E25A4A", hub_pin=None, white="#FFFFFF")


# ---------- primitives (units: 271-wide cloud) ----------
def cloud(x=0, y=0, w=271):
    s = w / 271
    g = unary_union([Point(65, 119).buffer(65, Q), Point(141, 80).buffer(80, Q),
                     Point(210, 123).buffer(61, Q), box(65, 119, 210, 184)])
    return affinity.translate(affinity.scale(g, s, s, origin=(0, 0)), x, y)


def pin(cx, cy, r, tip):
    """Map pin: head circle radius r centred at (cx, cy), point `tip` below the centre."""
    a = math.acos(r / tip)
    pts = [(cx - r * math.sin(a), cy + r * math.cos(a)), (cx, cy + tip), (cx + r * math.sin(a), cy + r * math.cos(a))]
    g = unary_union([Point(cx, cy).buffer(r, Q), Polygon(pts)])
    return g.buffer(-2, Q).buffer(2, Q)  # soften the tip


def stroke(points, w, cap=1):
    return LineString(points).buffer(w / 2, Q, cap_style=cap, join_style=1)


def arrow(x, y0, y1, w, head):
    """Vertical arrow from y0 (tail) to y1 (point)."""
    d = 1 if y1 > y0 else -1
    shaft = stroke([(x, y0), (x, y1 - d * w * 0.3)], w)
    chevron = stroke([(x - head, y1 - d * head), (x, y1), (x + head, y1 - d * head)], w)
    return unary_union([shaft, chevron])


def cloud_parts(x, y, w):
    """Handy reference points inside a cloud placed at (x, y) with width w."""
    h = w * 184 / 271
    return (lambda fx: x + fx * w), (lambda fy: y + fy * h), w


# ---------- glyphs cut out of a cloud ----------
def glyph(kind, x, y, w):
    X, Y, w = cloud_parts(x, y, w)
    sw = 0.08 * w
    if kind == "up":
        return arrow(X(0.47), Y(0.93), Y(0.43), sw * 0.95, 0.14 * w)
    if kind == "down":
        return arrow(X(0.47), Y(0.42), Y(0.90), sw * 0.95, 0.14 * w)
    if kind == "sync":
        return unary_union([arrow(X(0.31), Y(0.91), Y(0.37), sw, 0.12 * w),
                            arrow(X(0.61), Y(0.37), Y(0.89), sw, 0.12 * w)])
    if kind == "alert":
        return unary_union([stroke([(X(0.455), Y(0.42)), (X(0.455), Y(0.66))], 0.115 * w),
                            Point(X(0.455), Y(0.86)).buffer(0.066 * w, Q)])
    if kind == "plus":
        return unary_union([stroke([(X(0.47), Y(0.42)), (X(0.47), Y(0.88))], sw),
                            stroke([(X(0.30), Y(0.65)), (X(0.64), Y(0.65))], sw)])
    if kind == "slash":
        return stroke([(X(0.16), Y(0.02)), (X(0.84), Y(0.98))], 0.075 * w)
    if kind == "pin":
        return pin(X(0.454), Y(0.543), 0.181 * w, 0.273 * w)
    raise ValueError(kind)


# ---------- compositions ----------
def single_cloud(kind, col, colors):
    """24dp-style icon: one cloud, glyph cut out (stays readable when the app tints it)."""
    c = cloud(0, 0, 271)
    layers = []
    if kind == "pin":
        p = glyph("pin", 0, 0, 271)
        hx, hy = 0.454 * 271, 0.543 * 184
        body = c.difference(p).union(Point(hx, hy).buffer(0.065 * 271, Q))
        layers.append((colors[col], body))
    elif kind == "slash":
        g = glyph("slash", 0, 0, 271)
        layers.append((colors[col], c.difference(g.buffer(14, Q)).union(g)))
    elif kind:
        layers.append((colors[col], c.difference(glyph(kind, 0, 0, 271))))
    else:
        layers.append((colors[col], c))
    return layers


def hub(colors, dark):
    """'Scout Cloud projects': cloud with a pin (multicolour in light, cut-out pin in dark)."""
    if dark:
        return single_cloud("pin", "cloud", colors)
    c = cloud(0, 0, 271)
    p = glyph("pin", 0, 0, 271)
    hx, hy = 0.454 * 271, 0.543 * 184
    pin_ring = p.difference(Point(hx, hy).buffer(0.065 * 271, Q))
    return [(colors["cloud"], c), (colors["hub_pin"], pin_ring)]


def project(colors, map_col="map", trail_col="trail", pin_col="pin", cloud_col="cloud", kind=None):
    """Folded map with dotted trail, pin top right, small cloud bottom right (with optional glyph)."""
    sw = 14
    outline = [(765, 95), (828, 72), (890, 97), (952, 74), (952, 240), (890, 265), (828, 240), (765, 265), (765, 95)]
    m = unary_union([stroke(outline, sw), stroke([(828, 72), (828, 240)], sw), stroke([(890, 97), (890, 265)], sw)])
    dots = unary_union([Point(px, py).buffer(9, Q) for px, py in
                        [(791, 214), (813, 196), (837, 184), (861, 172), (884, 160), (906, 143), (931, 134), (955, 147)]])
    pn = pin(994, 93, 45, 70)
    hole = Point(994, 93).buffer(16, Q)
    cw = 185
    cx, cy = 883, 197
    cl = cloud(cx, cy, cw)
    gap_c, gap_p = 9, 7
    m = m.difference(cl.buffer(gap_c, Q)).difference(pn.buffer(gap_p, Q))
    dots = dots.difference(cl.buffer(gap_c, Q)).difference(pn.buffer(gap_p, Q))
    pn = pn.difference(cl.buffer(gap_c, Q)).difference(hole)
    if kind == "slash":
        g = glyph(kind, cx, cy, cw)
        cl = cl.difference(g.buffer(9, Q)).union(g)
    elif kind:
        cl = cl.difference(glyph(kind, cx, cy, cw))
    return [(colors[map_col], m), (colors[trail_col], dots), (colors[pin_col], pn), (colors[cloud_col], cl)]


# ---------- SVG output ----------
def path_d(geom, ox, oy, k):
    polys = getattr(geom, "geoms", [geom])
    out = []

    def ring(coords):
        pts = [((px - ox) * k, (py - oy) * k) for px, py in list(coords)[:-1]]
        return "M" + " ".join(f"{a:.2f},{b:.2f}" for a, b in pts) + "Z"

    for p in polys:
        if p.is_empty or p.geom_type != "Polygon":
            continue
        p = p.simplify(0.15, preserve_topology=True)
        out.append(ring(p.exterior.coords))
        out.extend(ring(i.coords) for i in p.interiors)
    return "".join(out)


def svg(layers, size, pad=0.04, view=48):
    allg = unary_union([g for _, g in layers])
    x0, y0, x1, y1 = allg.bounds
    side = max(x1 - x0, y1 - y0) * (1 + 2 * pad)
    ox, oy = (x0 + x1) / 2 - side / 2, (y0 + y1) / 2 - side / 2
    k = view / side
    body = "\n".join(f'  <path fill="{c}" fill-rule="evenodd" d="{path_d(g, ox, oy, k)}"/>' for c, g in layers if not g.is_empty)
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{size}" height="{size}" viewBox="0 0 {view} {view}">\n'
            f"{body}\n</svg>\n")


def build(out):
    os.makedirs(out, exist_ok=True)
    files = {}
    for dark, colors in ((False, LIGHT), (True, DARK)):
        sfx = "_dark" if dark else ""
        # 24 dp single clouds (tinted by the app in most places)
        for name, kind in [("ic_cloud_active_24dp", "pin"), ("ic_cloud_synchronize_24dp", "sync"),
                           ("ic_cloud_upload_24dp", "up"), ("ic_cloud_download_24dp", "down"),
                           ("ic_cloud_off_24dp", "slash")]:
            files[name + sfx] = svg(single_cloud(kind, "cloud", colors), 24)
        files["ic_cloud_attention_24dp" + sfx] = svg(single_cloud("alert", "red", colors), 24)
        files["brand_cloud_projects_48dp" + sfx] = svg(hub(colors, dark), 48)
        # 48 dp project icons (shown in full colour in project lists)
        variants = {
            "ic_cloud_project": project(colors),
            "ic_cloud_project_upload": project(colors, kind="up"),
            "ic_cloud_project_download": project(colors, map_col="grey", trail_col="grey", pin_col="grey", kind="down"),
            "ic_cloud_project_failed": project(colors, cloud_col="red", kind="alert"),
            "ic_cloud_project_localonly": project(colors, cloud_col="grey"),
            "ic_cloud_project_offline": project(colors, cloud_col="grey", kind="slash"),
            "ic_cloud_project_template": project(colors, kind="plus"),
        }
        for base, layers in variants.items():
            s = svg(layers, 48)
            files[f"{base}_48dp{sfx}"] = s
            files[f"{base}_param_48dp{sfx}"] = s
    files["ic_cloud_white_24dp"] = svg(single_cloud(None, "white", LIGHT), 24)
    for name, s in files.items():
        open(os.path.join(out, name + ".svg"), "w", encoding="utf-8").write(s)
    print(f"wrote {len(files)} icons to {out}")


if __name__ == "__main__":
    build(sys.argv[1])
