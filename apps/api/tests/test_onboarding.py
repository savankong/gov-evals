"""The first-run walkthrough.

The point of these is that the walkthrough cannot lie. Every step is derived
from the database, there is no endpoint that marks one done, and each step
either links somewhere real or hands over the request -- no dead ends.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from aegis.db import SessionLocal
from aegis.enums import Role
from aegis.main import create_app
from aegis.models import Base, Membership, Organization, Program, User
from aegis.security import ensure_role_definitions, hash_password

API = "/api/v1"


@pytest.fixture(scope="module")
def client():
    from aegis.db import engine

    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)

    session = SessionLocal()
    org = Organization(name="Onboarding Org", short_name="ONB")
    session.add(org)
    session.flush()
    ensure_role_definitions(session, org.id)
    program = Program(organization_id=org.id, name="Onboarding Program")
    account = User(
        email="onb@example.test",
        full_name="Onboarding Tester",
        password_hash=hash_password("onb-password"),
    )
    session.add_all([program, account])
    session.flush()
    session.add(Membership(user_id=account.id, organization_id=org.id, role=Role.ORG_ADMIN))
    session.commit()
    program_id = program.id
    session.close()

    app = create_app()
    app.router.on_startup.clear()
    with TestClient(app) as test_client:
        test_client.program_id = program_id
        yield test_client


@pytest.fixture(scope="module")
def auth(client):
    response = client.post(
        f"{API}/auth/login", json={"email": "onb@example.test", "password": "onb-password"}
    )
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def _get(client, auth):
    response = client.get(f"{API}/onboarding", headers=auth)
    assert response.status_code == 200, response.text
    return response.json()


class TestEmptyAccount:
    def test_a_fresh_account_is_reported_as_a_first_run(self, client, auth):
        body = _get(client, auth)
        assert body["first_run"] is True
        assert body["done"] == 0
        assert body["complete"] is False
        assert body["total"] == len(body["steps"])
        assert all(step["done"] is False for step in body["steps"])

    def test_the_steps_are_in_the_order_the_work_is_done(self, client, auth):
        keys = [step["key"] for step in _get(client, auth)["steps"]]
        assert keys == ["project", "mission", "system", "cases", "plan", "campaign", "experts"]

    def test_every_step_either_links_somewhere_or_hands_over_the_request(self, client, auth):
        """No dead ends.

        Projects, mission profiles and system versions have no screen yet, so
        those steps must carry the API call instead of a button that would go
        nowhere.
        """
        for step in _get(client, auth)["steps"]:
            assert step["href"] or step["command"] or step["blocked"], (
                f"{step['key']} offers no way to do it and no reason why not"
            )

    def test_a_screen_that_exists_is_not_described_as_missing(self, client, auth):
        """`command` means there is no screen. `blocked` means there is one.

        Conflating them told a new user "there is no screen for this yet" about
        the plan and campaign pages, which do exist -- they are just unreachable
        until a project does. That sends someone looking for a gap that is not
        there.
        """
        for step in _get(client, auth)["steps"]:
            if step["blocked"]:
                assert not step["command"], (
                    f"{step['key']} is blocked on a prerequisite but also claims no screen exists"
                )

    def test_the_first_step_now_has_a_screen(self, client, auth):
        """The walkthrough used to open by handing a new user a curl command.

        Projects, mission profiles and system versions were API-only, so three
        of seven steps advertised "there is no screen for this yet". They have
        screens now, and the very first thing a new account sees should be a
        link rather than a request body.
        """
        steps = {s["key"]: s for s in _get(client, auth)["steps"]}
        assert steps["project"]["href"] == "/projects/new"
        assert steps["project"]["command"] is None
        # The two that follow need a project first, and say so rather than
        # claiming no screen exists.
        for key in ("mission", "system"):
            assert steps[key]["command"] is None
            assert steps[key]["href"] or steps[key]["blocked"]

    def test_each_step_reports_what_was_counted(self, client, auth):
        """"3 projects" is checkable; "completed" is not."""
        for step in _get(client, auth)["steps"]:
            assert step["evidence"], f"{step['key']} claims a state without evidence"


class TestDerivedFromRealState:
    def test_creating_a_project_advances_exactly_one_step(self, client, auth):
        before = _get(client, auth)
        response = client.post(
            f"{API}/projects",
            headers=auth,
            json={"program_id": client.program_id, "name": "Walkthrough Project"},
        )
        assert response.status_code == 201, response.text
        after = _get(client, auth)

        assert after["done"] == before["done"] + 1
        assert after["first_run"] is False
        project_step = next(s for s in after["steps"] if s["key"] == "project")
        assert project_step["done"] is True
        assert "1 project" in project_step["evidence"]
        # Nothing else moved on its own.
        assert [s["key"] for s in after["steps"] if s["done"]] == ["project"]

    def test_a_project_turns_the_later_steps_into_real_links(self, client, auth):
        """Before a project exists there is nowhere to send someone."""
        body = _get(client, auth)
        for key in ("mission", "system", "plan", "campaign"):
            step = next(s for s in body["steps"] if s["key"] == key)
            assert step["href"] and step["href"].startswith("/projects/"), key
            assert step["blocked"] is None, key
            assert body["project_id"] and body["project_id"] in step["href"], key

    def test_no_step_hands_over_a_request_any_more(self, client, auth):
        """Every capability the walkthrough names now has an interface.

        `command` is kept for the next thing that lands API-first; it should be
        unused today, and a step quietly falling back to it is worth noticing.
        """
        assert all(s["command"] is None for s in _get(client, auth)["steps"])

    def test_a_dataset_advances_the_cases_step_with_its_counts(self, client, auth):
        project_id = _get(client, auth)["project_id"]
        created = client.post(
            f"{API}/projects/{project_id}/datasets",
            headers=auth,
            json={"name": "Walkthrough Dataset"},
        )
        assert created.status_code == 201, created.text

        cases = next(s for s in _get(client, auth)["steps"] if s["key"] == "cases")
        assert cases["done"] is True
        assert "1 dataset" in cases["evidence"]
        # No version uploaded yet, so it says zero examples rather than implying data.
        assert "0 example" in cases["evidence"]

    def test_an_expert_profile_advances_the_experts_step(self, client, auth):
        assert (
            next(s for s in _get(client, auth)["steps"] if s["key"] == "experts")["done"] is False
        )
        response = client.put(
            f"{API}/expert-profiles/me",
            headers=auth,
            json={"display_name": "Onboarding Tester", "disciplines": ["legal"]},
        )
        assert response.status_code == 200, response.text
        assert (
            next(s for s in _get(client, auth)["steps"] if s["key"] == "experts")["done"] is True
        )


class TestShippedContentDoesNotCount:
    """Found by running it, not by reading it.

    The evaluation packs install roughly nineteen approved library scenarios at
    startup. Counting every approved scenario marked "load the cases to test
    against" as done on an account where nobody had loaded anything -- a step
    reading as complete because of content that came in the box, which is the
    one thing this checklist must never do.
    """

    def test_library_scenarios_do_not_complete_the_cases_step(self, client, auth):
        from aegis.db import SessionLocal
        from aegis.models import Scenario

        session = SessionLocal()
        session.add(
            Scenario(
                key="library-case",
                title="A scenario that shipped in a pack",
                project_id=None,  # library scenarios carry no project
                approved=True,
            )
        )
        session.commit()
        session.close()

        cases = next(s for s in _get(client, auth)["steps"] if s["key"] == "cases")
        assert cases["done"] is True, "this account already has a dataset from an earlier test"
        # The evidence must name the library scenarios as uncounted rather than
        # folding them into the total.
        assert "not counted" in cases["evidence"]
        assert "library scenario" in cases["evidence"]


class TestCannotBeFaked:
    def test_there_is_no_endpoint_that_marks_a_step_done(self, client, auth):
        """The structural claim the whole feature rests on.

        Other products let you press "mark as done". This one must not, because
        the rest of it refuses to let anything be asserted rather than measured.
        """
        for method in ("POST", "PUT", "PATCH", "DELETE"):
            # client.delete() takes no json kwarg, so go through request().
            response = client.request(method, f"{API}/onboarding", headers=auth)
            assert response.status_code == 405, (
                f"{method} /api/v1/onboarding should not exist, got {response.status_code}"
            )

    def test_completion_is_recomputed_rather_than_stored(self, client, auth):
        body = _get(client, auth)
        assert body["complete"] == (body["done"] == body["total"])
        assert body["done"] == sum(1 for s in body["steps"] if s["done"])

    def test_it_needs_authentication(self, client):
        assert client.get(f"{API}/onboarding").status_code == 401
