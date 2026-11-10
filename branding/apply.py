#!/usr/bin/env python3
"""Apply one client's branding to a CLEAN QField checkout, at build time.

Usage:
    python3 branding/apply.py customers/<key>/customer.yml <path to QField checkout> [--env-file out.env]

Nothing here is ever committed into QField's code: the build checks out QField at the
version in upstream.lock, runs this script on that copy, then compiles it.

Steps
  1. validate customer.yml
  2. app ID, app name, default server           (rebrand_ids.sh)
  3. on-screen wording QField -> app name        (rename_texts.py)
  4. links: QField documentation/website -> client help/support links
  5. About page                                  (overlays/QfAbout.qml)
  6. small patches: help search, mascot easter egg, translator link, plugin catalogue
  7. logos and launcher icon                     (customers/<key>/assets)
  8. colours                                     (theme.json from QField's, with client colours)
  9. NOTICE.md (GPL notice + list of changed files)
 10. scan: fail if any user-visible QField name or link is left (when upstream_name.visible is false)
 11. write build settings (env file) for CMake

Every patch checks that the code it changes still looks the way it did when the patch was
written. If a new QField release changes it, the build stops with a clear message instead of
silently shipping something wrong.
"""
import argparse
import glob
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys

import yaml

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)

# Upstream file fingerprints: the overlay was written against exactly these versions.
UPSTREAM_SHA256 = {
    "src/app/qml/QfAbout.qml": "fb7ca733874168bd02b4ffd0b0edb8061be046d76c77224b04fe92b4621f6989",  # QField v4.3.7
}

# Files where QField URLs are internal (never shown to users) and may remain.
INTERNAL_URL_ALLOW = {
    "src/core/utils/qfurlutils.cpp",        # qfield.org/action/ deep-link handling
    "src/core/utils/qfurlutils.h",
    "src/core/qfieldcloud/qfcloudstatus.cpp",  # status page only used for QField's own server
    "src/core/qfieldcloud/qfcloudstatus.h",
    "src/app/qfchangelogcontents.cpp",      # changelog feed; the changelog is not reachable (About replaced)
    "src/app/qml/QfChangelog.qml",
    "src/core/locator/qfhelplocatorfilter.cpp",  # documentation search; filter is unregistered (step 6)
    "src/core/locator/qfhelplocatorfilter.h",
}
QFIELD_URL = re.compile(r"https?://[A-Za-z0-9.-]*(qfield\.org|qfield\.cloud|opengis\.ch|github\.com/opengisch|transifex\.com/opengisch)[^\s\"'<>)]*")


def fail(msg):
    sys.exit(f"\nBRANDING FAILED: {msg}\n")


def info(msg):
    print(f"[branding] {msg}", flush=True)


# ---------------------------------------------------------------- 1. config
REQUIRED = ["client.key", "app.name", "app.cloud_name", "app.id", "app.icon", "server.url",
            "look.primary", "about.organisation", "about.support_email", "about.website"]


def get(cfg, dotted, default=None):
    cur = cfg
    for part in dotted.split("."):
        if not isinstance(cur, dict) or part not in cur:
            return default
        cur = cur[part]
    return cur


def validate(cfg):
    if "CHANGEME" in yaml.safe_dump(cfg):
        fail("customer.yml still contains CHANGEME placeholders: fill in every value first")
    missing = [k for k in REQUIRED if get(cfg, k) in (None, "")]
    if missing:
        fail("customer.yml is missing: " + ", ".join(missing))
    if not re.fullmatch(r"[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*){2,}", get(cfg, "app.id")):
        fail(f"app.id '{get(cfg, 'app.id')}' must look like com.example.app (lowercase, at least 3 parts)")
    if get(cfg, "app.id").startswith("ch.opengis."):
        fail("app.id must not use QField's ch.opengis prefix")
    if not re.fullmatch(r"https://[A-Za-z0-9.-]+(:[0-9]+)?", get(cfg, "server.url").rstrip("/")):
        fail("server.url must be https://host (no path)")
    if len(get(cfg, "app.name")) > 16:
        print(f"[branding] WARNING: app name '{get(cfg, 'app.name')}' is long and may be cut off under the icon")
    for k in ("look.primary", "look.accent_dark_theme", "look.highlight"):
        v = get(cfg, k)
        if v and not re.fullmatch(r"#[0-9A-Fa-f]{6}", v):
            fail(f"{k} must be a colour like #1E2742")


