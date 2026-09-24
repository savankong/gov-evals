"""Target, Capture, Deliver: finding the weakness, working it, shipping it.

Three claims are held here, each the product refusing something:

  * A missing confidence is unknown. It is never counted as confident, and
    never as unsure, however convenient either would be for a sort.
  * A trace or review from someone unqualified is kept on the record and is
    not delivered as expert data.
  * Nothing leaves in a package unless it is exactly UNCLASSIFIED, carries no
    personal information, and holds a judgement someone actually made.
"""

from __future__ import annotations

import io
import json
import math
import zipfile

import pytest
from fastapi.testclient import TestClient

from aegis import targeting
from aegis.connectors import TargetRequest
from aegis.connectors.builtin import EchoAdapter, _logprob_confidence
from aegis.db import SessionLocal
from aegis.enums import Classification, Discipline, ResultStatus, Role
from aegis.hashing import content_hash
from aegis.main import create_app
from aegis.models import (
    Base,
    Campaign,
    Dataset,
    DatasetVersion,
    Evaluation,
    HumanReview,
    Membership,
    Organization,
    Program,
    Project,
    Result,
    Run,
    Scenario,
    System,
    SystemVersion,
    User,
)
from aegis.runner.engine import execute_run
from aegis.security import ensure_role_definitions, hash_password

API = "/api/v1"
AREA = "Source selection (FAR 15.3)"
OTHER_AREA = "Bid protests (FAR 33.1)"


# ---------------------------------------------------------------------------
# Confidence is evidence about one answer, and unknown stays unknown
# ---------------------------------------------------------------------------


class TestConfidence:
    @pytest.mark.parametrize("value", [None, "0.9", True, 1.5, -0.1, 90])
    def test_anything_but_a_probability_is_unknown(self, value):
        assert targeting.confidence_of({"confidence": value}) == (None, None)

    def test_a_probability_keeps_its_source(self):
        assert targeting.confidence_of({"confidence": 0.9, "confidence_source": "logprob"}) == (
            0.9,
            "logprob",
        )

    def test_one_sample_agrees_with_itself_and_says_nothing(self):
        assert targeting.sample_agreement([], "an answer") is None

    def test_agreement_is_the_share_giving_the_same_answer(self):
        assert targeting.sample_agreement(["Yes.", "No"], "yes.") == pytest.approx(2 / 3)

    def test_wrong_with_no_confidence_is_neither_confident_nor_unsure(self):
        outcome = targeting.Outcome()
        outcome.add(Result(status=ResultStatus.FAIL, response={}), 0.8)
        assert outcome.failed == 1
        assert outcome.confidence_unknown_wrong == 1
        assert outcome.confident_wrong == 0
        assert outcome.unsure_wrong == 0

    def test_the_threshold_decides_confident_and_is_inclusive(self):
        outcome = targeting.Outcome()
        outcome.add(Result(status=ResultStatus.FAIL, response={"confidence": 0.8}), 0.8)
        outcome.add(Result(status=ResultStatus.FAIL, response={"confidence": 0.79}), 0.8)
        assert (outcome.confident_wrong, outcome.unsure_wrong) == (1, 1)

    @pytest.mark.parametrize(
        "status", [ResultStatus.NOT_EVALUATED, ResultStatus.PENDING_HUMAN, ResultStatus.ERROR]
    )
    def test_no_judgement_is_neither_a_pass_nor_a_failure(self, status):
        outcome = targeting.Outcome()
        outcome.add(Result(status=status, response={"confidence": 0.99}), 0.8)
        assert (outcome.passed, outcome.failed, outcome.unresolved) == (0, 0, 1)
        assert outcome.label == "not_evaluated"

    def test_logprobs_become_a_geometric_mean_probability(self):
        logprobs = {"content": [{"logprob": 0.0}, {"logprob": math.log(0.25)}]}
        assert _logprob_confidence(logprobs) == pytest.approx(0.5)
        assert _logprob_confidence({"content": []}) is None
        assert _logprob_confidence(None) is None

    def test_the_offline_target_claims_no_confidence_unless_configured(self):
        quiet = EchoAdapter({"parameters": {}}).invoke(TargetRequest(prompt="Summarise."))
        assert quiet.confidence is None and quiet.confidence_source is None
        loud = EchoAdapter({"parameters": {"report_confidence": True}}).invoke(
            TargetRequest(prompt="Summarise.")
        )
        assert 0.5 <= loud.confidence < 1.0 and loud.confidence_source == "reported"


