"""Evaluation runner.

Executes a campaign: for every (evaluation x system version) pair it resolves
scenarios, invokes the target, collects judgements from each configured
evaluator, aggregates them, stores immutable evidence, and rolls the results up
into a run verdict measured against the plan's threshold.

Two rules shape the whole file:

* A threshold is never invented. If the plan did not set one, the run reports
  its metrics and a verdict of `not_evaluated` (sections 34, 71).
* Every number is traceable. Each result stores the request, the response, the
  trace, each evaluator's judgement with its own provenance, and a content
  hash (sections 51, 52, 72).
"""

from __future__ import annotations

import platform
import random
import sys
import time
from collections.abc import Callable
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import audit
from ..connectors import TargetRequest, build_adapter
from ..enums import ResultStatus, RunStatus, Severity
from ..evaluators import EvaluationContext, Judgement, aggregate, build_evaluator
from ..hashing import content_hash, evidence_store
from ..models import (
    Campaign,
    DatasetItem,
    Evaluation,
    Evidence,
    Finding,
    HumanReview,
    Result,
    Run,
    Scenario,
    SystemVersion,
    utcnow,
)
from ..targeting import sample_agreement

# Aegis' own version, recorded on every run for reproducibility.
PLATFORM_VERSION = "0.1.0"


class JudgeFactory:
    """Builds the judge callable handed to model-based evaluators.

    The judge is an ordinary connector, so a program can point it at a
    government-hosted model, and the identity of that model travels with every
    judgement it produces.
    """

    def __init__(self, config: dict | None) -> None:
        self.config = config or {}
        self._adapter = None

    def build(self) -> Callable[[str, str, dict], dict] | None:
        if not self.config.get("connector_type"):
            return None

        def judge(system_prompt: str, prompt: str, evaluator_config: dict) -> dict:
            if self._adapter is None:
                self._adapter = build_adapter(self.config)
            parameters = dict(self.config.get("parameters") or {})
            # Judges run at low temperature so repeat evaluations are stable.
            parameters.setdefault("temperature", 0)
            response = self._adapter.invoke(
                TargetRequest(prompt=prompt, system_prompt=system_prompt, parameters=parameters)
            )
            if response.error:
                raise RuntimeError(response.error)
            return {
                "text": response.text,
                "model": self.config.get("model_name"),
                "model_version": self.config.get("model_version"),
                "connector": self.config.get("connector_type"),
                "temperature": parameters.get("temperature"),
            }

        return judge


def resolve_scenarios(db: Session, evaluation: Evaluation, project_id: str) -> list[Scenario]:
    """Select the scenarios an evaluation runs against.

    Selector keys: `keys` (explicit), `tags` (any match), `threat_types`,
    `pack` (source pack), `mission_tasks`, `limit`, `sample_seed`.
    Only approved scenarios run -- generated drafts stay out until a human
    accepts them (section 17).
    """
    selector = evaluation.scenario_selector or {}
    stmt = select(Scenario).where(
        Scenario.approved.is_(True),
        (Scenario.project_id == project_id) | (Scenario.project_id.is_(None)),
    )
    if keys := selector.get("keys"):
        stmt = stmt.where(Scenario.key.in_(keys))
    if threat_types := selector.get("threat_types"):
        stmt = stmt.where(Scenario.threat_type.in_(threat_types))
    if source := selector.get("pack"):
        stmt = stmt.where(Scenario.source == source)

    scenarios = list(db.execute(stmt).scalars())

    if tags := selector.get("tags"):
        wanted = set(tags)
        # Default to requiring every tag. Matching any tag is far too loose:
        # "tags: [red-team, data_poisoning]" would otherwise pull in every
        # red-team scenario and attribute unrelated failures to this
        # evaluation. Set tags_match: "any" where a union is intended.
        if selector.get("tags_match", "all") == "any":
            scenarios = [s for s in scenarios if wanted & set(s.tags or [])]
        else:
            scenarios = [s for s in scenarios if wanted <= set(s.tags or [])]
    if tasks := selector.get("mission_tasks"):
        wanted = set(tasks)
        scenarios = [s for s in scenarios if s.task in wanted or s.mission in wanted]

    # Project-local scenarios take precedence over identically keyed library ones.
    by_key: dict[str, Scenario] = {}
    for scenario in scenarios:
        existing = by_key.get(scenario.key)
        if existing is None or (scenario.project_id and not existing.project_id):
            by_key[scenario.key] = scenario
    scenarios = sorted(by_key.values(), key=lambda s: s.key)

    if limit := selector.get("limit"):
        rng = random.Random(selector.get("sample_seed", 1337))
        if len(scenarios) > limit:
            scenarios = sorted(rng.sample(scenarios, limit), key=lambda s: s.key)
    return scenarios


