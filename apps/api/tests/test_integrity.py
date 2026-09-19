"""Evidence integrity, audit chain, gates and red-team bookkeeping."""

from __future__ import annotations

from aegis import audit
from aegis.enums import ResultStatus, Severity
from aegis.hashing import canonical_json, content_hash, evidence_store
from aegis.models import AuditEvent, Campaign, Evaluation, Finding, Gate, Run
from aegis.runner.gates import evaluate_gate
from aegis.runner.redteam import (
    ATTACKS_BY_KEY,
    AdaptiveCampaignState,
    campaign_report,
    record_attempt,
    should_stop,
)


class TestHashing:
    def test_key_order_does_not_change_the_digest(self):
        assert content_hash({"a": 1, "b": 2}) == content_hash({"b": 2, "a": 1})

    def test_different_content_changes_the_digest(self):
        assert content_hash({"a": 1}) != content_hash({"a": 2})

    def test_canonical_json_is_stable(self):
        assert canonical_json({"b": 1, "a": 2}) == '{"a":2,"b":1}'

    def test_evidence_store_returns_a_verifiable_digest(self):
        stored = evidence_store().put_json("tests/artifact.json", {"value": 1})
        assert len(stored["sha256"]) == 64
        assert evidence_store().get(stored["storage_uri"]) == canonical_json({"value": 1}).encode()


class TestAuditChain:
    def test_chain_verifies(self, db):
        for i in range(5):
            audit.record(db, action=f"test.{i}", object_type="thing", object_id=str(i))
        db.flush()
        assert audit.verify_chain(db)["valid"] is True

    def test_editing_a_record_breaks_the_chain(self, db):
        for i in range(3):
            audit.record(db, action=f"test.{i}", object_type="thing", object_id=str(i))
        db.flush()
        event = db.query(AuditEvent).filter(AuditEvent.action == "test.1").one()
        event.detail = {"tampered": True}
        db.flush()
        outcome = audit.verify_chain(db)
        assert outcome["valid"] is False
        assert outcome["broken_at_sequence"] == event.sequence

    def test_removing_a_record_breaks_the_chain(self, db):
        for i in range(3):
            audit.record(db, action=f"test.{i}", object_type="thing", object_id=str(i))
        db.flush()
        db.delete(db.query(AuditEvent).filter(AuditEvent.action == "test.1").one())
        db.flush()
        assert audit.verify_chain(db)["valid"] is False


class TestGates:
    def _gate(self, db, project, criteria):
        gate = Gate(project_id=project.id, name="Release gate", criteria=criteria)
        db.add(gate)
        db.flush()
        return gate

    def _campaign(self, db, project):
        campaign = Campaign(project_id=project.id, name="Campaign")
        db.add(campaign)
        db.flush()
        return campaign

    def test_unresolved_critical_finding_fails_the_gate(self, db, project):
        db.add(
            Finding(
                project_id=project.id,
                key="F-0001",
                title="Critical failure",
                severity=Severity.CRITICAL,
                status="open",
            )
        )
        db.flush()
        gate = self._gate(
            db, project, [{"type": "no_findings_at_or_above", "severity": Severity.CRITICAL}]
        )
        check = evaluate_gate(db, gate, self._campaign(db, project))
        assert check.status == ResultStatus.FAIL

    def test_unmeasured_criterion_is_undetermined_not_a_pass(self, db, project):
        gate = self._gate(
            db,
            project,
            [{"type": "evaluation_verdict", "evaluation_key": "never-ran", "required_verdict": "pass"}],
        )
        check = evaluate_gate(db, gate, self._campaign(db, project))
        assert check.status == ResultStatus.NOT_EVALUATED

    def test_unknown_criterion_type_is_undetermined(self, db, project):
        gate = self._gate(db, project, [{"type": "invented_criterion"}])
        check = evaluate_gate(db, gate, self._campaign(db, project))
        assert check.status == ResultStatus.NOT_EVALUATED

    def test_outstanding_human_review_fails_a_gate_that_requires_it(self, db, project):
        from aegis.models import System, SystemVersion

        campaign = self._campaign(db, project)
        evaluation = Evaluation(key="e", name="e")
        system = System(project_id=project.id, name="S", slug="s")
        db.add_all([evaluation, system])
        db.flush()
        version = SystemVersion(system_id=system.id, version="v1", connector_type="echo")
        db.add(version)
        db.flush()
        run = Run(
            campaign_id=campaign.id,
            evaluation_id=evaluation.id,
            system_version_id=version.id,
            pending_human=3,
        )
        db.add(run)
        db.flush()
        gate = self._gate(db, project, [{"type": "human_review_complete"}])
        assert evaluate_gate(db, gate, campaign).status == ResultStatus.FAIL


