"""The recorded connector and the Acquisition Bench demonstration.

A demonstration is only worth showing if nobody can mistake it for a finding.
These tests hold three lines: a replay never answers a request it did not
record, the demonstration runs every recorded answer through the ordinary
engine with nothing lost on the way, and the report built from it says at the
top what was a stand-in and never calls the simulated reviewer an expert.
"""

from __future__ import annotations

import pytest
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
        # 30 questions and 9 calibration questions, for each of two models.
        assert len(results) == (30 + 9) * len(MODELS)
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
        # 9 calibration questions x 5 criteria x 2 models.
        assert alignment["comparisons"] == 90

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


# ---------------------------------------------------------------------------
# Benchmark pages
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def pages():
    """The demonstration seeded, one user inside its organisation, one outside."""
    from fastapi.testclient import TestClient

    from aegis.db import SessionLocal, engine
    from aegis.main import create_app
    from aegis.models import Base, Membership, Organization
    from aegis.security import hash_password

    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    install_all(db)
    insider = User(email="insider@example.test", password_hash=hash_password("pw-inside"))
    outsider = User(email="outsider@example.test", password_hash=hash_password("pw-outside"))
    db.add_all([insider, outsider])
    db.flush()
    seed_acquisition_bench_demo(db, insider)
    other = Organization(name="Elsewhere", short_name="ELSE")
    db.add(other)
    db.flush()
    db.add(Membership(user_id=outsider.id, organization_id=other.id, role="viewer"))
    db.commit()
    db.close()

    app = create_app()
    app.router.on_startup.clear()
    with TestClient(app) as client:
        def login(email, password):
            token = client.post(
                "/api/v1/auth/login", json={"email": email, "password": password}
            ).json()["access_token"]
            return {"Authorization": f"Bearer {token}"}

        yield client, login("insider@example.test", "pw-inside"), login("outsider@example.test", "pw-outside")


class TestBenchmarkPages:
    def test_the_index_lists_the_demonstration_with_its_leaders(self, pages):
        client, inside, _ = pages
        items = client.get("/api/v1/benchmarks", headers=inside).json()
        assert len(items) == 1
        item = items[0]
        assert item["demonstration"] is True
        assert item["questions"] == 30 and item["models"] == len(MODELS)
        rates = [t["pass_rate"] for t in item["top"]]
        assert rates == sorted(rates, reverse=True)

    def test_a_report_carries_every_question_without_calibration_repeats(self, pages):
        client, inside, _ = pages
        report_id = client.get("/api/v1/benchmarks", headers=inside).json()[0]["id"]
        body = client.get(f"/api/v1/benchmarks/{report_id}", headers=inside).json()
        rows = body["question_rows"]
        assert len(rows) == 30
        assert all(len(r["results"]) == len(MODELS) for r in rows)
        for row in rows:
            for result in row["results"].values():
                assert set(result["verdicts"]) == {c["id"] for c in row["criteria"]}
        # The page's figures are the report's figures.
        met = sum(
            v["verdict"] == "pass"
            for r in rows for res in r["results"].values() for v in res["verdicts"].values()
        )
        assert met == sum(r["criteria_passed"] for r in body["data"]["leaderboard"])

    def test_another_organisation_cannot_see_it(self, pages):
        client, inside, outside = pages
        report_id = client.get("/api/v1/benchmarks", headers=inside).json()[0]["id"]
        assert client.get("/api/v1/benchmarks", headers=outside).json() == []
        assert client.get(f"/api/v1/benchmarks/{report_id}", headers=outside).status_code == 404

    def test_an_unknown_report_is_not_found(self, pages):
        client, inside, _ = pages
        assert client.get("/api/v1/benchmarks/nope", headers=inside).status_code == 404

    def test_the_answers_shown_are_the_scored_ones_not_calibration(self, pages):
        """Calibration results repeat the same questions to measure the judge.
        The page shows the scored result for each question, never its
        calibration twin, even where the two carry the same verdicts."""
        from aegis.db import SessionLocal

        client, inside, _ = pages
        report_id = client.get("/api/v1/benchmarks", headers=inside).json()[0]["id"]
        rows = client.get(f"/api/v1/benchmarks/{report_id}", headers=inside).json()["question_rows"]
        shown = {res["result_id"] for r in rows for res in r["results"].values()}
        db = SessionLocal()
        try:
            calibration = {
                r.id
                for r in db.execute(select(Result)).scalars()
                if any((j.get("evaluator_metadata") or {}).get("calibration") for j in r.judgements or [])
            }
        finally:
            db.close()
        assert calibration and not (shown & calibration)
