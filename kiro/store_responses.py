# -*- coding: utf-8 -*-

"""
Response state store for OpenAI Responses API.

Manages stateful conversations by storing response history
with automatic expiration and JSON persistence.
"""

import json
import uuid
from collections import OrderedDict
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

from loguru import logger


class ResponseStateStore:
    """
    Response state store with automatic expiration and JSON persistence.

    Stores conversation state for the Responses API, enabling stateful
    conversations via previous_response_id.

    Storage format:
        response_id -> {
            "messages": [...],
            "model": "...",
            "metadata": {...},
            "created_at": "...",
            "last_accessed": "..."
        }
    """

    def __init__(self, max_age_days: int = 7, storage_path: str = "response_states.json"):
        """
        Initialize response state store.

        Args:
            max_age_days: Maximum age in days before state expires (default 7)
            storage_path: Path to JSON file for persistence
        """
        self._max_age_days = max_age_days
        self._storage_path = Path(storage_path)
        self._states: OrderedDict[str, Dict[str, Any]] = OrderedDict()
        self._load()
        self._cleanup_expired()

    def _load(self) -> None:
        """Load states from JSON file on startup."""
        if not self._storage_path.exists():
            return
        try:
            data = json.loads(self._storage_path.read_text(encoding="utf-8"))
            # Preserve order for LRU-style access
            for response_id, state in data.get("states", {}).items():
                self._states[response_id] = state
            logger.info(f"Loaded {len(self._states)} response state(s) from {self._storage_path}")
        except Exception as e:
            logger.warning(f"Failed to load response states: {e}")

    def _save(self) -> None:
        """Persist current states to JSON file (best-effort)."""
        try:
            self._storage_path.write_text(
                json.dumps({"states": dict(self._states)}, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except Exception as e:
            logger.warning(f"Failed to save response states: {e}")

    def _cleanup_expired(self) -> None:
        """Remove expired states based on max_age_days."""
        now = datetime.now(timezone.utc)
        cutoff = now - timedelta(days=self._max_age_days)

        expired_ids = []
        for response_id, state in self._states.items():
            try:
                last_accessed = datetime.fromisoformat(state.get("last_accessed", state.get("created_at")))
                if last_accessed < cutoff:
                    expired_ids.append(response_id)
            except Exception:
                # Invalid timestamp, mark for removal
                expired_ids.append(response_id)

        for response_id in expired_ids:
            del self._states[response_id]

        if expired_ids:
            logger.info(f"Cleaned up {len(expired_ids)} expired response state(s)")
            self._save()

    def create(
        self,
        messages: List[Dict[str, Any]],
        model: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> str:
        """
        Create a new response state.

        Args:
            messages: Full conversation history
            model: Model used for generation
            metadata: Optional metadata

        Returns:
            response_id: Unique ID for this response state
        """
        response_id = f"resp_{uuid.uuid4().hex}"
        now = datetime.now(timezone.utc).isoformat()

        state = {
            "messages": messages,
            "model": model,
            "metadata": metadata or {},
            "created_at": now,
            "last_accessed": now,
        }

        self._states[response_id] = state
        self._save()

        logger.debug(f"Created response state {response_id} with {len(messages)} message(s)")
        return response_id

    def get(self, response_id: str) -> Optional[Dict[str, Any]]:
        """
        Retrieve a response state by ID.

        Updates last_accessed timestamp.

        Args:
            response_id: Response ID to retrieve

        Returns:
            State dict or None if not found
        """
        state = self._states.get(response_id)
        if state:
            # Update last_accessed timestamp
            state["last_accessed"] = datetime.now(timezone.utc).isoformat()
            # Move to end (LRU)
            self._states.move_to_end(response_id)
            self._save()
            logger.debug(f"Retrieved response state {response_id}")
        return state

    def delete(self, response_id: str) -> bool:
        """
        Delete a response state.

        Args:
            response_id: Response ID to delete

        Returns:
            True if deleted, False if not found
        """
        if response_id in self._states:
            del self._states[response_id]
            self._save()
            logger.debug(f"Deleted response state {response_id}")
            return True
        return False

    def list_all(self) -> List[Dict[str, Any]]:
        """
        List all response states (for debugging/admin).

        Returns:
            List of state dicts with response_id included
        """
        return [
            {"response_id": rid, **state}
            for rid, state in self._states.items()
        ]

    def clear_all(self) -> int:
        """
        Clear all response states.

        Returns:
            Number of states cleared
        """
        count = len(self._states)
        self._states.clear()
        self._save()
        logger.info(f"Cleared all {count} response state(s)")
        return count
