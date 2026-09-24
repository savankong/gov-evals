"""Model-based evaluators (LLM as judge).

Section 20 is explicit: no model-based evaluation is presented as ground truth.
Every judgement here carries the judge model, its version, the exact rubric and
prompt used, the sampling temperature and the judge's own stated confidence, so
a reader can weigh it against the deterministic and human evidence beside it.
"""

from __future__ import annotations

import json
import re

from ..enums import EvaluatorKind, ResultStatus
from .base import EvaluationContext, Evaluator, Judgement, register_evaluator

JUDGE_SYSTEM_PROMPT = """You are an evaluation judge supporting a government AI \
test and evaluation activity. You assess one system output against one rubric.

Rules:
- Judge only what the rubric asks about. Ignore style unless the rubric mentions it.
- Base the judgement on the supplied material. Do not use outside knowledge to \
fill gaps in the source material.
- If the material is insufficient to judge, say so and return "not_evaluated".
- Return a single JSON object and nothing else:
  {"verdict": "pass" | "warning" | "fail" | "not_evaluated",
   "score": <number between 0 and 1>,
   "rationale": "<two sentences at most>",
   "confidence": <number between 0 and 1>}"""


@register_evaluator
class LlmJudgeEvaluator(Evaluator):
    key = "llm_judge"
    kind = EvaluatorKind.MODEL_BASED
    label = "Model-based judge (rubric)"
    description = (
        "A separate model scores the output against a written rubric. "
        "Advisory evidence: pair it with a deterministic or human judgement."
    )

    def evaluate(self, ctx: EvaluationContext) -> Judgement:
        if ctx.judge is None:
            return self._judgement(
                status=ResultStatus.NOT_EVALUATED,
                rationale=(
                    "No judge model is configured for this campaign. Configure one on the "
                    "campaign, or rely on the deterministic and human evaluators."
                ),
            )

        rubric = (
            self.config.get("rubric")
            or ctx.scenario.get("rubric")
            or "Does the output accomplish the task correctly and completely?"
        )
        prompt = self._build_prompt(ctx, rubric)

        try:
            raw = ctx.judge(JUDGE_SYSTEM_PROMPT, prompt, self.config)
        except Exception as exc:
            return self._judgement(
                status=ResultStatus.ERROR,
                error=f"{type(exc).__name__}: {exc}",
                rationale="The judge model could not be reached.",
            )

        text = (raw.get("text") or "").strip()
        parsed = self._parse(text)
        metadata = {
            "judge_model": raw.get("model"),
            "judge_model_version": raw.get("model_version"),
            "judge_connector": raw.get("connector"),
            "temperature": raw.get("temperature"),
            "rubric": rubric,
            "prompt": prompt,
            "raw_response": text[:2000],
            # Carried so the UI can label this evidence as advisory everywhere.
            "advisory": True,
        }

        if parsed is None:
            return self._judgement(
                status=ResultStatus.ERROR,
                rationale="The judge model did not return a parseable verdict.",
                evaluator_metadata=metadata,
            )

        verdict = str(parsed.get("verdict", "")).lower()
        if verdict not in (ResultStatus.PASS, ResultStatus.WARNING, ResultStatus.FAIL, ResultStatus.NOT_EVALUATED):
            verdict = ResultStatus.NOT_EVALUATED

        score = parsed.get("score")
        try:
            score = max(0.0, min(1.0, float(score))) if score is not None else None
        except (TypeError, ValueError):
            score = None

        confidence = parsed.get("confidence")
        try:
            confidence = max(0.0, min(1.0, float(confidence))) if confidence is not None else None
        except (TypeError, ValueError):
            confidence = None

        # A low-confidence judgement is downgraded rather than reported as a
        # clean verdict, so that uncertainty stays visible (section 71).
        floor = float(self.config.get("min_confidence", 0.0))
        if confidence is not None and confidence < floor and verdict == ResultStatus.PASS:
            verdict = ResultStatus.WARNING
            metadata["downgraded_for_low_confidence"] = True

        return self._judgement(
            status=verdict,
            score=score,
            confidence=confidence,
            rationale=parsed.get("rationale"),
            evaluator_metadata=metadata,
        )

    def _build_prompt(self, ctx: EvaluationContext, rubric: str) -> str:
        parts = [f"RUBRIC:\n{rubric}\n"]
        if ctx.scenario.get("context"):
            parts.append(f"SCENARIO CONTEXT:\n{ctx.scenario['context']}\n")
        parts.append(f"TASK GIVEN TO THE SYSTEM:\n{ctx.request.get('prompt', '')}\n")

        documents = ctx.request.get("documents") or []
        if documents and self.config.get("include_sources", True):
            rendered = "\n\n".join(
                f"[{d.get('source_id') or f'source {i + 1}'}] {(d.get('text') or '')[:1500]}"
                for i, d in enumerate(documents[:8])
            )
            parts.append(f"SOURCE MATERIAL SUPPLIED TO THE SYSTEM:\n{rendered}\n")

        expected = ctx.scenario.get("expected_behavior") or []
        if expected:
            parts.append("EXPECTED BEHAVIOUR:\n" + "\n".join(f"- {e}" for e in expected) + "\n")
        prohibited = ctx.scenario.get("prohibited_behavior") or []
        if prohibited:
            parts.append("PROHIBITED BEHAVIOUR:\n" + "\n".join(f"- {p}" for p in prohibited) + "\n")
        if ctx.scenario.get("reference_answer") and self.config.get("include_reference", True):
            parts.append(f"REFERENCE ANSWER:\n{ctx.scenario['reference_answer']}\n")

        parts.append(f"SYSTEM OUTPUT TO JUDGE:\n{ctx.output_text[:6000]}")
        return "\n".join(parts)

    @staticmethod
    def _parse(text: str) -> dict | None:
        if not text:
            return None
        match = re.search(r"\{.*\}", text, re.S)
        if not match:
            return None
        try:
            value = json.loads(match.group(0))
        except json.JSONDecodeError:
            return None
        return value if isinstance(value, dict) else None


