#!/usr/bin/env python3
"""Build Scout's app assets from the "Trail S" artwork (traced vector paths in this folder).

Usage (from the repository root):
    python3 customers/scout/design/make_assets.py

Writes customers/scout/assets/:
    logo.svg                                square app logo (About page, cloud sign-in, avatar)
    android/launcher_scout*.xml             adaptive launcher icon (background, foreground, monochrome)
    android/scout_vector.xml                splash screen logo
    android/notification_icon.xml           status-bar icon (white silhouette)
    theme_icons/*.svg                       cloud icons (light + _dark), welcome lockup, cloud card icon
and customers/scout/store/ Play Store icon and feature graphic (PNG rendering needs playwright).
Requires: shapely (for the cloud icons).
"""
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ASSETS = os.path.join(os.path.dirname(HERE), "assets")
STORE = os.path.join(os.path.dirname(HERE), "store")

INDIGO = "#22324A"
OFFWHITE = "#F1F5EC"
GREEN = "#7CC24A"

S_PATH, PIN_PATH = [l.strip() for l in open(os.path.join(HERE, "trail_mark.txt")) if l.strip()]
# the mark is drawn in a 100 x 100 box; it spans x 8.8 .. 91.2
MARK_X0, MARK_W = 8.8, 82.4


def word(name):
    lines = [l.strip() for l in open(os.path.join(HERE, name)) if l.strip()]
    w, h = lines[0].split()
    return float(w), float(h), lines[1]


def rounded_square(x, y, size, r):
    k = 0.5523 * r
    x2, y2 = x + size, y + size
    return (f"M{x + r},{y} L{x2 - r},{y} C{x2 - r + k},{y} {x2},{y + r - k} {x2},{y + r} "
            f"L{x2},{y2 - r} C{x2},{y2 - r + k} {x2 - r + k},{y2} {x2 - r},{y2} "
            f"L{x + r},{y2} C{x + r - k},{y2} {x},{y2 - r + k} {x},{y2 - r} "
            f"L{x},{y + r} C{x},{y + r - k} {x + r - k},{y} {x + r},{y} Z")


def svg_mark(s_col, pin_col, tx, ty, k):
    return (f'  <g transform="translate({tx:.3f},{ty:.3f}) scale({k:.5f})">\n'
            f'    <path fill="{s_col}" fill-rule="evenodd" d="{S_PATH}"/>\n'
            f'    <path fill="{pin_col}" fill-rule="evenodd" d="{PIN_PATH}"/>\n  </g>\n')


def tile_svg(size, radius, mark_frac=0.52):
    """Indigo (rounded) square with the off-white S and green pin centred."""
    k = size * mark_frac / 100
    t = size / 2 - 50 * k
    bg = rounded_square(0, 0, size, radius) if radius else f"M0,0H{size}V{size}H0Z"
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{size}" height="{size}" viewBox="0 0 {size} {size}">\n'
            f'  <path fill="{INDIGO}" d="{bg}"/>\n' + svg_mark(OFFWHITE, GREEN, t, t, k) + "</svg>\n")


def lockup_svg(mark_s, mark_pin, word_col):
    """The trail S is the first letter: mark + "cout" (welcome screen header, store banner)."""
    import re
    ww, wh, wd = word("word_scout.txt")
    letters = re.findall(r"M[^M]*", wd)
    cout = "".join(letters[1:])     # drop the wordmark's own S (first outline)
    c_x0 = 77.5                     # where "c" starts in the wordmark
    mark_right = 90.0               # right edge of the trail S body (mark units)
    gap = 8
    wx = (mark_right - MARK_X0) + gap - c_x0
    width = (mark_right - MARK_X0) + gap + (ww - c_x0)
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{width:.0f}" height="100" viewBox="0 0 {width:.2f} 100">\n'
            + svg_mark(mark_s, mark_pin, -MARK_X0, 0, 1) +
            f'  <path fill="{word_col}" fill-rule="evenodd" transform="translate({wx:.2f},0)" d="{cout}"/>\n'
            "</svg>\n")


FEATURE_HTML = """<!doctype html><html><head><meta charset="utf-8"><style>
html,body{{margin:0}} body{{width:1024px;height:500px;background:{indigo};position:relative;overflow:hidden;font-family:Inter,sans-serif}}
.lock{{position:absolute;left:100px;top:160px}}
.tag{{position:absolute;left:102px;top:300px;color:{offwhite};font-size:40px;font-weight:500;letter-spacing:0.2px}}
.trail{{position:absolute;left:0;top:0}}
</style></head><body>
<svg class="trail" width="1024" height="500" viewBox="0 0 1024 500">
  <path d="M600,430 C700,420 690,300 790,280 S900,200 905,150" fill="none" stroke="{green}" stroke-width="9" stroke-linecap="round" stroke-dasharray="0 26" opacity="0.9"/>
  <g transform="translate(905,140)">
    <path d="M0,-58 a40,40 0 0 1 40,40 c0,30 -40,62 -40,62 c0,0 -40,-32 -40,-62 a40,40 0 0 1 40,-40z" fill="{green}"/>
    <circle cx="0" cy="-18" r="14" fill="{indigo}"/>
  </g>
</svg>
<svg class="lock" width="{w:.0f}" height="110" viewBox="0 0 {lw:.2f} 100">{lock}</svg>
<div class="tag">{tagline}</div>
</body></html>
"""


