#!/usr/bin/env python3
"""Skill launcher: run wiki-market-intel straight from the skill folder.

* puts the bundled package (`src/`) on the import path, so nothing needs installing;
* installs any missing third-party library once, with pip;
* writes data and reports to the current folder (or a temp folder if it is read-only),
  never into the skill directory, which is read-only in some agents;
* copies each new report to /mnt/user-data/outputs when that folder exists (Claude.ai),
  so the user can download it.
"""

from __future__ import annotations

import importlib.util
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SKILL_DIR / "src"))

# import name -> pip requirement
REQUIREMENTS = {
    "httpx": "httpx>=0.27,<1", "pydantic": "pydantic>=2.7,<3", "tenacity": "tenacity>=8.2",
    "dateutil": "python-dateutil>=2.9", "jinja2": "jinja2>=3.1", "matplotlib": "matplotlib>=3.8",
    "yaml": "pyyaml>=6.0",
}
OUTPUTS = Path("/mnt/user-data/outputs")


def ensure_dependencies() -> None:
    if sys.version_info < (3, 10):
        sys.exit("wiki-market-intel needs Python 3.10 or newer.")
    missing = [req for module, req in REQUIREMENTS.items() if importlib.util.find_spec(module) is None]
    if not missing:
        return
    print(f"Installing missing libraries (first run only): {', '.join(missing)}", file=sys.stderr)
    base = [sys.executable, "-m", "pip", "install", "--quiet", *missing]
    for extra in ([], ["--user"], ["--break-system-packages"]):
        if subprocess.run(base + extra, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE).returncode == 0:
            importlib.invalidate_caches()
            return
    sys.exit("Could not install: " + " ".join(missing) + ". Install them with pip and run again.")


def writable_base() -> Path:
    here = Path.cwd()
    if os.access(here, os.W_OK) and not str(here).startswith(str(SKILL_DIR)):
        return here
    return Path(tempfile.gettempdir())


def main() -> int:
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
    """{result file: modification time} for every analysis, comparison and portfolio report."""
    if not reports.exists():
        return {}
    return {p: p.stat().st_mtime for name in ("analysis.json", "comparison.json", "portfolio.json")
            for p in reports.rglob(name)}


if __name__ == "__main__":
    sys.exit(main())