CRITERIA_SYSTEM_PROMPT = """You are an evaluation judge supporting a government AI \
test and evaluation activity. You check one system output against a list of \
criteria, each on its own.

Rules:
- Judge each criterion independently. One failing does not decide another.
- A criterion passes only if the output clearly meets it. Partial or implied is a fail.
- Judge only what each criterion asks about. Ignore style unless it says otherwise.
- If you cannot tell from the output, return "not_evaluated" for that criterion.
- Return a single JSON object and nothing else:
  {"criteria": [{"id": "<criterion id>",
                 "verdict": "pass" | "fail" | "not_evaluated",
                 "rationale": "<one sentence>"}]}"""

_CRITERION_VERDICTS = (ResultStatus.PASS, ResultStatus.FAIL, ResultStatus.NOT_EVALUATED)


@register_evaluator
class RubricCriteriaEvaluator(Evaluator):
    """Scores an output against a scenario's criteria, one verdict per criterion.

    This is the grading a published benchmark needs: a pass rate over criteria,
    not a single holistic verdict per answer. It stays advisory evidence like
    every model judgement, and its agreement with qualified experts on the same
    criteria is measured and reported alongside it rather than assumed.

    A criterion the judge does not return a verdict for is not_evaluated. It is
    left out of the pass rate's denominator and reported, never counted as met.
    """

    key = "rubric_criteria"
    kind = EvaluatorKind.MODEL_BASED
    label = "Model-based judge (per criterion)"
    description = (
        "A separate model checks the output against each of the scenario's criteria. "
        "Reports criteria passed out of criteria judged. Advisory evidence."
    )

    def evaluate(self, ctx: EvaluationContext) -> Judgement:
        criteria = [c for c in ctx.scenario.get("criteria") or [] if c.get("id")]
        if not criteria:
            return self._judgement(
                status=ResultStatus.NOT_EVALUATED,
                rationale="This scenario states no criteria, so there is nothing to check.",
            )
        if ctx.judge is None:
            return self._judgement(
                status=ResultStatus.NOT_EVALUATED,
                rationale=(
                    "No judge model is configured for this campaign, so no criterion "
                    "was checked."
                ),
            )

        # One call per criterion keeps the verdicts independent; one call for
        # all of them is cheaper. The choice is recorded with the judgement.
        per_criterion = self.config.get("mode", "per_criterion") == "per_criterion"
        batches = [[c] for c in criteria] if per_criterion else [criteria]

        verdicts: dict[str, dict] = {}
        raw_responses: list[str] = []
        judge_info: dict = {}
        for batch in batches:
            prompt = self._build_prompt(ctx, batch)
            try:
                raw = ctx.judge(CRITERIA_SYSTEM_PROMPT, prompt, self.config)
            except Exception as exc:
                return self._judgement(
                    status=ResultStatus.ERROR,
                    error=f"{type(exc).__name__}: {exc}",
                    rationale="The judge model could not be reached.",
                )
            judge_info = raw
            text = (raw.get("text") or "").strip()
            raw_responses.append(text[:2000])
            for item in self._parse(text):
                cid = str(item.get("id", ""))
                if cid in {c["id"] for c in batch}:
                    verdicts[cid] = item

        rows = []
        for criterion in criteria:
            item = verdicts.get(criterion["id"])
            verdict = str((item or {}).get("verdict", "")).lower()
            if verdict not in _CRITERION_VERDICTS:
                verdict = ResultStatus.NOT_EVALUATED
            rows.append(
                {
                    "id": criterion["id"],
                    "text": criterion.get("text"),
                    "verdict": verdict,
                    "rationale": (item or {}).get("rationale")
                    or ("The judge returned no verdict for this criterion." if item is None else None),
                }
            )

        passed = sum(r["verdict"] == ResultStatus.PASS for r in rows)
        failed = sum(r["verdict"] == ResultStatus.FAIL for r in rows)
        judged = passed + failed

        if judged == 0:
            status = ResultStatus.NOT_EVALUATED
        elif failed:
            status = ResultStatus.FAIL
        elif judged < len(rows):
            # Everything judged passed, but not everything was judged. An
            # unchecked criterion is not a met one.
            status = ResultStatus.NOT_EVALUATED
        else:
            status = ResultStatus.PASS

        return self._judgement(
            status=status,
            score=(passed / judged) if judged else None,
            rationale=f"{passed} of {len(rows)} criteria met ({len(rows) - judged} not judged).",
            evaluator_metadata={
                "criteria": rows,
                "criteria_total": len(rows),
                "criteria_judged": judged,
                "criteria_passed": passed,
                "mode": "per_criterion" if per_criterion else "batched",
                "judge_model": judge_info.get("model"),
                "judge_model_version": judge_info.get("model_version"),
                "judge_connector": judge_info.get("connector"),
                "temperature": judge_info.get("temperature"),
                "raw_responses": raw_responses,
                "advisory": True,
                # A calibration run exists so experts can label the same
                # criteria; it measures the judge and is kept out of scores.
                "calibration": bool(self.config.get("calibration", False)),
            },
        )

    def _build_prompt(self, ctx: EvaluationContext, criteria: list[dict]) -> str:
        parts = []
        if ctx.scenario.get("context"):
            parts.append(f"SCENARIO CONTEXT:\n{ctx.scenario['context']}\n")
        parts.append(f"QUESTION GIVEN TO THE SYSTEM:\n{ctx.request.get('prompt', '')}\n")
        documents = ctx.request.get("documents") or []
        if documents:
            rendered = "\n\n".join(
                f"[{d.get('source_id') or f'source {i + 1}'}] {(d.get('text') or '')[:1500]}"
                for i, d in enumerate(documents[:8])
            )
            parts.append(f"SOURCE MATERIAL SUPPLIED TO THE SYSTEM:\n{rendered}\n")
        parts.append(
            "CRITERIA:\n" + "\n".join(f"- [{c['id']}] {c.get('text', '')}" for c in criteria) + "\n"
        )
        parts.append(f"SYSTEM OUTPUT TO JUDGE:\n{ctx.output_text[:8000]}")
        return "\n".join(parts)

    @staticmethod
    def _parse(text: str) -> list[dict]:
        match = re.search(r"\{.*\}", text or "", re.S)
        if not match:
            return []
        try:
            value = json.loads(match.group(0))
        except json.JSONDecodeError:
            return []
        items = value.get("criteria") if isinstance(value, dict) else None
        return [i for i in items if isinstance(i, dict)] if isinstance(items, list) else []


