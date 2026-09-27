"""Runtime settings. Everything configurable comes from here or from WMI_* environment variables."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

VERSION = "0.3.1"


def _env(name: str, default: str) -> str:
    return os.environ.get(f"WMI_{name}", default)


@dataclass(frozen=True)
class Settings:
    # Wikimedia asks every client to identify itself with contact information.
    user_agent: str = field(default_factory=lambda: _env(
        "USER_AGENT", f"wiki-market-intel/{VERSION} (https://github.com/hsirenko/Wikimedia1)"))
    pageviews_base: str = field(default_factory=lambda: _env(
        "PAGEVIEWS_BASE", "https://wikimedia.org/api/rest_v1/metrics/pageviews"))
    wikipedia_api: str = "https://{lang}.wikipedia.org/w/api.php"
    wikidata_api: str = field(default_factory=lambda: _env("WIKIDATA_API", "https://www.wikidata.org/w/api.php"))
    timeout_seconds: float = field(default_factory=lambda: float(_env("TIMEOUT", "30")))
    max_attempts: int = field(default_factory=lambda: int(_env("MAX_ATTEMPTS", "4")))
    data_dir: Path = field(default_factory=lambda: Path(_env("DATA_DIR", "data")))
    reports_dir: Path = field(default_factory=lambda: Path(_env("REPORTS_DIR", "reports")))
    # Defaults for traffic classes: humans on every device.
    access: str = "all-access"
    agent: str = "user"
    pivot_language: str = "en"

    @property
    def raw_dir(self) -> Path:
        return self.data_dir / "raw"

    @property
    def cache_dir(self) -> Path:
        return self.data_dir / "cache"
