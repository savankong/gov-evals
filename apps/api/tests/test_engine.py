"""Runner behaviour, with an emphasis on what must never be inferred."""

from __future__ import annotations

from aegis.enums import ResultStatus, RunStatus
from aegis.models import Campaign, Evaluation, Run, Scenario, System, SystemVersion
from aegis.runner.engine import _run_verdict, execute_run, resolve_scenarios


def make_system(db, project, profile="cooperative"):
    system = System(project_id=project.id, name="Target", slug="target", kind="llm")
    db.add(system)
    db.flush()
    version = SystemVersion(
        system_id=system.id,
        version="v1",
        connector_type="echo",
        parameters={"profile": profile, "seed": 1},
        config_hash="hash-v1",
    )
    db.add(version)
    db.flush()
    return version


def make_scenario(db, project, key, tags, **kwargs):
    scenario = Scenario(
        project_id=project.id,
        key=key,
        title=key,
        input=kwargs.pop("input", {"prompt": "Summarise the supplied material."}),
        tags=tags,
        content_hash=f"hash-{key}",
        **kwargs,
    )
    db.add(scenario)
    db.flush()
    return scenario


def make_evaluation(db, key, evaluators, selector, aggregation="all_must_pass"):
    evaluation = Evaluation(
        key=key,
        name=key,
        evaluators=evaluators,
        scenario_selector=selector,
        aggregation=aggregation,
    )
    db.add(evaluation)
    db.flush()
    return evaluation


class TestScenarioSelection:
    def test_tags_are_required_together_by_default(self, db, project):
        """An evaluation asking for [red-team, data_poisoning] must not collect
        every red-team scenario -- that would attribute unrelated failures to it."""
        make_scenario(db, project, "poison-1", ["red-team", "data_poisoning"])
        make_scenario(db, project, "injection-1", ["red-team", "prompt_injection"])
        evaluation = make_evaluation(
            db, "poisoning", [], {"tags": ["red-team", "data_poisoning"]}
        )
        matched = resolve_scenarios(db, evaluation, project.id)
        assert [s.key for s in matched] == ["poison-1"]

    def test_any_matching_is_available_when_asked_for(self, db, project):
        make_scenario(db, project, "poison-1", ["red-team", "data_poisoning"])
        make_scenario(db, project, "injection-1", ["red-team", "prompt_injection"])
        evaluation = make_evaluation(
            db, "all-red-team", [], {"tags": ["data_poisoning", "prompt_injection"], "tags_match": "any"}
        )
        assert len(resolve_scenarios(db, evaluation, project.id)) == 2

    def test_unapproved_scenarios_never_run(self, db, project):
        """A generated draft stays out of every run until a human approves it."""
        make_scenario(db, project, "approved-1", ["mission-task"])
        make_scenario(db, project, "draft-1", ["mission-task"], approved=False, generated=True)
        evaluation = make_evaluation(db, "tasks", [], {"tags": ["mission-task"]})
        assert [s.key for s in resolve_scenarios(db, evaluation, project.id)] == ["approved-1"]


class TestRunVerdict:
    def _run(self, **kwargs):
        run = Run(campaign_id="c", evaluation_id="e", system_version_id="v")
        for key, value in kwargs.items():
            setattr(run, key, value)
        return run

    def test_no_threshold_means_no_judgement(self):
        run = self._run(threshold={}, passed=10, scenario_count=10)
        assert _run_verdict(run, {"pass_rate": 1.0}) == ResultStatus.NOT_EVALUATED

    def test_nothing_scoreable_never_passes_vacuously(self):
        """`max_failures: 0` is satisfied trivially when nothing was judged.
        That must report NOT EVALUATED, not a pass."""
        run = self._run(threshold={"max_failures": 0}, scenario_count=5, passed=0, warned=0, failed=0)
        assert _run_verdict(run, {"pass_rate": None}) == ResultStatus.NOT_EVALUATED

    def test_threshold_met_passes(self):
        run = self._run(threshold={"min_pass_rate": 0.9}, passed=10, scenario_count=10)
        assert _run_verdict(run, {"pass_rate": 1.0}) == ResultStatus.PASS

    def test_threshold_missed_fails(self):
        run = self._run(threshold={"min_pass_rate": 0.9}, passed=5, failed=5, scenario_count=10)
        assert _run_verdict(run, {"pass_rate": 0.5}) == ResultStatus.FAIL

    def test_outstanding_human_review_is_not_a_clean_pass(self):
        run = self._run(
            threshold={"min_pass_rate": 0.9}, passed=9, scenario_count=10, pending_human=1
        )
        assert _run_verdict(run, {"pass_rate": 1.0}) == ResultStatus.WARNING

    def test_unmeasured_metric_blocks_a_verdict(self):
        run = self._run(threshold={"min_scores": {"groundedness_overlap": 0.8}}, passed=5, scenario_count=5)
        assert _run_verdict(run, {"pass_rate": 1.0}) == ResultStatus.NOT_EVALUATED


