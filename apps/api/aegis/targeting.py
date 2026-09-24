"""Where a model is weak, and whether expert time has been spent there yet.

The platform's goal is narrower than "collect government data": it is to
collect the data the model is bad at, because that is what a frontier lab will
pay for and what changes the model when it trains on it. So before any expert
hour is spent, the question is where the model fails -- and, more sharply,
where it fails while sure of itself. A model that is wrong and unsure already
knows to hedge. A model that is wrong and confident will say the wrong thing
to a contracting officer in the tone of the right one.

Three rules shape this module.

  * Confidence is evidence about one answer, recorded with where it came from
    (`reported` by the lab, `logprob` from the API, `sample_agreement` from
    asking the same question more than once). A result with no confidence is
    counted as unknown -- never as confident, and never as unsure.
  * Nothing here is combined into a single figure. A weakness map is a table
    of counts a reader can sort, not a ranking the product has decided on.
    Which area is worth most to a customer is a commercial call.
  * A knowledge area nobody declared is reported as undeclared. It is not
    guessed from tags, because a guessed bin is a wrong price.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session

from .enums import ResultStatus

#: The confidence at or above which a wrong answer counts as confidently wrong.
#: A default the reader can change per request, and shown wherever it is used.
CONFIDENT_AT = 0.8

#: How an undeclared knowledge area is labelled. Not a bin anyone can buy.
UNDECLARED_LABEL = "Not declared"

UNRESOLVED = (ResultStatus.NOT_EVALUATED, ResultStatus.PENDING_HUMAN, ResultStatus.ERROR)


def confidence_of(response: dict | None) -> tuple[float | None, str | None]:
    """The model's confidence in one answer, and where that number came from.

    Anything that is not a number between 0 and 1 is unknown. A lab that sends
    a percentage, or a string, has not told us a confidence we can compare.
    """
    value = (response or {}).get("confidence")
    source = (response or {}).get("confidence_source")
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None, None
    if not 0.0 <= float(value) <= 1.0:
        return None, None
    return float(value), source or "unspecified"


def _normalise(text: str) -> str:
    return " ".join((text or "").lower().split())


def sample_agreement(previous: list[str], current: str) -> float | None:
    """Share of the samples so far that gave this same answer.

    Needs at least two samples; one sample agrees with itself and says nothing.
    Works on any model with no cooperation from the lab, which is why it is the
    fallback when the target reports no confidence of its own.
    """
    if not previous:
        return None
    samples = [*previous, current]
    target = _normalise(current)
    return sum(1 for s in samples if _normalise(s) == target) / len(samples)


# ---------------------------------------------------------------------------
# Resolving a result to the knowledge area it tested
# ---------------------------------------------------------------------------


class AreaResolver:
    """Resolve results and scenarios to a knowledge area, caching lookups.

    The scenario's declaration wins. A result run from a dataset item takes the
    item's own `knowledge_area` field. Neither means undeclared.
    """

    def __init__(self, db: Session) -> None:
        self.db = db
        self._scenarios: dict[str, object] = {}
        self._items: dict[str, dict] = {}

    def scenario(self, scenario_id: str | None):
        from .models import Scenario

        if not scenario_id:
            return None
        if scenario_id not in self._scenarios:
            self._scenarios[scenario_id] = self.db.get(Scenario, scenario_id)
        return self._scenarios[scenario_id]

    def for_result(self, result) -> str | None:
        from .models import DatasetItem

        scenario = self.scenario(result.scenario_id)
        if scenario is not None and scenario.knowledge_area:
            return scenario.knowledge_area
        if result.dataset_item_id:
            if result.dataset_item_id not in self._items:
                item = self.db.get(DatasetItem, result.dataset_item_id)
                self._items[result.dataset_item_id] = (item.payload or {}) if item else {}
            area = self._items[result.dataset_item_id].get("knowledge_area")
            if isinstance(area, str) and area.strip():
                return area.strip()
        return None


def results_in_scope(db: Session, project_id: str | None = None) -> list:
    """Every result, or every result in one project."""
    from .models import Campaign, Result, Run

    query = select(Result)
    if project_id:
        query = (
            query.join(Run, Run.id == Result.run_id)
            .join(Campaign, Campaign.id == Run.campaign_id)
            .where(Campaign.project_id == project_id)
        )
    return list(db.execute(query.order_by(Result.created_at)).scalars())


# ---------------------------------------------------------------------------
# Per-scenario outcome: what the model did on this problem
# ---------------------------------------------------------------------------


@dataclass
class Outcome:
    passed: int = 0
    failed: int = 0
    warned: int = 0
    unresolved: int = 0
    confident_wrong: int = 0
    unsure_wrong: int = 0
    confidence_unknown_wrong: int = 0
    confidences: list[float] = field(default_factory=list)

    def add(self, result, confident_at: float) -> None:
        status = result.status
        if status == ResultStatus.PASS:
            self.passed += 1
        elif status == ResultStatus.WARNING:
            self.warned += 1
        elif status == ResultStatus.FAIL:
            self.failed += 1
            confidence, _ = confidence_of(result.response)
            if confidence is None:
                self.confidence_unknown_wrong += 1
            elif confidence >= confident_at:
                self.confident_wrong += 1
            else:
                self.unsure_wrong += 1
        else:
            # NOT_EVALUATED, PENDING_HUMAN and ERROR say nothing about whether
            # the model was right, so they are kept apart from both.
            self.unresolved += 1

    @property
    def label(self) -> str:
        """One word for a delivery record. Unknown stays unknown.

        Failing once is enough to call it a failure: a model that gets a
        contract question right two times in three is not safe to ask it.
        """
        if self.failed:
            return "failed"
        if self.passed or self.warned:
            return "passed"
        return "not_evaluated"

    def as_dict(self) -> dict:
        return {
            "passed": self.passed,
            "failed": self.failed,
            "warned": self.warned,
            "unresolved": self.unresolved,
            "confident_wrong": self.confident_wrong,
            "unsure_wrong": self.unsure_wrong,
            "confidence_unknown_wrong": self.confidence_unknown_wrong,
            "outcome": self.label,
        }


def scenario_outcomes(
    db: Session,
    scenario_ids: Iterable[str] | None = None,
    confident_at: float = CONFIDENT_AT,
    project_id: str | None = None,
) -> dict[str, Outcome]:
    """What the model did on each scenario, across every run of it."""
    wanted = set(scenario_ids) if scenario_ids is not None else None
    out: dict[str, Outcome] = {}
    for result in results_in_scope(db, project_id):
        if not result.scenario_id:
            continue
        if wanted is not None and result.scenario_id not in wanted:
            continue
        out.setdefault(result.scenario_id, Outcome()).add(result, confident_at)
    return out


# ---------------------------------------------------------------------------
# The weakness map
# ---------------------------------------------------------------------------


def weakness_map(
    db: Session, project_id: str | None = None, confident_at: float = CONFIDENT_AT
) -> dict:
    """Model outcomes and expert effort, per knowledge area."""
    from .models import ReasoningTrace

    resolver = AreaResolver(db)
    areas: dict[str | None, dict] = {}

    def row(area: str | None) -> dict:
        if area not in areas:
            areas[area] = {
                "outcome": Outcome(),
                "scenarios": set(),
                "failed_scenarios": set(),
                "traced_scenarios": set(),
                "traces": 0,
                "qualified_traces": 0,
                "expert_seconds": 0,
                "traces_without_time": 0,
            }
        return areas[area]

    with_confidence = 0
    sources: dict[str, int] = {}
    results = results_in_scope(db, project_id)
    for result in results:
        entry = row(resolver.for_result(result))
        entry["outcome"].add(result, confident_at)
        if result.scenario_id:
            entry["scenarios"].add(result.scenario_id)
            if result.status == ResultStatus.FAIL:
                entry["failed_scenarios"].add(result.scenario_id)
        confidence, source = confidence_of(result.response)
        if confidence is not None:
            with_confidence += 1
            sources[source] = sources.get(source, 0) + 1

    traces = db.execute(select(ReasoningTrace)).scalars()
    for trace in traces:
        if project_id:
            scenario = resolver.scenario(trace.scenario_id)
            if scenario is None or scenario.project_id not in (None, project_id):
                continue
        entry = row(trace.knowledge_area)
        entry["traces"] += 1
        if trace.qualified:
            entry["qualified_traces"] += 1
            if trace.scenario_id:
                entry["traced_scenarios"].add(trace.scenario_id)
            if trace.time_spent_seconds is None:
                entry["traces_without_time"] += 1
            else:
                entry["expert_seconds"] += trace.time_spent_seconds

    rows = []
    for area, entry in areas.items():
        outcome: Outcome = entry["outcome"]
        rows.append(
            {
                "knowledge_area": area,
                "label": area or UNDECLARED_LABEL,
                "declared": area is not None,
                "results": outcome.passed + outcome.failed + outcome.warned + outcome.unresolved,
                **{k: v for k, v in outcome.as_dict().items() if k != "outcome"},
                "scenarios": len(entry["scenarios"]),
                "failed_scenarios": len(entry["failed_scenarios"]),
                # The capture backlog: problems the model got wrong that no
                # qualified expert has worked yet.
                "failed_without_trace": len(entry["failed_scenarios"] - entry["traced_scenarios"]),
                "traces": entry["traces"],
                "qualified_traces": entry["qualified_traces"],
                "expert_seconds": entry["expert_seconds"],
                "traces_without_time": entry["traces_without_time"],
            }
        )

    # Declared areas first, most confidently wrong first. A reader re-sorts by
    # whatever they are pricing on; this order is a starting point, not a rank.
    rows.sort(
        key=lambda r: (
            not r["declared"],
            -r["confident_wrong"],
            -r["failed"],
            r["label"].lower(),
        )
    )

    return {
        "confident_at": confident_at,
        "areas": rows,
        "results": len(results),
        "confidence": {
            "with_confidence": with_confidence,
            "without_confidence": len(results) - with_confidence,
            "sources": sources,
        },
    }
