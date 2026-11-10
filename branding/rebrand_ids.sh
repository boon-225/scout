#!/usr/bin/env bash
# rebrand_ids.sh - set app name, app ID and default server on a CLEAN QField checkout.
#
# Called by branding/apply.py during every build (never run on committed QField code).
# Run from the root of the QField checkout (tested on QField v4.3.7):
#   rebrand_ids.sh "AppName" com.yourbrand field https://cloud.yourbrand.com
#
#   1  App name shown to users          e.g. "AgriField"
#   2  Package prefix (reverse domain)  e.g. com.agrifield      (lowercase, dots, no hyphens)
#   3  Package suffix                   e.g. app                -> final app ID com.agrifield.app
#   4  Your QFieldCloud server URL      e.g. https://cloud.agrifield.com   (no trailing slash)
#
# What it changes (and nothing else):
#   - Package prefix ch.opengis -> your prefix in every source/build file that uses it
#   - Default app name and package suffix in CMakeLists.txt
#   - Default QFieldCloud server, sign-up and plan links -> your server
#   - "Rate this app" store link -> your app ID
#   - Writes .branding-changed-files (list of modified files, used for NOTICE.md)
# Icons, colours, links and on-screen wording are separate steps in apply.py.
#
# Licence: this script is part of your fork and is GPL-2.0-or-later like the rest of it.

set -euo pipefail

if [ $# -ne 4 ]; then
  sed -n '2,12p' "$0"; exit 1
fi

APP_NAME="$1"; PREFIX="$2"; SUFFIX="$3"; SERVER="${4%/}"

# ---- input checks ---------------------------------------------------------
[[ "$APP_NAME" =~ ^[A-Za-z0-9][A-Za-z0-9\ ._-]{1,29}$ ]] || { echo "Bad app name '$APP_NAME' (letters, digits, space . _ - ; max 30)"; exit 1; }
[[ "$PREFIX" =~ ^[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)+$ ]] || { echo "Bad prefix '$PREFIX' (use e.g. com.agrifield)"; exit 1; }
[[ "$SUFFIX" =~ ^[a-z][a-z0-9_]*$ ]]                     || { echo "Bad suffix '$SUFFIX' (lowercase letters/digits/_ only)"; exit 1; }
[[ "$SERVER" =~ ^https://[A-Za-z0-9.-]+(:[0-9]+)?$ ]]   || { echo "Bad server URL '$SERVER' (must be https://host)"; exit 1; }
[ "$PREFIX" != "ch.opengis" ]                             || { echo "Choose your own prefix, not ch.opengis"; exit 1; }
[ -f CMakeLists.txt ] && grep -q 'set(APP_NAME "QField"' CMakeLists.txt \
  || { echo "Run from the root of an UNMODIFIED QField checkout"; exit 1; }

PREFIX_PATH="${PREFIX//.//}"          # com.agrifield -> com/agrifield
APP_ID="${PREFIX}.${SUFFIX}"
CHANGED=()
note() { CHANGED+=("$1"); }

# sed -i that works on Linux and macOS
sedi() { if sed --version >/dev/null 2>&1; then sed -i "$@"; else sed -i '' "$@"; fi; }

# ---- 1. Store link (must run before the generic prefix replacement) ------
f=src/app/qml/QfWelcomeScreen.qml
sedi "s#market://details?id=ch\.opengis\.qfield#market://details?id=${APP_ID}#" "$f"; note "$f"

# ---- 2. Package prefix ch.opengis -> PREFIX ---------------------------------
# Every source/build file that mentions the prefix (found automatically, so the
# script keeps working when QField adds or moves files). Java files are handled below.
mapfile -t PREFIX_FILES < <(grep -rlI -e 'ch\.opengis\.' -e 'ch/opengis/' \
    src platform/android/AndroidManifest.xml.in platform/android/build.gradle.in \
    platform/android/proguard-rules.pro cmake CMakeLists.txt scripts/ci \
    .github/workflows/android.yml 2>/dev/null | sort -u)
for f in "${PREFIX_FILES[@]}"; do
  sedi -e "s#ch\.opengis\.#${PREFIX}.#g" -e "s#ch/opengis/#${PREFIX_PATH}/#g" "$f"; note "$f"
done

# Java sources: move folder and fix package lines
OLD_JAVA=platform/android/src/ch/opengis/qfield
NEW_JAVA="platform/android/src/${PREFIX_PATH}/qfield"
mkdir -p "$(dirname "$NEW_JAVA")"
if git rev-parse --git-dir >/dev/null 2>&1; then git mv "$OLD_JAVA" "$NEW_JAVA"; else mv "$OLD_JAVA" "$NEW_JAVA"; fi
rmdir -p platform/android/src/ch/opengis 2>/dev/null || true
for f in "$NEW_JAVA"/*.java; do
  sedi -e "s#ch\.opengis\.#${PREFIX}.#g" -e "s#ch/opengis/#${PREFIX_PATH}/#g" "$f"; note "$f"
done

# ---- 3. Defaults in CMakeLists.txt --------------------------------------
sedi -e "s#set(APP_NAME \"QField\"#set(APP_NAME \"${APP_NAME}\"#" \
     -e "s#set(APP_PACKAGE_NAME \"qfield\"#set(APP_PACKAGE_NAME \"${SUFFIX}\"#" CMakeLists.txt

# CI and Docker build scripts set their own name/package per build type
# (release, dev, beta, all-files-access); rebrand those too.
for f in scripts/ci/generate-version-details.sh scripts/ci/env_gh.sh scripts/build-vcpkg.sh; do
  [ -f "$f" ] || { echo "WARNING: $f not found - check manually"; continue; }
  sedi -e "/APP_NAME=/ s#QField#${APP_NAME}#g" \
       -e "/APP_PACKAGE_NAME=/ s#qfield#${SUFFIX}#g" "$f"; note "$f"
done

# ---- 4. Default server and its links ---------------------------------------
# (qfcloudstatus.cpp is deliberately NOT changed, so the app never shows
#  QFieldCloud's public status page for your server.)
mapfile -t URL_FILES < <(grep -rlI 'https://app\.qfield\.cloud' src | grep -v 'qfcloudstatus\.cpp' | sort -u)
for f in "${URL_FILES[@]}"; do
  sedi "s#https://app\.qfield\.cloud#${SERVER}#g" "$f"; note "$f"
done

# ---- 5. List of changed files (apply.py writes NOTICE.md) ------------------
printf '%s\n' "${CHANGED[@]}" | sort -u > .branding-changed-files

echo
echo "Done. App ID: ${APP_ID}   Name: ${APP_NAME}   Server: ${SERVER}"
echo "Leftover ch.opengis references (should list only docs/translations/iOS CI you haven't set up yet):"
grep -rIl "ch\.opengis\|ch/opengis" --exclude-dir=.git --exclude-dir=i18n --exclude-dir=vcpkg --exclude=NOTICE.md . | head -20 || echo "  none"
echo
