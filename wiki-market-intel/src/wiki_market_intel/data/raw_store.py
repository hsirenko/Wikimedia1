"""Archive raw HTTP responses for reproducibility/debugging."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4


class RawStore:
    def __init__(self, root: Path):
        self.root = Path(root)

    def save(self, *, source: str, endpoint: str, url: str, request: dict,
             status: int, response: object) -> tuple[Path, str]:
        retrieved_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
        folder = self.root / source / endpoint
        folder.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        path = folder / f"{stamp}-{uuid4().hex[:8]}.json"
        envelope = {
            "source": source,
            "endpoint": endpoint,
            "retrieved_at": retrieved_at,
            "status": status,
            "request": {"url": url, **(request or {})},
            "response": response,
        }
        path.write_text(json.dumps(envelope, ensure_ascii=False, indent=2), "utf-8")
        return path, retrieved_at
