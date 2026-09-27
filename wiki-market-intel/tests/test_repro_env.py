"""Dependencies and environment setup stay reproducible."""

import importlib.util
from pathlib import Path

ROOT = Path(__file__).parents[1]


def _launcher():
    spec = importlib.util.spec_from_file_location("wiki_market", ROOT / "scripts" / "wiki_market.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_python_version_file_is_3_13():
    assert (ROOT / ".python-version").read_text().strip() == "3.13"


def test_lockfiles_pin_every_direct_dependency_with_hashes():
    pyproject = (ROOT / "pyproject.toml").read_text()
    runtime = _launcher().lock_pins(ROOT / "requirements.lock")
    dev = _launcher().lock_pins(ROOT / "requirements-dev.lock")
    assert runtime["httpx"] == "0.28.1"
    assert runtime["reportlab"] == "5.0.1"
    assert "pytest" not in runtime
    assert dev["pytest"] == "9.1.1"
    assert dev["httpx"] == runtime["httpx"]
    lock = (ROOT / "requirements.lock").read_text()
    assert "--hash=sha256:" in lock
    assert "httpx==0.28.1" in pyproject
    assert 'requires-python = ">=3.13,<3.14"' in pyproject


def test_current_environment_matches_the_runtime_lock():
    assert _launcher().environment_matches_lock(ROOT / "requirements.lock")


def test_zip_ships_the_lock_and_python_pin(tmp_path):
    import shutil
    import subprocess
    import zipfile

    import pytest

    if not shutil.which("rsync") or not shutil.which("zip"):
        pytest.skip("needs rsync and zip")
    out = tmp_path / "skill.zip"
    subprocess.run(["sh", str(ROOT / "scripts" / "build_zip.sh"), str(out)], check=True, capture_output=True)
    names = set(zipfile.ZipFile(out).namelist())
    prefix = f"{ROOT.name}/"
    for required in (".python-version", "requirements.lock", "scripts/lock.sh", "scripts/wiki_market.py"):
        assert prefix + required in names
