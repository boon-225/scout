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
and customers/scout/store/images/ source SVGs for the Play Store icon and feature graphic.
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
    """Mark + "Scout" wordmark side by side (welcome screen header)."""
    ww, wh, wd = word("word_scout.txt")
    wk = 0.83                       # wordmark height relative to the mark
    gap = 52
    wx = MARK_W + gap
    width = wx + ww * wk
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{width:.0f}" height="100" viewBox="0 0 {width:.2f} 100">\n'
            + svg_mark(mark_s, mark_pin, -MARK_X0, 0, 1) +
            f'  <path fill="{word_col}" fill-rule="evenodd" transform="translate({wx:.2f},{(100 - wh * wk) / 2 + 2:.2f}) scale({wk})" d="{wd}"/>\n'
            "</svg>\n")


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
    print("assets written to", ASSETS)


if __name__ == "__main__":
    main()
