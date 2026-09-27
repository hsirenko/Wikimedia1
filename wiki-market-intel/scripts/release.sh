#!/bin/sh
# Tag this commit and publish wiki-market-intel-skill.zip on GitHub Releases.
#   sh scripts/release.sh 0.3.0
# Run from a commit that contains the skill you want users to download (not from
# an unrelated default-branch snapshot). Push access and `gh` are required.
set -e
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
REPO="$(cd "$ROOT/.." && pwd)"
VERSION="${1:?usage: sh scripts/release.sh 0.3.0}"
VERSION="${VERSION#v}"
TAG="v$VERSION"
ZIP="${TMPDIR:-/tmp}/wiki-market-intel-skill.zip"

cd "$REPO"
if ! git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  echo "error: not a git repository" >&2
  exit 1
fi
if [ -n "$(git status --porcelain)" ]; then
  echo "error: working tree is not clean; commit or stash first." >&2
  exit 1
fi
if [ ! -f "$ROOT/SKILL.md" ]; then
  echo "error: $ROOT/SKILL.md is missing on this commit." >&2
  exit 1
fi

sh "$ROOT/scripts/build_zip.sh" "$ZIP"
if git rev-parse "$TAG" >/dev/null 2>&1; then
  echo "error: tag $TAG already exists." >&2
  exit 1
fi
git tag -a "$TAG" -m "wiki-market-intel $VERSION"
git push origin "$TAG"
if gh release view "$TAG" >/dev/null 2>&1; then
  gh release upload "$TAG" "$ZIP" --clobber
else
  gh release create "$TAG" "$ZIP" \
    --title "wiki-market-intel $VERSION" \
    --notes "Download wiki-market-intel-skill.zip and upload it in Claude.ai: Customize → Skills → Upload a skill.

Do not use Code → Download ZIP on the repository: that archive is the whole repo, not the skill package.

Cursor and Claude Code: copy the wiki-market-intel/ folder into ~/.cursor/skills/ or ~/.claude/skills/."
fi
echo "Release: https://github.com/hsirenko/Wikimedia1/releases/tag/$TAG"
echo "Latest zip: https://github.com/hsirenko/Wikimedia1/releases/latest/download/wiki-market-intel-skill.zip"
