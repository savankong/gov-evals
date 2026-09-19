"""Runtime configuration.

Every setting resolves to a value that works with no external dependency, so a
fresh checkout starts on a disconnected machine. Deployment-specific values
come from the environment (see .env.example).
"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

from .enums import Classification


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="AEGIS_", env_file=(".env", "../../.env"), extra="ignore"
    )

    env: str = "development"
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    secret_key: str = "change-me-in-every-deployment"
    access_token_ttl_minutes: int = 720

    database_url: str = "sqlite:///./data/aegis.db"

    evidence_backend: str = "file"
    evidence_path: str = "./data/evidence"
    s3_endpoint_url: str = ""
    s3_bucket: str = ""
    # Required for SigV4 signing. DigitalOcean Spaces uses the Space's region
    # (nyc3, ams3, sfo3, fra1, sgp1, syd1); AWS uses the bucket's region.
    s3_region: str = "us-east-1"
    s3_access_key: str = ""
    s3_secret_key: str = ""
    # Prefix inside the bucket, so one bucket can hold several deployments.
    s3_prefix: str = ""

    # Set on hosts whose container filesystem does not survive a deploy
    # (App Platform, Cloud Run, Heroku and similar).
    ephemeral_filesystem: bool = False

    # Highest marking this deployment may hold. Empty means no ceiling.
    # A deployment on infrastructure that is not accredited for a marking
    # should set this so the platform refuses the data rather than relying on
    # every operator to remember.
    max_classification: str = ""

    queue_backend: str = "inline"
    redis_url: str = "redis://redis:6379/0"
    worker_concurrency: int = 4

    telemetry_enabled: bool = False
    otlp_endpoint: str = ""

    # "allow" | "deny". Under "deny" a connector may only reach hosts named in
    # the allowlist -- the posture disconnected deployments run in.
    egress_policy: str = "allow"
    egress_allowlist: str = ""

    bootstrap_email: str = "admin@aegis.local"
    bootstrap_password: str = "aegis-dev-password"
    seed_demo: bool = True

    oidc_issuer: str = ""
    oidc_client_id: str = ""
    oidc_client_secret: str = ""

    cors_origins: str = "http://localhost:3000,http://127.0.0.1:3000"

    @property
    def allowlisted_hosts(self) -> list[str]:
        return [h.strip().lower() for h in self.egress_allowlist.split(",") if h.strip()]

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def is_sqlite(self) -> bool:
        return self.database_url.startswith("sqlite")

    def ensure_directories(self) -> None:
        if self.evidence_backend == "file":
            Path(self.evidence_path).mkdir(parents=True, exist_ok=True)
        if self.is_sqlite:
            raw = self.database_url.split("///", 1)[-1]
            parent = Path(raw).parent
            if str(parent) not in ("", "."):
                parent.mkdir(parents=True, exist_ok=True)


# Managed platforms inject connection strings under their own names, in formats
# SQLAlchemy does not accept as-is. Translating them here keeps the deployment
# spec declarative and means no shell wrapper has to exist purely to rewrite a
# URL before the process starts.
PLATFORM_DATABASE_VARS = ("AEGIS_DATABASE_URL", "DATABASE_URL")
PLATFORM_REDIS_VARS = ("AEGIS_REDIS_URL", "REDIS_URL")


def normalize_database_url(url: str) -> str:
    """Name the driver SQLAlchemy should use for a Postgres URL.

    DigitalOcean, Heroku and others hand out `postgres://` or `postgresql://`.
    SQLAlchemy 2 resolves the bare scheme to psycopg2, which this project does
    not depend on, so the psycopg (v3) driver is named explicitly.
    """
    if url.startswith("postgres://"):
        url = "postgresql://" + url[len("postgres://") :]
    if url.startswith("postgresql://"):
        url = "postgresql+psycopg://" + url[len("postgresql://") :]
    return url


def adopt_platform_env(env: dict | None = None) -> dict[str, str]:
    """Copy platform-provided connection strings into the settings namespace.

    An explicitly set AEGIS_* value always wins: an operator who names a URL
    means it. Returns what was adopted, for logging.
    """
    import os as _os

    env = env if env is not None else _os.environ
    adopted: dict[str, str] = {}

    aegis_db, platform_db = PLATFORM_DATABASE_VARS
    if not env.get(aegis_db) and env.get(platform_db):
        env[aegis_db] = normalize_database_url(env[platform_db])
        adopted[aegis_db] = platform_db

    aegis_redis, platform_redis = PLATFORM_REDIS_VARS
    if not env.get(aegis_redis) and env.get(platform_redis):
        env[aegis_redis] = env[platform_redis]
        adopted[aegis_redis] = platform_redis

    return adopted


DEFAULT_SECRET = "change-me-in-every-deployment"
MIN_SECRET_BYTES = 32


class InsecureConfiguration(RuntimeError):
    """Raised when a non-development deployment carries a weak configuration."""


def _validate(settings: Settings) -> None:
    """Refuse to start a real deployment with development defaults.

    A shipped default signing key is a credential everyone has. Failing loudly
    at startup is better than running with one in an environment that handles
    sensitive evaluation data.
    """
    if settings.env == "development":
        return

    problems = []
    if settings.secret_key == DEFAULT_SECRET:
        problems.append(
            "AEGIS_SECRET_KEY is still the shipped default. Generate one per deployment, "
            "for example: python -c 'import secrets; print(secrets.token_urlsafe(48))'"
        )
    elif len(settings.secret_key.encode()) < MIN_SECRET_BYTES:
        problems.append(
            f"AEGIS_SECRET_KEY is shorter than {MIN_SECRET_BYTES} bytes, which is below the "
            "recommended length for HMAC-SHA256 token signing."
        )
    if settings.bootstrap_password == "aegis-dev-password":
        problems.append(
            "AEGIS_BOOTSTRAP_PASSWORD is still the shipped default. Set one, or disable local "
            "accounts and federate through OIDC."
        )
    if settings.seed_demo:
        problems.append(
            "AEGIS_SEED_DEMO is enabled. Demonstration data should not be created outside "
            "development."
        )

    # A platform-as-a-service container has an ephemeral filesystem. SQLite and
    # a local evidence directory both vanish on the next deploy, taking the
    # audit chain and every stored artifact with them. Losing evidence quietly
    # is the worst failure this product can have, so it is refused at startup.
    if settings.ephemeral_filesystem:
        if settings.is_sqlite:
            problems.append(
                "AEGIS_EPHEMERAL_FILESYSTEM is set and the database is SQLite. The database "
                "would be lost on every deploy. Point AEGIS_DATABASE_URL at a managed "
                "Postgres instance."
            )
        if settings.evidence_backend == "file":
            problems.append(
                "AEGIS_EPHEMERAL_FILESYSTEM is set and the evidence backend is 'file'. Stored "
                "evidence would be lost on every deploy. Set AEGIS_EVIDENCE_BACKEND=s3 and "
                "configure an object store."
            )

    if settings.max_classification and settings.max_classification not in Classification.ALL:
        problems.append(
            f"AEGIS_MAX_CLASSIFICATION={settings.max_classification!r} is not a known marking. "
            f"Use one of: {', '.join(Classification.ALL)}."
        )

    if problems:
        raise InsecureConfiguration(
            "Refusing to start with a development configuration in environment "
            f"'{settings.env}':\n  - " + "\n  - ".join(problems)
        )


@lru_cache
def get_settings() -> Settings:
    adopt_platform_env()
    settings = Settings()
    _validate(settings)
    if os.getenv("AEGIS_SKIP_DIRS") != "1":
        settings.ensure_directories()
    return settings
