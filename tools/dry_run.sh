#!/usr/bin/env bash
# dry_run.sh <client> - apply a client's branding to a fresh QField checkout on this computer
# and run the "no visible QField" scan, without compiling. Takes about a minute.
#   tools/dry_run.sh scout
# The branded copy is left in ./_dryrun/qfield so you can inspect it (git -C _dryrun/qfield diff --stat).
set -euo pipefail
CLIENT="${1:?usage: tools/dry_run.sh <client>}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
REF="$(tr -d '[:space:]' < "$ROOT/upstream.lock")"
WORK="$ROOT/_dryrun"
rm -rf "$WORK" && mkdir -p "$WORK"
git clone --quiet --depth 1 --branch "$REF" https://github.com/opengisch/QField.git "$WORK/qfield"
python3 "$ROOT/branding/apply.py" "$ROOT/customers/$CLIENT/customer.yml" "$WORK/qfield" \
  --env-file "$WORK/branding.env" --outdir "$WORK/branding-out"
echo
echo "Build settings:"; cat "$WORK/branding.env"
echo "Changed files:   git -C \"$WORK/qfield\" status --short | wc -l  ->  $(git -C "$WORK/qfield" status --short | wc -l)"
