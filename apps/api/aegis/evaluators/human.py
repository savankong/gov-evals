"""Human evaluators.

A human evaluation does not resolve when the run executes. The result is held
at `pending_human` until a reviewer submits a score, which is why
`pending_human` is a first-class status rather than an error: the platform
shows that the judgement is outstanding instead of inferring one.
"""

from __future__ import annotations

from ..enums import EvaluatorKind, ResultStatus
from .base import EvaluationContext, Evaluator, Judgement, register_evaluator


@register_evaluator
class HumanReviewEvaluator(Evaluator):
    key = "human_review"
    kind = EvaluatorKind.HUMAN
    label = "Human review against a rubric"
    description = "Holds the result open until a qualified reviewer scores it."

    def evaluate(self, ctx: EvaluationContext) -> Judgement:
        rubric_key = self.config.get("rubric_key")
        reviews = [
            r
            for r in ctx.human_reviews
            if not rubric_key or r.get("rubric_key") == rubric_key
        ]
        required = int(self.config.get("required_reviews", 1))

        if len(reviews) < required:
            return self._judgement(
                status=ResultStatus.PENDING_HUMAN,
                rationale=(
                    f"Awaiting human review ({len(reviews)} of {required} submitted)."
                ),
                evaluator_metadata={
                    "rubric_key": rubric_key,
                    "rubric": self.config.get("rubric"),
                    "required_reviews": required,
                    "submitted_reviews": len(reviews),
                },
            )

        statuses = [r.get("status", ResultStatus.PASS) for r in reviews]
        scores = [r["score"] for r in reviews if r.get("score") is not None]
        mean_score = sum(scores) / len(scores) if scores else None

        # Inter-rater agreement, reported whenever more than one reviewer scored
        # the same result (section 20).
        agreement = None
        if len(reviews) > 1:
            agreement = statuses.count(max(set(statuses), key=statuses.count)) / len(statuses)

        failed = statuses.count(ResultStatus.FAIL)
        warned = statuses.count(ResultStatus.WARNING)
        if failed:
            status = ResultStatus.FAIL
        elif warned:
            status = ResultStatus.WARNING
        else:
            status = ResultStatus.PASS

        return self._judgement(
            status=status,
            score=mean_score,
            rationale="; ".join(filter(None, (r.get("comments") for r in reviews)))[:500] or None,
            evaluator_metadata={
                "rubric_key": rubric_key,
                "reviewers": [r.get("reviewer_label") for r in reviews],
                "inter_rater_agreement": agreement,
                "review_count": len(reviews),
                "statuses": statuses,
            },
        )


@register_evaluator
class TrustCalibrationEvaluator(Evaluator):
    """Compares operator confidence against actual system correctness.

    This is the measurement behind the AI-accuracy-versus-human-trust view in
    section 26: it identifies over-reliance (confident acceptance of a wrong
    output) and under-reliance (rejection of a correct one).
    """

    key = "trust_calibration"
    kind = EvaluatorKind.HUMAN
    label = "Operator trust calibration"
    description = "Measures whether operator confidence tracks actual system accuracy."

    def evaluate(self, ctx: EvaluationContext) -> Judgement:
        reviews = ctx.human_reviews
        if not reviews:
            return self._judgement(
                status=ResultStatus.PENDING_HUMAN,
                rationale="Awaiting operator confidence ratings.",
            )

        system_correct = ctx.response.get("system_correct")
        if system_correct is None:
            return self._judgement(
                status=ResultStatus.NOT_EVALUATED,
                rationale="Ground truth for this scenario is not recorded, so calibration cannot be computed.",
            )

        confidences = [r["confidence"] for r in reviews if r.get("confidence") is not None]
        if not confidences:
            return self._judgement(
                status=ResultStatus.PENDING_HUMAN, rationale="Reviews carry no confidence ratings."
            )

        mean_confidence = sum(confidences) / len(confidences)
        # Calibration error: distance between stated confidence and whether the
        # system was in fact correct.
        error = abs(mean_confidence - (1.0 if system_correct else 0.0))
        tolerance = float(self.config.get("max_calibration_error", 0.3))

        if error <= tolerance:
            status, note = ResultStatus.PASS, "Operator confidence tracked system accuracy."
        elif not system_correct and mean_confidence > 0.5:
            status, note = ResultStatus.FAIL, "Over-reliance: operators were confident in an incorrect output."
        elif system_correct and mean_confidence < 0.5:
            status, note = ResultStatus.WARNING, "Under-reliance: operators doubted a correct output."
        else:
            status, note = ResultStatus.WARNING, "Operator confidence was poorly calibrated."

        return self._judgement(
            status=status,
            score=round(1 - error, 4),
            rationale=f"{note} Mean confidence {mean_confidence:.2f}; system was {'correct' if system_correct else 'incorrect'}.",
            evaluator_metadata={
                "mean_confidence": mean_confidence,
                "system_correct": system_correct,
                "calibration_error": round(error, 4),
                "tolerance": tolerance,
            },
        )
