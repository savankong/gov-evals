"""Expert review: who is qualified to judge, and what follows when they are not.

The product's position is that a human judgement is evidence to the extent the
judge was qualified to make it. These tests hold that line in both directions:
an unqualified review is never discarded, and it never resolves a run.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import pytest
from fastapi.testclient import TestClient

from aegis.db import SessionLocal
from aegis.enums import Discipline, ResultStatus, Role
from aegis.evaluators import EvaluationContext, build_evaluator
from aegis.expertise import qualify
from aegis.main import create_app
from aegis.models import Base, Membership, Organization, Program, User
from aegis.security import ensure_role_definitions, hash_password

API = "/api/v1"


@dataclass
class FakeProfile:
    disciplines: list = field(default_factory=list)
    active: bool = True
    verified: bool = True


class TestQualify:
    def test_no_profile_is_not_expert_evidence(self):
        ok, note = qualify([Discipline.ACQUISITION], None)
        assert ok is False
        assert "opinion" in note.lower()

    def test_overlapping_discipline_qualifies(self):
        profile = FakeProfile(disciplines=[Discipline.ACQUISITION, Discipline.LEGAL])
        ok, note = qualify([Discipline.ACQUISITION], profile)
        assert ok is True
        assert "Acquisition" in note

    def test_unrelated_discipline_does_not_qualify_and_says_why(self):
        profile = FakeProfile(disciplines=[Discipline.CYBER])
        ok, note = qualify([Discipline.MEDICAL], profile)
        assert ok is False
        # The reason names both sides, so the reviewer can see the mismatch.
        assert "Cybersecurity" in note and "Medical" in note

    def test_inactive_profile_does_not_qualify(self):
        profile = FakeProfile(disciplines=[Discipline.ACQUISITION], active=False)
        assert qualify([Discipline.ACQUISITION], profile)[0] is False

    def test_undeclared_requirement_is_reported_as_unchecked_not_as_vetted(self):
        """The distinction the whole feature rests on.

        Nothing to check against is not the same as having checked. The review
        counts -- withholding it would strand every pre-existing dataset -- but
        the note must not imply the reviewer was vetted for this item.
        """
        profile = FakeProfile(disciplines=[Discipline.CYBER])
        ok, note = qualify([], profile)
        assert ok is True
        assert "no expertise requirement is declared" in note.lower()
        assert "holds" not in note.lower()

    def test_filing_under_a_discipline_you_do_not_hold_is_refused(self):
        profile = FakeProfile(disciplines=[Discipline.CYBER])
        ok, note = qualify([Discipline.CYBER], profile, submitted_under=Discipline.MEDICAL)
        assert ok is False
        assert "not on the reviewer's profile" in note

    def test_filing_under_a_discipline_the_item_does_not_need_is_refused(self):
        profile = FakeProfile(disciplines=[Discipline.CYBER, Discipline.MEDICAL])
        ok, note = qualify([Discipline.CYBER], profile, submitted_under=Discipline.MEDICAL)
        assert ok is False
        assert "this item needs" in note

    def test_unverified_profile_qualifies_but_the_record_says_so(self):
        profile = FakeProfile(disciplines=[Discipline.LEGAL], verified=False)
        ok, note = qualify([Discipline.LEGAL], profile)
        assert ok is True
        assert "has not been verified" in note

    def test_an_unknown_discipline_still_gets_a_readable_label(self):
        """A customer vocabulary the product has never seen must still read."""
        profile = FakeProfile(disciplines=["flight_surgeon"])
        ok, note = qualify(["flight_surgeon"], profile)
        assert ok is True
        assert "Flight surgeon" in note


class TestExpertRequirementInTheEvaluator:
    """`require_expertise` is what makes the qualification consequential."""

    def _ctx(self, reviews):
        return EvaluationContext(scenario={}, request={}, response={}, human_reviews=reviews)

    def test_unqualified_reviews_never_resolve_the_result(self):
        evaluator = build_evaluator(
            {"evaluator": "human_review", "config": {"require_expertise": True}}
        )
        judgement = evaluator.evaluate(
            self._ctx(
                [
                    {
                        "status": ResultStatus.PASS,
                        "qualified": False,
                        "qualification_note": "Outside the discipline.",
                    }
                ]
            )
        )
        # Section 71: a judgement nobody qualified made is not a judgement.
        assert judgement.status == ResultStatus.PENDING_HUMAN
        assert judgement.evaluator_metadata["uncounted_reviews"] == 1
        assert "do not count" in judgement.rationale

    def test_a_qualified_review_resolves_it(self):
        evaluator = build_evaluator(
            {"evaluator": "human_review", "config": {"require_expertise": True}}
        )
        judgement = evaluator.evaluate(
            self._ctx([{"status": ResultStatus.FAIL, "qualified": True, "expertise": "legal"}])
        )
        assert judgement.status == ResultStatus.FAIL
        assert judgement.evaluator_metadata["counted_reviews"] == 1

    def test_an_unqualified_review_is_recorded_rather_than_discarded(self):
        evaluator = build_evaluator(
            {"evaluator": "human_review", "config": {"require_expertise": True}}
        )
        judgement = evaluator.evaluate(
            self._ctx(
                [
                    {"status": ResultStatus.PASS, "qualified": False, "qualification_note": "no"},
                    {"status": ResultStatus.PASS, "qualified": True, "expertise": "cyber"},
                ]
            )
        )
        assert judgement.status == ResultStatus.PASS
        assert judgement.evaluator_metadata["submitted_reviews"] == 2
        assert judgement.evaluator_metadata["counted_reviews"] == 1
        assert judgement.evaluator_metadata["reasons_not_counted"] == ["no"]

    def test_without_the_flag_behaviour_is_unchanged(self):
        """Existing plans keep working: expertise is opt-in, not retroactive."""
        evaluator = build_evaluator({"evaluator": "human_review"})
        judgement = evaluator.evaluate(
            self._ctx([{"status": ResultStatus.PASS, "qualified": False}])
        )
        assert judgement.status == ResultStatus.PASS

    def test_two_unqualified_reviews_still_do_not_make_a_quorum(self):
        evaluator = build_evaluator(
            {
                "evaluator": "human_review",
                "config": {"require_expertise": True, "required_reviews": 2},
            }
        )
        judgement = evaluator.evaluate(
            self._ctx(
                [
                    {"status": ResultStatus.PASS, "qualified": False},
                    {"status": ResultStatus.PASS, "qualified": False},
                ]
            )
        )
        assert judgement.status == ResultStatus.PENDING_HUMAN


# ---------------------------------------------------------------------------
# HTTP surface
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def client():
    from aegis.db import engine

    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)

    session = SessionLocal()
    org = Organization(name="Expert Test Org", short_name="EXPTEST")
    session.add(org)
    session.flush()
    ensure_role_definitions(session, org.id)
    program = Program(organization_id=org.id, name="Expert Test Program")
    admin = User(
        email="admin@example.test",
        full_name="Admin",
        password_hash=hash_password("admin-password"),
    )
    reviewer = User(
        email="reviewer@example.test",
        full_name="Reviewer",
        password_hash=hash_password("reviewer-password"),
    )
    session.add_all([program, admin, reviewer])
    session.flush()
    session.add_all(
        [
            Membership(user_id=admin.id, organization_id=org.id, role=Role.ORG_ADMIN),
            Membership(user_id=reviewer.id, organization_id=org.id, role=Role.REVIEWER),
        ]
    )
    session.commit()
    program_id = program.id
    session.close()

    app = create_app()
    app.router.on_startup.clear()
    with TestClient(app) as test_client:
        test_client.program_id = program_id
        yield test_client


def _auth(client, email, password):
    response = client.post(f"{API}/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


@pytest.fixture(scope="module")
def admin_auth(client):
    return _auth(client, "admin@example.test", "admin-password")


@pytest.fixture(scope="module")
def reviewer_auth(client):
    return _auth(client, "reviewer@example.test", "reviewer-password")


class TestDisciplines:
    def test_the_vocabulary_is_offered_and_marked_extensible(self, client, admin_auth):
        response = client.get(f"{API}/disciplines", headers=admin_auth)
        assert response.status_code == 200
        body = response.json()
        assert body["extensible"] is True
        assert any(d["key"] == Discipline.ACQUISITION for d in body["disciplines"])


class TestProfiles:
    def test_a_reviewer_declares_and_amends_their_own_expertise(self, client, reviewer_auth):
        assert client.get(f"{API}/expert-profiles/me", headers=reviewer_auth).json() is None

        created = client.put(
            f"{API}/expert-profiles/me",
            headers=reviewer_auth,
            json={
                "display_name": "Reviewer",
                "disciplines": [Discipline.ACQUISITION],
                "title": "Contracting officer",
                "years_experience": 12,
            },
        )
        assert created.status_code == 200, created.text
        assert created.json()["verified"] is False
        assert created.json()["disciplines"] == [Discipline.ACQUISITION]

        # Amending is an update of the same profile, not a second one.
        again = client.put(
            f"{API}/expert-profiles/me",
            headers=reviewer_auth,
            json={"display_name": "Reviewer", "disciplines": [Discipline.ACQUISITION]},
        )
        assert again.json()["id"] == created.json()["id"]

    def test_nobody_verifies_their_own_profile(self, client, admin_auth):
        mine = client.put(
            f"{API}/expert-profiles/me",
            headers=admin_auth,
            json={"display_name": "Admin", "disciplines": [Discipline.POLICY]},
        ).json()
        response = client.post(
            f"{API}/expert-profiles/{mine['id']}/verify", headers=admin_auth
        )
        assert response.status_code == 403
        assert "cannot be verified by the person it describes" in response.text

    def test_verification_is_dropped_when_the_claim_changes(
        self, client, admin_auth, reviewer_auth
    ):
        profile = client.get(f"{API}/expert-profiles/me", headers=reviewer_auth).json()
        verified = client.post(
            f"{API}/expert-profiles/{profile['id']}/verify", headers=admin_auth
        )
        assert verified.status_code == 200
        assert verified.json()["verified"] is True
        assert verified.json()["verified_by"] == "Admin"

        # A verification is a statement about a specific claim.
        changed = client.put(
            f"{API}/expert-profiles/me",
            headers=reviewer_auth,
            json={
                "display_name": "Reviewer",
                "disciplines": [Discipline.ACQUISITION, Discipline.LEGAL],
            },
        )
        assert changed.json()["verified"] is False

    def test_a_reviewer_cannot_verify_anyone(self, client, reviewer_auth, admin_auth):
        target = client.get(f"{API}/expert-profiles/me", headers=admin_auth).json()
        response = client.post(
            f"{API}/expert-profiles/{target['id']}/verify", headers=reviewer_auth
        )
        assert response.status_code == 403


class TestDatasetExpertise:
    def _project(self, client, auth):
        response = client.post(
            f"{API}/projects",
            headers=auth,
            json={"program_id": client.program_id, "name": "Expertise Project"},
        )
        assert response.status_code == 201, response.text
        return response.json()["id"]

    def test_a_dataset_declares_which_discipline_can_judge_it(self, client, admin_auth):
        project_id = self._project(client, admin_auth)
        created = client.post(
            f"{API}/projects/{project_id}/datasets",
            headers=admin_auth,
            json={"name": "Contract clauses", "required_expertise": [Discipline.ACQUISITION]},
        )
        assert created.status_code == 201, created.text
        dataset_id = created.json()["id"]
        assert created.json()["required_expertise"] == [Discipline.ACQUISITION]

        patched = client.patch(
            f"{API}/datasets/{dataset_id}",
            headers=admin_auth,
            json={"required_expertise": [Discipline.LEGAL]},
        )
        assert patched.status_code == 200
        assert patched.json()["required_expertise"] == [Discipline.LEGAL]

        # A partial update leaves everything it does not mention alone.
        assert patched.json()["name"] == "Contract clauses"

    def test_the_index_reports_expertise_and_counts(self, client, admin_auth):
        response = client.get(f"{API}/datasets", headers=admin_auth)
        assert response.status_code == 200
        rows = response.json()
        assert rows, "the dataset created above should be listed"
        row = next(r for r in rows if r["name"] == "Contract clauses")
        assert row["required_expertise"] == [Discipline.LEGAL]
        assert row["example_count"] == 0
        assert row["run_count"] == 0

    def test_coverage_names_a_discipline_nobody_holds(self, client, admin_auth):
        response = client.get(f"{API}/expertise-coverage", headers=admin_auth)
        assert response.status_code == 200
        body = response.json()
        legal = next(r for r in body["coverage"] if r["discipline"] == Discipline.LEGAL)
        # The reviewer picked up Legal in the profile test above.
        assert legal["covered"] is True
        assert any(r["name"] == "Reviewer" for r in legal["reviewers"])


class TestReviewQueue:
    def test_the_queue_reports_what_the_caller_can_act_on(self, client, reviewer_auth):
        response = client.get(f"{API}/review-queue/summary", headers=reviewer_auth)
        assert response.status_code == 200
        body = response.json()
        assert body["has_profile"] is True
        assert Discipline.ACQUISITION in body["my_disciplines"]
        # Nothing has run in this fixture, so the queue is empty rather than absent.
        assert body["pending_total"] == 0

    def test_scopes_are_accepted_and_an_unknown_one_is_refused(self, client, reviewer_auth):
        for scope in ("mine", "all", "unqualified"):
            assert (
                client.get(f"{API}/review-queue?scope={scope}", headers=reviewer_auth).status_code
                == 200
            )
        assert (
            client.get(f"{API}/review-queue?scope=everything", headers=reviewer_auth).status_code
            == 422
        )

    def test_a_reviewer_without_a_profile_is_told_so_rather_than_shown_an_empty_queue(
        self, client, admin_auth
    ):
        """The summary distinguishes "nothing for you" from "you have no profile"."""
        body = client.get(f"{API}/review-queue/summary", headers=admin_auth).json()
        assert "has_profile" in body and "pending_for_me" in body
