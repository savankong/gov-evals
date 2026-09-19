"""Model connector framework (sections 19, 46, 56)."""

from . import builtin  # noqa: F401  (registers the shipped adapters)
from .base import (
    EgressDenied,
    ModelAdapter,
    TargetRequest,
    TargetResponse,
    available_adapters,
    build_adapter,
    get_adapter,
    register_adapter,
)

__all__ = [
    "EgressDenied",
    "ModelAdapter",
    "TargetRequest",
    "TargetResponse",
    "available_adapters",
    "build_adapter",
    "get_adapter",
    "register_adapter",
]
