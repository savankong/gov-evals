"""External tool evaluators.

Section 20 allows an evaluation to invoke a static analyser, security scanner,
simulation, domain validator, database lookup or external benchmark harness.
Both adapters record the tool identity and version so the judgement is
attributable and reproducible.
"""

from __future__ import annotations

import json
import shlex
import subprocess

import httpx

from ..enums import EvaluatorKind, ResultStatus
from .base import EvaluationContext, Evaluator, Judgement, register_evaluator


@register_evaluator
class ExternalCommandEvaluator(Evaluator):
    """Runs a local validator and reads its verdict.

    The command is supplied by the evaluation definition, which is an
    administrative action: only users with evaluation:write can create one.
    The result payload is passed on stdin as JSON rather than interpolated into
    the command line, so scenario content cannot alter the command.
    """

    key = "external_command"
    kind = EvaluatorKind.EXTERNAL_TOOL
    label = "External command validator"
    description = "Executes a configured local tool and reads a JSON verdict from stdout."

    def evaluate(self, ctx: EvaluationContext) -> Judgement:
        command = self.config.get("command")
        if not command:
            return self._judgement(
                status=ResultStatus.NOT_EVALUATED, rationale="No command configured."
            )

        argv = command if isinstance(command, list) else shlex.split(command)
        payload = json.dumps(
            {
                "scenario": ctx.scenario,
                "request": ctx.request,
                "response": ctx.response,
                "threshold": ctx.threshold,
            },
            default=str,
        )
        timeout = float(self.config.get("timeout_seconds", 120))

        try:
            completed = subprocess.run(  # noqa: S603 - argv is operator-supplied, never scenario-derived
                argv,
                input=payload,
                capture_output=True,
                text=True,
                timeout=timeout,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            return self._judgement(
                status=ResultStatus.ERROR, error=f"{type(exc).__name__}: {exc}"
            )

        metadata = {
            "command": argv[0],
            "exit_code": completed.returncode,
            "stderr": (completed.stderr or "")[:1000],
            "tool_version": self.config.get("tool_version"),
        }

        stdout = (completed.stdout or "").strip()
        if stdout:
            try:
                parsed = json.loads(stdout)
                return self._judgement(
                    status=parsed.get("verdict", ResultStatus.NOT_EVALUATED),
                    score=parsed.get("score"),
                    rationale=parsed.get("rationale"),
                    evaluator_metadata={**metadata, "raw": stdout[:2000]},
                )
            except json.JSONDecodeError:
                pass

        # Fall back to the exit code when the tool does not speak JSON.
        ok = completed.returncode == 0
        return self._judgement(
            status=ResultStatus.PASS if ok else ResultStatus.FAIL,
            score=1.0 if ok else 0.0,
            rationale=f"Tool exited with code {completed.returncode}.",
            evaluator_metadata={**metadata, "raw": stdout[:2000]},
        )


@register_evaluator
class ExternalHttpEvaluator(Evaluator):
    key = "external_http"
    kind = EvaluatorKind.EXTERNAL_TOOL
    label = "External validation service"
    description = "POSTs the result to a validation service and reads a JSON verdict."

    def evaluate(self, ctx: EvaluationContext) -> Judgement:
        url = self.config.get("url")
        if not url:
            return self._judgement(status=ResultStatus.NOT_EVALUATED, rationale="No URL configured.")
        try:
            with httpx.Client(timeout=float(self.config.get("timeout_seconds", 60))) as client:
                response = client.post(
                    url,
                    json={
                        "scenario": ctx.scenario,
                        "request": ctx.request,
                        "response": ctx.response,
                        "threshold": ctx.threshold,
                    },
                    headers=self.config.get("headers") or {},
                )
            response.raise_for_status()
            parsed = response.json()
        except Exception as exc:  # noqa: BLE001
            return self._judgement(status=ResultStatus.ERROR, error=f"{type(exc).__name__}: {exc}")

        return self._judgement(
            status=parsed.get("verdict", ResultStatus.NOT_EVALUATED),
            score=parsed.get("score"),
            rationale=parsed.get("rationale"),
            confidence=parsed.get("confidence"),
            evaluator_metadata={"service": url, "service_version": parsed.get("version")},
        )