class TestConfidenceInTheEngine:
    def _run(self, db, project, parameters, repetitions):
        system = System(project_id=project.id, name="Target", slug="target", kind="llm")
        db.add(system)
        db.flush()
        version = SystemVersion(
            system_id=system.id,
            version="v1",
            connector_type="echo",
            parameters=parameters,
            config_hash="h",
        )
        db.add(version)
        db.add(
            Scenario(
                project_id=project.id,
                key="s",
                title="s",
                input={"prompt": "Summarise."},
                tags=["t"],
                content_hash="hs",
            )
        )
        evaluation = Evaluation(
            key="e",
            name="e",
            evaluators=[{"evaluator": "citation_validity"}],
            scenario_selector={"tags": ["t"], "repetitions": repetitions},
        )
        db.add(evaluation)
        campaign = Campaign(project_id=project.id, name="c")
        db.add(campaign)
        db.flush()
        run = Run(campaign_id=campaign.id, evaluation_id=evaluation.id, system_version_id=version.id)
        db.add(run)
        db.flush()
        execute_run(db, run)
        return sorted(run.results, key=lambda r: r.repetition)

    def test_repeated_samples_measure_agreement_from_the_second_on(self, db, project):
        results = self._run(db, project, {"profile": "cooperative"}, repetitions=3)
        assert [targeting.confidence_of(r.response) for r in results] == [
            (None, None),
            (1.0, "sample_agreement"),
            (1.0, "sample_agreement"),
        ]

    def test_a_reported_confidence_wins_and_is_hashed_with_the_response(self, db, project):
        results = self._run(
            db, project, {"profile": "cooperative", "report_confidence": True}, repetitions=2
        )
        assert {targeting.confidence_of(r.response)[1] for r in results} == {"reported"}
        # The digest covers the response, so it covers the confidence in it.
        assert all("confidence" in r.response for r in results)


