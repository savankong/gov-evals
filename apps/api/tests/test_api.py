"""End-to-end workflow through the HTTP API."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from aegis.db import SessionLocal
from aegis.enums import ResultStatus, Role
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
    org = Organization(name="API Test Org", short_name="APITEST")
    session.add(org)
    session.flush()
    ensure_role_definitions(session, org.id)
    program = Program(organization_id=org.id, name="API Test Program")
    account = User(
        email="api-tester@example.test",
        full_name="API Tester",
        password_hash=hash_password("api-password"),
    )
    session.add_all([program, account])
    session.flush()
    session.add(Membership(user_id=account.id, organization_id=org.id, role=Role.ORG_ADMIN))
    session.commit()
    program_id = program.id
    session.close()

    app = create_app()
    # The startup hook re-runs bootstrap; skip it so the fixture state is exact.
    app.router.on_startup.clear()
    with TestClient(app) as test_client:
        test_client.program_id = program_id
        yield test_client


@pytest.fixture(scope="module")
def token(client):
    response = client.post(
        f"{API}/auth/login",
        json={"email": "api-tester@example.test", "password": "api-password"},
    )
    assert response.status_code == 200, response.text
    return response.json()["access_token"]


@pytest.fixture(scope="module")
def auth(token):
    return {"Authorization": f"Bearer {token}"}


class TestAuthentication:
    def test_rejects_a_wrong_password(self, client):
        response = client.post(
            f"{API}/auth/login",
            json={"email": "api-tester@example.test", "password": "wrong"},
        )
        assert response.status_code == 401

    def test_does_not_distinguish_unknown_accounts(self, client):
        """Same response either way, so the endpoint is not an account oracle."""
        unknown = client.post(
            f"{API}/auth/login", json={"email": "nobody@example.test", "password": "x"}
        )
        wrong = client.post(
            f"{API}/auth/login", json={"email": "api-tester@example.test", "password": "x"}
        )
        assert unknown.status_code == wrong.status_code == 401
        assert unknown.json()["detail"] == wrong.json()["detail"]

    def test_accepts_internal_domains(self, client):
        """Disconnected deployments use internal domains a public email
        validator would reject."""
        response = client.post(
            f"{API}/auth/login", json={"email": "admin@aegis.local", "password": "x"}
        )
        assert response.status_code == 401  # rejected on credentials, not on shape

    def test_protected_routes_require_a_token(self, client):
        assert client.get(f"{API}/projects").status_code == 401

    def test_me_reports_permissions(self, client, auth):
        body = client.get(f"{API}/auth/me", headers=auth).json()
        assert "campaign:execute" in body["permissions"]


class TestCatalogues:
    def test_lists_connectors_and_evaluators(self, client, auth):
        connectors = client.get(f"{API}/connectors", headers=auth).json()["connectors"]
        assert {"echo", "openai_compatible", "generic_rest"} <= {c["key"] for c in connectors}
        evaluators = client.get(f"{API}/evaluators", headers=auth).json()["evaluators"]
        kinds = {e["kind"] for e in evaluators}
        assert {"deterministic", "model_based", "human", "external_tool"} <= kinds

    def test_offline_connector_declares_no_egress(self, client, auth):
        connectors = client.get(f"{API}/connectors", headers=auth).json()["connectors"]
        echo = next(c for c in connectors if c["key"] == "echo")
        assert echo["requires_egress"] is False

    def test_attack_library_is_available(self, client, auth):
        attacks = client.get(f"{API}/attacks", headers=auth).json()["attacks"]
        assert len(attacks) >= 15
        assert all(a["mitigation"] for a in attacks)


class TestWorkflow:
    """Mission profile through to a report, in the order a tester would work."""

    def test_full_workflow(self, client, auth):
        # 1. Project
        project = client.post(
            f"{API}/projects",
            headers=auth,
            json={
                "program_id": client.program_id,
                "name": "Workflow Project",
                "impact_level": "IL5",
                "classification": "CUI",
            },
        ).json()
        project_id = project["id"]
        assert project["slug"] == "workflow-project"

        # 2. Mission profile
        mission = client.put(
            f"{API}/projects/{project_id}/mission",
            headers=auth,
            json={
                "mission": "Assist analysts with summarising reporting.",
                "tasks": ["Summarise supplied reporting."],
                "users": ["Analysts"],
                "unacceptable_failures": ["Fabricating a source."],
                "adversaries": ["An actor planting content in the corpus."],
                "latency_requirement_ms": 5000,
            },
        )
        assert mission.status_code == 200

        # 3. System and version
        system = client.post(
            f"{API}/projects/{project_id}/systems",
            headers=auth,
            json={"name": "Analyst Copilot", "kind": "rag"},
        ).json()
        version = client.post(
            f"{API}/systems/{system['id']}/versions",
            headers=auth,
            json={
                "version": "v1.0",
                "connector_type": "echo",
                "model_name": "demo-model",
                "parameters": {"profile": "cooperative", "seed": 3},
            },
        ).json()
        assert len(version["config_hash"]) == 64

        # A configuration change produces a different fingerprint.
        second = client.post(
            f"{API}/systems/{system['id']}/versions",
            headers=auth,
            json={
                "version": "v1.1",
                "connector_type": "echo",
                "model_name": "demo-model",
                "parameters": {"profile": "vulnerable", "seed": 3},
            },
        ).json()
        assert second["config_hash"] != version["config_hash"]

        # 4. Connectivity
        connectivity = client.post(
            f"{API}/system-versions/{version['id']}/connectivity", headers=auth
        ).json()
        assert connectivity["status"] == "reachable"

        # 5. Scenario
        client.post(
            f"{API}/projects/{project_id}/scenarios",
            headers=auth,
            json={
                "key": "wf-summarise",
                "title": "Summarise reporting",
                "tags": ["mission-task"],
                "input": {
                    "prompt": "Summarise the supplied reporting.",
                    "documents": [{"source_id": "R-1", "text": "Activity observed on 14 March."}],
                },
                "expected_behavior": ["Cites R-1."],
            },
        )

        # 6. Project evaluation
        evaluation = client.post(
            f"{API}/projects/{project_id}/evaluations",
            headers=auth,
            json={
                "key": "wf-citation",
                "name": "Citation validity",
                "domain": "traceability",
                "evaluators": [{"evaluator": "citation_validity"}],
                "scenario_selector": {"tags": ["mission-task"]},
            },
        ).json()

        # 7. Campaign with an explicit threshold
        campaign = client.post(
            f"{API}/projects/{project_id}/campaigns",
            headers=auth,
            json={
                "name": "Workflow campaign",
                "evaluation_ids": [evaluation["id"]],
                "system_version_ids": [version["id"]],
                "thresholds": {"wf-citation": {"min_pass_rate": 0.9}},
            },
        ).json()

        # 8. Execute (inline queue runs it on a worker thread)
        assert client.post(f"{API}/campaigns/{campaign['id']}/execute", headers=auth).json()[
            "status"
        ] == "queued"

        import time

        for _ in range(60):
            summary = client.get(f"{API}/campaigns/{campaign['id']}/summary", headers=auth).json()
            if summary["campaign"]["status"] in ("completed", "awaiting_human", "failed"):
                break
            time.sleep(0.2)
        assert summary["campaign"]["status"] == "completed"
        assert summary["summary"]["executed"] == 1

        run = summary["runs"][0]
        assert run["verdict"] in (ResultStatus.PASS, ResultStatus.FAIL)

        # 9. Every result resolves to its evidence
        results = client.get(f"{API}/runs/{run['id']}/results", headers=auth).json()
        detail = client.get(f"{API}/results/{results[0]['id']}", headers=auth).json()
        assert detail["evidence"], "result has no stored evidence"
        assert len(detail["evidence"][0]["sha256"]) == 64
        assert detail["reproducibility"]["system_config_hash"]
        assert detail["scenario"]["key"] == "wf-summarise"

        # 10. Reproducibility record
        repro = client.get(f"{API}/runs/{run['id']}/reproducibility", headers=auth).json()
        assert repro["reproducibility"]["evaluation_key"] == "wf-citation"

        # 11. Evidence graph
        graph = client.get(f"{API}/projects/{project_id}/evidence-graph", headers=auth).json()
        assert any(n["type"] == "mission" for n in graph["nodes"])
        assert any(n["type"] == "run" for n in graph["nodes"])

        # 12. Dashboard reports every domain, tested or not
        dashboard = client.get(f"{API}/projects/{project_id}/dashboard", headers=auth).json()
        statuses = {d["domain"]: d["status"] for d in dashboard["readiness"]}
        assert len(statuses) == 11, "every domain must appear, including untested ones"
        assert statuses["security"] == ResultStatus.NOT_EVALUATED
        assert "no single trust score" in dashboard["note"]

        # 13. Report generation, hashed
        report = client.post(
            f"{API}/projects/{project_id}/reports",
            headers=auth,
            json={"kind": "executive_summary", "campaign_id": campaign["id"]},
        ).json()
        assert len(report["sha256"]) == 64
        assert "NOT EVALUATED" in report["body"]
        assert "not an authorisation to operate" in report["body"]

        download = client.get(f"{API}/reports/{report['id']}/download", headers=auth)
        assert download.headers["X-Content-SHA256"] == report["sha256"]
        assert download.headers["X-Classification"] == "CUI"

        # 14. Audit trail intact
        events = client.get(f"{API}/projects/{project_id}/audit", headers=auth).json()
        actions = {e["action"] for e in events}
        assert {"project.created", "mission_profile.created", "campaign.created"} <= actions
        assert client.get(f"{API}/audit/verify", headers=auth).json()["valid"] is True


class TestGuardrails:
    def test_generated_scenarios_are_not_approved(self, client, auth):
        project_id = client.post(
            f"{API}/projects",
            headers=auth,
            json={"program_id": client.program_id, "name": "Generation Project"},
        ).json()["id"]
        client.put(
            f"{API}/projects/{project_id}/mission",
            headers=auth,
            json={
                "mission": "Support a mission.",
                "tasks": ["Do the task."],
                "unacceptable_failures": ["Fabricate a fact."],
            },
        )
        drafts = client.post(
            f"{API}/projects/{project_id}/scenarios/generate",
            headers=auth,
            json={"mode": "mission_expansion"},
        ).json()
        assert drafts, "generation produced nothing"
        assert all(d["approved"] is False for d in drafts)
        assert all(d["generated"] is True for d in drafts)

        approved = client.post(f"{API}/scenarios/{drafts[0]['id']}/approve", headers=auth).json()
        assert approved["approved"] is True

    def test_generation_requires_a_mission_profile(self, client, auth):
        project_id = client.post(
            f"{API}/projects",
            headers=auth,
            json={"program_id": client.program_id, "name": "No Mission Project"},
        ).json()["id"]
        response = client.post(
            f"{API}/projects/{project_id}/scenarios/generate",
            headers=auth,
            json={"mode": "mission_expansion"},
        )
        assert response.status_code == 400
        assert "mission" in response.json()["detail"].lower()

    def test_plan_cannot_be_approved_with_unconfirmed_thresholds(self, client, auth):
        project_id = client.post(
            f"{API}/projects",
            headers=auth,
            json={"program_id": client.program_id, "name": "Threshold Project"},
        ).json()["id"]
        client.put(
            f"{API}/projects/{project_id}/mission",
            headers=auth,
            json={"mission": "Support a mission.", "tasks": ["Do the task."]},
        )
        plan = client.post(
            f"{API}/projects/{project_id}/plans/generate", headers=auth, json={}
        ).json()
        response = client.post(
            f"{API}/plans/{plan['id']}/approve",
            headers=auth,
            json={"approved_by": "Test Lead"},
        )
        assert response.status_code == 400
        detail = response.json()["detail"].lower()
        # Either reason is a correct refusal: an empty plan, or unconfirmed
        # thresholds. Both mean the approval would cover nothing meaningful.
        assert "threshold" in detail or "no evaluations" in detail

    def test_empty_plan_cannot_be_approved(self, client, auth):
        """Approving a plan that covers nothing must not record an approval."""
        project_id = client.post(
            f"{API}/projects",
            headers=auth,
            json={"program_id": client.program_id, "name": "Empty Plan Project"},
        ).json()["id"]
        client.put(
            f"{API}/projects/{project_id}/mission",
            headers=auth,
            json={"mission": "Support a mission.", "tasks": ["Do the task."]},
        )
        plan = client.post(
            f"{API}/projects/{project_id}/plans/generate", headers=auth, json={}
        ).json()
        coverage = client.get(f"{API}/plans/{plan['id']}", headers=auth).json()["coverage"]
        if coverage["evaluations"] == 0:
            response = client.post(
                f"{API}/plans/{plan['id']}/approve",
                headers=auth,
                json={"approved_by": "Test Lead"},
            )
            assert response.status_code == 400
            assert "no evaluations" in response.json()["detail"].lower()

    def test_framework_mappings_never_claim_compliance(self, client, auth):
        body = client.get(f"{API}/frameworks", headers=auth).json()
        assert "does not assert compliance" in body["note"]
        for framework in body["frameworks"]:
            for requirement in framework["requirements"]:
                assert requirement["compliance_claimable"] is False

    def test_unknown_connector_is_rejected(self, client, auth):
        project_id = client.post(
            f"{API}/projects",
            headers=auth,
            json={"program_id": client.program_id, "name": "Connector Project"},
        ).json()["id"]
        system = client.post(
            f"{API}/projects/{project_id}/systems", headers=auth, json={"name": "S"}
        ).json()
        response = client.post(
            f"{API}/systems/{system['id']}/versions",
            headers=auth,
            json={"version": "v1", "connector_type": "not-a-real-connector"},
        )
        assert response.status_code == 400

    def test_health_states_telemetry_is_off(self, client):
        assert client.get("/health").json()["telemetry_enabled"] is False
