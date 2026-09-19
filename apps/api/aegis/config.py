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
    s3_access_key: str = ""
    s3_secret_key: str = ""

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
        Path(self.evidence_path).mkdir(parents=True, exist_ok=True)
        if self.is_sqlite:
            raw = self.database_url.split("///", 1)[-1]
            parent = Path(raw).parent
            if str(parent) not in ("", "."):
                parent.mkdir(parents=True, exist_ok=True)


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
    if problems:
        raise InsecureConfiguration(
            "Refusing to start with a development configuration in environment "
            f"'{settings.env}':\n  - " + "\n  - ".join(problems)
        )


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    _validate(settings)
    if os.getenv("AEGIS_SKIP_DIRS") != "1":
        settings.ensure_directories()
    return settings