# ---------------------------------------------------------------- helpers
def read(path):
    with open(path, encoding="utf-8", errors="surrogateescape") as f:
        return f.read()


def write(path, text):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8", errors="surrogateescape", newline="") as f:
        f.write(text)


CHANGED = set()


def patch(qf, rel, old, new, count=1):
    """Replace `old` with `new` in qf/rel; `old` must occur exactly `count` times."""
    p = os.path.join(qf, rel)
    s = read(p)
    n = s.count(old)
    if n != count:
        fail(f"{rel}: expected {count} occurrence(s) of the code to patch, found {n}.\n"
             f"  Looking for: {old[:120]!r}\n  QField has probably changed here: review this patch in branding/apply.py.")
    write(p, s.replace(old, new))
    CHANGED.add(rel)


def qml_str(s):
    return s.replace("\\", "\\\\").replace('"', '\\"')


# ---------------------------------------------------------------- steps
def step_ids(cfg, qf):
    app_id = get(cfg, "app.id")
    prefix, suffix = app_id.rsplit(".", 1)
    subprocess.run(["bash", os.path.join(HERE, "rebrand_ids.sh"), get(cfg, "app.name"), prefix, suffix,
                    get(cfg, "server.url").rstrip("/")], cwd=qf, check=True)
    lst = os.path.join(qf, ".branding-changed-files")
    if os.path.exists(lst):
        CHANGED.update(l.strip() for l in open(lst) if l.strip())
        os.remove(lst)
    return suffix


def step_texts(cfg, qf):
    # strict clients (upstream_name.visible: false) keep nothing; others may keep credit phrases
    keep = [] if get(cfg, "upstream_name.visible") is False else (get(cfg, "upstream_name.keep_phrases") or [])
    args = [sys.executable, os.path.join(HERE, "rename_texts.py"), get(cfg, "app.name"), get(cfg, "app.cloud_name")]
    for k in keep:
        args += ["--keep", k]
    out = subprocess.run(args, cwd=qf, check=True, capture_output=True, text=True).stdout
    print(out.splitlines()[0] if out else "")
    CHANGED.update(l.strip() for l in out.splitlines()[1:] if l.strip())


def step_links(cfg, qf):
    help_url = get(cfg, "links.help_url") or get(cfg, "about.website")
    email = get(cfg, "about.support_email")
    website = get(cfg, "about.website")
    support = f"mailto:{email}" if email else website

    # specific links first
    patch(qf, "src/app/qml/QfWelcomeScreen.qml", 'Qt.openUrlExternally("https://www.qfield.org/");',
          f'Qt.openUrlExternally("{qml_str(support)}");')
    patch(qf, "src/app/qml/QfWelcomeScreen.qml", 'Qt.openUrlExternally("https://apps.microsoft.com/detail/xp99h3bcx4bw7f");',
          f'Qt.openUrlExternally("{qml_str(website)}");')
    patch(qf, "src/app/qml/QfWelcomeScreen.qml", 'Qt.openUrlExternally("itms-apps://itunes.apple.com/app/qfield-for-qgis/id1531726814");',
          f'Qt.openUrlExternally("{qml_str(website)}");')
    patch(qf, "src/app/qml/QfCloudLogin.qml", "<a href=\"https://qfield.cloud/\">", f"<a href=\"{qml_str(help_url)}\">")

    # every QField documentation / product-site link -> client help page
    docs = re.compile(r"https://docs\.qfield\.org[^\s\"'<>)\\]*|https://(www\.)?qfield\.cloud/?(?=[\\\"'])")
    for p in glob.glob(os.path.join(qf, "src/**/*.qml"), recursive=True) + \
             glob.glob(os.path.join(qf, "src/**/*.cpp"), recursive=True) + \
             glob.glob(os.path.join(qf, "src/**/*.h"), recursive=True):
        rel = os.path.relpath(p, qf)
        if rel in INTERNAL_URL_ALLOW:
            continue
        s = read(p)
        new = docs.sub(help_url, s)
        if new != s:
            write(p, new)
            CHANGED.add(rel)
    info(f"links -> help: {help_url}, support: {support}")