class TestExecuteRun:
    def _setup(self, db, project, evaluators, profile="cooperative", threshold=None):
        version = make_system(db, project, profile)
        make_scenario(
            db,
            project,
            "s-1",
            ["mission-task"],
            input={
                "prompt": "Summarise the supplied material.",
                "documents": [{"source_id": "DOC-1", "text": "The schedule slipped by two months."}],
            },
        )
        evaluation = make_evaluation(db, "eval-1", evaluators, {"tags": ["mission-task"]})
        campaign = Campaign(project_id=project.id, name="Test campaign")
        db.add(campaign)
        db.flush()
        run = Run(
            campaign_id=campaign.id,
            evaluation_id=evaluation.id,
            system_version_id=version.id,
            threshold=threshold or {},
        )
        db.add(run)
        db.flush()
        return run

    def test_executes_and_stores_evidence(self, db, project):
        from aegis.models import Evidence

        run = self._setup(db, project, [{"evaluator": "citation_validity"}])
        execute_run(db, run)
        assert run.status == RunStatus.COMPLETED
        assert run.scenario_count == 1
        evidence = db.query(Evidence).filter(Evidence.run_id == run.id).all()
        assert len(evidence) == 1
        assert len(evidence[0].sha256) == 64

    def test_records_reproducibility(self, db, project):
        run = self._setup(db, project, [{"evaluator": "citation_validity"}])
        execute_run(db, run)
        record = run.reproducibility
        for field in (
            "platform_version",
            "system_config_hash",
            "model_parameters",
            "evaluation_hash",
            "evaluators",
            "connector",
        ):
            assert field in record, f"reproducibility record is missing {field}"

    def test_results_are_hashed(self, db, project):
        from aegis.models import Result

        run = self._setup(db, project, [{"evaluator": "citation_validity"}])
        execute_run(db, run)
        result = db.query(Result).filter(Result.run_id == run.id).one()
        assert len(result.content_hash) == 64

    def test_failures_open_a_finding(self, db, project):
        from aegis.models import Finding

        run = self._setup(
            db,
            project,
            [{"evaluator": "regex_absent", "config": {"patterns": ["Summary"]}}],
        )
        execute_run(db, run)
        assert run.failed == 1
        findings = db.query(Finding).filter(Finding.project_id == project.id).all()
        assert len(findings) == 1
        assert findings[0].cluster_key == "regex_absent"
        assert findings[0].reproduction["failed_executions"] == 1

    def test_human_evaluator_holds_the_run_open(self, db, project):
        run = self._setup(db, project, [{"evaluator": "human_review"}])
        execute_run(db, run)
        assert run.status == RunStatus.AWAITING_HUMAN
        assert run.pending_human == 1
        assert run.verdict == ResultStatus.NOT_EVALUATED

    def test_empty_selector_reports_rather_than_passing(self, db, project):
        version = make_system(db, project)
        evaluation = make_evaluation(db, "eval-empty", [], {"tags": ["no-such-tag"]})
        campaign = Campaign(project_id=project.id, name="Empty")
        db.add(campaign)
        db.flush()
        run = Run(
            campaign_id=campaign.id,
            evaluation_id=evaluation.id,
            system_version_id=version.id,
            threshold={"min_pass_rate": 0.9},
        )
        db.add(run)
        db.flush()
        execute_run(db, run)
        assert run.verdict == ResultStatus.NOT_EVALUATED
        assert "No approved scenarios matched" in run.error


class TestDeterminism:
    def test_same_configuration_produces_the_same_output(self, db, project):
        """Reproducibility is only meaningful if the offline target is stable."""
        from aegis.connectors import TargetRequest, build_adapter

        config = {"connector_type": "echo", "parameters": {"profile": "cooperative"}}
        first = build_adapter(config).invoke(TargetRequest(prompt="same prompt"))
        second = build_adapter(config).invoke(TargetRequest(prompt="same prompt"))
        assert first.text == second.text


