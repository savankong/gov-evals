"""Model connector framework (sections 19, 46, 56)."""

from .base import (  # noqa: F401
    EgressDenied,
    ModelAdapter,
    TargetRequest,
    TargetResponse,
    available_adapters,
    build_adapter,
    get_adapter,
    register_adapter,
)
from . import builtin  # noqa: F401  (registers the shipped adapters)

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
