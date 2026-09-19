"""Assurance case builder and evidence graph (sections 29, 30)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import audit
from ..db import get_db
from ..enums import ResultStatus, Severity
from ..models import (
    AssuranceCase,
    AssuranceClaim,
    AssuranceEvidenceLink,
    Campaign,
    Evaluation,
    Finding,
    MissionProfile,
    Requirement,
    Risk,
    Run,
    SystemVersion,
    User,
    utcnow,
)
from ..schemas import AssuranceCaseIn, AssuranceCaseOut, ClaimIn, EvidenceLinkIn
from ..security import Permission, get_current_user, require
from .deps import audit_context, fetch, get_project

router = APIRouter(tags=["assurance"])


@router.get("/projects/{project_id}/assurance", response_model=list[AssuranceCaseOut])
def list_cases(project_id: str, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    return list(
        db.execute(
            select(AssuranceCase)
            .where(AssuranceCase.project_id == project_id)
            .order_by(AssuranceCase.created_at.desc())
        ).scalars()
    )


@router.post("/projects/{project_id}/assurance", response_model=AssuranceCaseOut, status_code=201)
def create_case(
    project_id: str,
    payload: AssuranceCaseIn,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require(Permission.ASSURANCE_WRITE)),
):
    project = get_project(db, project_id)
    case = AssuranceCase(project_id=project_id, **payload.model_dump())
    db.add(case)
    db.flush()
    audit.record(
        db, action="assurance_case.created", object_type="assurance_case", object_id=case.id,
        detail={"title": case.title}, **audit_context(db, project, user, request),
    )
    db.commit()
    db.refresh(case)
    return case


@router.post("/projects/{project_id}/assurance/draft", response_model=AssuranceCaseOut, status_code=201)
def draft_case(
    project_id: str,
    request: Request,
    campaign_id: str | None = None,
    system_version_id: str | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(require(Permission.ASSURANCE_WRITE)),
):
    """Draft a case from what the project has actually evaluated.

    Claims are generated per evaluation domain with their support status read
    straight from the runs. A domain with no runs produces a claim marked
    NOT EVALUATED rather than being left out, so the gaps appear in the
    argument instead of being invisible.
    """
    project = get_project(db, project_id)
    mission = db.execute(
        select(MissionProfile).where(MissionProfile.project_id == project_id)
    ).scalar_one_or_none()

    campaign = db.get(Campaign, campaign_id) if campaign_id else None
    if campaign is None:
        campaign = db.execute(
            select(Campaign)
            .where(Campaign.project_id == project_id)
            .order_by(Campaign.created_at.desc())
            .limit(1)
        ).scalar_one_or_none()

    runs = (
        list(db.execute(select(Run).where(Run.campaign_id == campaign.id)).scalars())
        if campaign
        else []
    )

    # A case argues about one system version. A campaign often evaluates
    # several, so the runs are narrowed to the version this case covers --
    # otherwise the argument would draw on evidence from a system it is not
    # about, which is exactly the confusion an assurance case exists to prevent.
    target_version_id = system_version_id or (runs[0].system_version_id if runs else None)
    if target_version_id:
        runs = [r for r in runs if r.system_version_id == target_version_id]

    covered_version = db.get(SystemVersion, target_version_id) if target_version_id else None
    version_label = (
        f"{covered_version.system.name} {covered_version.version}"
        if covered_version and covered_version.system
        else "the evaluated system"
    )

    case = AssuranceCase(
        project_id=project_id,
        system_version_id=target_version_id,
        title=f"Deployment assurance case: {project.name}",
        context=(
            f"Mission: {mission.mission}" if mission else "No mission profile is recorded."
        )
        + (
            f" Covers {version_label}. Evidence drawn from campaign '{campaign.name}'."
            if campaign
            else " No campaign has been executed."
        ),
        status="draft",
    )
    db.add(case)
    db.flush()

    root = AssuranceClaim(
        case_id=case.id,
        statement=(
            f"{version_label} is suitable for its intended mission under the conditions "
            "and limitations recorded in this case."
        ),
        argument=(
            "The subclaims below decompose suitability by evaluation domain. Each carries the "
            "evidence that supports it, the evidence that counters it, and its known limitations."
        ),
        support_status=ResultStatus.NOT_EVALUATED,
        ordinal=0,
    )
    db.add(root)
    db.flush()

    by_domain: dict[str, list[Run]] = {}
    for run in runs:
        evaluation = db.get(Evaluation, run.evaluation_id)
        if evaluation:
            by_domain.setdefault(evaluation.domain, []).append(run)

    from ..enums import Domain

    ordinal = 0
    for domain in Domain.ALL:
        domain_runs = by_domain.get(domain, [])
        if not domain_runs and domain not in (
            Domain.PERFORMANCE,
            Domain.SECURITY,
            Domain.RESPONSIBLE_AI,
            Domain.HUMAN_FACTORS,
        ):
            continue

        support = _support_status(domain_runs)
        claim = AssuranceClaim(
            case_id=case.id,
            parent_id=root.id,
            statement=_claim_statement(domain, version_label),
            argument=(
                f"Supported by {len(domain_runs)} evaluation run(s) in this campaign."
                if domain_runs
                else "No evaluation in this project addresses this domain."
            ),
            support_status=support,
            known_limitations=(
                []
                if domain_runs
                else ["This domain has not been evaluated. No conclusion is available."]
            ),
            ordinal=ordinal,
        )
        db.add(claim)
        db.flush()
        ordinal += 1

        for run in domain_runs:
            db.add(
                AssuranceEvidenceLink(
                    claim_id=claim.id,
                    ref_type="run",
                    ref_id=run.id,
                    # A run that reached no judgement is neither support nor
                    # counter-evidence. Recording it as "counters" would
                    # overstate what is known; recording it as "supports" would
                    # be worse.
                    stance=_stance_for(run.verdict),
                    note=(
                        "Run produced no judgement against a threshold."
                        if run.verdict == ResultStatus.NOT_EVALUATED
                        else None
                    ),
                )
            )

        blocking = [
            f
            for f in db.execute(
                select(Finding).where(Finding.project_id == project_id, Finding.domain == domain)
            ).scalars()
            if Severity.ORDER.get(f.severity, 9) <= Severity.ORDER[Severity.HIGH]
        ]
        for finding in blocking:
            db.add(
                AssuranceEvidenceLink(
                    claim_id=claim.id,
                    ref_type="finding",
                    ref_id=finding.id,
                    stance="counters",
                    note="Unresolved finding at high severity or above.",
                )
            )

    db.flush()
    root.support_status = _roll_up(db, case)
    audit.record(
        db,
        action="assurance_case.drafted",
        object_type="assurance_case",
        object_id=case.id,
        detail={"campaign_id": campaign.id if campaign else None, "claims": ordinal + 1},
        **audit_context(db, project, user, request),
    )
    db.commit()
    db.refresh(case)
    return case


def _stance_for(verdict: str) -> str:
    """Map a run verdict onto the stance its evidence takes toward a claim."""
    if verdict == ResultStatus.PASS:
        return "supports"
    if verdict in (ResultStatus.FAIL, ResultStatus.ERROR):
        return "counters"
    # warning, pending_human and not_evaluated all leave the question open.
    return "inconclusive"


def _claim_statement(domain: str, project_name: str) -> str:
    from ..enums import Domain

    statements = {
        Domain.PERFORMANCE: f"{project_name} accomplishes its assigned mission tasks correctly.",
        Domain.RELIABILITY: f"{project_name} performs consistently across repeated use.",
        Domain.ROBUSTNESS: f"{project_name} continues to function when inputs or conditions vary.",
        Domain.SECURITY: f"An adversary cannot manipulate {project_name} into unintended behaviour.",
        Domain.SAFETY: f"{project_name} does not produce outcomes the program has declared unacceptable.",
        Domain.RESPONSIBLE_AI: f"{project_name} satisfies the Responsible AI requirements applicable to it.",
        Domain.HUMAN_FACTORS: f"Operators can use {project_name} appropriately and calibrate their reliance on it.",
        Domain.MISSION_EFFECTIVENESS: f"{project_name} improves the mission outcome it supports.",
        Domain.INTEGRATION: f"{project_name} operates correctly within its surrounding system.",
        Domain.RESILIENCE: f"{project_name} recovers from failure, degradation or disruption.",
        Domain.TRACEABILITY: f"Outputs of {project_name} can be reconstructed from the evidence behind them.",
    }
    return statements.get(domain, f"{project_name} satisfies the {domain} requirements.")


def _support_status(runs: list[Run]) -> str:
    """How well the evidence supports a claim.

    A claim backed partly by passing runs and partly by runs that reached no
    judgement is `warning` -- partially supported -- not `pass`. Reading it as
    fully supported would let unevaluated ground pass for tested ground, which
    is the failure mode this product exists to prevent.
    """
    if not runs:
        return ResultStatus.NOT_EVALUATED
    verdicts = [r.verdict for r in runs]
    if ResultStatus.FAIL in verdicts or ResultStatus.ERROR in verdicts:
        return ResultStatus.FAIL
    if all(v == ResultStatus.NOT_EVALUATED for v in verdicts):
        return ResultStatus.NOT_EVALUATED
    if (
        ResultStatus.WARNING in verdicts
        or ResultStatus.PENDING_HUMAN in verdicts
        or ResultStatus.NOT_EVALUATED in verdicts
    ):
        return ResultStatus.WARNING
    return ResultStatus.PASS


def _roll_up(db: Session, case: AssuranceCase) -> str:
    children = [c for c in case.claims if c.parent_id is not None]
    statuses = [c.support_status for c in children]
    if not statuses:
        return ResultStatus.NOT_EVALUATED
    if ResultStatus.FAIL in statuses:
        return ResultStatus.FAIL
    if ResultStatus.NOT_EVALUATED in statuses or ResultStatus.WARNING in statuses:
        # A case with an unevaluated subclaim is not a supported case.
        return ResultStatus.WARNING
    return ResultStatus.PASS


@router.get("/assurance/{case_id}")
def read_case(case_id: str, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    case = fetch(db, AssuranceCase, case_id, "Assurance case")

    def render(claim: AssuranceClaim) -> dict:
        return {
            "id": claim.id,
            "statement": claim.statement,
            "argument": claim.argument,
            "support_status": claim.support_status,
            "confidence_note": claim.confidence_note,
            "known_limitations": claim.known_limitations,
            "mitigations": claim.mitigations,
            "requirement": _requirement_brief(db, claim.requirement_id),
            "evidence": [
                {
                    "id": link.id,
                    "ref_type": link.ref_type,
                    "ref_id": link.ref_id,
                    "stance": link.stance,
                    "note": link.note,
                    "detail": _evidence_detail(db, link),
                }
                for link in claim.evidence_links
            ],
            "children": [
                render(child)
                for child in sorted(
                    (c for c in case.claims if c.parent_id == claim.id), key=lambda c: c.ordinal
                )
            ],
        }

    roots = sorted((c for c in case.claims if c.parent_id is None), key=lambda c: c.ordinal)
    return {
        "case": AssuranceCaseOut.model_validate(case).model_dump(),
        "claims": [render(c) for c in roots],
    }


def _requirement_brief(db: Session, requirement_id: str | None) -> dict | None:
    if not requirement_id:
        return None
    requirement = db.get(Requirement, requirement_id)
    if requirement is None:
        return None
    return {"id": requirement.id, "key": requirement.key, "statement": requirement.statement}


def _evidence_detail(db: Session, link: AssuranceEvidenceLink) -> dict:
    if link.ref_type == "run":
        run = db.get(Run, link.ref_id)
        if run:
            evaluation = db.get(Evaluation, run.evaluation_id)
            version = db.get(SystemVersion, run.system_version_id)
            system_label = (
                f"{version.system.name} {version.version}"
                if version and version.system
                else None
            )
            return {
                "label": evaluation.name if evaluation else "Evaluation run",
                "system": system_label,
                "verdict": run.verdict,
                "passed": run.passed,
                "failed": run.failed,
                "executions": run.scenario_count,
                "metrics": run.metrics,
            }
    if link.ref_type == "finding":
        finding = db.get(Finding, link.ref_id)
        if finding:
            return {
                "label": f"{finding.key} {finding.title}",
                "severity": finding.severity,
                "status": finding.status,
            }
    if link.ref_type == "risk":
        risk = db.get(Risk, link.ref_id)
        if risk:
            return {"label": f"{risk.key} {risk.title}", "severity": risk.severity, "status": risk.status}
    return {"label": f"{link.ref_type} {link.ref_id}"}


@router.post("/assurance/{case_id}/claims", status_code=201)
def add_claim(
    case_id: str,
    payload: ClaimIn,
    db: Session = Depends(get_db),
    user: User = Depends(require(Permission.ASSURANCE_WRITE)),
):
    case = fetch(db, AssuranceCase, case_id, "Assurance case")
    claim = AssuranceClaim(case_id=case_id, **payload.model_dump())
    db.add(claim)
    db.flush()
    audit.record(
        db,
        action="assurance_claim.created",
        object_type="assurance_claim",
        object_id=claim.id,
        project_id=case.project_id,
        actor_id=user.id,
        actor_label=user.email,
        detail={"statement": claim.statement[:200]},
    )
    db.commit()
    return {"id": claim.id, "statement": claim.statement, "support_status": claim.support_status}


@router.post("/claims/{claim_id}/evidence", status_code=201)
def link_evidence(
    claim_id: str,
    payload: EvidenceLinkIn,
    db: Session = Depends(get_db),
    user: User = Depends(require(Permission.ASSURANCE_WRITE)),
):
    claim = fetch(db, AssuranceClaim, claim_id, "Claim")
    link = AssuranceEvidenceLink(claim_id=claim_id, **payload.model_dump())
    db.add(link)
    db.flush()

    # Recompute support from the linked evidence rather than trusting the label.
    supporting = [e for e in claim.evidence_links if e.stance == "supports"]
    countering = [e for e in claim.evidence_links if e.stance == "counters"]
    inconclusive = [e for e in claim.evidence_links if e.stance == "inconclusive"]
    if countering:
        claim.support_status = (
            ResultStatus.FAIL if len(countering) > len(supporting) else ResultStatus.WARNING
        )
    elif supporting:
        # Supported, but held at warning while inconclusive evidence remains:
        # the claim is not fully established while questions are open.
        claim.support_status = ResultStatus.WARNING if inconclusive else ResultStatus.PASS
    elif inconclusive:
        claim.support_status = ResultStatus.NOT_EVALUATED

    audit.record(
        db,
        action="assurance_evidence.linked",
        object_type="assurance_claim",
        object_id=claim_id,
        actor_id=user.id,
        actor_label=user.email,
        detail={"ref_type": link.ref_type, "ref_id": link.ref_id, "stance": link.stance},
    )
    db.commit()
    return {"id": link.id, "claim_support_status": claim.support_status}


@router.post("/assurance/{case_id}/accept", response_model=AssuranceCaseOut)
def accept_case(
    case_id: str,
    decision_authority: str,
    residual_risk_statement: str,
    db: Session = Depends(get_db),
    user: User = Depends(require(Permission.RISK_ACCEPT)),
):
    """Record an authority's acceptance of the residual risk in this case."""
    case = fetch(db, AssuranceCase, case_id, "Assurance case")
    unsupported = [
        c.statement
        for c in case.claims
        if c.support_status in (ResultStatus.FAIL, ResultStatus.NOT_EVALUATED)
    ]
    case.status = "accepted"
    case.decision_authority = decision_authority
    case.residual_risk_statement = residual_risk_statement
    case.accepted_at = utcnow()
    audit.record(
        db,
        action="assurance_case.accepted",
        object_type="assurance_case",
        object_id=case.id,
        project_id=case.project_id,
        actor_id=user.id,
        actor_label=user.email,
        detail={
            "decision_authority": decision_authority,
            "recorded_by": user.email,
            # Recorded so the audit trail shows what was open at acceptance.
            "claims_unsupported_or_unevaluated": unsupported,
        },
    )
    db.commit()
    db.refresh(case)
    return case


