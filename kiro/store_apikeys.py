# -*- coding: utf-8 -*-

"""
API Key Management - Storage and Verification.

Manages multiple API keys with JSON file persistence.
"""

import json
import os
import secrets
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

from loguru import logger

from kiro.config import PROXY_API_KEY


class ApiKeyEntry:
    """Single API key entry."""

    def __init__(self, id: str, name: str, key: str, created_at: str, enabled: bool = True):
        self.id = id
        self.name = name
        self.key = key
        self.created_at = created_at
        self.enabled = enabled

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "key": self.key,
            "created_at": self.created_at,
            "enabled": self.enabled,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "ApiKeyEntry":
        return cls(
            id=data["id"],
            name=data["name"],
            key=data["key"],
            created_at=data["created_at"],
            enabled=data.get("enabled", True),
        )


class ApiKeyManager:
    """Manages multiple API keys with JSON persistence."""

    def __init__(self, storage_path: str = "apikeys.json"):
        self._keys: Dict[str, ApiKeyEntry] = {}
        self._storage_path = Path(storage_path)
        self._load()

    def _generate_key(self) -> str:
        """Generate a new API key with sk- prefix."""
        return f"sk-{secrets.token_hex(24)}"

    def _generate_id(self) -> str:
        """Generate a short unique ID."""
        return secrets.token_hex(4)

    def _load(self) -> None:
        """Load keys from JSON file, or seed from PROXY_API_KEY."""
        if self._storage_path.exists():
            try:
                data = json.loads(self._storage_path.read_text(encoding="utf-8"))
                for entry in data.get("keys", []):
                    key_entry = ApiKeyEntry.from_dict(entry)
                    self._keys[key_entry.id] = key_entry
                logger.info(f"Loaded {len(self._keys)} API key(s) from {self._storage_path}")
                return
            except Exception as e:
                logger.error(f"Failed to load API keys from {self._storage_path}: {e}")

        # Seed with PROXY_API_KEY from environment
        if PROXY_API_KEY:
            entry = ApiKeyEntry(
                id=self._generate_id(),
                name="Default (from env)",
                key=PROXY_API_KEY,
                created_at=datetime.now(timezone.utc).isoformat(),
                enabled=True,
            )
            self._keys[entry.id] = entry
            logger.info("Seeded API key manager with PROXY_API_KEY from environment")
            self._save()

    def _save(self) -> None:
        """Persist keys to JSON file."""
        data = {"keys": [entry.to_dict() for entry in self._keys.values()]}
        try:
            self._storage_path.write_text(
                json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8"
            )
        except Exception as e:
            logger.error(f"Failed to save API keys: {e}")

    def list_keys(self) -> List[dict]:
        """List all keys with key field masked (first 8 chars only)."""
        result = []
        for entry in self._keys.values():
            result.append({
                "id": entry.id,
                "name": entry.name,
                "key_preview": entry.key[:8] + "..." if len(entry.key) > 8 else entry.key,
                "created_at": entry.created_at,
                "enabled": entry.enabled,
            })
        return result

    def create_key(self, name: str) -> dict:
        """Create a new API key. Returns full key (shown only once)."""
        entry = ApiKeyEntry(
            id=self._generate_id(),
            name=name,
            key=self._generate_key(),
            created_at=datetime.now(timezone.utc).isoformat(),
            enabled=True,
        )
        self._keys[entry.id] = entry
        self._save()
        logger.info(f"API key created: id={entry.id}, name={entry.name}")
        return {
            "id": entry.id,
            "name": entry.name,
            "key": entry.key,
            "created_at": entry.created_at,
        }

    def update_key(self, key_id: str, name: Optional[str] = None, enabled: Optional[bool] = None) -> Optional[dict]:
        """Update key name or enabled status."""
        entry = self._keys.get(key_id)
        if not entry:
            return None
        if name is not None:
            entry.name = name
        if enabled is not None:
            entry.enabled = enabled
        self._save()
        logger.info(f"API key updated: id={key_id}, name={entry.name}, enabled={entry.enabled}")
        return {
            "id": entry.id,
            "name": entry.name,
            "key_preview": entry.key[:8] + "..." if len(entry.key) > 8 else entry.key,
            "created_at": entry.created_at,
            "enabled": entry.enabled,
        }

    def delete_key(self, key_id: str) -> bool:
        """Delete a key by ID."""
        if key_id not in self._keys:
            return False
        del self._keys[key_id]
        self._save()
        logger.info(f"API key deleted: id={key_id}")
        return True

    def verify_key(self, bearer_token: str) -> bool:
        """
        Verify a bearer token against all enabled keys and PROXY_API_KEY.

        Checks:
        1. PROXY_API_KEY from .env (always valid)
        2. Dynamically created keys in apikeys.json (if enabled)
        """
        # Check PROXY_API_KEY from .env first
        if bearer_token == PROXY_API_KEY:
            return True

        # Check dynamically created keys
        for entry in self._keys.values():
            if entry.enabled and entry.key == bearer_token:
                return True

        return False
