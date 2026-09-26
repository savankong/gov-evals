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


# ---------------------------------------------------------------------------
# Public benchmark pages: no login, published reports only
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def site():
    """The demonstration seeded (and so published), an org admin, a read-only
    member of the same organisation, and someone from elsewhere."""
    from fastapi.testclient import TestClient

    from aegis.db import SessionLocal, engine
    from aegis.enums import Role
    from aegis.main import create_app
    from aegis.models import Base, Membership, Organization
    from aegis.security import hash_password

    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    install_all(db)
    admin = User(email="owner@example.test", password_hash=hash_password("pw-owner"))
    reader = User(email="reader@example.test", password_hash=hash_password("pw-reader"))
    stranger = User(email="stranger@example.test", password_hash=hash_password("pw-stranger"))
    db.add_all([admin, reader, stranger])
    db.flush()
    seed_acquisition_bench_demo(db, admin)
    demo_org = db.execute(select(Organization).where(Organization.short_name == "DEMO-PEO")).scalar_one()
    db.add(Membership(user_id=reader.id, organization_id=demo_org.id, role=Role.READ_ONLY))
    other = Organization(name="Elsewhere", short_name="ELSE2")
    db.add(other)
    db.flush()
    db.add(Membership(user_id=stranger.id, organization_id=other.id, role=Role.ORG_ADMIN))
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

        yield (
            client,
            login("owner@example.test", "pw-owner"),
            login("reader@example.test", "pw-reader"),
            login("stranger@example.test", "pw-stranger"),
        )


def _report():
    from aegis.db import SessionLocal

    db = SessionLocal()
    return db, db.execute(select(Report).where(Report.kind == "benchmark")).scalar_one()


class TestPublicBenchmarks:
    def test_the_published_demonstration_needs_no_login(self, site):
        client = site[0]
        items = client.get("/api/v1/public/benchmarks").json()
        assert len(items) == 1 and items[0]["demonstration"] is True
        detail = client.get(f"/api/v1/public/benchmarks/{items[0]['id']}")
        assert detail.status_code == 200
        assert len(detail.json()["question_rows"]) == 30

    def test_nothing_on_the_public_page_points_into_the_app(self, site):
        client = site[0]
        report_id = client.get("/api/v1/public/benchmarks").json()[0]["id"]
        body = client.get(f"/api/v1/public/benchmarks/{report_id}").json()
        assert "result_id" not in str(body)
        assert all("id" not in c for c in body["data"]["campaigns"])
        assert "id" not in body["project"]

    def test_a_held_out_question_is_counted_but_not_shown(self, site):
        client, owner, *_ = site
        report_id = client.get("/api/v1/public/benchmarks").json()[0]["id"]
        db, _ = _report()
        try:
            scenario = db.execute(
                select(Scenario).where(
                    Scenario.key == "acqb-q01-market-research", Scenario.project_id.is_not(None)
                )
            ).scalar_one()
            tags = list(scenario.tags)
            scenario.tags = [t for t in tags if t != "split:public"] + ["split:private"]
            db.commit()
            public = client.get(f"/api/v1/public/benchmarks/{report_id}").json()
            private = client.get(f"/api/v1/benchmarks/{report_id}", headers=owner).json()
            assert "acqb-q01-market-research" not in {r["key"] for r in public["question_rows"]}
            assert "acqb-q01-market-research" in {r["key"] for r in private["question_rows"]}
            # Still in the pass rate: holding a question out hides it, not its score.
            assert public["data"]["leaderboard"] == private["data"]["leaderboard"]
            assert (public["data"]["example"] or {}).get("scenario_key") != "acqb-q01-market-research"
        finally:
            scenario.tags = tags
            db.commit()
            db.close()

    def test_unpublishing_takes_it_off_the_public_pages(self, site):
        client, owner, *_ = site
        report_id = client.get("/api/v1/public/benchmarks").json()[0]["id"]
        assert client.post(f"/api/v1/benchmarks/{report_id}/unpublish", headers=owner).status_code == 200
        assert client.get("/api/v1/public/benchmarks").json() == []
        assert client.get(f"/api/v1/public/benchmarks/{report_id}").status_code == 404
        assert client.post(f"/api/v1/benchmarks/{report_id}/publish", headers=owner).status_code == 200
        assert len(client.get("/api/v1/public/benchmarks").json()) == 1

    def test_publishing_needs_the_report_permission_in_that_project(self, site):
        client, _, reader, stranger = site
        report_id = client.get("/api/v1/public/benchmarks").json()[0]["id"]
        assert client.post(f"/api/v1/benchmarks/{report_id}/unpublish").status_code == 401
        assert client.post(f"/api/v1/benchmarks/{report_id}/unpublish", headers=reader).status_code == 403
        assert client.post(f"/api/v1/benchmarks/{report_id}/unpublish", headers=stranger).status_code == 404
        assert len(client.get("/api/v1/public/benchmarks").json()) == 1

    def test_only_an_unclassified_report_is_ever_public(self, site):
        client, owner, *_ = site
        db, report = _report()
        try:
            report.classification = "CUI"
            db.commit()
            # Already published, then marked CUI: it leaves the public pages.
            assert client.get("/api/v1/public/benchmarks").json() == []
            assert client.get(f"/api/v1/public/benchmarks/{report.id}").status_code == 404
            refused = client.post(f"/api/v1/benchmarks/{report.id}/publish", headers=owner)
            assert refused.status_code == 400
        finally:
            report.classification = "UNCLASSIFIED"
            db.commit()
            db.close()
