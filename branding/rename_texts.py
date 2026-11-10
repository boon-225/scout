#!/usr/bin/env python3
"""Rename "QField" / "QFieldCloud" in the app's user-visible texts.

Usage (from the root of a clean QField checkout; called by branding/apply.py):
    python3 rename_texts.py "AppName" "AppName Cloud" [--keep "phrase" ...]

What it changes - only text shown to users, never code identifiers:
  * QML   qsTr("...") / qsTr('...') strings    (src/**/*.qml)
  * C++   tr("...") strings                     (src/**/*.cpp, *.h)
  * Qt translations i18n/*.ts: <source> AND <translation> of the same messages,
    so every language keeps its translation (the .ts files are compiled at build time)
  * Android texts platform/android/res/values*/strings.xml

"QFieldCloud" -> the cloud name; the word "QField" -> the app name.
Messages containing a --keep phrase are left unchanged (for clients who keep QField credits).
With no --keep phrases, every user-visible "QField" is renamed. "QFieldSync" (the QGIS plugin
users need) is not matched, because it is a different word.

Run it once on a clean checkout; running it twice is harmless (nothing left to replace).
Licence: GPL-2.0-or-later, as the rest of this repository.
"""
import glob
import re
import sys

import argparse

_ap = argparse.ArgumentParser()
_ap.add_argument("app")
_ap.add_argument("cloud")
_ap.add_argument("--keep", action="append", default=[], help="phrase whose messages keep the QField name")
_args = _ap.parse_args()
APP, CLOUD = _args.app, _args.cloud
KEEP = tuple(_args.keep)

WORD = re.compile(r"\bQField\b(?!Cloud)")


def rename(text: str) -> str:
    if KEEP and any(k in text for k in KEEP):
        return text
    return WORD.sub(APP, text.replace("QFieldCloud", CLOUD))


changed = {}


def write_if_changed(path, old, new):
    if new != old:
        with open(path, "w", encoding="utf-8", newline="") as f:
            f.write(new)
        changed[path] = changed.get(path, 0) + 1


# 1. QML qsTr("...") / qsTr('...')
qml_pat = re.compile(r"""(\bqsTr\(\s*)("(?:[^"\\]|\\.)*"|'(?:[^'\\]|\\.)*')""")
for path in glob.glob("src/**/*.qml", recursive=True):
    old = open(path, encoding="utf-8").read()
    new = qml_pat.sub(lambda m: m.group(1) + rename(m.group(2)), old)
    write_if_changed(path, old, new)

# 2. C++ tr("...") (including QObject::tr / tr( "..." ))
cpp_pat = re.compile(r"""(\btr\(\s*)("(?:[^"\\]|\\.)*")""")
for path in glob.glob("src/**/*.cpp", recursive=True) + glob.glob("src/**/*.h", recursive=True):
    old = open(path, encoding="utf-8", errors="surrogateescape").read()
    new = cpp_pat.sub(lambda m: m.group(1) + rename(m.group(2)), old)
    if new != old:
        with open(path, "w", encoding="utf-8", errors="surrogateescape", newline="") as f:
            f.write(new)
        changed[path] = 1

# 3. Qt translation files: rename inside <source>, <translation> and <numerusform> of each message,
#    deciding KEEP from the message's source text so source and translation stay consistent.
msg_pat = re.compile(r"<message\b.*?</message>", re.S)
txt_pat = re.compile(r"(<(source|translation|numerusform)\b[^>]*>)(.*?)(</\2>)", re.S)
for path in glob.glob("i18n/*.ts"):
    old = open(path, encoding="utf-8").read()

    def fix_message(m):
        block = m.group(0)
        src = re.search(r"<source>(.*?)</source>", block, re.S)
        if KEEP and src and any(k in src.group(1).replace("&apos;", "'") for k in KEEP):
            return block
        return txt_pat.sub(lambda t: t.group(1) + WORD.sub(APP, t.group(3).replace("QFieldCloud", CLOUD)) + t.group(4), block)

    new = msg_pat.sub(fix_message, old)
    write_if_changed(path, old, new)

# 4. Android string resources (all languages)
str_pat = re.compile(r"(<string\b[^>]*>)(.*?)(</string>)", re.S)
for path in glob.glob("platform/android/res/values*/strings.xml"):
    old = open(path, encoding="utf-8").read()
    new = str_pat.sub(lambda m: m.group(1) + rename(m.group(2)) + m.group(3), old)
    write_if_changed(path, old, new)

print(f"Renamed QField -> {APP!r}, QFieldCloud -> {CLOUD!r} in {len(changed)} files")
for p in sorted(changed):
    print("  ", p)
