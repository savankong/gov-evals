"""Dataset upload, parsing and the quality report computed at upload time.

The report exists so a problem with the file is known before a campaign spends
a budget running against it, which means these tests are about what the
platform *says* as much as what it stores.
"""

from __future__ import annotations

import io

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
    org = Organization(name="Dataset Test Org", short_name="DSTEST")
    session.add(org)
    session.flush()
    ensure_role_definitions(session, org.id)
    program = Program(organization_id=org.id, name="Dataset Test Program")
    admin = User(
        email="ds-admin@example.test",
        full_name="Dataset Admin",
        password_hash=hash_password("ds-password"),
    )
    reader = User(
        email="ds-reader@example.test",
        full_name="Dataset Reader",
        password_hash=hash_password("ds-password"),
    )
    session.add_all([program, admin, reader])
    session.flush()
    session.add_all(
        [
            Membership(user_id=admin.id, organization_id=org.id, role=Role.ORG_ADMIN),
            Membership(user_id=reader.id, organization_id=org.id, role=Role.READ_ONLY),
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


def _auth(client, email):
    response = client.post(f"{API}/auth/login", json={"email": email, "password": "ds-password"})
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


@pytest.fixture(scope="module")
def auth(client):
    return _auth(client, "ds-admin@example.test")


@pytest.fixture(scope="module")
def reader_auth(client):
    return _auth(client, "ds-reader@example.test")


@pytest.fixture(scope="module")
def dataset(client, auth):
    project = client.post(
        f"{API}/projects",
        headers=auth,
        json={"program_id": client.program_id, "name": "Upload Project"},
    )
    assert project.status_code == 201, project.text
    created = client.post(
        f"{API}/projects/{project.json()['id']}/datasets",
        headers=auth,
        json={"name": "Upload Dataset"},
    )
    assert created.status_code == 201, created.text
    return created.json()["id"]


def _upload(client, auth, dataset_id, name, body, version=None):
    return client.post(
        f"{API}/datasets/{dataset_id}/versions",
        headers=auth,
        files={"file": (name, io.BytesIO(body.encode()), "application/octet-stream")},
        params={"version": version} if version else None,
    )


class TestUpload:
    def test_jsonl_becomes_a_version_with_a_quality_report(self, client, auth, dataset):
        body = "\n".join(
            [
                '{"input": "Is clause 4 enforceable?", "expected": "yes"}',
                '{"input": "Who bears the schedule risk?", "expected": "the contractor"}',
            ]
        )
        response = _upload(client, auth, dataset, "cases.jsonl", body)
        assert response.status_code == 201, response.text
        created = response.json()
        assert created["item_count"] == 2
        assert created["source_format"] == "jsonl"
        assert created["is_current"] is True
        assert created["content_hash"]
        assert created["quality_report"]["rows_with_expected_answer"] == 2
        assert created["quality_report"]["issues"] == []

    def test_the_version_label_is_read_from_the_query_string(self, client, auth, dataset):
        """The web client sends it there, so the contract is pinned here.

        `version` is declared as a plain scalar beside an UploadFile, which
        FastAPI reads from the query string rather than the multipart body.
        """
        response = _upload(client, auth, dataset, "more.jsonl", '{"input": "a"}', version="v-named")
        assert response.status_code == 201, response.text
        assert response.json()["version"] == "v-named"

    def test_uploading_again_moves_the_current_marker_rather_than_replacing(
        self, client, auth, dataset
    ):
        versions = client.get(f"{API}/datasets/{dataset}/versions", headers=auth).json()
        assert len(versions) == 2
        current = [v for v in versions if v["is_current"]]
        assert len(current) == 1, "exactly one version is current"
        assert current[0]["version"] == "v-named"
        # Nothing was deleted: a result naming an older version still resolves.
        assert {v["version"] for v in versions} >= {"v1", "v-named"}

    def test_an_unnamed_version_is_numbered_from_the_count(self, client, auth, dataset):
        response = _upload(client, auth, dataset, "again.jsonl", '{"input": "b"}')
        assert response.json()["version"] == "v3"


class TestParsing:
    def test_csv_is_parsed_into_rows(self, client, auth, dataset):
        body = "input,expected\nfirst question,first answer\nsecond question,second answer\n"
        response = _upload(client, auth, dataset, "cases.csv", body)
        assert response.status_code == 201, response.text
        assert response.json()["source_format"] == "csv"
        assert response.json()["item_count"] == 2

    def test_unlabelled_text_is_one_case_per_line(self, client, auth, dataset):
        response = _upload(client, auth, dataset, "cases.txt", "one\ntwo\n\nthree\n")
        assert response.status_code == 201, response.text
        assert response.json()["source_format"] == "text"
        # The blank line is not a case.
        assert response.json()["item_count"] == 3

    def test_a_json_array_is_accepted(self, client, auth, dataset):
        response = _upload(client, auth, dataset, "cases.json", '[{"input": "x"}, {"input": "y"}]')
        assert response.status_code == 201, response.text
        assert response.json()["source_format"] == "json"
        assert response.json()["item_count"] == 2


class TestRefusals:
    def test_an_empty_file_is_refused(self, client, auth, dataset):
        response = _upload(client, auth, dataset, "empty.jsonl", "")
        assert response.status_code == 400
        assert "no usable rows" in response.text

    def test_unparseable_json_is_refused_with_the_reason(self, client, auth, dataset):
        response = _upload(client, auth, dataset, "broken.json", "{not json")
        assert response.status_code == 400
        assert "Could not parse" in response.text

    def test_a_reader_cannot_upload(self, client, reader_auth, dataset):
        response = _upload(client, reader_auth, dataset, "cases.jsonl", '{"input": "a"}')
        assert response.status_code == 403

    def test_an_oversized_file_is_refused(self, client, auth, dataset, monkeypatch):
        from aegis.routers import datasets as datasets_router

        monkeypatch.setattr(datasets_router, "MAX_UPLOAD_BYTES", 10)
        response = _upload(client, auth, dataset, "big.jsonl", '{"input": "far too long"}')
        assert response.status_code == 413


class TestQualityReport:
    """What the report says is the point of computing it at upload."""

    def test_duplicates_and_missing_expected_answers_are_named(self, client, auth, dataset):
        body = "\n".join(
            ['{"input": "same"}', '{"input": "same"}', '{"input": ""}'],
        )
        report = _upload(client, auth, dataset, "messy.jsonl", body).json()["quality_report"]
        assert report["duplicates"] == 1
        assert report["empty_inputs"] == 1
        issues = " ".join(report["issues"])
        assert "duplicate" in issues
        assert "no input text" in issues
        # The one that matters most: nothing to compare against is not a pass.
        assert "NOT EVALUATED" in issues

    def test_fields_present_on_only_some_rows_are_reported(self, client, auth, dataset):
        body = '{"input": "a", "expected": "x"}\n{"input": "b"}'
        report = _upload(client, auth, dataset, "ragged.jsonl", body).json()["quality_report"]
        assert any("only some rows" in issue for issue in report["issues"])


class TestReadBack:
    def test_the_detail_view_returns_versions_newest_first(self, client, auth, dataset):
        response = client.get(f"{API}/datasets/{dataset}", headers=auth)
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["dataset"]["name"] == "Upload Dataset"
        assert body["project"]["name"] == "Upload Project"
        assert body["current_version_id"]
        assert len(body["versions"]) >= 2

    def test_items_are_returned_in_order_with_their_hashes(self, client, auth, dataset):
        versions = client.get(f"{API}/datasets/{dataset}/versions", headers=auth).json()
        first = next(v for v in versions if v["version"] == "v1")
        response = client.get(f"{API}/dataset-versions/{first['id']}/items", headers=auth)
        assert response.status_code == 200
        items = response.json()["items"]
        assert [i["ordinal"] for i in items] == [0, 1]
        assert items[0]["payload"]["input"] == "Is clause 4 enforceable?"
        assert all(i["content_hash"] for i in items)