# ---------------------------------------------------------------------------
# The API: a small world with one qualified and one unqualified expert
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def world():
    from aegis.db import engine

    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)

    s = SessionLocal()
    org = Organization(name="Capture Org", short_name="CAP")
    s.add(org)
    s.flush()
    ensure_role_definitions(s, org.id)
    program = Program(organization_id=org.id, name="Capture Program")
    s.add(program)
    s.flush()
    project = Project(program_id=program.id, name="Capture Project", slug="capture")
    s.add(project)
    users = {}
    for key in ("contracting", "cyber", "reader"):
        users[key] = User(
            email=f"{key}@example.test",
            full_name=f"{key.title()} Person",
            password_hash=hash_password("pw-capture"),
        )
    s.add_all(users.values())
    s.flush()
    for key, user in users.items():
        role = Role.READ_ONLY if key == "reader" else Role.ORG_ADMIN
        s.add(Membership(user_id=user.id, organization_id=org.id, role=role))

    system = System(project_id=project.id, name="Lab model", slug="lab", kind="llm")
    s.add(system)
    s.flush()
    version = SystemVersion(system_id=system.id, version="v1", connector_type="echo", config_hash="x")
    evaluation = Evaluation(key="e", name="Contract reasoning")
    s.add_all([version, evaluation])
    s.flush()
    campaign = Campaign(project_id=project.id, name="Probe")
    s.add(campaign)
    s.flush()
    run = Run(campaign_id=campaign.id, evaluation_id=evaluation.id, system_version_id=version.id)
    s.add(run)
    s.flush()

    def scenario(key, area, **kw):
        row = Scenario(
            project_id=project.id,
            key=key,
            title=key,
            task="Decide.",
            input={"prompt": f"Problem {key}", "documents": [{"source_id": "D1", "text": "t"}]},
            reference_answer="THE ANSWER",
            knowledge_area=area,
            required_expertise=kw.pop("required", [Discipline.ACQUISITION]),
            content_hash=f"h-{key}",
            **kw,
        )
        s.add(row)
        s.flush()
        return row

    def result(sc, status, confidence=None):
        row = Result(
            run_id=run.id,
            scenario_id=sc.id,
            status=status,
            request={"prompt": sc.input["prompt"]},
            response={"text": f"model answer to {sc.key}", "confidence": confidence,
                      "confidence_source": "reported" if confidence is not None else None},
            content_hash=f"r-{sc.key}-{status}",
        )
        s.add(row)
        s.flush()
        return row

    ids = {}
    # Failed while sure of itself: the most valuable problem to capture.
    sc = scenario("confident-miss", AREA)
    ids["confident_miss"] = sc.id
    ids["confident_miss_result"] = result(sc, ResultStatus.FAIL, 0.95).id
    # Failed, and nobody knows how sure it was.
    sc = scenario("unknown-miss", AREA)
    ids["unknown_miss"] = sc.id
    result(sc, ResultStatus.FAIL)
    # Got it right.
    sc = scenario("solved", AREA)
    ids["solved"] = sc.id
    ids["solved_result"] = result(sc, ResultStatus.PASS, 0.9).id
    # Never judged.
    sc = scenario("pending", OTHER_AREA)
    ids["pending"] = sc.id
    ids["pending_result"] = result(sc, ResultStatus.PENDING_HUMAN, 0.9).id
    # Nobody said what it tests.
    sc = scenario("undeclared", None, required=[])
    ids["undeclared"] = sc.id
    result(sc, ResultStatus.FAIL, 0.4)
    # Needs a discipline only the cyber expert holds.
    sc = scenario("cyber-only", OTHER_AREA, required=[Discipline.CYBER])
    ids["cyber_only"] = sc.id
    # Sensitive: CUI.
    sc = scenario("cui", AREA, classification=Classification.CUI)
    ids["cui"] = sc.id
    result(sc, ResultStatus.FAIL, 0.99)

    s.commit()
    ids["project"] = project.id
    s.close()

    app = create_app()
    app.router.on_startup.clear()
    with TestClient(app) as client:
        auth = {}
        for key in ("contracting", "cyber", "reader"):
            token = client.post(
                f"{API}/auth/login", json={"email": f"{key}@example.test", "password": "pw-capture"}
            ).json()["access_token"]
            auth[key] = {"Authorization": f"Bearer {token}"}
        for key, disciplines in (("contracting", [Discipline.ACQUISITION]), ("cyber", [Discipline.CYBER])):
            response = client.put(
                f"{API}/expert-profiles/me",
                headers=auth[key],
                json={"display_name": f"{key} expert", "disciplines": disciplines,
                      "years_experience": 12},
            )
            assert response.status_code == 200, response.text
        client.as_ = auth
        client.ids = ids
        yield client


def _trace(client, who, scenario_id, **kw):
    body = {
        "scenario_id": scenario_id,
        "steps": [
            {"text": "Identify the evaluation factors stated in Section M.", "basis": "FAR 15.304"},
            {"text": "Compare the proposal only against those factors.", "basis": "FAR 15.305(a)"},
        ],
        "final_answer": "The proposal is acceptable on the stated factors.",
        "time_spent_seconds": 900,
        **kw,
    }
    return client.post(f"{API}/reasoning-traces", headers=client.as_[who], json=body)


def _area(client, label, **params):
    response = client.get(f"{API}/weakness-map", headers=client.as_["reader"], params=params)
    assert response.status_code == 200, response.text
    return next(row for row in response.json()["areas"] if row["label"] == label)


class TestWeaknessMap:
    def test_counts_by_area_with_confidence_kept_apart(self, world):
        row = _area(world, AREA)
        assert (row["failed"], row["passed"]) == (3, 1)
        assert row["confident_wrong"] == 2  # the confident miss and the CUI one
        assert row["confidence_unknown_wrong"] == 1
        assert row["unsure_wrong"] == 0

    def test_the_threshold_is_the_readers_and_is_echoed(self, world):
        response = world.get(
            f"{API}/weakness-map", headers=world.as_["reader"], params={"confident_at": 0.3}
        )
        assert response.json()["confident_at"] == 0.3
        undeclared = next(r for r in response.json()["areas"] if not r["declared"])
        assert undeclared["confident_wrong"] == 1

    def test_an_undeclared_area_is_reported_as_such_and_listed_last(self, world):
        areas = world.get(f"{API}/weakness-map", headers=world.as_["reader"]).json()["areas"]
        assert areas[-1]["knowledge_area"] is None
        assert areas[-1]["label"] == targeting.UNDECLARED_LABEL

    def test_pending_counts_as_unresolved_not_as_anything_else(self, world):
        row = _area(world, OTHER_AREA)
        assert (row["passed"], row["failed"], row["unresolved"]) == (0, 0, 1)

    def test_there_is_no_single_figure(self, world):
        """No magic number: the map is counts a reader sorts, never a score."""
        body = world.get(f"{API}/weakness-map", headers=world.as_["reader"]).json()
        for row in body["areas"]:
            for key in row:
                assert not any(w in key for w in ("score", "roi", "value", "priority", "rank"))


