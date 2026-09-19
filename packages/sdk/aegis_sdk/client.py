"""Aegis Eval client.

Designed for the two cases in PRD sections 44 and 66: a developer exploring
results interactively, and a CI pipeline that must fail a build when an
evaluation gate does not pass.
"""

from __future__ import annotations

import os
import time
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any, TypeVar

import httpx

DEFAULT_TIMEOUT = 60.0
# typing.Self is 3.11+; the SDK supports 3.9, so a bound TypeVar is used instead.
_AegisT = TypeVar("_AegisT", bound="Aegis")
TERMINAL_STATUSES = {"completed", "failed", "cancelled", "awaiting_human"}


class AegisError(RuntimeError):
    """An API call failed."""

    def __init__(self, message: str, status_code: int | None = None, detail: Any = None) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.detail = detail


@dataclass
class Run:
    """One evaluation executed against one system version."""

    raw: dict

    @property
    def id(self) -> str:
        return self.raw["id"]

    @property
    def verdict(self) -> str:
        return self.raw.get("verdict", "not_evaluated")

    @property
    def evaluation(self) -> str:
        brief = self.raw.get("evaluation") or {}
        return brief.get("name") or brief.get("key") or self.raw.get("evaluation_id", "")

    @property
    def metrics(self) -> dict:
        return self.raw.get("metrics") or {}

    @property
    def judged(self) -> bool:
        """Whether anything in this run reached a pass or fail judgement."""
        return (self.raw.get("passed", 0) + self.raw.get("warned", 0) + self.raw.get("failed", 0)) > 0

    def __repr__(self) -> str:
        return f"<Run {self.evaluation!r} verdict={self.verdict} " f"{self.raw.get('passed')}/{self.raw.get('scenario_count')}>"


@dataclass
class Campaign:
    """A campaign and its runs."""

    raw: dict
    runs: list[Run]

    @property
    def id(self) -> str:
        return self.raw["id"]

    @property
    def status(self) -> str:
        return self.raw.get("status", "unknown")

    def summary(self) -> dict:
        return self.raw.get("summary") or {}

    @property
    def failed_runs(self) -> list[Run]:
        return [r for r in self.runs if r.verdict == "fail"]

    @property
    def unevaluated_runs(self) -> list[Run]:
        """Runs that produced no judgement.

        Worth checking in CI: a suite that silently evaluated nothing is not a
        suite that passed.
        """
        return [r for r in self.runs if r.verdict == "not_evaluated"]

    def __repr__(self) -> str:
        s = self.summary()
        return (
            f"<Campaign {self.raw.get('name')!r} status={self.status} "
            f"executed={s.get('executed')} failed={s.get('failed')}>"
        )


@dataclass
class GateResult:
    """The outcome of a deployment gate check."""

    raw: dict

    @property
    def status(self) -> str:
        return self.raw.get("status", "not_evaluated")

    @property
    def passed(self) -> bool:
        """True only on an explicit pass.

        An undetermined gate is not a passed gate: a criterion that could not be
        measured must not let a release through.
        """
        return self.status == "pass"

    @property
    def blocking(self) -> list[dict]:
        return [
            c
            for c in self.raw.get("criteria_results", [])
            if c.get("status") in ("fail", "not_evaluated")
        ]

    def explain(self) -> str:
        lines = [f"Gate {self.raw.get('gate', {}).get('name', '')}: {self.status.upper()}"]
        lines.extend(
            f"  [{criterion.get('status', '').upper():<14}] "
            f"{criterion.get('label')}: {criterion.get('detail')}"
            for criterion in self.raw.get("criteria_results", [])
        )
        return "\n".join(lines)


class _Namespace:
    def __init__(self, client: Aegis) -> None:
        self._client = client


class Projects(_Namespace):
    def list(self) -> list[dict]:
        return self._client.get("/projects")

    def get(self, project_id: str) -> dict:
        return self._client.get(f"/projects/{project_id}")

    def dashboard(self, project_id: str) -> dict:
        return self._client.get(f"/projects/{project_id}/dashboard")

    def create(self, program_id: str, name: str, **fields: Any) -> dict:
        return self._client.post("/projects", {"program_id": program_id, "name": name, **fields})

    def set_mission(self, project_id: str, mission: str, **fields: Any) -> dict:
        return self._client.put(f"/projects/{project_id}/mission", {"mission": mission, **fields})


