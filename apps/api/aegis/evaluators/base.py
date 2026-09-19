"""Evaluator interface and multi-evaluator consensus.

Section 20 defines four evaluator kinds -- deterministic, model-based, human
and external tool. Section 21 requires that no single evaluator or metric is
treated as definitive, so an evaluation carries a list of evaluators and an
explicit aggregation rule, and every judgement records who produced it.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from typing import Any

from ..enums import EvaluatorKind, ResultStatus


@dataclass
class Judgement:
    """One evaluator's opinion about one result.

    A model-based judgement is never presented as ground truth: `kind` travels
    with the score everywhere it is displayed (section 20).
    """

    evaluator_key: str
    kind: str
    status: str = ResultStatus.NOT_EVALUATED
    score: float | None = None
    rationale: str | None = None
    # Provenance of the judgement itself: judge model, version, prompt,
    # temperature, rubric, tool version. Required for model-based evaluators.
    evaluator_metadata: dict = field(default_factory=dict)
    confidence: float | None = None
    error: str | None = None

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class EvaluationContext:
    """Everything an evaluator may look at."""

    scenario: dict
    request: dict
    response: dict
    threshold: dict = field(default_factory=dict)
    config: dict = field(default_factory=dict)
    system_version: dict = field(default_factory=dict)
    # Set by the runner when a judge model is configured for this campaign.
    judge: Callable[[str, str, dict], dict] | None = None
    # Human reviews already recorded against this result.
    human_reviews: list[dict] = field(default_factory=list)

    @property
    def output_text(self) -> str:
        return (self.response.get("text") or "").strip()

    @property
    def retrieved(self) -> list[dict]:
        return self.response.get("retrieved") or []

    @property
    def citations(self) -> list[dict]:
        return self.response.get("citations") or []

    @property
    def trace(self) -> list[dict]:
        return self.response.get("trace") or []


class Evaluator(ABC):
    """Plugin base class (section 56)."""

    key: str = "base"
    kind: str = EvaluatorKind.DETERMINISTIC
    label: str = "Base evaluator"
    description: str = ""

    def __init__(self, config: dict | None = None) -> None:
        self.config = config or {}

    @abstractmethod
    def evaluate(self, ctx: EvaluationContext) -> Judgement:
        """Judge a single result."""

    def _judgement(self, **kwargs: Any) -> Judgement:
        kwargs.setdefault("evaluator_key", self.key)
        kwargs.setdefault("kind", self.kind)
        meta = kwargs.setdefault("evaluator_metadata", {})
        meta.setdefault("evaluator_key", self.key)
        meta.setdefault("config", self.config)
        return Judgement(**kwargs)


_REGISTRY: dict[str, type[Evaluator]] = {}


def register_evaluator(cls: type[Evaluator]) -> type[Evaluator]:
    _REGISTRY[cls.key] = cls
    return cls


def get_evaluator(key: str) -> type[Evaluator]:
    if key not in _REGISTRY:
        raise KeyError(f"Unknown evaluator '{key}'. Registered: {sorted(_REGISTRY)}")
    return _REGISTRY[key]


def available_evaluators() -> list[dict]:
    return [
        {"key": k, "kind": c.kind, "label": c.label, "description": c.description}
        for k, c in sorted(_REGISTRY.items())
    ]


def build_evaluator(spec: dict) -> Evaluator:
    """Instantiate from an evaluation definition entry.

    Spec shape: {"evaluator": "regex_absent", "config": {...}, "weight": 1.0}
    """
    return get_evaluator(spec.get("evaluator", spec.get("key", "")))(spec.get("config") or {})


# ---------------------------------------------------------------------------
# Consensus
# ---------------------------------------------------------------------------

#: Ordered worst-first so `max` over this key picks the most severe status.
_SEVERITY_RANK = {
    ResultStatus.PASS: 0,
    ResultStatus.NOT_EVALUATED: 1,
    ResultStatus.PENDING_HUMAN: 2,
    ResultStatus.WARNING: 3,
    ResultStatus.ERROR: 4,
    ResultStatus.FAIL: 5,
}


def aggregate(judgements: list[Judgement], rule: str = "all_must_pass") -> tuple[str, float | None]:
    """Combine independent judgements into one status and score.

    Rules:
      all_must_pass  - any fail fails; any pending human keeps the result open.
      any_pass       - one supporting judgement is enough (rarely appropriate).
      majority       - simple majority of scoreable judgements.
      weighted       - weighted mean of scores against the evaluation threshold.
      worst_case     - most severe status wins (the default for safety and
                       security evaluations, where one breach is a breach).
    """
    if not judgements:
        return ResultStatus.NOT_EVALUATED, None

    scored = [j for j in judgements if j.score is not None]
    mean_score = sum(j.score for j in scored) / len(scored) if scored else None

    if all(j.status == ResultStatus.NOT_EVALUATED for j in judgements):
        return ResultStatus.NOT_EVALUATED, mean_score

    if rule == "any_pass":
        if any(j.status == ResultStatus.PASS for j in judgements):
            return ResultStatus.PASS, mean_score
        return max(judgements, key=lambda j: _SEVERITY_RANK.get(j.status, 0)).status, mean_score

    if rule == "majority":
        considered = [j for j in judgements if j.status in ResultStatus.SCOREABLE]
        if not considered:
            return _worst(judgements), mean_score
        passes = sum(1 for j in considered if j.status == ResultStatus.PASS)
        if passes * 2 > len(considered):
            return ResultStatus.PASS, mean_score
        return (
            ResultStatus.FAIL
            if any(j.status == ResultStatus.FAIL for j in considered)
            else ResultStatus.WARNING
        ), mean_score

    if rule == "weighted":
        weights = [float(j.evaluator_metadata.get("weight", 1.0)) for j in scored]
        total = sum(weights)
        weighted_score = (
            sum(j.score * w for j, w in zip(scored, weights, strict=True)) / total
            if total
            else mean_score
        )
        if weighted_score is None:
            return _worst(judgements), None
        # Threshold is supplied by the plan, not invented here.
        return (ResultStatus.PASS if weighted_score >= 0.5 else ResultStatus.FAIL), weighted_score

    # all_must_pass and worst_case share the same severity walk; they differ
    # only in that all_must_pass surfaces a pending human review as blocking.
    worst = _worst(judgements)
    if rule == "worst_case" and worst == ResultStatus.PENDING_HUMAN:
        scoreable = [j for j in judgements if j.status in ResultStatus.SCOREABLE]
        if scoreable:
            worst = _worst(scoreable)
    return worst, mean_score


def _worst(judgements: list[Judgement]) -> str:
    return max(judgements, key=lambda j: _SEVERITY_RANK.get(j.status, 0)).status