def scenario_to_dict(scenario: Scenario) -> dict:
    return {
        "id": scenario.id,
        "key": scenario.key,
        "title": scenario.title,
        "mission": scenario.mission,
        "task": scenario.task,
        "context": scenario.context,
        "input": scenario.input or {},
        "expected_behavior": scenario.expected_behavior or [],
        "prohibited_behavior": scenario.prohibited_behavior or [],
        "rubric": scenario.rubric,
        "reference_answer": scenario.reference_answer,
        "reference_sources": scenario.reference_sources or [],
        "difficulty": scenario.difficulty,
        "threat_type": scenario.threat_type,
        "tags": scenario.tags or [],
        "criteria": scenario.criteria or [],
        "version": scenario.version,
        "content_hash": scenario.content_hash,
        # Selector fields evaluators read directly off the scenario input.
        **{
            k: v
            for k, v in (scenario.input or {}).items()
            if k
            in (
                "relevant_source_ids",
                "authorized_tools",
                "attack_success_indicators",
                "prohibited_patterns",
                "required_strings",
            )
        },
    }


def dataset_items_as_scenarios(db: Session, dataset_version_id: str) -> list[dict]:
    """Treat dataset rows as scenarios so uploaded test sets run unchanged."""
    items = list(
        db.execute(
            select(DatasetItem)
            .where(DatasetItem.dataset_version_id == dataset_version_id)
            .order_by(DatasetItem.ordinal)
        ).scalars()
    )
    scenarios = []
    for item in items:
        payload = item.payload or {}
        scenarios.append(
            {
                "id": None,
                "dataset_item_id": item.id,
                "key": f"item-{item.ordinal:05d}",
                "title": (payload.get("input") or payload.get("prompt") or "")[:120],
                "input": {
                    "prompt": payload.get("input") or payload.get("prompt") or "",
                    "documents": payload.get("documents") or [],
                    "tools": payload.get("tools") or [],
                },
                "reference_answer": payload.get("expected") or payload.get("reference"),
                "expected_behavior": payload.get("expected_behavior") or [],
                "prohibited_behavior": payload.get("prohibited_behavior") or [],
                "rubric": payload.get("rubric"),
                "tags": payload.get("tags") or [],
                "content_hash": item.content_hash,
                **{
                    k: payload[k]
                    for k in (
                        "relevant_source_ids",
                        "authorized_tools",
                        "attack_success_indicators",
                        "required_strings",
                    )
                    if k in payload
                },
            }
        )
    return scenarios


def build_request(scenario: dict, system_version: SystemVersion) -> TargetRequest:
    payload = scenario.get("input") or {}
    prompt = payload.get("prompt") or payload.get("input") or scenario.get("title") or ""
    return TargetRequest(
        prompt=prompt,
        system_prompt=payload.get("system_prompt") or system_version.system_prompt,
        documents=payload.get("documents") or [],
        tools=payload.get("tools") or list(system_version.tool_access or []),
        parameters=dict(system_version.parameters or {}),
        metadata={"scenario_key": scenario.get("key")},
    )


