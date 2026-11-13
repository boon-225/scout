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
  7. screens: welcome screen, settings tabs, cloud menu, launch behaviour   (screens: in customer.yml)
  8. logos, launcher icon and theme icons        (customers/<key>/assets)
  9. colours                                     (theme.json from QField's, with client colours)
 10. NOTICE.md (GPL notice + list of changed files)
 11. scan: fail if any user-visible QField name or link is left (when upstream_name.visible is false)
 12. write build settings (env file) for CMake

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
    for k in ("look.primary", "look.accent_dark_theme", "look.highlight", "look.cloud", "look.cloud_dark_theme"):
        v = get(cfg, k)
        if v and not re.fullmatch(r"#[0-9A-Fa-f]{6}", v):
            fail(f"{k} must be a colour like #1E2742")
    # Play Store listing: name limits and the listing files under customers/<key>/store/
    store_name = get(cfg, "app.store_name")
    if store_name:
        if len(store_name) > 30:
            fail(f"app.store_name '{store_name}' is {len(store_name)} characters; the Play Store allows 30")
        if store_name != store_name.strip() or "  " in store_name:
            fail(f"app.store_name '{store_name}' has extra spaces")
        store = os.path.join(REPO, "customers", get(cfg, "client.key"), "store")
        limits = {"title.txt": 30, "short_description.txt": 80, "full_description.txt": 4000}
        for lang in sorted(os.listdir(store)) if os.path.isdir(store) else []:
            for name, limit in limits.items():
                f = os.path.join(store, lang, name)
                if not os.path.isfile(f):
                    continue
                text = open(f, encoding="utf-8").read().rstrip("\n")
                if len(text) > limit:
                    fail(f"store/{lang}/{name} is {len(text)} characters; the Play Store allows {limit}")
                if lang == "en-US" and name == "title.txt" and text != store_name:
                    fail(f"store/en-US/title.txt ('{text}') must equal app.store_name ('{store_name}')")


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


def patch_between(qf, rel, start, end, new):
    """Replace the block from `start` through `end` (each must occur exactly once, in order)."""
    p = os.path.join(qf, rel)
    s = read(p)
    if s.count(start) != 1 or s.count(end) != 1 or s.index(start) > s.index(end):
        fail(f"{rel}: could not find the block to replace (start found {s.count(start)}x, end {s.count(end)}x).\n"
             f"  Block starts with: {start.strip()[:100]!r}\n  QField has probably changed here: review branding/apply.py.")
    i, j = s.index(start), s.index(end) + len(end)
    write(p, s[:i] + new + s[j:])
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


REWRITES = [
    # (file, old sentence, new sentence): user texts that name QField tools by necessity.
    # The translations of a rewritten sentence are cleared, so other languages show the new
    # English text until re-translated (better than a sentence that no longer matches).
    ("src/gui/qml/QfProjectCreationScreen.qml",
     "For more advanced needs, we advise you to create projects in QGIS using QFieldSync.",
     "For more advanced needs, we advise you to create projects in QGIS."),
]


def step_rewrites(cfg, qf):
    if get(cfg, "upstream_name.visible") is not False:
        return
    for rel, old, new in REWRITES:
        patch(qf, rel, old, new)
        msg = re.compile(r"<message\b.*?</message>", re.S)
        hits = 0
        for p in glob.glob(os.path.join(qf, "i18n/*.ts")):
            text = read(p)

            def fix(m):
                nonlocal hits
                block = m.group(0)
                if old not in block:
                    return block
                hits += 1
                block = block.replace(old, new, 1)  # the <source>
                return re.sub(r"<translation\b[^>]*>.*?</translation>", '<translation type="unfinished"></translation>', block, flags=re.S)

            out = msg.sub(fix, text)
            if out != text:
                write(p, out)
                CHANGED.add(os.path.relpath(p, qf))
        info(f"rewrote '{old[:50]}...' in {rel} and {hits} translation entries")


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

    # app data folder on the phone ("QField" -> app name): created by the Android code and passed to
    # the rest of the app, so renaming it here is consistent everywhere
    folder = get(cfg, "app.data_folder") or get(cfg, "app.name")
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9 _-]{0,30}", folder):
        fail(f"app.data_folder '{folder}' must be letters, digits, space, - or _")
    f = qml_str(folder)
    patch(qf, f"{java}/QFieldActivity.java", 'dataDir = dataDir + "QField/";', f'dataDir = dataDir + "{f}/";')
    patch(qf, f"{java}/QFieldActivity.java", 'String rootDataDir = storagePath + "/QField/";', f'String rootDataDir = storagePath + "/{f}/";')
    patch(qf, f"{java}/QFieldActivity.java", 'String dataDir = file.getAbsolutePath() + "/QField/";', f'String dataDir = file.getAbsolutePath() + "/{f}/";')
    patch(qf, "src/core/platforms/qfplatformutilities.cpp", 'QStringLiteral( "/QField Documents/QField/" )', f'QStringLiteral( "/{f} Documents/{f}/" )')
    # camera maker written into photos' metadata (shown in gallery photo details)
    patch(qf, "src/core/utils/qffileutils.cpp", 'metadata["Exif.Image.Make"] = QStringLiteral( "QField" );', f'metadata["Exif.Image.Make"] = QStringLiteral( "{app}" );')
    patch(qf, "src/core/utils/qffileutils.cpp", 'metadata["Xmp.tiff.Make"] = QStringLiteral( "QField" );', f'metadata["Xmp.tiff.Make"] = QStringLiteral( "{app}" );')

    # online plugin catalogue (QField's) -> client catalogue or none
    catalog = get(cfg, "links.plugin_catalog_url") or ""
    patch(qf, "src/app/qfpluginmodel.cpp", '#define REMOTE_PLUGINS_URL "https://qfield.org/plugins.json"',
          f'#define REMOTE_PLUGINS_URL "{catalog}"')



