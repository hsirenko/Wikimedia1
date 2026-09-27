#!/usr/bin/env python3
"""Skill launcher: run wiki-market-intel straight from the skill folder.

* puts the bundled package (`src/`) on the import path, so nothing needs installing;
* requires CPython 3.13 and installs *exactly* the versions in requirements.lock
  (hashes required), upgrading anything that does not match;
* writes data and reports to the current folder (or a temp folder if it is read-only),
  never into the skill directory, which is read-only in some agents;
* copies each new report to /mnt/user-data/outputs when that folder exists (Claude.ai),
  so the user can download it.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
from importlib import metadata
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SKILL_DIR / "src"))

MIN_VERSION = (3, 13)
MAX_VERSION = (3, 14)   # 3.13.x only — matches requires-python and .python-version
LOCK = SKILL_DIR / "requirements.lock"
OUTPUTS = Path("/mnt/user-data/outputs")


def _python_version(executable: str) -> tuple[int, int] | None:
    try:
        out = subprocess.run(
            [executable, "-c", "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')"],
            capture_output=True, text=True, timeout=5)
        if out.returncode != 0:
            return None
        major, minor = out.stdout.strip().split(".")
        return int(major), int(minor)
    except (OSError, ValueError, subprocess.TimeoutExpired):
        return None


def _acceptable(version: tuple[int, int] | None) -> bool:
    return version is not None and MIN_VERSION <= version < MAX_VERSION


def _newer_python() -> str | None:
    """A 3.10+ interpreter when `python3` is the macOS / Xcode 3.9 stub."""
    names = ("python3.13", "python3.12", "python3.11", "python3.10", "python3")
    candidates: list[Path] = [SKILL_DIR / ".venv" / "bin" / "python"]
    for folder in (Path("/opt/homebrew/bin"), Path("/usr/local/bin")):
        candidates.extend(folder / name for name in names)
    for name in names:
        found = shutil.which(name)
        if found:
            candidates.append(Path(found))
    seen: set[str] = set()
    for path in candidates:
        resolved = str(path.resolve()) if path.exists() else ""
        if not resolved or resolved in seen or not os.access(path, os.X_OK):
            continue
        seen.add(resolved)
        if _acceptable(_python_version(resolved)):
            return resolved
    return None


def ensure_python() -> None:
    if _acceptable(sys.version_info[:2]):
        return
    found = _newer_python()
    if found:
        os.execv(found, [found, str(Path(__file__).resolve()), *sys.argv[1:]])
    sys.exit(
        f"wiki-market-intel needs CPython 3.13 (see .python-version); this is {sys.version.split()[0]}. "
        "Install 3.13 (e.g. `brew install python@3.13`) and rerun, or call the script with that interpreter.")


def lock_pins(lock: Path | None = None) -> dict[str, str]:
    """{distribution_name: exact version} from a uv/pip lockfile, including hashed ones."""
    path = lock or LOCK
    pins: dict[str, str] = {}
    if not path.is_file():
        return pins
    for raw in path.read_text("utf-8").splitlines():
        line = raw.split("#", 1)[0].strip().rstrip("\\").strip()
        if not line or line.startswith("--") or "==" not in line:
            continue
        req = line.split(";")[0].strip()
        name, version = req.split("==", 1)
        pins[name.strip().lower()] = version.strip()
    return pins


def environment_matches_lock(lock: Path | None = None) -> bool:
    """True only when every locked distribution is installed at the locked version."""
    pins = lock_pins(lock)
    if not pins:
        return False
    for name, want in pins.items():
        try:
            have = metadata.version(name)
        except metadata.PackageNotFoundError:
            return False
        if have != want:
            return False
    return True


def ensure_dependencies() -> None:
    """Install or upgrade to the hashed lock. Never keep a pre-existing mismatched version."""
    if not LOCK.is_file():
        sys.exit(f"wiki-market-intel is missing {LOCK.name}; the skill zip is incomplete.")
    if environment_matches_lock():
        return
    print(f"Installing missing libraries (first run only): {', '.join(missing)}", file=sys.stderr)
    base = [sys.executable, "-m", "pip", "install", "--quiet", *missing]
    for extra in ([], ["--user"], ["--break-system-packages"]):
        if subprocess.run(base + extra, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE).returncode == 0:
            importlib_invalidate()
            if environment_matches_lock():
                return
    sys.exit(
        f"Could not install hashed dependencies from {LOCK}. "
        "Use CPython 3.13 and: python3 -m pip install --require-hashes -r requirements.lock")


def importlib_invalidate() -> None:
    from importlib import invalidate_caches
    invalidate_caches()


def writable_base() -> Path:
    here = Path.cwd()
    if os.access(here, os.W_OK) and not str(here).startswith(str(SKILL_DIR)):
        return here
    return Path(tempfile.gettempdir())


def main() -> int:
    ensure_python()
    ensure_dependencies()
    base = writable_base()
    os.environ.setdefault("WMI_DATA_DIR", str(base / "wiki_market_data"))
    os.environ.setdefault("WMI_REPORTS_DIR", str(base / "wiki_market_reports"))

    from wiki_market_intel.cli import main as cli_main   # after the path and dependencies are ready

    reports = Path(os.environ["WMI_REPORTS_DIR"])
    before = results(reports)
    code = cli_main(sys.argv[1:])
    if code == 0 and OUTPUTS.is_dir():
        for path, mtime in results(reports).items():
            if before.get(path) == mtime:
                continue                   # unchanged by this run
            target = OUTPUTS / "/".join(path.parent.parts[-3:])
            shutil.copytree(path.parent, target, dirs_exist_ok=True)
            print(f"Copied for download: {target}")
    return code


def results(reports: Path) -> dict[Path, float]:
    """{result file: modification time} for every analysis, comparison and portfolio report, and every PDF."""
    if not reports.exists():
        return {}
    return {p: p.stat().st_mtime for name in ("analysis.json", "comparison.json", "portfolio.json", "report.pdf", "brief.pdf")
            for p in reports.rglob(name)}


if __name__ == "__main__":
    sys.exit(main())