ORIGINAL_SHA256 = {}


def fingerprint_upstream(qf):
    """Record fingerprints of overlaid files before any step changes them."""
    for rel in UPSTREAM_SHA256:
        ORIGINAL_SHA256[rel] = hashlib.sha256(open(os.path.join(qf, rel), "rb").read()).hexdigest()


def step_about(cfg, qf):
    rel = "src/app/qml/QfAbout.qml"
    have = ORIGINAL_SHA256[rel]
    if have != UPSTREAM_SHA256[rel]:
        fail(f"{rel} differs from the QField version the Scout About page was written for.\n"
             f"  Compare the new upstream file with branding/overlays/QfAbout.qml, update the overlay,\n"
             f"  then set UPSTREAM_SHA256['{rel}'] = '{have}' in branding/apply.py.")
    s = read(os.path.join(HERE, "overlays", "QfAbout.qml"))
    values = {
        "@ORGANISATION@": get(cfg, "about.organisation", ""),
        "@WEBSITE@": get(cfg, "about.website", ""),
        "@SUPPORT_EMAIL@": get(cfg, "about.support_email", ""),
        "@HELP_URL@": get(cfg, "links.help_url") or get(cfg, "about.website", ""),
        "@PRIVACY_URL@": get(cfg, "about.privacy_policy_url", "") or "",
        "@SOURCE_URL@": get(cfg, "about.source_url", "") or "",
    }
    for k, v in values.items():
        s = s.replace(k, qml_str(v))
    left = re.findall(r"@[A-Z_]+@", s)
    if left:
        fail(f"About page placeholders not filled: {left}")
    write(os.path.join(qf, rel), s)
    CHANGED.add(rel)


def step_patches(cfg, qf):
    # documentation search in the search bar (searches QField's online docs)
    patch(qf, "src/core/locator/qflocatormodelsuperbridge.cpp",
          "  locator()->registerFilter( new QfHelpLocatorFilter( this ) );",
          "  // white-label: QField documentation search disabled\n  // locator()->registerFilter( new QfHelpLocatorFilter( this ) );")
    # "hello nyuki" mascot easter egg
    patch(qf, "src/app/qml/QgisMobileapp.qml", "if (lowered === 'hello nyuki') {", "if (false && lowered === 'hello nyuki') {")
    # "join the translator community" link (QField's translation project)
    patch(qf, "src/app/qml/QfAppSettings.qml",
          'text: qsTr("Found a missing or incomplete language? %1Join the translator community.%2")',
          'visible: false\n                text: qsTr("Found a missing or incomplete language? %1Join the translator community.%2")')
    patch(qf, "src/app/qml/QfAppSettings.qml", "'<a href=\"https://explore.transifex.com/opengisch/qfield-for-qgis/\">'", "'<a href=\"\">'")
    # Android notifications: sync notification title and channel names shown in system settings
    java = os.path.join("platform/android/src", get(cfg, "app.id").rsplit(".", 1)[0].replace(".", "/"), "qfield")
    app, cloud = qml_str(get(cfg, "app.name")), qml_str(get(cfg, "app.cloud_name"))
    patch(qf, f"{java}/QFieldCloudService.java", 'new NotificationChannel(CHANNEL_ID, "QFieldCloud",', f'new NotificationChannel(CHANNEL_ID, "{cloud}",')
    patch(qf, f"{java}/QFieldCloudService.java", 'setDescription("QFieldCloud service")', f'setDescription("{cloud} service")')
    patch(qf, f"{java}/QFieldCloudService.java", '.setContentTitle("QFieldCloud")', f'.setContentTitle("{cloud}")', count=2)
    patch(qf, f"{java}/QFieldPositioningService.java", 'CHANNEL_ID, "QField", NotificationManager', f'CHANNEL_ID, "{app}", NotificationManager')
    patch(qf, f"{java}/QFieldPositioningService.java", 'setDescription("QField Positioning")', f'setDescription("{app} Positioning")')

    # online plugin catalogue (QField's) -> client catalogue or none
    catalog = get(cfg, "links.plugin_catalog_url") or ""
    patch(qf, "src/app/qfpluginmodel.cpp", '#define REMOTE_PLUGINS_URL "https://qfield.org/plugins.json"',
          f'#define REMOTE_PLUGINS_URL "{catalog}"')


