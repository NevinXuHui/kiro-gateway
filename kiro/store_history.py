# -*- coding: utf-8 -*-

"""
Request history store.

FIFO buffer (max 200 records) with JSON file persistence.
"""

import json
import uuid
from collections import deque
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from loguru import logger


class RequestHistory:
    """Request history with FIFO eviction and JSON persistence."""

    def __init__(self, max_size: int = 200, storage_path: str = "request_history.json"):
        self._max_size = max_size
        self._records: deque[dict] = deque(maxlen=max_size)
        self._storage_path = Path(storage_path)
        self._load()

    def _load(self) -> None:
        """Load history from JSON file on startup."""
        if not self._storage_path.exists():
            return
        try:
            data = json.loads(self._storage_path.read_text(encoding="utf-8"))
            for entry in data.get("records", []):
                self._records.append(entry)
            logger.info(f"Loaded {len(self._records)} history record(s) from {self._storage_path}")
        except Exception as e:
            logger.warning(f"Failed to load request history: {e}")

    def _save(self) -> None:
        """Persist current records to JSON file (best-effort)."""
        try:
            self._storage_path.write_text(
                json.dumps({"records": list(self._records)}, ensure_ascii=False),
                encoding="utf-8",
            )
        except Exception:
            pass  # best-effort, don't break request flow

    def record(
        self,
        endpoint: str,
        method: str,
        model: str,
        stream: bool,
        status_code: int,
        latency_ms: int,
        input_tokens: Optional[int] = None,
        output_tokens: Optional[int] = None,
        error: Optional[str] = None,
    ) -> dict:
        entry = {
            "id": str(uuid.uuid4()),
            "time": datetime.now(timezone.utc).isoformat(),
            "endpoint": endpoint,
            "method": method,
            "model": model,
            "stream": stream,
            "status_code": status_code,
            "latency_ms": latency_ms,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "error": error,
        }
        self._records.appendleft(entry)
        self._save()
        return entry

    def list(self, limit: int = 50, offset: int = 0) -> tuple[list[dict], int]:
        total = len(self._records)
        items = list(self._records)
        return items[offset : offset + limit], total

    def clear(self) -> int:
        count = len(self._records)
        self._records.clear()
        self._save()
        return count
