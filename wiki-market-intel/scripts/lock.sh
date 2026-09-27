#!/bin/sh
# Recreate the hashed lockfiles from pyproject.toml for Python 3.13.
#   sh scripts/lock.sh
# Commit both lockfiles if they change. The skill launcher installs requirements.lock.
set -e
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
if ! command -v uv >/dev/null 2>&1; then
  echo "error: uv is required to refresh the lockfiles (https://docs.astral.sh/uv/)." >&2
  exit 1
fi
uv pip compile pyproject.toml --extra pdf --python-version 3.13 --generate-hashes \
  -o requirements.lock
# Dev lock is the runtime lock plus pytest; -c keeps every shared pin identical.
uv pip compile pyproject.toml --extra pdf --extra dev --python-version 3.13 --generate-hashes \
  -c requirements.lock -o requirements-dev.lock
echo "Wrote $ROOT/requirements.lock and $ROOT/requirements-dev.lock"