class TestRegressionMatching:
    """A campaign covering several systems must not produce phantom regressions."""

    def _campaign_with_runs(self, db, project, name, versions, evaluation, statuses):
        from aegis.models import Campaign, Result, Run

        campaign = Campaign(project_id=project.id, name=name)
        db.add(campaign)
        db.flush()
        runs = []
        for version, status in zip(versions, statuses):
            run = Run(
                campaign_id=campaign.id,
                evaluation_id=evaluation.id,
                system_version_id=version.id,
                verdict=status,
            )
            db.add(run)
            db.flush()
            scenario = make_scenario(db, project, f"{name}-{version.id[:6]}", ["t"])
            db.add(
                Result(
                    run_id=run.id,
                    scenario_id=scenario.id,
                    status=status,
                    response={"text": f"output from {version.version}"},
                )
            )
            runs.append(run)
        db.flush()
        return campaign, runs

    def test_runs_match_on_system_version_not_evaluation_alone(self, db, project):
        """Comparing a campaign against itself must find zero differences.

        Before this was fixed, a campaign covering two system versions compared
        one system's run against the other's and reported the difference
        between two systems as a regression.
        """
        from aegis.runner.comparison import compare_campaigns

        good = make_system(db, project, "cooperative")
        bad = SystemVersion(
            system_id=good.system_id, version="v2", connector_type="echo",
            parameters={"profile": "fabricating"}, config_hash="hash-v2",
        )
        db.add(bad)
        db.flush()

        evaluation = make_evaluation(db, "eval-regress", [], {"tags": ["t"]})
        campaign, _ = self._campaign_with_runs(
            db, project, "dual", [good, bad], evaluation,
            [ResultStatus.PASS, ResultStatus.FAIL],
        )

        diff = compare_campaigns(db, campaign, campaign)
        assert diff["regression_detected"] is False
        assert diff["totals"] == {"new_failures": 0, "resolved": 0, "degraded": 0, "improved": 0}

    def test_missing_baseline_for_a_system_is_reported_not_guessed(self, db, project):
        from aegis.runner.comparison import compare_campaigns

        first = make_system(db, project, "cooperative")
        second = SystemVersion(
            system_id=first.system_id, version="v2", connector_type="echo",
            parameters={"profile": "cooperative"}, config_hash="hash-v2",
        )
        third = SystemVersion(
            system_id=first.system_id, version="v3", connector_type="echo",
            parameters={"profile": "cooperative"}, config_hash="hash-v3",
        )
        db.add_all([second, third])
        db.flush()

        evaluation = make_evaluation(db, "eval-missing", [], {"tags": ["t"]})
        baseline, _ = self._campaign_with_runs(
            db, project, "base", [first, second], evaluation,
            [ResultStatus.PASS, ResultStatus.PASS],
        )
        candidate, _ = self._campaign_with_runs(
            db, project, "cand", [third], evaluation, [ResultStatus.FAIL]
        )

        diff = compare_campaigns(db, baseline, candidate)
        # The baseline ran this evaluation against two versions and neither is
        # the candidate's, so no unambiguous comparison exists.
        assert diff["comparisons"][0]["status"] == "no_baseline"
        assert "unambiguous" in diff["comparisons"][0]["note"]

    def test_single_baseline_version_compares_across_the_version_boundary(self, db, project):
        """The ordinary case: v2 measured against v1."""
        from aegis.runner.comparison import compare_campaigns

        v1 = make_system(db, project, "cooperative")
        v2 = SystemVersion(
            system_id=v1.system_id, version="v2", connector_type="echo",
            parameters={"profile": "cooperative"}, config_hash="hash-v2",
        )
        db.add(v2)
        db.flush()

        evaluation = make_evaluation(db, "eval-upgrade", [], {"tags": ["t"]})
        baseline, _ = self._campaign_with_runs(
            db, project, "v1run", [v1], evaluation, [ResultStatus.PASS]
        )
        candidate, _ = self._campaign_with_runs(
            db, project, "v2run", [v2], evaluation, [ResultStatus.PASS]
        )

        diff = compare_campaigns(db, baseline, candidate)
        assert diff["comparisons"][0].get("status") != "no_baseline"
        assert (
            diff["comparisons"][0]["match_note"]
            == "matched_by_evaluation_across_system_versions"
        )