def step_theme_code(cfg, qf):
    """Theme support for client icon sets: '<icon>_dark.svg' variants and a per-theme cloud colour."""
    # use '<name>_dark.svg' in the dark theme when the client supplies one
    patch(qf, "src/gui/qftheme.cpp",
          'QString QfTheme::getThemeVectorIcon( const QString &name ) const\n{\n'
          '  return QStringLiteral( "qrc:/themes/qfield/nodpi/%1.svg" ).arg( name );\n}',
          'QString QfTheme::getThemeVectorIcon( const QString &name ) const\n{\n'
          '  // white-label: dark-theme variant of the icon when one exists\n'
          '  if ( mDarkTheme && QFile::exists( QStringLiteral( ":/themes/qfield/nodpi/%1_dark.svg" ).arg( name ) ) )\n'
          '  {\n'
          '    return QStringLiteral( "qrc:/themes/qfield/nodpi/%1_dark.svg" ).arg( name );\n'
          '  }\n'
          '  return QStringLiteral( "qrc:/themes/qfield/nodpi/%1.svg" ).arg( name );\n}')
    # cloud colour may differ between light and dark theme ("cloudColor" in light/darkThemeColors);
    # set before applyColors(), whose mainColor change notifies QML
    patch(qf, "src/gui/qftheme.cpp",
          "  applyColors( mDarkTheme ? mDarkThemeColors : mLightThemeColors );\n",
          "  {\n"
          "    // white-label: per-theme cloud colour\n"
          "    const QColor themedCloudColor( ( mDarkTheme ? mDarkThemeColors : mLightThemeColors ).value( QStringLiteral( \"cloudColor\" ) ).toString() );\n"
          "    if ( themedCloudColor.isValid() )\n"
          "    {\n"
          "      mCloudColor = themedCloudColor;\n"
          "    }\n"
          "  }\n"
          "  applyColors( mDarkTheme ? mDarkThemeColors : mLightThemeColors );\n")


WELCOME = "src/app/qml/QfWelcomeScreen.qml"


