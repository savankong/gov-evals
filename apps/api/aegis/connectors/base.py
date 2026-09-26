"""Model adapter interface.

Section 46: the architecture may not depend on any one model provider, cloud,
inference service or evaluator model. Everything the runner needs from a target
system is expressed here, and new targets are added by registering a subclass
rather than by editing the core.
"""

from __future__ import annotations

import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlparse

from ..config import get_settings


class EgressDenied(RuntimeError):
    """Raised when a connector target is outside the deployment's allowlist."""


@dataclass
class TargetRequest:
    """What the runner asks a target system to do."""

    prompt: str
    system_prompt: str | None = None
    messages: list[dict] | None = None
    documents: list[dict] = field(default_factory=list)
    tools: list[dict] = field(default_factory=list)
    parameters: dict = field(default_factory=dict)
    metadata: dict = field(default_factory=dict)


@dataclass
class TargetResponse:
    """What came back, plus everything needed to judge and reproduce it."""

    text: str
    raw: dict = field(default_factory=dict)
    # None when the connector cannot measure it (a replay), never a made-up zero.
    latency_ms: int | None = 0
    tokens_in: int | None = None
    tokens_out: int | None = None
    # Observable execution trace: retrieval steps, tool calls, actions.
    # Hidden model reasoning is never requested or stored (section 25).
    trace: list[dict] = field(default_factory=list)
    retrieved: list[dict] = field(default_factory=list)
    citations: list[dict] = field(default_factory=list)
    error: str | None = None
    refused: bool = False
    # How sure the target was of this answer, 0-1, and how that was obtained:
    # "reported" by the target itself, or "logprob" from token probabilities.
    # None is unknown, which is the common case and is reported as such.
    confidence: float | None = None
    confidence_source: str | None = None


class ModelAdapter(ABC):
    """Base class for every target system adapter.

    `config` is the SystemVersion record rendered as a dict, so an adapter sees
    the endpoint, parameters, system prompt, tool list and credential reference
    exactly as they were recorded for reproducibility.
    """

    #: Registry key used in SystemVersion.connector_type.
    key: str = "base"
    #: Human label shown in the system registry UI.
    label: str = "Base adapter"
    #: Whether this adapter reaches outside the deployment boundary.
    requires_egress: bool = True

    def __init__(self, config: dict, secret: str | None = None) -> None:
        self.config = config or {}
        self.secret = secret
        self.endpoint = self.config.get("endpoint") or ""
        self.parameters = dict(self.config.get("parameters") or {})
        self.timeout = float(self.parameters.get("timeout_seconds", 60))

    @abstractmethod
    def invoke(self, request: TargetRequest) -> TargetResponse:
        """Execute one request against the target system."""

    def describe(self) -> dict:
        """Configuration fingerprint stored on every run for reproducibility."""
        return {
            "connector_type": self.key,
            "endpoint": self.endpoint,
            "model": self.config.get("model_name"),
            "model_version": self.config.get("model_version"),
            "parameters": self.parameters,
            "requires_egress": self.requires_egress,
        }

    # -- helpers -----------------------------------------------------------

    def _check_egress(self, url: str) -> None:
        """Enforce the deployment's egress policy before any outbound call."""
        settings = get_settings()
        if settings.egress_policy != "deny" or not self.requires_egress:
            return
        host = (urlparse(url).hostname or "").lower()
        allowed = settings.allowlisted_hosts
        if host in ("localhost", "127.0.0.1", "::1"):
            return
        if host not in allowed:
            raise EgressDenied(
                f"Egress policy is 'deny' and host '{host}' is not on the allowlist. "
                "Add it to AEGIS_EGRESS_ALLOWLIST or use a connector that stays inside "
                "the deployment boundary."
            )

    @staticmethod
    def _timed(fn, *args, **kwargs) -> tuple[Any, int]:
        started = time.perf_counter()
        value = fn(*args, **kwargs)
        return value, int((time.perf_counter() - started) * 1000)


_REGISTRY: dict[str, type[ModelAdapter]] = {}


def register_adapter(cls: type[ModelAdapter]) -> type[ModelAdapter]:
    """Plugin entry point (section 56). Third parties call this at import."""
    _REGISTRY[cls.key] = cls
    return cls


def get_adapter(key: str) -> type[ModelAdapter]:
    if key not in _REGISTRY:
        raise KeyError(
            f"Unknown connector '{key}'. Registered connectors: {sorted(_REGISTRY)}"
        )
    return _REGISTRY[key]


def available_adapters() -> list[dict]:
    return [
        {"key": k, "label": c.label, "requires_egress": c.requires_egress}
        for k, c in sorted(_REGISTRY.items())
    ]


def build_adapter(config: dict, secret: str | None = None) -> ModelAdapter:
    return get_adapter(config.get("connector_type", "echo"))(config, secret)
