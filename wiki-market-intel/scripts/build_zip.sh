#!/bin/sh
# Build an uploadable Agent Skill zip from this folder (the skill directory itself).
#   sh scripts/build_zip.sh                 -> ../wiki-market-intel-skill-<N>.zip, N = last number + 1
#   sh scripts/build_zip.sh <folder>        -> the next numbered zip in that folder
#   sh scripts/build_zip.sh <file.zip>      -> exactly that file
# Numbered builds never overwrite an earlier one, so the highest number is always the latest.
# The zip holds one folder, wiki-market-intel/, with SKILL.md at its root. Local-only material
# (virtualenv, caches, downloaded data, generated reports, secrets) is left out, and so are the
# sample reports (examples/) and agent evals (evals/): in testing, a model answered from a saved
# sample instead of running the analysis, so the installed skill carries no saved results.
set -e
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
NAME="$(basename "$ROOT")"
TARGET="${1:-$ROOT/..}"
case "$TARGET" in
  *.zip) OUT="$TARGET" ;;
  *)
    DIR="$(cd "$TARGET" && pwd)"
    LAST=$(ls "$DIR" 2>/dev/null | sed -n "s/^$NAME-skill-\([0-9][0-9]*\)\.zip$/\1/p" | sort -n | tail -1)
    OUT="$DIR/$NAME-skill-$(( ${LAST:-0} + 1 )).zip"
    ;;
esac
STAGE="$(mktemp -d)"
# Top-level folders are anchored with a leading "/", so src/wiki_market_intel/data/ (code) stays in.
rsync -a --exclude "/.venv/" --exclude "/data/" --exclude "/reports/" --exclude "/wiki_market_data/" \
      --exclude "/wiki_market_reports/" --exclude "/examples/" --exclude "/evals/" --exclude "/.env" \
      --exclude ".pytest_cache/" --exclude "__pycache__/" --exclude "*.egg-info/" --exclude ".DS_Store" \
      "$ROOT/" "$STAGE/$NAME/"
rm -f "$OUT"
(cd "$STAGE" && zip -qr "$OUT" "$NAME")
echo "Built $OUT"