class Systems(_Namespace):
    def list(self, project_id: str) -> list[dict]:
        return self._client.get(f"/projects/{project_id}/systems")

    def create(self, project_id: str, name: str, kind: str = "llm", **fields: Any) -> dict:
        return self._client.post(
            f"/projects/{project_id}/systems", {"name": name, "kind": kind, **fields}
        )

    def add_version(self, system_id: str, version: str, **fields: Any) -> dict:
        return self._client.post(
            f"/systems/{system_id}/versions", {"version": version, **fields}
        )

    def versions(self, system_id: str) -> list[dict]:
        return self._client.get(f"/systems/{system_id}/versions")

    def check_connectivity(self, version_id: str) -> dict:
        return self._client.post(f"/system-versions/{version_id}/connectivity")


class Evaluations(_Namespace):
    def library(self, **filters: Any) -> list[dict]:
        query = "&".join(f"{k}={v}" for k, v in filters.items() if v is not None)
        return self._client.get(f"/evaluations{'?' + query if query else ''}")

    def load(self, pack: str) -> list[dict]:
        """Every evaluation belonging to a pack."""
        return self.library(pack=pack)

    def generate_plan(self, project_id: str, system_version_id: str | None = None) -> dict:
        return self._client.post(
            f"/projects/{project_id}/plans/generate",
            {"system_version_id": system_version_id},
        )

    def plan(self, plan_id: str) -> dict:
        return self._client.get(f"/plans/{plan_id}")


class Campaigns(_Namespace):
    def create(
        self,
        project_id: str,
        name: str,
        system_version_ids: list[str],
        *,
        evaluation_keys: list[str] | None = None,
        plan_id: str | None = None,
        thresholds: dict | None = None,
        **fields: Any,
    ) -> dict:
        return self._client.post(
            f"/projects/{project_id}/campaigns",
            {
                "name": name,
                "system_version_ids": system_version_ids,
                "evaluation_keys": evaluation_keys or [],
                "plan_id": plan_id,
                "thresholds": thresholds or {},
                **fields,
            },
        )

    def execute(self, campaign_id: str, judge: dict | None = None) -> dict:
        return self._client.post(f"/campaigns/{campaign_id}/execute", judge)

    def summary(self, campaign_id: str) -> dict:
        return self._client.get(f"/campaigns/{campaign_id}/summary")

    def comparison(self, campaign_id: str) -> dict:
        return self._client.get(f"/campaigns/{campaign_id}/comparison")

    def regression(self, campaign_id: str, baseline_campaign_id: str | None = None) -> dict:
        suffix = f"?baseline_campaign_id={baseline_campaign_id}" if baseline_campaign_id else ""
        return self._client.get(f"/campaigns/{campaign_id}/regression{suffix}")


class Findings(_Namespace):
    def list(self, project_id: str, **filters: Any) -> list[dict]:
        query = "&".join(f"{k}={v}" for k, v in filters.items() if v is not None)
        return self._client.get(f"/projects/{project_id}/findings{'?' + query if query else ''}")

    def get(self, finding_id: str) -> dict:
        return self._client.get(f"/findings/{finding_id}")

    def update(self, finding_id: str, **fields: Any) -> dict:
        return self._client.patch(f"/findings/{finding_id}", fields)


class Gates(_Namespace):
    def list(self, project_id: str) -> list[dict]:
        return self._client.get(f"/projects/{project_id}/gates")

    def check(self, gate_id: str, campaign_id: str) -> GateResult:
        return GateResult(self._client.post(f"/gates/{gate_id}/check?campaign_id={campaign_id}"))


class Reports(_Namespace):
    def generate(self, project_id: str, kind: str, **fields: Any) -> dict:
        return self._client.post(f"/projects/{project_id}/reports", {"kind": kind, **fields})

    def list(self, project_id: str) -> list[dict]:
        return self._client.get(f"/projects/{project_id}/reports")


