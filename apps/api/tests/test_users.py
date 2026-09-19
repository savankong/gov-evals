"""Local account administration.

The interesting tests are the refusals. Creating a user is easy; the value is
in what the endpoints will not let an administrator do to themselves or to the
deployment.
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
GOOD = "a-sufficiently-long-password"


@pytest.fixture(scope="module")
def client():
    from aegis.db import engine

    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)

    session = SessionLocal()
    org = Organization(name="Users Org", short_name="USERS")
    session.add(org)
    session.flush()
    ensure_role_definitions(session, org.id)
    program = Program(organization_id=org.id, name="Users Program")
    admin = User(
        email="root@example.test", full_name="Root", password_hash=hash_password(GOOD)
    )
    plain = User(
        email="plain@example.test", full_name="Plain", password_hash=hash_password(GOOD)
    )
    federated = User(
        email="sso@example.test",
        full_name="Federated",
        identity_provider="oidc",
        external_subject="sub-123",
    )
    session.add_all([program, admin, plain, federated])
    session.flush()
    session.add_all(
        [
            Membership(user_id=admin.id, organization_id=org.id, role=Role.ORG_ADMIN),
            Membership(user_id=plain.id, organization_id=org.id, role=Role.READ_ONLY),
            Membership(user_id=federated.id, organization_id=org.id, role=Role.READ_ONLY),
        ]
    )
    session.commit()
    org_id, fed_id = org.id, federated.id
    session.close()

    app = create_app()
    app.router.on_startup.clear()
    with TestClient(app) as c:
        c.org_id = org_id
        c.federated_id = fed_id
        yield c


def _auth(client, email, password=GOOD):
    r = client.post(f"{API}/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


@pytest.fixture(scope="module")
def admin(client):
    return _auth(client, "root@example.test")


@pytest.fixture(scope="module")
def plain(client):
    return _auth(client, "plain@example.test")


class TestCreating:
    def test_an_administrator_creates_an_account_that_can_sign_in(self, client, admin):
        r = client.post(
            f"{API}/users",
            headers=admin,
            json={
                "email": "New.Person@Example.test",
                "full_name": "New Person",
                "password": GOOD,
                "organization_id": client.org_id,
                "role": Role.EVALUATOR,
            },
        )
        assert r.status_code == 201, r.text
        body = r.json()
        # Normalised, so the address cannot be duplicated by case.
        assert body["email"] == "new.person@example.test"
        assert body["has_local_password"] is True
        assert [m["role"] for m in body["memberships"]] == [Role.EVALUATOR]

        assert _auth(client, "new.person@example.test")

    def test_the_same_address_cannot_be_registered_twice(self, client, admin):
        r = client.post(
            f"{API}/users",
            headers=admin,
            json={"email": "NEW.PERSON@example.test", "password": GOOD},
        )
        assert r.status_code == 409

    def test_a_role_without_an_organisation_is_refused(self, client, admin):
        r = client.post(
            f"{API}/users",
            headers=admin,
            json={"email": "x@example.test", "password": GOOD, "role": Role.EVALUATOR},
        )
        assert r.status_code == 400
        assert "organization_id" in r.text

    def test_an_unknown_role_is_refused(self, client, admin):
        r = client.post(
            f"{API}/users",
            headers=admin,
            json={
                "email": "y@example.test",
                "password": GOOD,
                "organization_id": client.org_id,
                "role": "supreme-commander",
            },
        )
        assert r.status_code == 400

    def test_a_reader_cannot_create_accounts(self, client, plain):
        r = client.post(
            f"{API}/users", headers=plain, json={"email": "z@example.test", "password": GOOD}
        )
        assert r.status_code == 403


class TestPasswordPolicy:
    def test_a_short_password_is_refused(self, client, admin):
        r = client.post(
            f"{API}/users", headers=admin, json={"email": "short@example.test", "password": "short"}
        )
        assert r.status_code == 400
        assert "at least" in r.text

    def test_the_shipped_default_is_refused(self, client, admin):
        """It is published in this repository, so it is not a credential."""
        r = client.post(
            f"{API}/users",
            headers=admin,
            json={"email": "default@example.test", "password": "aegis-dev-password"},
        )
        assert r.status_code == 400
        assert "shipped default" in r.text


class TestPasswords:
    def test_changing_your_own_requires_the_current_one(self, client):
        auth = _auth(client, "new.person@example.test")
        wrong = client.post(
            f"{API}/users/me/password",
            headers=auth,
            json={"current_password": "not-the-password", "new_password": "another-long-one"},
        )
        assert wrong.status_code == 401

        ok = client.post(
            f"{API}/users/me/password",
            headers=auth,
            json={"current_password": GOOD, "new_password": "another-long-one"},
        )
        assert ok.status_code == 200, ok.text
        # The limitation is stated rather than discovered.
        assert "remain valid until they expire" in ok.json()["note"]
        assert _auth(client, "new.person@example.test", "another-long-one")

    def test_me_is_not_treated_as_a_user_id(self, client, admin):
        """`/users/me/password` must not fall through to `/users/{user_id}/password`."""
        r = client.post(
            f"{API}/users/me/password",
            headers=admin,
            json={"current_password": GOOD, "new_password": "root-longer-password"},
        )
        assert r.status_code == 200, r.text
        assert _auth(client, "root@example.test", "root-longer-password")

    def test_an_administrator_cannot_reset_their_own_through_the_admin_route(self, client):
        auth = _auth(client, "root@example.test", "root-longer-password")
        me = client.get(f"{API}/auth/me", headers=auth).json()
        r = client.post(
            f"{API}/users/{me['user']['id']}/password",
            headers=auth,
            json={"new_password": "yet-another-long-password"},
        )
        assert r.status_code == 409
        assert "/users/me/password" in r.text

    def test_a_federated_account_cannot_be_given_a_local_password(self, client):
        """That would add a second way in the identity provider never agreed to."""
        auth = _auth(client, "root@example.test", "root-longer-password")
        r = client.post(
            f"{API}/users/{client.federated_id}/password",
            headers=auth,
            json={"new_password": "a-perfectly-long-password"},
        )
        assert r.status_code == 409
        assert "oidc" in r.text


class TestDeactivation:
    def _admin(self, client):
        return _auth(client, "root@example.test", "root-longer-password")

    def test_an_account_is_deactivated_rather_than_deleted(self, client):
        auth = self._admin(client)
        target = next(
            u for u in client.get(f"{API}/users", headers=auth).json()
            if u["email"] == "plain@example.test"
        )
        r = client.patch(f"{API}/users/{target['id']}", headers=auth, json={"is_active": False})
        assert r.status_code == 200, r.text
        assert r.json()["is_active"] is False

        # The row is still there, and still listed.
        listed = client.get(f"{API}/users", headers=auth).json()
        assert any(u["id"] == target["id"] for u in listed)
        # And it cannot sign in.
        denied = client.post(
            f"{API}/auth/login", json={"email": "plain@example.test", "password": GOOD}
        )
        assert denied.status_code == 401

    def test_deactivated_accounts_can_be_hidden_but_are_shown_by_default(self, client):
        auth = self._admin(client)
        default = client.get(f"{API}/users", headers=auth).json()
        hidden = client.get(f"{API}/users?include_inactive=false", headers=auth).json()
        assert len(default) > len(hidden)

    def test_you_cannot_deactivate_yourself(self, client):
        auth = self._admin(client)
        me = client.get(f"{API}/auth/me", headers=auth).json()
        r = client.patch(f"{API}/users/{me['user']['id']}", headers=auth, json={"is_active": False})
        assert r.status_code == 409
        assert "your own account" in r.text

    def test_there_is_no_delete_endpoint(self, client):
        """Deleting a user would orphan every audit entry naming them."""
        auth = self._admin(client)
        target = next(
            u for u in client.get(f"{API}/users", headers=auth).json()
            if u["email"] == "plain@example.test"
        )
        r = client.request("DELETE", f"{API}/users/{target['id']}", headers=auth)
        assert r.status_code == 405


class TestLastAdministrator:
    """The refusal that stops someone locking everyone out of their own deployment."""

    def test_the_last_admin_grant_cannot_be_revoked(self, client):
        auth = _auth(client, "root@example.test", "root-longer-password")
        me = client.get(f"{API}/auth/me", headers=auth).json()
        user = client.get(f"{API}/users/{me['user']['id']}", headers=auth).json()
        grant = next(m for m in user["memberships"] if m["role"] == Role.ORG_ADMIN)

        r = client.request(
            "DELETE", f"{API}/users/{user['id']}/memberships/{grant['id']}", headers=auth
        )
        assert r.status_code == 409
        assert "last active administrator" in r.text

    def test_it_can_be_revoked_once_somebody_else_holds_it(self, client):
        auth = _auth(client, "root@example.test", "root-longer-password")
        second = client.post(
            f"{API}/users",
            headers=auth,
            json={
                "email": "second.admin@example.test",
                "password": GOOD,
                "organization_id": client.org_id,
                "role": Role.ORG_ADMIN,
            },
        )
        assert second.status_code == 201, second.text

        me = client.get(f"{API}/auth/me", headers=auth).json()
        user = client.get(f"{API}/users/{me['user']['id']}", headers=auth).json()
        grant = next(m for m in user["memberships"] if m["role"] == Role.ORG_ADMIN)
        r = client.request(
            "DELETE", f"{API}/users/{user['id']}/memberships/{grant['id']}", headers=auth
        )
        assert r.status_code == 200, r.text

    def test_granting_the_same_role_twice_is_not_an_error(self, client):
        auth = _auth(client, "second.admin@example.test")
        target = next(
            u for u in client.get(f"{API}/users", headers=auth).json()
            if u["email"] == "new.person@example.test"
        )
        body = {"organization_id": client.org_id, "role": Role.REVIEWER}
        first = client.post(f"{API}/users/{target['id']}/memberships", headers=auth, json=body)
        second = client.post(f"{API}/users/{target['id']}/memberships", headers=auth, json=body)
        assert first.status_code in (200, 201)
        assert second.status_code in (200, 201)
        assert first.json()["id"] == second.json()["id"]
