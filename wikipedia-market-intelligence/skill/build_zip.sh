#!/bin/sh
# Build an uploadable Agent Skill zip from this package.
#   sh skill/build_zip.sh [output.zip]
# The zip holds one folder, wiki-market-intel/, with SKILL.md at its root.
set -e
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
OUT="${1:-$ROOT/../wiki-market-intel-skill.zip}"
STAGE="$(mktemp -d)/wiki-market-intel"
mkdir -p "$STAGE/scripts" "$STAGE/references"
cp "$ROOT/skill/SKILL.md" "$STAGE/SKILL.md"
cp "$ROOT/skill/wiki_market.py" "$STAGE/scripts/wiki_market.py"
cp "$ROOT/README.md" "$STAGE/references/README.md"
cp -R "$ROOT/src" "$STAGE/src"
cp -R "$ROOT/tests" "$STAGE/tests"
cp "$ROOT/pyproject.toml" "$STAGE/pyproject.toml"
find "$STAGE" -name "__pycache__" -type d -prune -exec rm -rf {} +
find "$STAGE" -name ".DS_Store" -delete
rm -f "$OUT"
(cd "$(dirname "$STAGE")" && zip -qr "$OUT" wiki-market-intel)
echo "Built $OUT"
