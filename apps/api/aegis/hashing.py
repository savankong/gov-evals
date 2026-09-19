"""Content hashing and the evidence store.

Section 52 requires that evidence presented later can be shown to correspond to
the artifact that was originally evaluated. Everything hashable is hashed with
SHA-256 over a canonical JSON encoding, so the same logical object always
produces the same digest regardless of key order or whitespace.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
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

    The file backend keeps everything inside the customer boundary with no
    outbound dependency; the s3 backend targets any S3-compatible endpoint
    (including MinIO running on-premises).
    """

    def __init__(self) -> None:
        self.settings = get_settings()
        self.backend = self.settings.evidence_backend
        self.root = Path(self.settings.evidence_path)

    def put(self, key: str, data: bytes, media_type: str = "application/json") -> dict:
        digest = sha256_bytes(data)
        if self.backend == "s3":
            uri = self._put_s3(key, data, media_type)
        else:
            uri = self._put_file(key, data)
        return {
            "storage_uri": uri,
            "sha256": digest,
            "size_bytes": len(data),
            "media_type": media_type,
        }

    def put_json(self, key: str, value: Any) -> dict:
        return self.put(key, canonical_json(value).encode("utf-8"), "application/json")

    def get(self, uri: str) -> bytes:
        if uri.startswith("s3://"):
            return self._get_s3(uri)
        return Path(uri.removeprefix("file://")).read_bytes()

    # -- backends ----------------------------------------------------------

    def _put_file(self, key: str, data: bytes) -> str:
        path = self.root / key
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return f"file://{path.resolve()}"

    def _client(self):  # pragma: no cover - requires boto3 + an endpoint
        import boto3

        return boto3.client(
            "s3",
            endpoint_url=self.settings.s3_endpoint_url or None,
            aws_access_key_id=self.settings.s3_access_key or None,
            aws_secret_access_key=self.settings.s3_secret_key or None,
        )

    def _put_s3(self, key: str, data: bytes, media_type: str) -> str:  # pragma: no cover
        self._client().put_object(
            Bucket=self.settings.s3_bucket, Key=key, Body=data, ContentType=media_type
        )
        return f"s3://{self.settings.s3_bucket}/{key}"

    def _get_s3(self, uri: str) -> bytes:  # pragma: no cover
        _, _, rest = uri.partition("s3://")
        bucket, _, key = rest.partition("/")
        return self._client().get_object(Bucket=bucket, Key=key)["Body"].read()


_store: EvidenceStore | None = None


def evidence_store() -> EvidenceStore:
    global _store
    if _store is None:
        _store = EvidenceStore()
    return _store
