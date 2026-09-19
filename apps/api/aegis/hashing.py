"""Content hashing and the evidence store.

Section 52 requires that evidence presented later can be shown to correspond to
the artifact that was originally evaluated. Everything hashable is hashed with
SHA-256 over a canonical JSON encoding, so the same logical object always
produces the same digest regardless of key order or whitespace.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

from .config import get_settings


def canonical_json(value: Any) -> str:
    """Stable JSON encoding: sorted keys, no insignificant whitespace."""
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str, ensure_ascii=False)


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def content_hash(value: Any) -> str:
    """Digest of any JSON-serialisable object."""
    return sha256_text(canonical_json(value))


class EvidenceStore:
    """Writes evidence artifacts and returns a URI plus digest.

    Storage itself lives in `aegis.storage`; this class owns hashing and the
    key layout, so the two concerns stay separable.
    """

    def __init__(self, backend=None) -> None:
        from .storage import build_backend

        self.settings = get_settings()
        self.backend = backend or build_backend(self.settings)

    @property
    def backend_name(self) -> str:
        return self.backend.name

    def put(self, key: str, data: bytes, media_type: str = "application/json") -> dict:
        digest = sha256_bytes(data)
        uri = self.backend.put(key, data, media_type)
        return {
            "storage_uri": uri,
            "sha256": digest,
            "size_bytes": len(data),
            "media_type": media_type,
        }

    def put_json(self, key: str, value: Any) -> dict:
        return self.put(key, canonical_json(value).encode("utf-8"), "application/json")

    def get(self, uri: str) -> bytes:
        return self.backend.get(uri)

    def check(self) -> dict:
        """Confirm the store is reachable and writable."""
        return self.backend.check()


_store: EvidenceStore | None = None


def evidence_store() -> EvidenceStore:
    global _store
    if _store is None:
        _store = EvidenceStore()
    return _store


def reset_evidence_store() -> None:
    """Drop the cached store. Used by tests and after a configuration change."""
    global _store
    _store = None
