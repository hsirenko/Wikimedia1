"""The uploadable zip must contain every source file (an unanchored exclude once dropped a package)."""

import shutil
import subprocess
import zipfile
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[1]


@pytest.mark.skipif(not shutil.which("rsync") or not shutil.which("zip"), reason="needs rsync and zip")
def test_zip_contains_every_source_file_and_no_samples(tmp_path):
    out = tmp_path / "skill.zip"
    subprocess.run(["sh", str(ROOT / "scripts" / "build_zip.sh"), str(out)], check=True, capture_output=True)
    names = set(zipfile.ZipFile(out).namelist())
    prefix = f"{ROOT.name}/"
    expected = {prefix + str(p.relative_to(ROOT)) for p in (ROOT / "src").rglob("*.py") if "__pycache__" not in p.parts}
    assert expected <= names, sorted(expected - names)[:5]
    for required in ("SKILL.md", "scripts/wiki_market.py", "requirements.lock", ".python-version", "README.md"):
        assert prefix + required in names
    assert not any(n.startswith(prefix + d) for n in names for d in ("examples/", "evals/", ".venv/", "data/"))


@pytest.mark.skipif(not shutil.which("rsync") or not shutil.which("zip"), reason="needs rsync and zip")
def test_builds_into_a_folder_are_numbered_and_never_overwrite(tmp_path):
    for _ in range(2):
        subprocess.run(["sh", str(ROOT / "scripts" / "build_zip.sh"), str(tmp_path)], check=True, capture_output=True)
    names = sorted(p.name for p in tmp_path.glob("*.zip"))
    assert names == [f"{ROOT.name}-skill-1.zip", f"{ROOT.name}-skill-2.zip"]