class TestCapture:
    def test_the_queue_leads_with_what_the_model_got_wrong(self, world):
        tasks = world.get(
            f"{API}/capture/tasks", headers=world.as_["contracting"], params={"scope": "all"}
        ).json()["tasks"]
        outcomes = [t["model"]["outcome"] for t in tasks if t["qualified_traces"] == 0]
        # Every failure before any unknown, every unknown before any pass.
        order = {"failed": 0, "not_evaluated": 1, "passed": 2}
        assert [order[o] for o in outcomes] == sorted(order[o] for o in outcomes)
        # Among failures, the confident miss comes first.
        assert tasks[0]["model"]["confident_wrong"] >= 1

    def test_mine_is_what_the_viewer_can_qualify_on(self, world):
        mine = world.get(f"{API}/capture/tasks", headers=world.as_["contracting"]).json()["tasks"]
        assert world.ids["cyber_only"] not in {t["scenario_id"] for t in mine}
        assert all(t["viewer_is_qualified"] for t in mine)

    def test_the_problem_is_shown_without_its_answer(self, world):
        body = world.get(
            f"{API}/capture/tasks/{world.ids['confident_miss']}", headers=world.as_["contracting"]
        ).json()
        assert "THE ANSWER" not in json.dumps(body["problem"])
        assert body["model_answers"][0]["confidence"] == 0.95

    def test_a_qualified_trace_counts_and_clears_the_backlog(self, world):
        before = _area(world, AREA)["failed_without_trace"]
        response = _trace(world, "contracting", world.ids["unknown_miss"], expertise="acquisition")
        assert response.status_code == 201, response.text
        trace = response.json()
        assert trace["qualified"] is True
        assert trace["knowledge_area"] == AREA
        assert len(trace["content_hash"]) == 64
        assert "THE ANSWER" not in json.dumps(trace["problem"])
        after = _area(world, AREA)
        assert after["failed_without_trace"] == before - 1
        assert after["expert_seconds"] >= 900

    def test_an_unqualified_trace_is_kept_and_clears_nothing(self, world):
        before = _area(world, AREA)
        response = _trace(world, "cyber", world.ids["confident_miss"])
        assert response.status_code == 201, response.text
        assert response.json()["qualified"] is False
        assert "does not cover" in response.json()["qualification_note"]
        after = _area(world, AREA)
        assert after["traces"] == before["traces"] + 1
        assert after["failed_without_trace"] == before["failed_without_trace"]

    def test_a_trace_is_at_least_as_sensitive_as_its_problem(self, world):
        response = _trace(world, "contracting", world.ids["cui"], classification="UNCLASSIFIED")
        assert response.status_code == 201, response.text
        assert response.json()["classification"] == Classification.CUI

    def test_a_model_answer_to_another_problem_is_refused(self, world):
        response = _trace(
            world, "contracting", world.ids["unknown_miss"],
            result_id=world.ids["solved_result"],
        )
        assert response.status_code == 400

    def test_a_trace_needs_a_step_that_says_something(self, world):
        empty = _trace(world, "contracting", world.ids["solved"], steps=[])
        blank = _trace(world, "contracting", world.ids["solved"], steps=[{"text": "   "}])
        assert empty.status_code == 422
        assert blank.status_code == 400

    def test_reading_is_not_permission_to_capture(self, world):
        assert _trace(world, "reader", world.ids["solved"]).status_code == 403