class TestAdaptiveRedTeam:
    def test_stops_at_the_budget(self):
        state = AdaptiveCampaignState(attack_key="direct-injection", budget=3)
        for i in range(3):
            record_attempt(
                state, mutation=f"m{i}", payload="p", response_text="no", status=ResultStatus.PASS
            )
        assert should_stop(state) is True
        assert state.stop_reason == "attack_budget_exhausted"

    def test_stops_on_first_success(self):
        state = AdaptiveCampaignState(attack_key="direct-injection", budget=10)
        record_attempt(state, mutation="m0", payload="p", response_text="approved", status=ResultStatus.FAIL)
        assert should_stop(state, stop_on_first_success=True) is True
        assert state.stop_reason == "objective_demonstrated"

    def test_failed_mutations_are_not_retried(self):
        state = AdaptiveCampaignState(attack_key="direct-injection", budget=10)
        record_attempt(state, mutation="obfuscate", payload="p", response_text="no", status=ResultStatus.PASS)
        assert "obfuscate" in state.exhausted

    def test_a_campaign_that_found_nothing_does_not_claim_resistance(self):
        """Exhausting a budget without success bounds the result; it does not
        establish that the system is resistant."""
        state = AdaptiveCampaignState(attack_key="direct-injection", budget=2)
        for i in range(2):
            record_attempt(
                state, mutation=f"m{i}", payload="p", response_text="no", status=ResultStatus.PASS
            )
        should_stop(state)
        report = campaign_report(state)
        assert report["outcome"] == "not_demonstrated"
        assert "is not evidence that the system is resistant" in report["conclusion"]

    def test_a_successful_campaign_names_the_variant(self):
        state = AdaptiveCampaignState(attack_key="direct-injection", budget=5)
        record_attempt(
            state, mutation="authority_framing", payload="p", response_text="approved",
            status=ResultStatus.FAIL,
        )
        report = campaign_report(state)
        assert report["outcome"] == "vulnerable"
        assert "authority_framing" in report["conclusion"]
        assert report["recommended_mitigation"]

    def test_every_shipped_attack_declares_a_mitigation(self):
        for key, attack in ATTACKS_BY_KEY.items():
            assert attack.mitigation, f"{key} has no recommended mitigation"
            assert attack.category, f"{key} has no category"


class TestConfigurationGuards:
    """A real deployment must not run on shipped defaults."""

    def _settings(self, **overrides):
        from aegis.config import Settings

        return Settings(**{"env": "production", **overrides})

    def test_default_secret_is_refused_outside_development(self):
        from aegis.config import DEFAULT_SECRET, InsecureConfiguration, _validate
        import pytest

        with pytest.raises(InsecureConfiguration) as exc:
            _validate(self._settings(secret_key=DEFAULT_SECRET))
        assert "AEGIS_SECRET_KEY" in str(exc.value)

    def test_short_secret_is_refused(self):
        from aegis.config import InsecureConfiguration, _validate
        import pytest

        with pytest.raises(InsecureConfiguration):
            _validate(self._settings(secret_key="short", bootstrap_password="x" * 20, seed_demo=False))

    def test_demo_seeding_is_refused_outside_development(self):
        from aegis.config import InsecureConfiguration, _validate
        import pytest

        with pytest.raises(InsecureConfiguration) as exc:
            _validate(
                self._settings(
                    secret_key="k" * 48, bootstrap_password="a-real-password", seed_demo=True
                )
            )
        assert "AEGIS_SEED_DEMO" in str(exc.value)

    def test_a_properly_configured_deployment_starts(self):
        from aegis.config import _validate

        _validate(
            self._settings(
                secret_key="k" * 48, bootstrap_password="a-real-password", seed_demo=False
            )
        )

    def test_development_is_left_alone(self):
        from aegis.config import _validate

        _validate(self._settings(env="development"))


class TestReportLegibility:
    """A report a program executive reads must be unambiguous."""

    def test_results_table_names_the_system_when_several_were_evaluated(self, db, project):
        from aegis.models import Campaign, Evaluation, Run, System, SystemVersion
        from aegis.reports import executive_report

        system = System(project_id=project.id, name="Copilot", slug="copilot")
        db.add(system)
        db.flush()
        versions = []
        for label in ("v1", "v2"):
            version = SystemVersion(
                system_id=system.id, version=label, connector_type="echo", config_hash=f"h-{label}"
            )
            db.add(version)
            versions.append(version)
        evaluation = Evaluation(key="shared", name="Shared evaluation")
        campaign = Campaign(project_id=project.id, name="Dual")
        db.add_all([evaluation, campaign])
        db.flush()

        for version, failed in zip(versions, (0, 4)):
            db.add(
                Run(
                    campaign_id=campaign.id,
                    evaluation_id=evaluation.id,
                    system_version_id=version.id,
                    verdict="fail" if failed else "pass",
                    scenario_count=4,
                    passed=4 - failed,
                    failed=failed,
                )
            )
        db.flush()

        body = executive_report(db, project, campaign)
        assert "| System |" in body
        assert "Copilot v1" in body and "Copilot v2" in body

    def test_report_states_it_is_not_an_authorisation(self, db, project):
        from aegis.reports import executive_report

        body = executive_report(db, project, None)
        assert "not an authorisation to operate" in body
        assert "NOT EVALUATED" in body
