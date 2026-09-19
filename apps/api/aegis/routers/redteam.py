"""Adaptive red-team campaigns (section 23)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import audit
from ..connectors import TargetRequest, build_adapter
from ..db import get_db
from ..enums import ResultStatus, Severity
from ..evaluators import EvaluationContext, build_evaluator
from ..models import Finding, MissionProfile, SystemVersion, User
from ..runner.engine import system_version_config
from ..runner.redteam import (
    ATTACKS_BY_KEY,
    AdaptiveCampaignState,
    campaign_report,
    next_variant,
    record_attempt,
    should_stop,
)
from ..schemas import AdaptiveRedTeamRequest
from ..security import Permission, require
from .deps import audit_context, get_project

router = APIRouter(tags=["red-team"])

MAX_BUDGET = 40


@router.post("/projects/{project_id}/red-team/adaptive")
def adaptive_campaign(
    project_id: str,
    payload: AdaptiveRedTeamRequest,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require(Permission.CAMPAIGN_EXECUTE)),
):
    """Run attack -> evaluate -> learn -> mutate -> retest against one target.

    The campaign is bounded by an explicit budget. Every attempt, including the
    ones that failed, is returned and stored: an attack that did not work is
    part of the evidence, and the conclusion says what the campaign did and did
    not establish.
    """
    project = get_project(db, project_id)
    template = ATTACKS_BY_KEY.get(payload.attack_key)
    if template is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            f"Unknown attack '{payload.attack_key}'. See GET /attacks for the library.",
        )

    version = db.get(SystemVersion, payload.system_version_id)
    if version is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "System version not found")

    budget = max(1, min(int(payload.budget), MAX_BUDGET))
    mission = db.execute(
        select(MissionProfile).where(MissionProfile.project_id == project_id)
    ).scalar_one_or_none()
    task = (
        payload.mission_task
        or (mission.tasks[0] if mission and mission.tasks else None)
        or "Complete the assigned task using the supplied material."
    )

    adapter = build_adapter(system_version_config(version))
    evaluator = build_evaluator({"evaluator": "attack_success", "config": {}})
    state = AdaptiveCampaignState(attack_key=template.key, budget=budget)

    while not should_stop(state, payload.stop_on_first_success):
        variant = next_variant(template, state, seed=hash(version.id) % 10_000)
        if variant is None:
            state.stop_reason = "mutation_strategies_exhausted"
            break
        mutation, payload_text = variant

        mutated = type(template)(
            key=template.key,
            name=template.name,
            category=template.category,
            description=template.description,
            vector=template.vector,
            payload=payload_text,
            carrier=template.carrier,
            success_indicators=template.success_indicators,
            severity=template.severity,
            mitigation=template.mitigation,
        )
        scenario_input = mutated.render(task, index=state.spent)

        response = adapter.invoke(
            TargetRequest(
                prompt=scenario_input.get("prompt", ""),
                system_prompt=version.system_prompt,
                documents=scenario_input.get("documents") or [],
                tools=list(version.tool_access or []),
                parameters=version.parameters or {},
            )
        )
        if response.error:
            record_attempt(
                state,
                mutation=mutation,
                payload=payload_text,
                response_text="",
                status=ResultStatus.ERROR,
            )
            state.stop_reason = f"target_unreachable: {response.error[:200]}"
            break

        judgement = evaluator.evaluate(
            EvaluationContext(
                scenario=scenario_input,
                request={"prompt": scenario_input.get("prompt"), "documents": scenario_input.get("documents") or []},
                response={
                    "text": response.text,
                    "trace": response.trace,
                    "retrieved": response.retrieved,
                },
            )
        )
        record_attempt(
            state,
            mutation=mutation,
            payload=payload_text,
            response_text=response.text,
            status=judgement.status,
        )

    report = campaign_report(state)

    finding_key = None
    if report["outcome"] == "vulnerable":
        count = len(
            list(db.execute(select(Finding.id).where(Finding.project_id == project_id)).scalars())
        )
        successful = next(a for a in state.attempts if a["attack_succeeded"])
        finding = Finding(
            project_id=project_id,
            key=f"F-{count + 1:04d}",
            title=f"{template.name} succeeded under adaptive testing",
            severity=template.severity if template.severity in Severity.ALL else Severity.HIGH,
            domain="security",
            cluster_key=f"adaptive:{template.key}",
            system_version_id=version.id,
            expected_behavior=(
                "Adversarial content must not change what the system does or says."
            ),
            actual_behavior=(
                f"The '{successful['mutation']}' variant of {template.name} achieved its "
                f"objective on round {successful['round']}."
            ),
            reproduction={
                "attack_key": template.key,
                "mutation": successful["mutation"],
                "payload": successful["payload"],
                "rounds_used": state.spent,
                "budget": budget,
                "attempts": state.attempts,
                "system_version_id": version.id,
                "system_config_hash": version.config_hash,
            },
            mitigation=template.mitigation,
            framework_refs=template.framework_refs,
        )
        db.add(finding)
        db.flush()
        finding_key = finding.key

    audit.record(
        db,
        action="red_team.adaptive_campaign",
        object_type="system_version",
        object_id=version.id,
        detail={
            "attack": template.key,
            "outcome": report["outcome"],
            "rounds": state.spent,
            "budget": budget,
            "finding": finding_key,
        },
        **audit_context(db, project, user, request),
    )
    db.commit()

    return {**report, "finding_key": finding_key, "system_version_id": version.id}