class TestDelivery:
    @pytest.fixture(scope="class")
    def package(self, world):
        # A trace on the confident miss, shown the model answer, by the right expert.
        response = _trace(
            world, "contracting", world.ids["confident_miss"],
            result_id=world.ids["confident_miss_result"], expertise="acquisition",
        )
        assert response.status_code == 201
        # One with PII, which must stay home.
        assert _trace(world, "contracting", world.ids["solved"], contains_pii=True).status_code == 201
        # A qualified review on a pending result: still no judgement to deliver.
        s = SessionLocal()
        s.add(HumanReview(result_id=world.ids["pending_result"], status=ResultStatus.PASS,
                          qualified=True, expertise="acquisition"))
        s.add(HumanReview(result_id=world.ids["confident_miss_result"], status=ResultStatus.FAIL,
                          qualified=True, expertise="acquisition", comments="Wrong factor."))
        s.add(HumanReview(result_id=world.ids["solved_result"], status=ResultStatus.PASS,
                          qualified=False))
        s.commit()
        s.close()

        created = world.post(
            f"{API}/data-packages", headers=world.as_["contracting"],
            json={"name": "Lab A / source selection", "customer": "Lab A"},
        )
        assert created.status_code == 201, created.text
        return created.json()

    def _records(self, world, package):
        response = world.get(
            f"{API}/data-packages/{package['id']}/download", headers=world.as_["contracting"]
        )
        assert response.status_code == 200, response.text
        assert response.headers["X-Content-SHA256"] == package["sha256"]
        return [json.loads(line) for line in response.text.splitlines()]

    def test_only_qualified_unclassified_clean_judged_records_leave(self, world, package):
        records = self._records(world, package)
        for record in records:
            if record["kind"] == "reasoning_trace":
                assert record["problem"]["title"] not in ("cui", "solved")
        excluded = {e["reason"]: e["records"] for e in package["manifest"]["excluded"]}
        assert excluded["not_qualified"] >= 1       # the cyber expert's trace
        assert excluded["not_unclassified"] >= 1    # the CUI trace
        assert excluded["contains_pii"] >= 1        # the flagged one
        assert excluded["no_judgement"] >= 1        # the pending result
        assert excluded["no_qualified_judgement"] >= 1

    def test_a_scored_response_carries_only_qualified_judgements(self, world, package):
        scored = [r for r in self._records(world, package) if r["kind"] == "scored_response"]
        assert [r["id"] for r in scored] == [world.ids["confident_miss_result"]]
        assert scored[0]["model_confidence"] == 0.95
        assert [j["status"] for j in scored[0]["judgements"]] == [ResultStatus.FAIL]

    def test_each_record_carries_a_digest_that_checks(self, world, package):
        for record in self._records(world, package):
            digest = record.pop("sha256")
            assert content_hash(record) == digest

    def test_experts_are_pseudonymous(self, world, package):
        body = world.get(
            f"{API}/data-packages/{package['id']}/download", headers=world.as_["contracting"]
        ).text
        assert "Contracting Person" not in body and "contracting@example.test" not in body
        assert "contracting expert" not in body

    def test_records_are_binned_by_area_and_model_outcome(self, world, package):
        bins = package["manifest"]["bins"]
        assert {"knowledge_area": AREA, "model_outcome": "failed",
                "kind": "reasoning_trace", "records": 2} in bins

    def test_a_selection_with_nothing_deliverable_says_why(self, world):
        response = world.post(
            f"{API}/data-packages", headers=world.as_["contracting"],
            json={"name": "Nothing", "knowledge_areas": [OTHER_AREA]},
        )
        assert response.status_code == 422
        assert "no judgement was ever made" in response.json()["detail"]

    def test_a_package_that_changed_after_it_was_built_is_not_sent(self, world, package):
        from aegis.hashing import evidence_store
        from aegis.models import DataPackage

        s = SessionLocal()
        uri = s.get(DataPackage, package["id"]).storage_uri
        s.close()
        original = evidence_store().get(uri)
        path = uri.removeprefix("file://")
        try:
            with open(path, "ab") as handle:
                handle.write(b'{"kind":"smuggled"}\n')
            response = world.get(
                f"{API}/data-packages/{package['id']}/download", headers=world.as_["contracting"]
            )
            assert response.status_code == 409
        finally:
            with open(path, "wb") as handle:
                handle.write(original)

    def test_building_a_package_needs_permission(self, world):
        response = world.post(
            f"{API}/data-packages", headers=world.as_["reader"], json={"name": "x"}
        )
        assert response.status_code == 403