def feature_graphic_html(tagline):
    import re
    lock = lockup_svg(OFFWHITE, GREEN, OFFWHITE)
    lw = float(re.search(r'viewBox="0 0 ([\d.]+) 100"', lock).group(1))
    body = lock.split("\n", 1)[1].rsplit("</svg>", 1)[0]
    return FEATURE_HTML.format(indigo=INDIGO, offwhite=OFFWHITE, green=GREEN, w=lw * 1.1, lw=lw, lock=body,
                               tagline=tagline.replace("&", "&amp;"))


def render_png(html_path, png_path, w, h):
    try:
        import asyncio
        from playwright.async_api import async_playwright
    except ImportError:
        print(f"playwright not installed: open {html_path} in a browser and save a {w}x{h} screenshot as {png_path}")
        return

    async def go():
        async with async_playwright() as p:
            b = await p.chromium.launch()
            pg = await b.new_page(viewport={"width": w, "height": h})
            await pg.set_content(open(html_path, encoding="utf-8").read())
            await pg.wait_for_timeout(300)
            await pg.screenshot(path=png_path)
            await b.close()
    asyncio.run(go())


def vector_xml(groups, size_dp=108, viewport=108, comment="Scout Trail S"):
    body = []
    for (tx, ty, k), paths in groups:
        body.append(f'    <group android:translateX="{tx:.3f}" android:translateY="{ty:.3f}" '
                    f'android:scaleX="{k:.5f}" android:scaleY="{k:.5f}">')
        for col, d in paths:
            body.append(f'        <path android:fillColor="{col}" android:fillType="evenOdd" android:pathData="{d}" />')
        body.append("    </group>")
    return (f'<?xml version="1.0" encoding="utf-8"?>\n<!-- {comment} (customers/scout/design/make_assets.py) -->\n'
            f'<vector xmlns:android="http://schemas.android.com/apk/res/android"\n'
            f'    android:width="{size_dp}dp" android:height="{size_dp}dp"\n'
            f'    android:viewportWidth="{viewport}" android:viewportHeight="{viewport}">\n' + "\n".join(body) + "\n</vector>\n")


def main():
    andr = os.path.join(ASSETS, "android")
    themes = os.path.join(ASSETS, "theme_icons")
    os.makedirs(andr, exist_ok=True)
    os.makedirs(themes, exist_ok=True)
    os.makedirs(os.path.join(STORE, "source"), exist_ok=True)

    open(os.path.join(ASSETS, "logo.svg"), "w").write(tile_svg(512, 112))

    # adaptive launcher icon: 108 x 108, the visible tile is about the middle 72
    k = 72 * 0.52 / 100
    t = 54 - 50 * k
    mark = [(OFFWHITE, S_PATH), (GREEN, PIN_PATH)]
    files = {
        "launcher_scout.xml": (
            '<?xml version="1.0" encoding="utf-8"?>\n'
            '<adaptive-icon xmlns:android="http://schemas.android.com/apk/res/android">\n'
            '    <background android:drawable="@drawable/launcher_scout_background" />\n'
            '    <foreground android:drawable="@drawable/launcher_scout_foreground" />\n'
            '    <monochrome android:drawable="@drawable/launcher_scout_monochrome" />\n'
            '</adaptive-icon>\n'),
        "launcher_scout_background.xml": vector_xml([((0, 0, 1), [(INDIGO, "M0,0h108v108h-108z")])]),
        "launcher_scout_foreground.xml": vector_xml([((t, t, k), mark)]),
        "launcher_scout_monochrome.xml": vector_xml([((t, t, k), [("#FFFFFF", S_PATH), ("#FFFFFF", PIN_PATH)])]),
    }
    # splash: rounded tile with the mark
    k2 = 108 * 0.52 / 100
    t2 = 54 - 50 * k2
    files["scout_vector.xml"] = vector_xml([((0, 0, 1), [(INDIGO, rounded_square(0, 0, 108, 24))]), ((t2, t2, k2), mark)])
    # status bar: white silhouette, 24 dp
    k3 = 0.20
    t3 = 12 - 50 * k3
    files["notification_icon.xml"] = vector_xml([((t3, t3, k3), [("#FFFFFF", S_PATH), ("#FFFFFF", PIN_PATH)])],
                                                size_dp=24, viewport=24)
    for name, text in files.items():
        open(os.path.join(andr, name), "w").write(text)

    # welcome screen lockup (light / dark theme)
    open(os.path.join(themes, "brand_lockup.svg"), "w").write(lockup_svg(INDIGO, GREEN, INDIGO))
    open(os.path.join(themes, "brand_lockup_dark.svg"), "w").write(lockup_svg(OFFWHITE, GREEN, OFFWHITE))
    # cloud icons
    subprocess.check_call([sys.executable, os.path.join(HERE, "trail_icons.py"), themes])

    # Play Store sources (rendered to PNG by store/render.py)
    open(os.path.join(STORE, "source", "icon.svg"), "w").write(tile_svg(512, 0, 0.54))
    open(os.path.join(STORE, "source", "lockup_dark.svg"), "w").write(lockup_svg(OFFWHITE, GREEN, OFFWHITE))
    fg = os.path.join(STORE, "source", "feature_graphic.html")
    open(fg, "w", encoding="utf-8").write(feature_graphic_html("Field Data & Insights"))
    icon_html = os.path.join(STORE, "source", "icon.html")
    open(icon_html, "w").write('<!doctype html><html><body style="margin:0">' + tile_svg(512, 0, 0.54) + "</body></html>")
    os.makedirs(os.path.join(STORE, "images"), exist_ok=True)
    render_png(fg, os.path.join(STORE, "images", "featureGraphic.png"), 1024, 500)
    render_png(icon_html, os.path.join(STORE, "images", "icon.png"), 512, 512)
    print("assets written to", ASSETS)


if __name__ == "__main__":
    main()
