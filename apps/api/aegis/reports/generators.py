"""Test artifact generation (sections 40, 41).

Every report is assembled from stored records and carries the identifiers a
reader needs to go back to the evidence. Reports state what was not tested as
prominently as what was: a scope section that omits the gaps is not a defensible
artifact.
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..enums import Domain, FindingStatus, ResultStatus, Severity, TEVVLayer
from ..models import (
    AssuranceCase,
    Campaign,
    Evaluation,
    Finding,
    MissionProfile,
    Project,
    Risk,
    Run,
    SystemVersion,
)

STATUS_LABEL = {
    ResultStatus.PASS: "PASS",
    ResultStatus.WARNING: "WARNING",
    ResultStatus.FAIL: "FAIL",
    ResultStatus.ERROR: "ERROR",
    ResultStatus.NOT_EVALUATED: "NOT EVALUATED",
    ResultStatus.PENDING_HUMAN: "AWAITING HUMAN REVIEW",
}


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


def _banner(classification: str) -> str:
    return f"**{classification.upper()}**"


def _project_context(db: Session, project: Project) -> dict:
    mission = db.execute(
        select(MissionProfile).where(MissionProfile.project_id == project.id)
    ).scalar_one_or_none()
    return {"project": project, "mission": mission}


def executive_report(db: Session, project: Project, campaign: Campaign | None = None) -> str:
    """Section 41. Readable by a program executive without ML background."""
    mission = _project_context(db, project)["mission"]
    campaigns = (
        [campaign]
        if campaign
        else list(
            db.execute(
                select(Campaign)
                .where(Campaign.project_id == project.id)
                .order_by(Campaign.created_at.desc())
                .limit(1)
            ).scalars()
        )
    )
    runs: list[Run] = []
    for item in campaigns:
        runs.extend(db.execute(select(Run).where(Run.campaign_id == item.id)).scalars())

    findings = list(
        db.execute(select(Finding).where(Finding.project_id == project.id)).scalars()
    )
    risks = list(db.execute(select(Risk).where(Risk.project_id == project.id)).scalars())

    lines = [
        _banner(project.classification),
        "",
        f"# Evaluation summary: {project.name}",
        "",
        f"Generated {_now()} by Aegis Eval. Every figure below links to stored evidence.",
        "",
        "## What was evaluated",
        "",
    ]

    versions = {}
    for run in runs:
        version = db.get(SystemVersion, run.system_version_id)
        if version and version.id not in versions:
            versions[version.id] = version
    if versions:
        for version in versions.values():
            system = version.system
            lines.append(
                f"- **{system.name if system else 'System'} {version.version}** "
                f"({version.model_provider or 'provider not recorded'} / "
                f"{version.model_name or 'model not recorded'}), "
                f"configuration hash `{version.config_hash[:12]}`"
            )
    else:
        lines.append("- No system version has been evaluated in this project yet.")

    lines += ["", "## Intended use", ""]
    if mission:
        lines.append(f"**Mission.** {mission.mission}")
        if mission.tasks:
            lines.append("")
            lines.append("**Tasks.**")
            lines += [f"- {t}" for t in mission.tasks]
        if mission.users:
            lines.append("")
            lines.append(f"**Users.** {', '.join(str(u) for u in mission.users)}")
        if mission.operational_environment:
            lines.append("")
            lines.append(f"**Environment.** {mission.operational_environment}")
        if mission.unacceptable_failures:
            lines.append("")
            lines.append("**Failures the program has declared unacceptable.**")
            lines += [f"- {f}" for f in mission.unacceptable_failures]
    else:
        lines.append(
            "No mission profile is recorded. Results below therefore carry no operational "
            "context, which materially limits what they support."
        )

    lines += ["", "## Scope: what was and was not tested", ""]
    covered_layers, covered_domains = set(), set()
    for run in runs:
        evaluation = db.get(Evaluation, run.evaluation_id)
        if evaluation:
            covered_layers.add(evaluation.layer)
            covered_domains.add(evaluation.domain)

    lines.append("| CDAO T&E area | Covered in this evaluation |")
    lines.append("| --- | --- |")
    for layer in TEVVLayer.ALL:
        lines.append(
            f"| {TEVVLayer.LABELS[layer]} | {'Yes' if layer in covered_layers else '**Not evaluated**'} |"
        )
    lines += ["", "| Domain | Status |", "| --- | --- |"]
    domain_status = _domain_rollup(db, runs)
    for domain in Domain.ALL:
        status = domain_status.get(domain, ResultStatus.NOT_EVALUATED)
        lines.append(f"| {Domain.LABELS[domain]} | {STATUS_LABEL[status]} |")

    lines += [
        "",
        "A domain marked NOT EVALUATED has not been tested. It is not an implied pass.",
        "",
        "## Results",
        "",
    ]
    if runs:
        totals = {
            "executions": sum(r.scenario_count for r in runs),
            "passed": sum(r.passed for r in runs),
            "warning": sum(r.warned for r in runs),
            "failed": sum(r.failed for r in runs),
            "errors": sum(r.errored for r in runs),
            "pending": sum(r.pending_human for r in runs),
        }
        lines.append(
            f"{totals['executions']} scenario executions across {len(runs)} evaluations: "
            f"{totals['passed']} passed, {totals['warning']} warning, {totals['failed']} failed, "
            f"{totals['errors']} errored, {totals['pending']} awaiting human review."
        )
        # A campaign often covers several system versions, so each row names
        # the system it describes. Without it the table reads as duplicated
        # rows with contradictory numbers.
        multiple_systems = len({r.system_version_id for r in runs}) > 1
        header = "| Evaluation |" + (" System |" if multiple_systems else "")
        header += " Verdict | Passed | Failed | Executions |"
        divider = "| --- |" + (" --- |" if multiple_systems else "") + " --- | --- | --- | --- |"
        lines += ["", header, divider]

        for run in sorted(runs, key=lambda r: (r.verdict, r.system_version_id)):
            evaluation = db.get(Evaluation, run.evaluation_id)
            version = db.get(SystemVersion, run.system_version_id)
            system_cell = ""
            if multiple_systems:
                label = (
                    f"{version.system.name} {version.version}"
                    if version and version.system
                    else "unknown"
                )
                system_cell = f" {label} |"
            lines.append(
                f"| {evaluation.name if evaluation else run.evaluation_id} |"
                f"{system_cell} "
                f"{STATUS_LABEL.get(run.verdict, run.verdict)} | {run.passed} | {run.failed} | "
                f"{run.scenario_count} |"
            )
    else:
        lines.append("No evaluations have been executed.")

    lines += ["", "## Findings", ""]
    if findings:
        for severity in Severity.ALL:
            bucket = [f for f in findings if f.severity == severity]
            if bucket:
                lines.append(f"**{severity.title()}: {len(bucket)}**")
                for finding in bucket[:8]:
                    lines.append(f"- `{finding.key}` {finding.title} — {finding.status}")
                lines.append("")
    else:
        lines.append("No findings have been opened.")

    lines += ["", "## Risks", ""]
    if risks:
        lines += ["| Risk | Severity | Status | Residual | Acceptance authority |", "| --- | --- | --- | --- | --- |"]
        for risk in risks:
            lines.append(
                f"| `{risk.key}` {risk.title} | {risk.severity or 'not scored'} | {risk.status} | "
                f"{risk.residual_severity or 'not assessed'} | {risk.acceptance_authority or 'not recorded'} |"
            )
    else:
        lines.append("No risks have been recorded against this project.")

    lines += ["", "## Mitigations", ""]
    mitigated = [f for f in findings if f.mitigation]
    if mitigated:
        for finding in mitigated:
            lines.append(
                f"- `{finding.key}`: {finding.mitigation} "
                f"(status: {finding.mitigation_status}; retest: {finding.retest_status or 'not run'})"
            )
    else:
        lines.append("No mitigations have been recorded.")

    lines += ["", "## Evidence", ""]
    lines.append(
        f"Every result in this report is stored with the request, the response, the execution "
        f"trace, each evaluator's judgement and a SHA-256 content hash. "
        f"Campaign identifiers: {', '.join(c.id for c in campaigns) or 'none'}."
    )

    lines += ["", "## Limitations", ""]
    lines += _limitations(db, project, runs, findings)
    lines += ["", "---", "", _banner(project.classification)]
    return "\n".join(lines)


def _limitations(db: Session, project: Project, runs: list[Run], findings: list[Finding]) -> list[str]:
    """What this evaluation does not establish. Section 71 in report form."""
    notes = []
    covered_layers = set()
    for run in runs:
        evaluation = db.get(Evaluation, run.evaluation_id)
        if evaluation:
            covered_layers.add(evaluation.layer)

    for layer in TEVVLayer.ALL:
        if layer not in covered_layers:
            notes.append(
                f"- **{TEVVLayer.LABELS[layer]}** was not performed. This evaluation says "
                f"nothing about that area."
            )

    if any(run.pending_human for run in runs):
        outstanding = sum(run.pending_human for run in runs)
        notes.append(
            f"- {outstanding} result(s) are awaiting human review. Those results carry no verdict yet."
        )

    not_evaluated = [r for r in runs if r.verdict == ResultStatus.NOT_EVALUATED]
    if not_evaluated:
        notes.append(
            f"- {len(not_evaluated)} evaluation(s) returned NOT EVALUATED, usually because the plan "
            "sets no threshold for them or no scenarios matched. Their measurements are recorded, "
            "but no pass or fail judgement was made."
        )

    judge_used = any(
        (run.reproducibility or {}).get("evaluators")
        and any(e.get("evaluator", "").startswith("llm_") for e in (run.reproducibility or {}).get("evaluators", []))
        for run in runs
    )
    if judge_used:
        notes.append(
            "- Some judgements came from a model-based judge. Those are advisory evidence, "
            "recorded with the judge model and rubric, and are not ground truth."
        )

    unresolved = [f for f in findings if f.status in FindingStatus.ACTIVE]
    if unresolved:
        notes.append(f"- {len(unresolved)} finding(s) remain unresolved at the time of this report.")

    notes.append(
        "- Results apply to the system versions, scenarios and conditions recorded here. "
        "A change to the model, prompts, retrieval corpus, tools or operating environment "
        "invalidates them until the suite is re-run."
    )
    notes.append(
        "- This report is evaluation evidence. It is not an authorisation to operate and does "
        "not substitute for the government's own accreditation process."
    )
    return notes


def _domain_rollup(db: Session, runs: list[Run]) -> dict[str, str]:
    from ..runner.engine import _domain_status

    by_domain: dict[str, list[str]] = {}
    for run in runs:
        evaluation = db.get(Evaluation, run.evaluation_id)
        if evaluation:
            by_domain.setdefault(evaluation.domain, []).append(run.verdict)
    return {domain: _domain_status(verdicts) for domain, verdicts in by_domain.items()}


def evaluation_plan_report(db: Session, project: Project, plan) -> str:
    """A test plan artifact: what will be tested, how, and against what bar."""
    from ..runner.planner import coverage_report

    coverage = coverage_report(db, plan)
    mission = _project_context(db, project)["mission"]

    lines = [
        _banner(project.classification),
        "",
        f"# Evaluation plan: {plan.name}",
        "",
        f"Generated {_now()}. Status: **{plan.status}**.",
        "",
        "## Basis",
        "",
        plan.rationale or "No rationale recorded.",
        "",
    ]
    if mission:
        lines += [
            "## Mission being evaluated against",
            "",
            mission.mission,
            "",
        ]
        if mission.unacceptable_failures:
            lines.append("Failures declared unacceptable by the program:")
            lines += [f"- {f}" for f in mission.unacceptable_failures]
            lines.append("")

    lines += ["## Coverage", "", "| CDAO T&E area | Evaluations |", "| --- | --- |"]
    for layer, info in coverage["layers"].items():
        lines.append(f"| {info['label']} | {info['count'] if info['count'] else '**none**'} |")
    lines += ["", "| Domain | Evaluations |", "| --- | --- |"]
    for domain, info in coverage["domains"].items():
        lines.append(f"| {info['label']} | {info['count'] if info['count'] else '**none**'} |")

    if coverage["uncovered_domains"]:
        lines += [
            "",
            "**Not covered by this plan:** " + ", ".join(coverage["uncovered_domains"]) + ".",
            "Those domains will report NOT EVALUATED until the plan is extended.",
        ]

    lines += ["", "## Evaluations", "", "| # | Evaluation | Layer | Domain | Threshold | Rationale |", "| --- | --- | --- | --- | --- | --- |"]
    for item in sorted(plan.items, key=lambda i: i.ordinal):
        if not item.included:
            continue
        evaluation = db.get(Evaluation, item.evaluation_id)
        threshold = dict(item.threshold or {})
        unconfirmed = threshold.pop("source", None) == "library_default_unconfirmed"
        threshold_text = ", ".join(f"{k}={v}" for k, v in threshold.items()) or "not set"
        if unconfirmed:
            threshold_text += " *(library default, not yet confirmed by the program)*"
        lines.append(
            f"| {item.ordinal + 1} | {evaluation.name if evaluation else item.evaluation_id} | "
            f"{TEVVLayer.LABELS.get(evaluation.layer, '-') if evaluation else '-'} | "
            f"{Domain.LABELS.get(evaluation.domain, '-') if evaluation else '-'} | "
            f"{threshold_text} | {(item.rationale or '').replace('|', '/')} |"
        )

    if coverage["thresholds_unconfirmed"]:
        lines += [
            "",
            f"**{coverage['thresholds_unconfirmed']} threshold(s) are still library defaults.** "
            "The program office sets the passing bar for each evaluation. Until each is confirmed, "
            "those evaluations report their measurements without a pass or fail judgement.",
        ]

    unmatched = coverage.get("evaluations_without_scenarios") or []
    if unmatched:
        lines += [
            "",
            f"**{len(unmatched)} evaluation(s) have no matching scenario** and will report "
            "NOT EVALUATED until scenarios are added or the selector is adjusted:",
            "",
        ]
        lines += [f"- {u['evaluation_name']} (`{u['evaluation_key']}`)" for u in unmatched]

    lines += ["", "---", "", _banner(project.classification)]
    return "\n".join(lines)


def findings_report(db: Session, project: Project) -> str:
    findings = list(
        db.execute(
            select(Finding).where(Finding.project_id == project.id).order_by(Finding.key)
        ).scalars()
    )
    lines = [
        _banner(project.classification),
        "",
        f"# Findings report: {project.name}",
        "",
        f"Generated {_now()}. {len(findings)} finding(s).",
        "",
    ]
    if not findings:
        lines.append("No findings have been opened against this project.")
        return "\n".join(lines)

    for severity in Severity.ALL:
        bucket = [f for f in findings if f.severity == severity]
        if not bucket:
            continue
        lines += [f"## {severity.title()} ({len(bucket)})", ""]
        for finding in bucket:
            lines += [
                f"### {finding.key} — {finding.title}",
                "",
                f"- **Severity:** {finding.severity}",
                f"- **Status:** {finding.status}",
                f"- **Domain:** {Domain.LABELS.get(finding.domain, finding.domain or 'not set')}",
                f"- **Owner:** {finding.owner or 'unassigned'}",
                "",
            ]
            if finding.expected_behavior:
                lines += ["**Expected behaviour.** " + finding.expected_behavior, ""]
            if finding.actual_behavior:
                lines += ["**Observed behaviour.** " + finding.actual_behavior, ""]
            reproduction = finding.reproduction or {}
            if reproduction:
                failed = reproduction.get("failed_executions")
                total = reproduction.get("total_executions")
                if failed is not None and total:
                    lines.append(f"**Reproduction.** {failed} of {total} executions reproduced this failure.")
                keys = reproduction.get("scenario_keys") or []
                if keys:
                    lines.append(f"Affected scenarios: {', '.join(keys[:8])}.")
                lines.append("")
            if finding.root_cause_hypothesis:
                lines += ["**Root cause hypothesis.** " + finding.root_cause_hypothesis, ""]
            lines += [
                f"**Mitigation.** {finding.mitigation or 'Pending.'}",
                f"**Retest.** {finding.retest_status or ('Required.' if finding.retest_required else 'Not required.')}",
                "",
                f"Evidence: run `{finding.run_id}`, {len(finding.result_ids or [])} result record(s).",
                "",
            ]
    lines += ["---", "", _banner(project.classification)]
    return "\n".join(lines)


def comparison_report(db: Session, project: Project, comparison: dict) -> str:
    """Vendor-neutral comparison (sections 31, 65). No winner is declared."""
    lines = [
        _banner(project.classification),
        "",
        f"# Model comparison: {comparison.get('campaign_name', '')}",
        "",
        f"Generated {_now()}.",
        "",
        "All systems below ran the same scenarios under the same conditions in a single "
        "campaign, which is what makes the columns comparable.",
        "",
    ]
    systems = comparison.get("systems") or []
    if not systems:
        lines.append("No systems were evaluated in this campaign.")
        return "\n".join(lines)

    header = "| Evaluation | Domain | " + " | ".join(s["label"] for s in systems) + " |"
    lines += [header, "| --- | --- | " + " | ".join("---" for _ in systems) + " |"]
    for row in comparison.get("rows") or []:
        cells = []
        for cell in row["cells"]:
            if cell["status"] == ResultStatus.NOT_EVALUATED:
                cells.append("NOT EVALUATED")
            else:
                rate = cell.get("pass_rate")
                rate_text = f"{rate:.0%}" if isinstance(rate, (int, float)) else "—"
                cells.append(f"{STATUS_LABEL.get(cell['status'], cell['status'])} ({rate_text})")
        lines.append(f"| {row['evaluation_name']} | {row['domain_label']} | " + " | ".join(cells) + " |")

    lines += [
        "",
        "## How to read this",
        "",
        comparison.get("note", ""),
        "",
        "The platform does not compute an overall winner. Weighting these dimensions against "
        "mission requirements is a program decision, and different missions weight them "
        "differently.",
        "",
        "---",
        "",
        _banner(project.classification),
    ]
    return "\n".join(lines)


def assurance_case_report(db: Session, project: Project, case: AssuranceCase) -> str:
    """Section 29 -- claim, argument, evidence, limitation, residual risk."""
    lines = [
        _banner(project.classification),
        "",
        f"# Assurance case: {case.title}",
        "",
        f"Generated {_now()}. Status: **{case.status}**.",
        "",
    ]
    if case.context:
        lines += ["## Context", "", case.context, ""]

    version = db.get(SystemVersion, case.system_version_id) if case.system_version_id else None
    if version:
        system = version.system
        lines += [
            "## System this case covers",
            "",
            f"{system.name if system else 'System'} {version.version} — "
            f"{version.model_name or 'model not recorded'}, configuration hash "
            f"`{version.config_hash[:16]}`.",
            "",
        ]

    roots = [c for c in case.claims if c.parent_id is None]
    for claim in sorted(roots, key=lambda c: c.ordinal):
        lines += _render_claim(db, case, claim, depth=0)

    lines += ["## Residual risk", ""]
    lines.append(case.residual_risk_statement or "No residual risk statement has been recorded.")
    lines += [
        "",
        f"**Decision authority.** {case.decision_authority or 'Not recorded.'}",
        "",
        "Residual risk is accepted by the designated authority, not by this platform. "
        "This document assembles the evidence for that decision; it does not make it.",
        "",
        "---",
        "",
        _banner(project.classification),
    ]
    return "\n".join(lines)


def _render_claim(db: Session, case: AssuranceCase, claim, depth: int) -> list[str]:
    heading = "#" * min(6, depth + 2)
    label = "Claim" if depth == 0 else "Subclaim"
    lines = [
        f"{heading} {label}: {claim.statement}",
        "",
        f"**Support status:** {STATUS_LABEL.get(claim.support_status, claim.support_status)}",
        "",
    ]
    if claim.argument:
        lines += [f"**Argument.** {claim.argument}", ""]

    if claim.evidence_links:
        lines += ["**Evidence.**", ""]
        for link in claim.evidence_links:
            stance = "counter-evidence" if link.stance != "supports" else "supports"
            detail = _evidence_detail(db, link)
            lines.append(f"- [{stance}] {detail}")
        lines.append("")
    else:
        lines += [
            "**Evidence.** None linked. A claim with no linked evidence is an assertion, "
            "not an argument.",
            "",
        ]

    if claim.known_limitations:
        lines += ["**Known limitations.**", ""]
        lines += [f"- {limitation}" for limitation in claim.known_limitations]
        lines.append("")
    if claim.mitigations:
        lines += ["**Mitigations.**", ""]
        lines += [f"- {mitigation}" for mitigation in claim.mitigations]
        lines.append("")
    if claim.confidence_note:
        lines += [f"**Confidence.** {claim.confidence_note}", ""]

    children = [c for c in case.claims if c.parent_id == claim.id]
    for child in sorted(children, key=lambda c: c.ordinal):
        lines += _render_claim(db, case, child, depth + 1)
    return lines


def _evidence_detail(db: Session, link) -> str:
    if link.ref_type == "run":
        run = db.get(Run, link.ref_id)
        if run:
            evaluation = db.get(Evaluation, run.evaluation_id)
            return (
                f"{evaluation.name if evaluation else 'Evaluation'}: {run.passed} passed, "
                f"{run.failed} failed of {run.scenario_count} executions "
                f"(verdict {STATUS_LABEL.get(run.verdict, run.verdict)}, run `{run.id[:8]}`)."
                + (f" {link.note}" if link.note else "")
            )
    if link.ref_type == "finding":
        finding = db.get(Finding, link.ref_id)
        if finding:
            return f"Finding `{finding.key}` ({finding.severity}, {finding.status}): {finding.title}."
    return f"{link.ref_type} `{link.ref_id}`" + (f" — {link.note}" if link.note else "")


REPORT_KINDS = {
    "executive_summary": "Executive evaluation summary",
    "evaluation_plan": "Evaluation plan / T&E strategy input",
    "findings": "Failure and findings report",
    "comparison": "Model comparison report",
    "assurance_case": "AI assurance case",
}