@router.get("/projects/{project_id}/evidence-graph")
def evidence_graph(project_id: str, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    """The section 30 graph: mission through to assurance claim."""
    get_project(db, project_id)  # 404s on an unknown project
    mission = db.execute(
        select(MissionProfile).where(MissionProfile.project_id == project_id)
    ).scalar_one_or_none()
    requirements = list(
        db.execute(select(Requirement).where(Requirement.project_id == project_id)).scalars()
    )
    campaigns = list(
        db.execute(select(Campaign).where(Campaign.project_id == project_id)).scalars()
    )
    runs = list(
        db.execute(
            select(Run).where(Run.campaign_id.in_([c.id for c in campaigns] or [""]))
        ).scalars()
    )
    findings = list(db.execute(select(Finding).where(Finding.project_id == project_id)).scalars())
    risks = list(db.execute(select(Risk).where(Risk.project_id == project_id)).scalars())
    cases = list(
        db.execute(select(AssuranceCase).where(AssuranceCase.project_id == project_id)).scalars()
    )

    nodes, edges = [], []
    nodes.append({"id": f"mission:{project_id}", "type": "mission",
                  "label": mission.mission[:80] if mission else "No mission profile"})
    nodes.extend(
        {"id": f"requirement:{r.id}", "type": "requirement", "label": r.key} for r in requirements
    )
    edges.extend(
        {"from": f"mission:{project_id}", "to": f"requirement:{r.id}"} for r in requirements
    )
    for run in runs:
        evaluation = db.get(Evaluation, run.evaluation_id)
        nodes.append(
            {
                "id": f"run:{run.id}",
                "type": "run",
                "label": evaluation.name if evaluation else "Run",
                "status": run.verdict,
                "executions": run.scenario_count,
            }
        )
        edges.append({"from": f"mission:{project_id}", "to": f"run:{run.id}"})
    for finding in findings:
        nodes.append({"id": f"finding:{finding.id}", "type": "finding",
                      "label": finding.key, "status": finding.status, "severity": finding.severity})
        if finding.run_id:
            edges.append({"from": f"run:{finding.run_id}", "to": f"finding:{finding.id}"})
    nodes.extend(
        {
            "id": f"risk:{risk.id}",
            "type": "risk",
            "label": risk.key,
            "status": risk.status,
            "severity": risk.severity,
        }
        for risk in risks
    )
    edges.extend(
        {"from": f"finding:{finding_id}", "to": f"risk:{risk.id}"}
        for risk in risks
        for finding_id in risk.finding_ids or []
    )
    for case in cases:
        nodes.append({"id": f"assurance:{case.id}", "type": "assurance_case",
                      "label": case.title[:60], "status": case.status})
        nodes.extend(
            {
                "id": f"claim:{claim.id}",
                "type": "claim",
                "label": claim.statement[:70],
                "status": claim.support_status,
            }
            for claim in case.claims
        )
        edges.extend(
            {"from": f"assurance:{case.id}", "to": f"claim:{claim.id}"} for claim in case.claims
        )
        for claim in case.claims:
            edges.extend(
                {
                    "from": f"{link.ref_type}:{link.ref_id}",
                    "to": f"claim:{claim.id}",
                    "stance": link.stance,
                }
                for link in claim.evidence_links
            )

    return {"nodes": nodes, "edges": edges}