def step_logos(cfg, qf, outdir):
    key, icon = get(cfg, "client.key"), get(cfg, "app.icon")
    assets = os.path.join(REPO, "customers", key, "assets")
    logo = os.path.join(assets, "logo.svg")
    if not os.path.exists(logo):
        fail(f"missing {logo}")
    # in-app logos: welcome screen / About (via APP_ICON_PATH), cloud sign-in, default avatar
    icon_dir = os.path.join(outdir, "icon")
    os.makedirs(icon_dir, exist_ok=True)
    shutil.copy(logo, os.path.join(icon_dir, f"{icon}.svg"))
    for rel in ("images/icons/qfieldcloud_logo.svg", "images/icons/nyuki.svg"):
        shutil.copy(logo, os.path.join(qf, rel))
        CHANGED.add(rel)
    # Android launcher icon + splash drawable
    need = [f"launcher_{icon}.xml", f"launcher_{icon}_background.xml", f"launcher_{icon}_foreground.xml",
            f"launcher_{icon}_monochrome.xml", f"{icon}_vector.xml"]
    for name in need:
        src = os.path.join(assets, "android", name)
        if not os.path.exists(src):
            fail(f"missing Android icon file {src}")
        dst = os.path.join("platform/android/res/drawable", name)
        shutil.copy(src, os.path.join(qf, dst))
        CHANGED.add(dst)
    # status-bar icon used by the sync and positioning notifications (QField's logo by default)
    src = os.path.join(assets, "android", "notification_icon.xml")
    if not os.path.exists(src):
        fail(f"missing {src}")
    dst = "platform/android/res/drawable/qfield_logo_vector.xml"
    shutil.copy(src, os.path.join(qf, dst))
    CHANGED.add(dst)
    # optional bitmaps (e.g. real logo foreground PNGs)
    for png in glob.glob(os.path.join(assets, "android", "drawable-*", "*.png")):
        dst = os.path.join("platform/android/res", os.path.relpath(png, os.path.join(assets, "android")))
        os.makedirs(os.path.dirname(os.path.join(qf, dst)), exist_ok=True)
        shutil.copy(png, os.path.join(qf, dst))
        CHANGED.add(dst)
    return icon_dir


def step_theme(cfg, qf, outdir):
    base = json.load(open(os.path.join(qf, "resources/theme/theme.json"), encoding="utf-8"))
    primary = get(cfg, "look.primary")
    dark_accent = get(cfg, "look.accent_dark_theme") or primary
    light, dark = base["lightThemeColors"], base["darkThemeColors"]
    for k in ("mainColor", "buttonBackgroundColor"):
        if k not in light or k not in dark:
            fail(f"theme.json no longer has '{k}'; review step_theme in branding/apply.py")
        light[k] = primary
        dark[k] = dark_accent
    path = os.path.join(outdir, "theme.json")
    json.dump(base, open(path, "w", encoding="utf-8"), indent=2)
    return path


def step_notice(cfg, qf, upstream):
    name = get(cfg, "app.name")
    lines = [f"# {name}", "",
             f"{name} is a modified version of **QField** (https://github.com/opengisch/QField),",
             "copyright (C) OPENGIS.ch and the QField contributors, licensed under the",
             "GNU General Public License version 2 or (at your option) any later version.",
             f"{name} is distributed under the same licence; see LICENSE.", "",
             f"{name} is an independent product and is not endorsed by OPENGIS.ch.",
             "\"QField\" and the QField logo belong to their owners.", "",
             "## Modifications", "",
             f"Built from upstream QField {upstream}. The branding scripts in this repository",
             f"(branding/, customers/{get(cfg, 'client.key')}/) changed the following files at build time:", ""]
    lines += [f"- {c}" for c in sorted(CHANGED)]
    write(os.path.join(qf, "NOTICE.md"), "\n".join(lines) + "\n")