class Aegis:
    """Aegis Eval API client.

    Credentials come from the environment by default so a token never has to
    appear in a script or a CI configuration file.
    """

    def __init__(
        self,
        base_url: str | None = None,
        token: str | None = None,
        *,
        email: str | None = None,
        password: str | None = None,
        timeout: float = DEFAULT_TIMEOUT,
        verify: bool | str = True,
    ) -> None:
        self.base_url = (base_url or os.getenv("AEGIS_URL") or "http://localhost:8000").rstrip("/")
        self.api = f"{self.base_url}/api/v1"
        self._token = token or os.getenv("AEGIS_TOKEN")
        self._client = httpx.Client(timeout=timeout, verify=verify)

        if not self._token:
            email = email or os.getenv("AEGIS_EMAIL")
            password = password or os.getenv("AEGIS_PASSWORD")
            if email and password:
                self.login(email, password)

        self.projects = Projects(self)
        self.systems = Systems(self)
        self.evaluations = Evaluations(self)
        self.campaigns = Campaigns(self)
        self.findings = Findings(self)
        self.gates = Gates(self)
        self.reports = Reports(self)

    # -- transport ---------------------------------------------------------

    def _headers(self) -> dict:
        headers = {"Accept": "application/json"}
        if self._token:
            headers["Authorization"] = f"Bearer {self._token}"
        return headers

    def _request(self, method: str, path: str, body: Any = None) -> Any:
        response = self._client.request(
            method, f"{self.api}{path}", json=body, headers=self._headers()
        )
        if response.status_code >= 400:
            detail: Any = None
            message = f"{response.status_code} {response.reason_phrase}"
            try:
                detail = response.json()
                if isinstance(detail.get("detail"), str):
                    message = detail["detail"]
            except Exception:
                detail = response.text
            raise AegisError(message, response.status_code, detail)
        if response.status_code == 204 or not response.content:
            return None
        return response.json()

    def get(self, path: str) -> Any:
        return self._request("GET", path)

    def post(self, path: str, body: Any = None) -> Any:
        return self._request("POST", path, body)

    def put(self, path: str, body: Any) -> Any:
        return self._request("PUT", path, body)

    def patch(self, path: str, body: Any) -> Any:
        return self._request("PATCH", path, body)

    def login(self, email: str, password: str) -> str:
        response = self._client.post(
            f"{self.api}/auth/login", json={"email": email, "password": password}
        )
        if response.status_code >= 400:
            raise AegisError("Sign-in failed", response.status_code)
        self._token = response.json()["access_token"]
        return self._token

    def whoami(self) -> dict:
        return self.get("/auth/me")

    def health(self) -> dict:
        return self._client.get(f"{self.base_url}/health").json()

    # -- high-level workflow ----------------------------------------------

    def evaluate(
        self,
        *,
        project_id: str,
        system_version_ids: list[str],
        name: str | None = None,
        suite: str | None = None,
        evaluation_keys: list[str] | None = None,
        plan_id: str | None = None,
        thresholds: dict | None = None,
        judge: dict | None = None,
        wait: bool = True,
        poll_seconds: float = 2.0,
        timeout_seconds: float = 1800.0,
    ) -> Campaign:
        """Create and run a campaign in one call.

        `suite` names an installed evaluation pack; its evaluations are resolved
        and run. Pass `evaluation_keys` or `plan_id` for finer control.
        """
        keys = list(evaluation_keys or [])
        if suite:
            keys.extend(e["key"] for e in self.evaluations.load(suite))
        if not keys and not plan_id:
            raise AegisError("Supply one of: suite, evaluation_keys or plan_id.")

        campaign = self.campaigns.create(
            project_id,
            name or f"SDK campaign {time.strftime('%Y-%m-%d %H:%M')}",
            system_version_ids,
            evaluation_keys=keys,
            plan_id=plan_id,
            thresholds=thresholds,
        )
        self.campaigns.execute(campaign["id"], judge)
        if not wait:
            return Campaign(campaign, [])
        return self.wait_for(campaign["id"], poll_seconds, timeout_seconds)

    def wait_for(
        self, campaign_id: str, poll_seconds: float = 2.0, timeout_seconds: float = 1800.0
    ) -> Campaign:
        deadline = time.time() + timeout_seconds
        while True:
            body = self.campaigns.summary(campaign_id)
            status = body["campaign"]["status"]
            if status in TERMINAL_STATUSES:
                return Campaign(
                    {**body["campaign"], "summary": body["summary"]},
                    [Run(r) for r in body["runs"]],
                )
            if time.time() > deadline:
                raise AegisError(
                    f"Campaign {campaign_id} did not finish within {timeout_seconds:.0f}s "
                    f"(last status: {status})."
                )
            time.sleep(poll_seconds)

    def iter_results(self, run_id: str, page_size: int = 200) -> Iterator[dict]:
        """Page through a run's results without holding them all in memory."""
        offset = 0
        while True:
            page = self.get(f"/runs/{run_id}/results?limit={page_size}&offset={offset}")
            if not page:
                return
            yield from page
            if len(page) < page_size:
                return
            offset += page_size

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> Aegis:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()