class TestDeliveryOfDatasetResults:
    def test_a_dataset_flagged_for_pii_keeps_its_results_home(self, world):
        s = SessionLocal()
        dataset = Dataset(project_id=world.ids["project"], name="Personnel", contains_pii=True)
        s.add(dataset)
        s.flush()
        version = DatasetVersion(dataset_id=dataset.id, version="v1")
        s.add(version)
        s.flush()
        result = s.get(Result, world.ids["solved_result"])
        run = s.get(Run, result.run_id)
        previous = run.dataset_version_id
        run.dataset_version_id = version.id
        s.add(HumanReview(result_id=result.id, status=ResultStatus.PASS, qualified=True))
        s.commit()
        try:
            response = world.post(
                f"{API}/data-packages", headers=world.as_["contracting"],
                json={"name": "PII check", "include_traces": False},
            )
            ids = []
            if response.status_code == 201:
                body = world.get(
                    f"{API}/data-packages/{response.json()['id']}/download",
                    headers=world.as_["contracting"],
                ).text
                ids = [json.loads(line)["id"] for line in body.splitlines()]
            assert world.ids["solved_result"] not in ids
        finally:
            run = s.get(Run, result.run_id)
            run.dataset_version_id = previous
            s.commit()
            s.close()


# ---------------------------------------------------------------------------
# Ingest: a provider's zip
# ---------------------------------------------------------------------------


def _zip(files: dict[str, bytes]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, data in files.items():
            archive.writestr(name, data)
    return buffer.getvalue()


class TestArchiveIngest:
    @pytest.fixture(scope="class")
    def dataset_id(self, world):
        created = world.post(
            f"{API}/projects/{world.ids['project']}/datasets",
            headers=world.as_["contracting"],
            json={"name": "Provider drop"},
        )
        assert created.status_code == 201, created.text
        return created.json()["id"]

    def _upload(self, world, dataset_id, body):
        return world.post(
            f"{API}/datasets/{dataset_id}/versions",
            headers=world.as_["contracting"],
            files={"file": ("drop.zip", io.BytesIO(body), "application/zip")},
        )

    def test_documents_and_structured_files_become_rows(self, world, dataset_id):
        body = _zip(
            {
                "protests/b-421.txt": b"The protest is denied.",
                "index.jsonl": b'{"input": "q1", "expected": "a1"}\n{"input": "q2"}\n',
                "scan.pdf": b"%PDF-1.7\xff\xfe\x00binary",
                "__MACOSX/._scan.pdf": b"junk",
                ".DS_Store": b"junk",
            }
        )
        response = self._upload(world, dataset_id, body)
        assert response.status_code == 201, response.text
        version = response.json()
        assert version["source_format"] == "zip"
        assert version["item_count"] == 4
        report = version["quality_report"]
        assert report["files_without_text"] == 1
        assert any("not text" in issue for issue in report["issues"])

        items = world.get(
            f"{API}/dataset-versions/{version['id']}/items", headers=world.as_["contracting"]
        ).json()["items"]
        by_file = {}
        for item in items:
            by_file.setdefault(item["payload"]["source_file"], []).append(item["payload"])
        assert set(by_file) == {"index.jsonl", "protests/b-421.txt", "scan.pdf"}
        assert by_file["protests/b-421.txt"][0]["input"] == "The protest is denied."
        assert [p["input"] for p in by_file["index.jsonl"]] == ["q1", "q2"]
        assert len(by_file["scan.pdf"][0]["source_sha256"]) == 64

    def test_too_many_files_is_refused_with_a_way_forward(self, world, dataset_id, monkeypatch):
        from aegis.routers import datasets

        monkeypatch.setattr(datasets, "MAX_ARCHIVE_ENTRIES", 2)
        response = self._upload(world, dataset_id, _zip({f"{i}.txt": b"x" for i in range(3)}))
        assert response.status_code == 400
        assert "Split it" in response.json()["detail"]

    def test_expansion_is_bounded_by_what_is_read_not_what_is_declared(
        self, world, dataset_id, monkeypatch
    ):
        from aegis.routers import datasets

        monkeypatch.setattr(datasets, "MAX_ARCHIVE_EXPANDED_BYTES", 1024)
        # Compresses to almost nothing; expands past the limit.
        response = self._upload(world, dataset_id, _zip({"bomb.txt": b"0" * 10_000}))
        assert response.status_code == 400
        assert "expands past" in response.json()["detail"]

    def test_a_file_that_is_not_a_zip_says_so(self, world, dataset_id):
        response = self._upload(world, dataset_id, b"not a zip at all")
        assert response.status_code == 400
        assert "zip" in response.json()["detail"].lower()
