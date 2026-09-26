"""The recorded connector and the Acquisition Bench demonstration.

A demonstration is only worth showing if nobody can mistake it for a finding.
These tests hold three lines: a replay never answers a request it did not
record, the demonstration runs every recorded answer through the ordinary
engine with nothing lost on the way, and the report built from it says at the
top what was a stand-in and never calls the simulated reviewer an expert.
"""

from __future__ import annotations

from sqlalchemy import select

from aegis.benchmark import benchmark_data
from aegis.connectors import TargetRequest, build_adapter
from aegis.demo_bench import (
    ANSWER_SYSTEM_PROMPT,
    MODELS,
    PROJECT_SLUG,
    QUESTIONS_PACK,
    REVIEWER_EMAIL,
    seed_acquisition_bench_demo,
)
from aegis.enums import ResultStatus
from aegis.models import Campaign, HumanReview, Project, Report, Result, Run, Scenario, User
from aegis.packs import install_all

HAIKU = MODELS[0][2]


def _replay(prompt: str, system_prompt: str = ANSWER_SYSTEM_PROMPT):
    adapter = build_adapter({"connector_type": "recorded", "parameters": {"recording": HAIKU}})
    return adapter.invoke(TargetRequest(prompt=prompt, system_prompt=system_prompt))


def _first_question(db) -> Scenario:
    return db.execute(
        select(Scenario).where(Scenario.source == QUESTIONS_PACK).order_by(Scenario.key)
    ).scalars().first()


class TestRecordedConnector:
    def test_a_recorded_request_replays_its_answer(self, db):
        install_all(db)
        response = _replay(_first_question(db).input["prompt"])
        assert response.error is None
        assert len(response.text) > 200
        assert response.raw["recorded_model"] == "claude-haiku-4-5"

    def test_an_unrecorded_request_is_an_error_not_an_answer(self):
        response = _replay("A question nobody recorded.")
        assert response.error and "No recorded response" in response.error
        assert response.text == ""

    def test_a_different_system_prompt_is_a_different_request(self, db):
        """The answer was given under one instruction. Replaying it for another
        would claim the model said something it was never asked."""
        install_all(db)
        response = _replay(_first_question(db).input["prompt"], system_prompt="Be terse.")
        assert response.error

    def test_timing_and_tokens_are_unknown_not_zero(self, db):
        install_all(db)
        response = _replay(_first_question(db).input["prompt"])
        assert response.latency_ms is None
        assert response.tokens_in is None and response.tokens_out is None


def _seed(db):
    install_all(db)
    admin = User(email="admin@example.test", full_name="Admin")
    db.add(admin)
    db.flush()
    assert seed_acquisition_bench_demo(db, admin) == "created"
    project = db.execute(select(Project).where(Project.slug == PROJECT_SLUG)).scalar_one()
    return admin, project


class TestDemonstration:
    def test_every_recorded_answer_and_verdict_is_replayed(self, db):
        _, project = _seed(db)
        campaigns = list(db.execute(select(Campaign).where(Campaign.project_id == project.id)).scalars())
        results = list(
            db.execute(
                select(Result).join(Run).where(Run.campaign_id.in_([c.id for c in campaigns]))
            ).scalars()
        )
        # 30 questions and 9 calibration questions, for each of three models.
        assert len(results) == (30 + 9) * 3
        assert not [r.id for r in results if r.error]
        for result in results:
            criteria = next(
                j["evaluator_metadata"]["criteria"]
                for j in result.judgements
                if j["evaluator_key"] == "rubric_criteria"
            )
            # A replayed judge that missed its recording would leave a criterion
            # undecided; every one was recorded, so every one is decided.
            assert {c["verdict"] for c in criteria} <= {ResultStatus.PASS, ResultStatus.FAIL}

    def test_the_shipped_questions_stay_unapproved(self, db):
        _, project = _seed(db)
        shipped = db.execute(
            select(Scenario).where(Scenario.source == QUESTIONS_PACK, Scenario.project_id.is_(None))
        ).scalars().all()
        assert shipped and not any(s.approved for s in shipped)
        copies = db.execute(select(Scenario).where(Scenario.project_id == project.id)).scalars().all()
        assert len(copies) == 30 and all(s.approved for s in copies)

    def test_the_simulated_reviewer_cannot_sign_in(self, db):
        _seed(db)
        reviewer = db.execute(select(User).where(User.email == REVIEWER_EMAIL)).scalar_one()
        assert reviewer.password_hash is None
        assert reviewer.is_active is False

    def test_calibration_labels_are_compared_with_the_judge(self, db):
        _, project = _seed(db)
        campaigns = list(db.execute(select(Campaign).where(Campaign.project_id == project.id)).scalars())
        alignment = benchmark_data(db, campaigns)["judge_alignment"]
        assert db.execute(select(HumanReview)).scalars().first() is not None
        assert alignment["comparisons"] >= 100

    def test_the_report_says_it_is_a_demonstration_and_names_no_expert(self, db):
        _, project = _seed(db)
        report = db.execute(select(Report).where(Report.project_id == project.id)).scalar_one()
        head = report.body.split("## Key measurements")[0]
        assert "DEMONSTRATION DATA -- NOT A PUBLISHED BENCHMARK" in head
        assert "simulated, not an expert" in head
        assert "Judge agreement with a simulated reviewer (not an expert)" in report.body
        assert "qualified expert(s) labelled" not in report.body
        assert "| | Expert: pass" not in report.body
        assert "Demonstration data." in report.body.split("## Limitations")[1]

    def test_seeding_twice_does_not_duplicate(self, db):
        admin, _ = _seed(db)
        assert seed_acquisition_bench_demo(db, admin) == "exists"
