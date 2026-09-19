"""Evidence storage backends.

Two backends satisfy one interface. `file` keeps artifacts on local disk, which
is what a single node or an air-gapped install uses. `s3` targets any
S3-compatible object store -- AWS S3, MinIO on premises, or DigitalOcean Spaces.

Object storage is not optional on a platform-as-a-service host. App Platform and
similar runtimes give each container an ephemeral filesystem, so evidence
written to disk disappears on the next deploy. `Settings` refuses that
combination outside development rather than losing the evidence quietly.
"""

from __future__ import annotations

import logging
import threading
from pathlib import Path

from .config import get_settings

log = logging.getLogger("aegis.storage")


class StorageError(RuntimeError):
    """The evidence store could not be reached or configured."""


class FileBackend:
    """Local disk. No dependency, no network."""

    name = "file"
    durable_across_restarts = False  # true only if the path is a real volume

    def __init__(self, root: str) -> None:
        self.root = Path(root)

    def put(self, key: str, data: bytes, media_type: str) -> str:
        path = self.root / key
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return f"file://{path.resolve()}"

    def get(self, uri: str) -> bytes:
        return Path(uri.removeprefix("file://")).read_bytes()

    def check(self) -> dict:
        try:
            self.root.mkdir(parents=True, exist_ok=True)
            probe = self.root / ".aegis-write-probe"
            probe.write_bytes(b"ok")
            probe.unlink()
            return {"backend": self.name, "writable": True, "location": str(self.root.resolve())}
        except OSError as exc:
            return {"backend": self.name, "writable": False, "error": str(exc)}


class S3Backend:
    """Any S3-compatible object store.

    The client is built once and reused: boto3 client construction resolves
    credentials and loads service models, which is far too expensive to repeat
    for every artifact a campaign writes.
    """

    name = "s3"
    durable_across_restarts = True

    def __init__(
        self,
        *,
        bucket: str,
        endpoint_url: str = "",
        region: str = "us-east-1",
        access_key: str = "",
        secret_key: str = "",
        prefix: str = "",
    ) -> None:
        if not bucket:
            raise StorageError(
                "AEGIS_EVIDENCE_BACKEND is 's3' but AEGIS_S3_BUCKET is not set."
            )
        self.bucket = bucket
        self.endpoint_url = endpoint_url or None
        self.region = region or "us-east-1"
        self.access_key = access_key or None
        self.secret_key = secret_key or None
        self.prefix = prefix.strip("/")
        self._client = None
        self._lock = threading.Lock()

    def _key(self, key: str) -> str:
        return f"{self.prefix}/{key}" if self.prefix else key

    def client(self):
        # Double-checked locking: campaign workers write concurrently and must
        # not each build their own client.
        if self._client is None:
            with self._lock:
                if self._client is None:
                    self._client = self._build_client()
        return self._client

    def _build_client(self):
        try:
            import boto3
            from botocore.config import Config
        except ImportError as exc:  # pragma: no cover - depends on the extra
            raise StorageError(
                "The s3 evidence backend needs boto3. Install the extra: pip install 'aegis-api[s3]'"
            ) from exc

        return boto3.client(
            "s3",
            endpoint_url=self.endpoint_url,
            # Region is not cosmetic: SigV4 signs with it, and a mismatch is
            # rejected with an opaque SignatureDoesNotMatch.
            region_name=self.region,
            aws_access_key_id=self.access_key,
            aws_secret_access_key=self.secret_key,
            config=Config(
                signature_version="s3v4",
                retries={"max_attempts": 5, "mode": "standard"},
                connect_timeout=10,
                read_timeout=60,
                # Spaces and MinIO serve paths, not virtual-hosted subdomains,
                # for arbitrary bucket names.
                s3={"addressing_style": "path"},
            ),
        )

    def put(self, key: str, data: bytes, media_type: str) -> str:
        full_key = self._key(key)
        try:
            self.client().put_object(
                Bucket=self.bucket,
                Key=full_key,
                Body=data,
                ContentType=media_type,
                # Evidence is never world-readable, whatever the bucket default.
                ACL="private",
            )
        except Exception as exc:
            raise StorageError(
                f"Could not write evidence to s3://{self.bucket}/{full_key}: {exc}"
            ) from exc
        return f"s3://{self.bucket}/{full_key}"

    def get(self, uri: str) -> bytes:
        _, _, rest = uri.partition("s3://")
        bucket, _, key = rest.partition("/")
        try:
            return self.client().get_object(Bucket=bucket, Key=key)["Body"].read()
        except Exception as exc:
            raise StorageError(f"Could not read evidence from {uri}: {exc}") from exc

    def check(self) -> dict:
        """Confirm the bucket is reachable and writable.

        Called at startup so a misconfigured store fails immediately rather
        than after a campaign has produced results it cannot store.
        """
        probe = self._key(".aegis-write-probe")
        try:
            client = self.client()
            client.put_object(Bucket=self.bucket, Key=probe, Body=b"ok", ACL="private")
            client.delete_object(Bucket=self.bucket, Key=probe)
            return {
                "backend": self.name,
                "writable": True,
                "location": f"s3://{self.bucket}/{self.prefix}".rstrip("/"),
                "endpoint": self.endpoint_url,
                "region": self.region,
            }
        except Exception as exc:
            return {
                "backend": self.name,
                "writable": False,
                "location": f"s3://{self.bucket}",
                "endpoint": self.endpoint_url,
                "region": self.region,
                "error": str(exc),
            }


def build_backend(settings=None):
    """Construct the configured backend."""
    settings = settings or get_settings()
    if settings.evidence_backend == "s3":
        return S3Backend(
            bucket=settings.s3_bucket,
            endpoint_url=settings.s3_endpoint_url,
            region=settings.s3_region,
            access_key=settings.s3_access_key,
            secret_key=settings.s3_secret_key,
            prefix=settings.s3_prefix,
        )
    if settings.evidence_backend != "file":
        raise StorageError(
            f"Unknown evidence backend {settings.evidence_backend!r}. Use 'file' or 's3'."
        )
    return FileBackend(settings.evidence_path)