def system_version_config(system_version: SystemVersion) -> dict:
    return {
        "connector_type": system_version.connector_type,
        "endpoint": system_version.endpoint,
        "credential_ref": system_version.credential_ref,
        "parameters": system_version.parameters or {},
        "model_name": system_version.model_name,
        "model_version": system_version.model_version,
        "system_prompt": system_version.system_prompt,
    }


def reproducibility_record(
    run: Run, evaluation: Evaluation, system_version: SystemVersion, adapter_description: dict
) -> dict:
    """Section 51 -- everything needed to recreate this run."""
    return {
        "captured_at": utcnow().isoformat(),
        "platform_version": PLATFORM_VERSION,
        "python_version": sys.version.split()[0],
        "host_platform": platform.platform(),
        "system_version_id": system_version.id,
        "system_config_hash": system_version.config_hash,
        "model_name": system_version.model_name,
        "model_version": system_version.model_version,
        "system_prompt_hash": content_hash(system_version.system_prompt or ""),
        "model_parameters": system_version.parameters or {},
        "random_seed": (system_version.parameters or {}).get("seed"),
        "connector": adapter_description,
        "evaluation_id": evaluation.id,
        "evaluation_key": evaluation.key,
        "evaluation_version": evaluation.version,
        "evaluation_hash": evaluation.content_hash,
        "evaluators": evaluation.evaluators or [],
        "aggregation": evaluation.aggregation,
        "threshold": run.threshold or {},
        "dataset_version_id": run.dataset_version_id,
    }


