#!/usr/bin/env bash
# Copy the data the deployed app needs into deploy_data/ (gitignored), for the Dockerfile.
#   chairs/ manuals/ sources.yaml  from TAGALONG_DATA_DIR (default ./data; read from .env if set there)
#   out/<chair>/figures/           manual figure crops the app serves (out/ itself is not uploaded)
# Runtime state (data/state: label decisions) is not copied: the deployed app starts fresh.
set -euo pipefail
cd "$(dirname "$0")/.."

if [ -z "${TAGALONG_DATA_DIR:-}" ] && [ -f .env ]; then
  TAGALONG_DATA_DIR=$(sed -n 's/^TAGALONG_DATA_DIR=//p' .env | tail -1)
fi
SRC="${TAGALONG_DATA_DIR:-./data}"
SRC="${SRC/#\~/$HOME}"
[ -d "$SRC" ] || { echo "No data folder at $SRC" >&2; exit 1; }

rm -rf deploy_data
mkdir -p deploy_data
for item in chairs manuals sources.yaml; do
  if [ -e "$SRC/$item" ]; then
    cp -R "$SRC/$item" deploy_data/
    echo "copied $SRC/$item"
  else
    echo "skipped $SRC/$item (not found)"
  fi
done

OUT="${TAGALONG_OUT_DIR:-./out}"
for figs in "$OUT"/*/figures; do
  [ -d "$figs" ] || continue
  chair=$(basename "$(dirname "$figs")")
  mkdir -p "deploy_data/out/$chair"
  cp -R "$figs" "deploy_data/out/$chair/"
  echo "copied $figs"
done

du -sh deploy_data