def step_screens(cfg, qf):
    """Screen changes chosen in customer.yml (screens:)."""
    app = get(cfg, "app.name")
    cloud = get(cfg, "app.cloud_name")

    if get(cfg, "screens.welcome") == "brand":
        # header: client lockup (logo + name) and tagline instead of the spinning logo dial; tap opens About
        lockup = os.path.join(REPO, "customers", get(cfg, "client.key"), "assets", "theme_icons", "brand_lockup.svg")
        m = re.search(r'viewBox="0 0 ([\d.]+) ([\d.]+)"', read(lockup)) if os.path.exists(lockup) else None
        if not m:
            fail("screens.welcome is 'brand' but assets/theme_icons/brand_lockup.svg (with a viewBox) is missing")
        aspect = float(m.group(1)) / float(m.group(2))
        tagline = qml_str(get(cfg, "app.tagline") or "")
        patch_between(qf, WELCOME,
                      "      RowLayout {\n        spacing: welcomeScreenLogo.imageSize / 4\n",
                      "        FontMetrics {\n          id: welcomeScreenTitleMetrics\n          font: welcomeScreenTitle.font\n        }\n      }\n",
                      f"""      ColumnLayout {{
        spacing: 8
        Layout.fillWidth: true
        Layout.topMargin: 0
        Layout.bottomMargin: 22
        Layout.alignment: Qt.AlignHCenter

        Image {{
          id: welcomeScreenLogo
          objectName: "welcomeScreenLogo"

          property real imageSize: Math.min(44, mainWindow.width / 8)
          property real value: 1 // kept for the screen's other bindings

          Layout.alignment: Qt.AlignHCenter
          Layout.preferredHeight: imageSize
          Layout.preferredWidth: imageSize * {aspect:.4f}
          source: QfTheme.darkTheme ? "qrc:/themes/qfield/nodpi/brand_lockup_dark.svg" : "qrc:/themes/qfield/nodpi/brand_lockup.svg"
          sourceSize.height: imageSize * 3
          fillMode: Image.PreserveAspectFit
          smooth: true

          MouseArea {{
            anchors.fill: parent
            onClicked: welcomeScreen.showAbout()
          }}
        }}

        Text {{
          id: welcomeScreenTitle
          objectName: "welcomeScreenTitle"

          Layout.fillWidth: true
          visible: text !== ""
          text: "{tagline}"
          font.pointSize: QfTheme.tipFont.pointSize
          color: QfTheme.secondaryTextColor
          horizontalAlignment: Text.AlignHCenter
          wrapMode: Text.WordWrap
        }}
      }}
""")
        # one wide cloud-projects card instead of the three tiles (cloud / local data / new project)
        patch_between(qf, WELCOME,
                      "          Container {\n            id: welcomeActionsContainer\n",
                      '              label: qsTr("Create new\\nproject")\n              onClicked: showProjectCreationScreen()\n            }\n          }\n',
                      f"""          Rectangle {{
            id: welcomeActionCloud
            objectName: "welcomeActionCloud"

            Layout.fillWidth: true
            Layout.preferredHeight: 84
            radius: 16
            color: cloudCardArea.pressed ? QfTheme.groupBoxSurfaceColor : QfTheme.groupBoxBackgroundColor
            border.width: 1
            border.color: QfTheme.controlBorderColor

            RowLayout {{
              anchors.fill: parent
              anchors.leftMargin: 14
              anchors.rightMargin: 10
              spacing: 14

              Image {{
                Layout.preferredWidth: 48
                Layout.preferredHeight: 48
                Layout.alignment: Qt.AlignVCenter
                source: QfTheme.darkTheme ? "qrc:/themes/qfield/nodpi/brand_cloud_projects_48dp_dark.svg" : "qrc:/themes/qfield/nodpi/brand_cloud_projects_48dp.svg"
                sourceSize.width: 144
                sourceSize.height: 144
                fillMode: Image.PreserveAspectFit
              }}

              ColumnLayout {{
                Layout.fillWidth: true
                Layout.alignment: Qt.AlignVCenter
                spacing: 2

                Text {{
                  Layout.fillWidth: true
                  text: "{qml_str(cloud)} " + qsTr("projects")
                  font.pointSize: QfTheme.defaultFont.pointSize
                  font.bold: true
                  color: QfTheme.mainTextColor
                  elide: Text.ElideRight
                }}

                Text {{
                  Layout.fillWidth: true
                  text: qsTr("Download and sync your projects")
                  font.pointSize: QfTheme.tipFont.pointSize
                  color: QfTheme.secondaryTextColor
                  wrapMode: Text.WordWrap
                }}
              }}

              QfToolButton {{
                Layout.preferredWidth: 36
                Layout.preferredHeight: 36
                Layout.alignment: Qt.AlignVCenter
                bgcolor: "transparent"
                iconSource: QfTheme.getThemeVectorIcon("ic_chevron_right_white_24dp")
                iconColor: QfTheme.secondaryTextColor
                onClicked: showQFieldCloudScreen()
              }}
            }}

            MouseArea {{
              id: cloudCardArea
              anchors.fill: parent
              onClicked: showQFieldCloudScreen()
            }}
          }}
""")
        # recent projects: plain heading, newest first (QField already keeps the last opened on top)
        patch(qf, WELCOME,
              '            text: qsTr("Recently Opened")\n            font.pointSize: QfTheme.tipFont.pointSize\n'
              '            font.bold: true\n            color: QfTheme.mainTextColor\n            horizontalAlignment: Text.AlignHCenter',
              '            text: qsTr("Recent projects")\n            font.pointSize: QfTheme.tipFont.pointSize\n'
              '            font.bold: true\n            color: QfTheme.secondaryTextColor\n            leftPadding: 4\n'
              '            horizontalAlignment: Text.AlignLeft')
        patch(qf, WELCOME,
              '                    var firstRun = settings && !settings.value("/QField/FirstRunFlag", false);\n'
              '                    if (!firstRun && firstShown === false)\n'
              '                      notes.push(qsTr("Last session"));',
              '                    notes.push(qsTr("Last opened"));')
        # softer brand-tinted background instead of QField's grey gradient
        patch(qf, WELCOME, 'color: QfTheme.darkTheme ? "#99000000" : "#99A5A5A5"',
              f'color: QfTheme.darkTheme ? "#99000000" : "#33{get(cfg, "look.primary")[1:]}"')

    if get(cfg, "screens.always_open_last_project"):
        # the last opened (or default) project opens on launch; the on/off switch is removed
        if True:
            patch_between(qf, WELCOME,
                          "          RowLayout {\n            Layout.leftMargin: 10\n            Layout.rightMargin: 10\n"
                          "            Layout.bottomMargin: mainWindow.sceneBottomMargin\n",
                          "              onCheckedChanged: {\n                registry.loadProjectOnLaunch = checked;\n"
                          "              }\n            }\n          }\n",
                          "          Item {\n            // white-label: 'load project on launch' switch removed (always on)\n"
                          "            Layout.preferredHeight: 10 + mainWindow.sceneBottomMargin\n          }\n")
        old = 'QSettings().value( "/QField/loadProjectOnLaunch", true ).toBool()'
        new = 'true /* white-label: always reopen the last project */'
        patch(qf, "src/app/qgismobileapp.cpp", old, new)
        patch(qf, "src/core/qfappinterface.cpp", old, new)

    if get(cfg, "screens.hide_cloud_settings_page"):
        # cloud screen menu: "Settings page" (opens the server's web settings) hidden
        patch(qf, "src/app/qml/QfCloudScreen.qml",
              "      property bool isVisible: Qt.platform.os !== \"ios\" && cloudConnection.url === cloudConnection.defaultUrl\n\n"
              "      text: qsTr('Settings page')",
              "      property bool isVisible: false // white-label: hidden\n\n"
              "      text: qsTr('Settings page')")

    if get(cfg, "screens.hide_variables_settings"):
        # settings: Variables tab hidden; the editor stays (invisible) so saved variables still apply
        patch(qf, "src/app/qml/QfAppSettings.qml",
              'model: [qsTr("General"), qsTr("Positioning"), qsTr("Variables")]',
              'model: [qsTr("General"), qsTr("Positioning")]')
        patch(qf, "src/app/qml/QfAppSettings.qml",
              "      Item {\n        QfVariableEditor {\n          id: variableEditor\n          anchors.fill: parent\n"
              "          anchors.margins: 4\n          anchors.bottomMargin: 4 + mainWindow.sceneBottomMargin\n        }\n      }\n"
              "    }\n  }\n",
              "    }\n  }\n\n"
              "  Item {\n    // white-label: Variables page hidden\n    visible: false\n"
              "    QfVariableEditor {\n      id: variableEditor\n      anchors.fill: parent\n    }\n  }\n")
    info("screens: " + ", ".join(k for k in ("welcome", "always_open_last_project", "hide_cloud_settings_page",
                                             "hide_variables_settings") if get(cfg, f"screens.{k}")))

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
    # folder icons with the QField "Q" (app files directory) -> the plain folder icons
    theme_icons = "images/themes/qfield/nodpi"
    for variant in ("param", "gray"):
        src = os.path.join(qf, theme_icons, f"ic_folder_{variant}_48dp.svg")
        dst = os.path.join(theme_icons, f"ic_folder_qfield_{variant}_48dp.svg")
        if not os.path.exists(src) or not os.path.exists(os.path.join(qf, dst)):
            fail(f"QField folder icons changed ({dst}); review step_logos in branding/apply.py")
        shutil.copy(src, os.path.join(qf, dst))
        CHANGED.add(dst)
    # theme icons: client versions of QField's icons (same file name) and extra ones (e.g. *_dark.svg)
    added = 0
    qrc_rel = "images/images.qrc"
    qrc = read(os.path.join(qf, qrc_rel))
    root_section = '    <qresource prefix="/">\n'
    for src in sorted(glob.glob(os.path.join(assets, "theme_icons", "*.svg"))):
        name = os.path.basename(src)
        dst = os.path.join(theme_icons, name)
        shutil.copy(src, os.path.join(qf, dst))
        CHANGED.add(dst)
        entry = f"<file>{os.path.relpath(dst, 'images').replace(os.sep, '/')}</file>"  # qrc paths are relative to images/
        if entry not in qrc:
            if qrc.count(root_section) != 1:
                fail("images/images.qrc layout changed; review step_logos in branding/apply.py")
            qrc = qrc.replace(root_section, root_section + f"        {entry}\n")
            added += 1
    if added:
        write(os.path.join(qf, qrc_rel), qrc)
        CHANGED.add(qrc_rel)
    n_theme = len(glob.glob(os.path.join(assets, "theme_icons", "*.svg")))
    if n_theme:
        info(f"theme icons: {n_theme} client icons ({added} new)")
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
    # cloud colour (QField's blue by default): theme setting + the cloud icons that have it built in
    cloud = get(cfg, "look.cloud")
    if cloud:
        fixed = base.get("fixedColors", {})
        for k in ("cloudColor", "qfieldcloudBlue"):
            if k not in fixed:
                fail(f"theme.json no longer has fixedColors.{k}; review step_theme in branding/apply.py")
            fixed[k] = cloud
        # per-theme cloud colour (read by the theme code patch in step_theme_code)
        light["cloudColor"] = cloud
        dark["cloudColor"] = get(cfg, "look.cloud_dark_theme") or cloud
        blue = re.compile(r"#4c6dac|#4a6fae", re.I)
        n = 0
        for p in glob.glob(os.path.join(qf, "images/themes/qfield/nodpi/*.svg")):
            s = read(p)
            new = blue.sub(cloud, s)
            if new != s:
                write(p, new)
                CHANGED.add(os.path.relpath(p, qf))
                n += 1
        has_own = glob.glob(os.path.join(REPO, "customers", get(cfg, "client.key"), "assets", "theme_icons", "ic_cloud_*.svg"))
        if n == 0 and not has_own:
            fail("no cloud icons with QField's blue found; review step_theme in branding/apply.py")
        info(f"cloud colour {cloud} (dark theme {dark['cloudColor']}): theme + {n} icons recoloured")
    # QField's green inside the remaining theme icons -> client highlight colour
    green = get(cfg, "look.highlight")
    if green:
        n = 0
        for p in glob.glob(os.path.join(qf, "images/themes/qfield/nodpi/*.svg")):
            s = read(p)
            new = re.sub(r"#80cc28", green, s, flags=re.I)
            if new != s:
                write(p, new)
                CHANGED.add(os.path.relpath(p, qf))
                n += 1
        info(f"highlight colour {green}: {n} icons recoloured")
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
    word = re.compile(r"\bQField(?:Cloud|Sync)?\b|OPENGIS")
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
    folder_name = re.compile(r'"/?QField/"')
    for p in glob.glob(os.path.join(qf, "platform/android/src/**/*.java"), recursive=True):
        s = read(p)
        for m in vis.finditer(s):
            problems.append(f"{os.path.relpath(p, qf)}: Android text {m.group(0)[:90]!r}")
        for m in folder_name.finditer(s):
            problems.append(f"{os.path.relpath(p, qf)}: phone folder named QField ({m.group(0)})")
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
    step_rewrites(cfg, qf)
    step_links(cfg, qf)
    step_about(cfg, qf)
    step_patches(cfg, qf)
    step_theme_code(cfg, qf)
    step_screens(cfg, qf)
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