def execute_run(db: Session, run: Run, judge_config: dict | None = None) -> Run:
    """Execute one run to completion and persist everything it produced."""
    evaluation = db.get(Evaluation, run.evaluation_id)
    system_version = db.get(SystemVersion, run.system_version_id)
    campaign = db.get(Campaign, run.campaign_id)
    if evaluation is None or system_version is None or campaign is None:
        run.status = RunStatus.FAILED
        run.error = "Run references an object that no longer exists."
        db.flush()
        return run

    run.status = RunStatus.RUNNING
    run.started_at = utcnow()
    db.flush()

    started = time.perf_counter()
    adapter = build_adapter(system_version_config(system_version))
    judge = JudgeFactory(judge_config).build()
    run.reproducibility = reproducibility_record(run, evaluation, system_version, adapter.describe())

    if run.dataset_version_id:
        scenarios = dataset_items_as_scenarios(db, run.dataset_version_id)
    else:
        scenarios = [
            scenario_to_dict(s) for s in resolve_scenarios(db, evaluation, campaign.project_id)
        ]

    if not scenarios:
        run.status = RunStatus.COMPLETED
        run.verdict = ResultStatus.NOT_EVALUATED
        run.completed_at = utcnow()
        run.scenario_count = 0
        run.error = "No approved scenarios matched this evaluation's selector."
        db.flush()
        return run

    evaluator_specs = evaluation.evaluators or []
    repetitions = max(1, int((evaluation.scenario_selector or {}).get("repetitions", 1)))

    counts = dict.fromkeys(ResultStatus.ALL, 0)
    latencies: list[int] = []
    evaluator_scores: dict[str, list[float]] = {}

    for scenario in scenarios:
        repetition_texts: list[str] = []
        for repetition in range(1, repetitions + 1):
            result = _execute_one(
                db,
                run=run,
                scenario=scenario,
                system_version=system_version,
                adapter=adapter,
                evaluator_specs=evaluator_specs,
                aggregation=evaluation.aggregation,
                judge=judge,
                repetition=repetition,
                repetition_texts=repetition_texts,
            )
            repetition_texts.append((result.response or {}).get("text") or "")
            counts[result.status] = counts.get(result.status, 0) + 1
            if result.latency_ms is not None:
                latencies.append(result.latency_ms)
            for judgement in result.judgements or []:
                if judgement.get("score") is not None:
                    evaluator_scores.setdefault(judgement["evaluator_key"], []).append(
                        judgement["score"]
                    )

    run.scenario_count = len(scenarios) * repetitions
    run.passed = counts[ResultStatus.PASS]
    run.warned = counts[ResultStatus.WARNING]
    run.failed = counts[ResultStatus.FAIL]
    run.errored = counts[ResultStatus.ERROR]
    run.pending_human = counts[ResultStatus.PENDING_HUMAN]

    scoreable = run.passed + run.warned + run.failed
    metrics: dict[str, Any] = {
        "scenarios": len(scenarios),
        "executions": run.scenario_count,
        "scoreable": scoreable,
        "pass_rate": round(run.passed / scoreable, 4) if scoreable else None,
        "fail_rate": round(run.failed / scoreable, 4) if scoreable else None,
        "not_evaluated": counts[ResultStatus.NOT_EVALUATED],
        "pending_human": run.pending_human,
        "errors": run.errored,
    }
    if latencies:
        ordered = sorted(latencies)
        metrics["latency_ms"] = {
            "median": ordered[len(ordered) // 2],
            "p95": ordered[min(len(ordered) - 1, int(len(ordered) * 0.95))],
            "max": ordered[-1],
            "mean": round(sum(ordered) / len(ordered), 1),
        }
    for key, scores in evaluator_scores.items():
        metrics[f"score.{key}"] = round(sum(scores) / len(scores), 4)

    run.metrics = metrics
    run.verdict = _run_verdict(run, metrics)
    run.status = (
        RunStatus.AWAITING_HUMAN if run.pending_human else RunStatus.COMPLETED
    )
    run.completed_at = utcnow()
    run.duration_ms = int((time.perf_counter() - started) * 1000)
    db.flush()

    _open_findings(db, run, evaluation, campaign)
    return run


def _execute_one(
    db: Session,
    *,
    run: Run,
    scenario: dict,
    system_version: SystemVersion,
    adapter,
    evaluator_specs: list[dict],
    aggregation: str,
    judge,
    repetition: int,
    repetition_texts: list[str],
) -> Result:
    request = build_request(scenario, system_version)
    request_dict = {
        "prompt": request.prompt,
        "system_prompt": request.system_prompt,
        "documents": request.documents,
        "tools": request.tools,
        "parameters": request.parameters,
    }

    response = adapter.invoke(request)
    confidence, confidence_source = response.confidence, response.confidence_source
    if confidence is None and not response.error:
        # No confidence from the target. Asking the same question again is
        # the one measure that needs nothing from the lab.
        confidence = sample_agreement(repetition_texts, response.text)
        confidence_source = "sample_agreement" if confidence is not None else None
    response_dict = {
        "text": response.text,
        "latency_ms": response.latency_ms,
        "tokens_in": response.tokens_in,
        "tokens_out": response.tokens_out,
        "retrieved": response.retrieved,
        "citations": response.citations,
        "error": response.error,
        # Part of the response rather than a column beside it, so the stored
        # evidence and its digest cover the confidence a weakness was found by.
        "confidence": confidence,
        "confidence_source": confidence_source,
        "repetition_outputs": [*repetition_texts, response.text] if repetition_texts else [],
        "system_correct": (scenario.get("input") or {}).get("system_correct"),
    }

    result = Result(
        run_id=run.id,
        scenario_id=scenario.get("id"),
        dataset_item_id=scenario.get("dataset_item_id"),
        request=request_dict,
        response={k: v for k, v in response_dict.items() if k != "repetition_outputs"},
        trace=response.trace,
        retrieval={"passages": response.retrieved, "citations": response.citations},
        latency_ms=response.latency_ms,
        tokens_in=response.tokens_in,
        tokens_out=response.tokens_out,
        repetition=repetition,
        error=response.error,
    )

    if response.error:
        result.status = ResultStatus.ERROR
        result.judgements = []
    else:
        human_reviews = _human_reviews_for(db, result)
        ctx = EvaluationContext(
            scenario=scenario,
            request=request_dict,
            response=response_dict,
            threshold=run.threshold or {},
            system_version=system_version_config(system_version),
            judge=judge,
            human_reviews=human_reviews,
        )
        judgements: list[Judgement] = []
        for spec in evaluator_specs:
            try:
                evaluator = build_evaluator(spec)
            except KeyError as exc:
                judgements.append(
                    Judgement(
                        evaluator_key=str(spec.get("evaluator")),
                        kind="unknown",
                        status=ResultStatus.ERROR,
                        error=str(exc),
                    )
                )
                continue
            judgement = evaluator.evaluate(ctx)
            if "weight" in spec:
                judgement.evaluator_metadata["weight"] = spec["weight"]
            judgements.append(judgement)

        status, score = aggregate(judgements, aggregation)
        result.status = status
        result.score = score
        result.judgements = [j.to_dict() for j in judgements]

    result.content_hash = content_hash(
        {
            "scenario": scenario.get("content_hash") or scenario.get("key"),
            "request": request_dict,
            "response": result.response,
            "judgements": result.judgements,
            "repetition": repetition,
        }
    )
    db.add(result)
    db.flush()

    _store_evidence(db, run, result, scenario)
    return result


def _human_reviews_for(db: Session, result: Result) -> list[dict]:
    """Reviews recorded against a previous execution of the same scenario.

    Lets a re-run reuse an existing human judgement rather than blocking on a
    second one, while still showing which reviewer produced it.
    """
    if not result.scenario_id:
        return []
    rows = db.execute(
        select(HumanReview)
        .join(Result, Result.id == HumanReview.result_id)
        .where(Result.scenario_id == result.scenario_id)
    ).scalars()
    return [
        {
            "reviewer_label": r.reviewer_label,
            "rubric_key": r.rubric_key,
            "score": r.score,
            "status": r.status,
            "comments": r.comments,
            "confidence": r.confidence,
        }
        for r in rows
    ]


def _store_evidence(db: Session, run: Run, result: Result, scenario: dict) -> None:
    """Persist the immutable artifact behind this result (section 52)."""
    payload = {
        "result_id": result.id,
        "run_id": run.id,
        "scenario": scenario,
        "request": result.request,
        "response": result.response,
        "trace": result.trace,
        "judgements": result.judgements,
        "status": result.status,
        "recorded_at": utcnow().isoformat(),
    }
    stored = evidence_store().put_json(f"runs/{run.id}/results/{result.id}.json", payload)
    db.add(
        Evidence(
            result_id=result.id,
            run_id=run.id,
            kind="execution_record",
            label=f"Execution record for {scenario.get('key')}",
            media_type=stored["media_type"],
            storage_uri=stored["storage_uri"],
            sha256=stored["sha256"],
            size_bytes=stored["size_bytes"],
        )
    )


def _run_verdict(run: Run, metrics: dict) -> str:
    """Compare run metrics against the plan's threshold.

    With no threshold, the run reports its numbers and returns
    `not_evaluated`. The product does not choose a passing bar (section 34).
    """
    threshold = run.threshold or {}
    if not threshold:
        return ResultStatus.NOT_EVALUATED

    # Counters default to 0 in the database but may be unset on an object that
    # has not been flushed, so read them defensively.
    passed, warned, failed = (run.passed or 0), (run.warned or 0), (run.failed or 0)
    errored, pending = (run.errored or 0), (run.pending_human or 0)

    if errored and errored == run.scenario_count:
        return ResultStatus.ERROR

    # Nothing reached a judgement, so no threshold can be said to have been met.
    # Without this guard a criterion like `max_failures: 0` would pass
    # vacuously on a run that evaluated nothing -- exactly the inferred success
    # section 71 forbids.
    if (passed + warned + failed) == 0:
        return ResultStatus.NOT_EVALUATED

    checks: list[bool] = []

    if (min_pass := threshold.get("min_pass_rate")) is not None:
        rate = metrics.get("pass_rate")
        if rate is None:
            return ResultStatus.NOT_EVALUATED
        checks.append(rate >= float(min_pass))

    if (max_fail := threshold.get("max_failures")) is not None:
        checks.append(failed <= int(max_fail))

    if (max_lat := threshold.get("max_latency_ms")) is not None:
        measured = (metrics.get("latency_ms") or {}).get(threshold.get("latency_statistic", "p95"))
        if measured is not None:
            checks.append(measured <= int(max_lat))

    for key, minimum in (threshold.get("min_scores") or {}).items():
        measured = metrics.get(f"score.{key}")
        if measured is None:
            return ResultStatus.NOT_EVALUATED
        checks.append(measured >= float(minimum))

    if not checks:
        return ResultStatus.NOT_EVALUATED
    if all(checks):
        # A run that satisfies its threshold but still holds outstanding human
        # review is not a clean pass.
        return ResultStatus.WARNING if pending else ResultStatus.PASS
    return ResultStatus.FAIL


def _open_findings(db: Session, run: Run, evaluation: Evaluation, campaign: Campaign) -> None:
    """Promote failures to findings, clustered by failure mode (section 27)."""
    failures = list(
        db.execute(
            select(Result).where(Result.run_id == run.id, Result.status == ResultStatus.FAIL)
        ).scalars()
    )
    if not failures:
        return

    clusters: dict[str, list[Result]] = {}
    for result in failures:
        clusters.setdefault(_cluster_key(result, evaluation), []).append(result)

    existing = db.execute(
        select(Finding.key).where(Finding.project_id == campaign.project_id)
    ).scalars()
    next_index = len(list(existing)) + 1

    for cluster_key, results in clusters.items():
        severity = _severity_for(evaluation, results)
        sample = results[0]
        reasons = [
            j.get("rationale")
            for r in results[:5]
            for j in (r.judgements or [])
            if j.get("status") == ResultStatus.FAIL and j.get("rationale")
        ]
        finding = Finding(
            project_id=campaign.project_id,
            key=f"F-{next_index:04d}",
            title=f"{evaluation.name}: {cluster_key.replace('_', ' ')}",
            severity=severity,
            domain=evaluation.domain,
            cluster_key=cluster_key,
            run_id=run.id,
            evaluation_id=evaluation.id,
            system_version_id=run.system_version_id,
            result_ids=[r.id for r in results],
            expected_behavior="; ".join((sample.scenario.expected_behavior or [])[:3])
            if sample.scenario
            else None,
            actual_behavior=(reasons[0] if reasons else None),
            reproduction={
                "failed_executions": len(results),
                "total_executions": run.scenario_count,
                "scenario_keys": [r.scenario.key for r in results[:10] if r.scenario],
                "reproducibility": run.reproducibility,
            },
            framework_refs=evaluation.framework_refs or [],
        )
        db.add(finding)
        next_index += 1

    audit.record(
        db,
        action="findings.opened",
        object_type="run",
        object_id=run.id,
        project_id=campaign.project_id,
        detail={"clusters": len(clusters), "failures": len(failures)},
    )
    db.flush()


def _cluster_key(result: Result, evaluation: Evaluation) -> str:
    """Group failures by the evaluator that rejected them (section 27)."""
    failing = [j for j in (result.judgements or []) if j.get("status") == ResultStatus.FAIL]
    if failing:
        return failing[0].get("evaluator_key") or evaluation.key
    return evaluation.key


def _severity_for(evaluation: Evaluation, results: list[Result]) -> str:
    """Derive an initial severity; a triager can always change it.

    Security and safety failures start high because an adversary only needs the
    attack to work once. Volume raises the floor for other domains.
    """
    base = (evaluation.default_threshold or {}).get("finding_severity")
    if base in Severity.ALL:
        return base
    if evaluation.domain in ("security", "safety"):
        return Severity.CRITICAL if len(results) > 2 else Severity.HIGH
    if len(results) > 20:
        return Severity.HIGH
    if len(results) > 5:
        return Severity.MEDIUM
    return Severity.LOW


def execute_campaign(db: Session, campaign: Campaign, judge_config: dict | None = None) -> Campaign:
    """Execute every queued run in a campaign and summarise the outcome."""
    campaign.status = RunStatus.RUNNING
    campaign.started_at = utcnow()
    db.flush()

    runs = list(
        db.execute(select(Run).where(Run.campaign_id == campaign.id).order_by(Run.created_at)).scalars()
    )
    for run in runs:
        if run.status in RunStatus.TERMINAL:
            continue
        try:
            execute_run(db, run, judge_config)
        except Exception as exc:
            run.status = RunStatus.FAILED
            run.error = f"{type(exc).__name__}: {exc}"
            run.completed_at = utcnow()
        db.commit()

    db.refresh(campaign)
    campaign.summary = summarize_campaign(db, campaign)
    campaign.status = (
        RunStatus.AWAITING_HUMAN
        if campaign.summary.get("pending_human")
        else RunStatus.COMPLETED
    )
    campaign.completed_at = utcnow()
    db.flush()
    db.commit()
    return campaign


def summarize_campaign(db: Session, campaign: Campaign) -> dict:
    """Roll runs up by domain. Never collapses to a single trust score (section 70)."""
    runs = list(db.execute(select(Run).where(Run.campaign_id == campaign.id)).scalars())
    totals = {"executed": 0, "passed": 0, "warning": 0, "failed": 0, "errors": 0, "pending_human": 0}
    domains: dict[str, dict] = {}

    for run in runs:
        totals["executed"] += run.scenario_count
        totals["passed"] += run.passed
        totals["warning"] += run.warned
        totals["failed"] += run.failed
        totals["errors"] += run.errored
        totals["pending_human"] += run.pending_human

        evaluation = db.get(Evaluation, run.evaluation_id)
        domain = evaluation.domain if evaluation else "performance"
        bucket = domains.setdefault(
            domain,
            {"runs": 0, "executed": 0, "passed": 0, "failed": 0, "warning": 0,
             "pending_human": 0, "verdicts": []},
        )
        bucket["runs"] += 1
        bucket["executed"] += run.scenario_count
        bucket["passed"] += run.passed
        bucket["failed"] += run.failed
        bucket["warning"] += run.warned
        bucket["pending_human"] += run.pending_human
        bucket["verdicts"].append(run.verdict)

    for bucket in domains.values():
        verdicts = bucket.pop("verdicts")
        bucket["status"] = _domain_status(verdicts)
        scoreable = bucket["passed"] + bucket["failed"] + bucket["warning"]
        bucket["pass_rate"] = round(bucket["passed"] / scoreable, 4) if scoreable else None

    findings = list(
        db.execute(
            select(Finding).where(
                Finding.project_id == campaign.project_id,
                Finding.run_id.in_([r.id for r in runs] or [""]),
            )
        ).scalars()
    )
    return {
        **totals,
        "runs": len(runs),
        "domains": domains,
        "findings": {
            severity: sum(1 for f in findings if f.severity == severity) for severity in Severity.ALL
        },
    }


def _domain_status(verdicts: list[str]) -> str:
    """A domain's status is the worst verdict inside it.

    `not_evaluated` never becomes a pass. If nothing in the domain reached a
    judgement, the domain reports NOT EVALUATED (section 71).
    """
    if not verdicts:
        return ResultStatus.NOT_EVALUATED
    if ResultStatus.FAIL in verdicts:
        return ResultStatus.FAIL
    if ResultStatus.ERROR in verdicts:
        return ResultStatus.ERROR
    if ResultStatus.WARNING in verdicts:
        return ResultStatus.WARNING
    if ResultStatus.PASS in verdicts:
        return ResultStatus.PASS
    return ResultStatus.NOT_EVALUATED