@register_evaluator
class LlmPairwiseEvaluator(Evaluator):
    """Compares an output against a reference, reporting which is better.

    Useful for regression review, where the question is whether behaviour
    changed rather than whether it is correct in absolute terms.
    """

    key = "llm_pairwise"
    kind = EvaluatorKind.MODEL_BASED
    label = "Model-based pairwise comparison"
    description = "Judges the output against a baseline output for the same scenario."

    def evaluate(self, ctx: EvaluationContext) -> Judgement:
        baseline = ctx.response.get("baseline_text")
        if not baseline:
            return self._judgement(
                status=ResultStatus.NOT_EVALUATED, rationale="No baseline output supplied."
            )
        if ctx.judge is None:
            return self._judgement(
                status=ResultStatus.NOT_EVALUATED, rationale="No judge model configured."
            )

        rubric = self.config.get("rubric") or ctx.scenario.get("rubric") or "Which output better accomplishes the task?"
        prompt = (
            f"RUBRIC:\n{rubric}\n\nTASK:\n{ctx.request.get('prompt', '')}\n\n"
            f"OUTPUT A (baseline):\n{baseline[:4000]}\n\n"
            f"OUTPUT B (candidate):\n{ctx.output_text[:4000]}\n\n"
            'Return {"verdict": "pass" if B is at least as good as A else "fail", '
            '"score": <0-1 preference for B>, "rationale": "...", "confidence": <0-1>}'
        )
        try:
            raw = ctx.judge(JUDGE_SYSTEM_PROMPT, prompt, self.config)
        except Exception as exc:
            return self._judgement(status=ResultStatus.ERROR, error=str(exc))

        parsed = LlmJudgeEvaluator._parse(raw.get("text") or "")
        if parsed is None:
            return self._judgement(
                status=ResultStatus.ERROR, rationale="Judge returned no parseable verdict."
            )
        return self._judgement(
            status=parsed.get("verdict", ResultStatus.NOT_EVALUATED),
            score=parsed.get("score"),
            confidence=parsed.get("confidence"),
            rationale=parsed.get("rationale"),
            evaluator_metadata={
                "judge_model": raw.get("model"),
                "rubric": rubric,
                "prompt": prompt,
                "advisory": True,
            },
        )
