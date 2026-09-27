"""Small on-disk cache for HTTP responses."""

from __future__ import annotations

import hashlib
import json
import shutil
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Protocol


@dataclass(frozen=True)
class CacheKey:
    source: str
    endpoint: str
    language: str
    article: str
    start: str
    end: str
    metric: str
    extra: str = ""

    def token(self) -> str:
        raw = json.dumps(asdict(self), sort_keys=True, ensure_ascii=False)
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()


class Cache(Protocol):
    def get(self, key: CacheKey) -> dict[str, Any] | None:
        ...

    def set(self, key: CacheKey, value: dict[str, Any], *, immutable: bool) -> None:
        ...


class NullCache:
    def get(self, key: CacheKey) -> dict[str, Any] | None:
        return None

    def set(self, key: CacheKey, value: dict[str, Any], *, immutable: bool) -> None:
        return None

    def clear(self) -> int:
        return 0


class JsonFileCache:
    def __init__(self, root: Path):
        self.root = Path(root)

    def _path(self, key: CacheKey) -> Path:
        return self.root / key.source / key.endpoint / f"{key.token()}.json"

    def get(self, key: CacheKey) -> dict[str, Any] | None:
        path = self._path(key)
        if not path.is_file():
            return None
        try:
            data = json.loads(path.read_text("utf-8"))
        except json.JSONDecodeError:
            return None
        return data.get("value") if isinstance(data, dict) else None

    def set(self, key: CacheKey, value: dict[str, Any], *, immutable: bool) -> None:
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "key": asdict(key),
            "immutable": bool(immutable),
            "stored_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "value": value,
        }
        path.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), "utf-8")

    def clear(self) -> int:
        if not self.root.exists():
            return 0
        files = [p for p in self.root.rglob("*.json") if p.is_file()]
        count = len(files)
        shutil.rmtree(self.root)
        return count
