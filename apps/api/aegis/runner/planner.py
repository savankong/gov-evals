"""Evaluation plan generation (section 13).

The planner drafts a T&E strategy from the mission profile, the system
architecture and the deployment context. It produces a draft a human edits and
approves -- it never approves itself, and it never chooses a passing threshold
on the customer's behalf.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..enums import Domain, SystemKind, TEVVLayer
from ..models import Evaluation, EvaluationPlan, EvaluationPlanItem, MissionProfile, SystemVersion


def _selection_reasons(
    evaluation: Evaluation,
    mission: MissionProfile | None,
    system_version: SystemVersion | None,
    impact_level: str | None,
) -> list[str]:
    """Explain why an evaluation is in the draft, so a tester can argue with it."""
    reasons = []
    if system_version:
        if evaluation.domain == Domain.SECURITY and system_version.tool_access:
            reasons.append("System grants the model tool access, widening the attack surface.")
        if "rag" in (evaluation.system_types or []) and system_version.rag_architecture:
            reasons.append("System retrieves from an external corpus, so retrieval is evaluated separately from generation.")
        if "agent" in (evaluation.system_types or []) and system_version.agent_capabilities:
            reasons.append("System takes autonomous actions, so tool authorisation and loop behaviour are in scope.")
    if mission:
        if evaluation.domain == Domain.SECURITY and mission.adversaries:
            reasons.append(f"Mission profile names adversaries: {', '.join(mission.adversaries[:3])}.")
        if evaluation.key == "latency-operational-load" and mission.latency_requirement_ms:
            reasons.append(f"Mission sets a {mission.latency_requirement_ms} ms latency requirement.")
        if evaluation.domain == Domain.HUMAN_FACTORS and mission.human_oversight:
            reasons.append("Mission requires human oversight, so operator reliance is measured.")
        for failure in mission.unacceptable_failures or []:
            text = failure.lower()
            if evaluation.domain == Domain.SECURITY and any(
                w in text for w in ("inject", "manipulat", "adversar", "exfiltrat")
            ):
                reasons.append(f"Addresses an unacceptable failure: \"{failure}\".")
                break
            if evaluation.domain in (Domain.PERFORMANCE, Domain.RESPONSIBLE_AI) and any(
                w in text for w in ("fabricat", "hallucinat", "unsupported", "invent")
            ):
                reasons.append(f"Addresses an unacceptable failure: \"{failure}\".")
                break
    if impact_level in ("IL5", "IL6") and evaluation.domain == Domain.SECURITY:
        reasons.append(f"Deployment impact level {impact_level} raises the security evidence bar.")
    if not reasons:
        reasons.append(f"Baseline coverage for the {Domain.LABELS.get(evaluation.domain, evaluation.domain)} domain.")
    return reasons


def _seed_threshold(evaluation: Evaluation, mission: MissionProfile | None) -> dict:
    """Start an item's threshold from the library default plus the mission.

    Where the mission profile states a requirement in measurable terms -- a
    latency budget, for instance -- it is carried into the draft rather than
    left for a tester to retype. The value still arrives flagged as
    unconfirmed: the program office owns the passing bar (section 34).
    """
    threshold = dict(evaluation.default_threshold or {})
    if mission and mission.latency_requirement_ms and evaluation.domain == Domain.INTEGRATION:
        threshold.setdefault("max_latency_ms", mission.latency_requirement_ms)
        threshold.setdefault("latency_statistic", "p95")
    threshold["source"] = "library_default_unconfirmed"
    return threshold


def generate_plan(
    db: Session,
    *,
    project,
    system_version: SystemVersion | None = None,
    name: str | None = None,
) -> EvaluationPlan:
    """Draft an evaluation plan for a project.

    Coverage is deliberately broad: layers and domains that cannot be covered
    by an automated evaluation still appear, marked NOT EVALUATED, so the gaps
    are visible rather than absent (section 71).
    """
    mission = db.execute(
        select(MissionProfile).where(MissionProfile.project_id == project.id)
    ).scalar_one_or_none()

    system_kind = None
    if system_version is not None:
        system = system_version.system
        system_kind = system.kind if system else None
    elif project.systems:
        system_kind = project.systems[0].kind

    library = list(
        db.execute(
            select(Evaluation).where(
                (Evaluation.project_id == project.id) | (Evaluation.project_id.is_(None))
            )
        ).scalars()
    )

    applicable: list[Evaluation] = []
    for evaluation in library:
        types = evaluation.system_types or []
        if types and system_kind and system_kind not in types:
            # Keep RAG and agent evaluations when the architecture shows those
            # components even if the system is registered as a plain LLM.
            if not (
                system_version
                and (
                    (SystemKind.RAG in types and system_version.rag_architecture)
                    or (SystemKind.AGENT in types and system_version.agent_capabilities)
                )
            ):
                continue
        applicable.append(evaluation)

    plan = EvaluationPlan(
        project_id=project.id,
        name=name or f"{project.name} evaluation plan (draft)",
        status="draft",
        rationale=(
            "Drafted from the mission profile, system architecture and deployment context. "
            "Thresholds are intentionally unset: the program office sets the passing bar for "
            "each evaluation before this plan is approved."
        ),
        generated_from={
            "mission_profile_id": mission.id if mission else None,
            "system_version_id": system_version.id if system_version else None,
            "system_kind": system_kind,
            "impact_level": project.impact_level,
            "library_size": len(library),
        },
    )
    db.add(plan)
    db.flush()

    ordered = sorted(
        applicable,
        key=lambda e: (TEVVLayer.ALL.index(e.layer) if e.layer in TEVVLayer.ALL else 9, e.key),
    )
    for index, evaluation in enumerate(ordered):
        db.add(
            EvaluationPlanItem(
                plan_id=plan.id,
                evaluation_id=evaluation.id,
                # The library's suggested threshold is copied in as a starting
                # point and flagged; nothing runs against it until a human
                # confirms the number.
                threshold=_seed_threshold(evaluation, mission),
                rationale=" ".join(
                    _selection_reasons(evaluation, mission, system_version, project.impact_level)
                ),
                ordinal=index,
            )
        )

    db.flush()
    return plan


def coverage_report(db: Session, plan: EvaluationPlan) -> dict:
    """What the plan covers, and just as importantly what it does not."""
    from .engine import resolve_scenarios

    items = [i for i in plan.items if i.included]
    evaluations = [db.get(Evaluation, i.evaluation_id) for i in items]
    evaluations = [e for e in evaluations if e]

    # An evaluation whose selector matches nothing will report NOT EVALUATED at
    # run time. Surfacing that here means a tester finds out while writing the
    # plan rather than after a campaign produces an empty result.
    unmatched = []
    for evaluation in evaluations:
        if evaluation.dataset_ref:
            continue
        matched = resolve_scenarios(db, evaluation, plan.project_id)
        if not matched:
            unmatched.append(
                {
                    "evaluation_key": evaluation.key,
                    "evaluation_name": evaluation.name,
                    "selector": evaluation.scenario_selector,
                }
            )

    by_layer = {layer: 0 for layer in TEVVLayer.ALL}
    by_domain = {domain: 0 for domain in Domain.ALL}
    for evaluation in evaluations:
        if evaluation.layer in by_layer:
            by_layer[evaluation.layer] += 1
        if evaluation.domain in by_domain:
            by_domain[evaluation.domain] += 1

    unconfirmed = [
        i.evaluation_id
        for i in items
        if (i.threshold or {}).get("source") == "library_default_unconfirmed"
    ]
    return {
        "evaluations": len(evaluations),
        "layers": {
            layer: {
                "label": TEVVLayer.LABELS[layer],
                "count": count,
                "covered": count > 0,
            }
            for layer, count in by_layer.items()
        },
        "domains": {
            domain: {
                "label": Domain.LABELS[domain],
                "count": count,
                "covered": count > 0,
            }
            for domain, count in by_domain.items()
        },
        "uncovered_layers": [TEVVLayer.LABELS[k] for k, v in by_layer.items() if v == 0],
        "uncovered_domains": [Domain.LABELS[k] for k, v in by_domain.items() if v == 0],
        "thresholds_unconfirmed": len(unconfirmed),
        "evaluations_without_scenarios": unmatched,
        "ready_to_approve": not unconfirmed and any(by_layer.values()),
        "note": (
            "An evaluation listed under evaluations_without_scenarios has no scenario matching "
            "its selector and will report NOT EVALUATED. Add scenarios, adjust the selector, or "
            "remove the evaluation from the plan."
        ),
    }