def step_scan(cfg, qf):
    if get(cfg, "upstream_name.visible") is not False:
        return
    problems = []
    tr = re.compile(r"""\b(?:qsTr|tr)\(\s*("(?:[^"\\]|\\.)*"|'(?:[^'\\]|\\.)*')""")
    word = re.compile(r"\bQField(?:Cloud)?\b|OPENGIS")
    for p in glob.glob(os.path.join(qf, "src/**/*.qml"), recursive=True) + \
             glob.glob(os.path.join(qf, "src/**/*.cpp"), recursive=True) + \
             glob.glob(os.path.join(qf, "src/**/*.h"), recursive=True):
        rel = os.path.relpath(p, qf)
        s = read(p)
        for m in tr.finditer(s):
            if word.search(m.group(1)):
                problems.append(f"{rel}: text {m.group(1)[:90]}")
        if rel not in INTERNAL_URL_ALLOW:
            for m in QFIELD_URL.finditer(s):
                problems.append(f"{rel}: link {m.group(0)}")
    for p in glob.glob(os.path.join(qf, "platform/android/res/values*/strings.xml")):
        for m in re.finditer(r"<string\b[^>]*>(.*?)</string>", read(p), re.S):
            if word.search(m.group(1)):
                problems.append(f"{os.path.relpath(p, qf)}: text {m.group(1)[:90]}")
    # Android code: notification titles/channels and dialog texts
    vis = re.compile(r'(setContentTitle|setContentText|setDescription|setTitle|setMessage|makeText|NotificationChannel)\([^;]*"[^"]*\bQField(?:Cloud)?\b[^"]*"', re.S)
    for p in glob.glob(os.path.join(qf, "platform/android/src/**/*.java"), recursive=True):
        for m in vis.finditer(read(p)):
            problems.append(f"{os.path.relpath(p, qf)}: Android text {m.group(0)[:90]!r}")
    if problems:
        fail("QField names or links are still visible:\n  " + "\n  ".join(problems[:60]) +
             (f"\n  ... and {len(problems) - 60} more" if len(problems) > 60 else ""))
    info("scan: no visible QField names or links left")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("config")
    ap.add_argument("qfield")
    ap.add_argument("--env-file", default="branding.env")
    ap.add_argument("--outdir", default=None, help="where generated icon/theme files go (default: <qfield>/../branding-out)")
    a = ap.parse_args()

    cfg = yaml.safe_load(open(a.config, encoding="utf-8"))
    qf = os.path.abspath(a.qfield)
    outdir = os.path.abspath(a.outdir or os.path.join(os.path.dirname(qf), "branding-out"))
    os.makedirs(outdir, exist_ok=True)
    upstream = open(os.path.join(REPO, "upstream.lock")).read().strip()

    validate(cfg)
    fingerprint_upstream(qf)
    info(f"client {get(cfg, 'client.key')}: {get(cfg, 'app.name')} ({get(cfg, 'app.id')}) on QField {upstream}")
    suffix = step_ids(cfg, qf)
    step_texts(cfg, qf)
    step_links(cfg, qf)
    step_about(cfg, qf)
    step_patches(cfg, qf)
    icon_dir = step_logos(cfg, qf, outdir)
    theme = step_theme(cfg, qf, outdir)
    step_notice(cfg, qf, upstream)
    step_scan(cfg, qf)

    env = {
        "CLIENT_KEY": get(cfg, "client.key"),
        "APP_NAME": get(cfg, "app.name"),
        "APP_PACKAGE_NAME": suffix,
        "APP_ID": get(cfg, "app.id"),
        "APP_ICON": get(cfg, "app.icon"),
        "APP_ICON_PATH": icon_dir,
        "APP_THEME_PATH": theme,
        "WITH_SAMPLE_PROJECTS": "ON" if get(cfg, "build.sample_projects", False) else "OFF",
        "WITH_ALL_FILES_ACCESS": "ON" if get(cfg, "build.all_files_access", False) else "OFF",
        "RELEASE_TAG_PREFIX": get(cfg, "release.tag_prefix", f"{get(cfg, 'client.key')}-v"),
    }
    with open(a.env_file, "w") as f:
        for k, v in env.items():
            f.write(f"{k}={v}\n")
    info(f"done: {len(CHANGED)} files branded; build settings written to {a.env_file}")


if __name__ == "__main__":
    main()
