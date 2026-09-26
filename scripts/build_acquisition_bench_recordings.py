"""Turn the Acquisition Bench demonstration's raw outputs into replay recordings.

Inputs, in one directory:

- answers-<model>.json   {scenario key: answer text}, one file per answering model
- judge-verdicts.json    {scenario key: {model id: {criterion id: {verdict, rationale}}}}
- demo-labels.json       {model id: {scenario key: {criterion id: verdict}}}

Outputs, in apps/api/aegis/recordings/: one recording per answering model, one
for the judge, and the demonstration labels. Each recording maps the exact
request the engine will send (system prompt and prompt) to the recorded text,
so a replay that drifts from what was recorded fails loudly instead of
answering something else.

    python scripts/build_acquisition_bench_recordings.py <input dir>
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "apps" / "api"))

from aegis.connectors.builtin import RECORDINGS_DIR, recording_key
from aegis.demo_bench import (
    ANSWER_SYSTEM_PROMPT,
    JUDGE,
    LABELS_RECORDING,
    MODELS,
)
from aegis.evaluators import EvaluationContext
from aegis.evaluators.model_based import (
    CRITERIA_SYSTEM_PROMPT,
    RubricCriteriaEvaluator,
)

QUESTIONS = ROOT / "packs" / "bench-acquisition-questions.yaml"
ANSWER_FILES = {
    "claude-haiku-4-5": "answers-haiku.json",
    "claude-sonnet-5": "answers-sonnet.json",
}
RECORDED_VIA = "Claude Code subagent, closed-book, September 2026"


def _write(name: str, doc: dict) -> None:
    RECORDINGS_DIR.mkdir(exist_ok=True)
    (RECORDINGS_DIR / f"{name}.json").write_text(json.dumps(doc, indent=1, sort_keys=True) + "\n")


def main(source: Path) -> int:
    scenarios = {s["key"]: s for s in yaml.safe_load(QUESTIONS.read_text())["scenarios"]}
    verdicts = json.loads((source / "judge-verdicts.json").read_text())
    judge = RubricCriteriaEvaluator({"evaluator": "rubric_criteria"})
    judge_responses: dict[str, dict] = {}

    for name, model_id, recording in MODELS:
        answers = json.loads((source / ANSWER_FILES[model_id]).read_text())
        missing = sorted(set(scenarios) - set(answers))
        if missing:
            raise SystemExit(f"{model_id} has no answer for {missing}")
        responses = {}
        for key, scenario in scenarios.items():
            prompt = scenario["input"]["prompt"]
            responses[recording_key(ANSWER_SYSTEM_PROMPT, prompt)] = {
                "scenario_key": key,
                "text": answers[key],
            }
            for criterion in scenario["criteria"]:
                verdict = verdicts[key][model_id][criterion["id"]]
                ctx = EvaluationContext(
                    scenario=scenario,
                    request={"prompt": prompt, "documents": []},
                    response={"text": answers[key]},
                )
                judge_prompt = judge._build_prompt(ctx, [criterion])
                judge_responses[recording_key(CRITERIA_SYSTEM_PROMPT, judge_prompt)] = {
                    "scenario_key": key,
                    "answered_by": model_id,
                    "criterion": criterion["id"],
                    "text": json.dumps(
                        {"criteria": [{"id": criterion["id"], **verdict}]}
                    ),
                }
        _write(
            recording,
            {
                "model": model_id,
                "display_name": name,
                "recorded_via": RECORDED_VIA,
                "system_prompt": ANSWER_SYSTEM_PROMPT,
                "responses": responses,
            },
        )

    _write(
        JUDGE["parameters"]["recording"],
        {
            "model": JUDGE["model_version"],
            "display_name": JUDGE["model_name"],
            "recorded_via": RECORDED_VIA + "; answers shown without the answering model's name",
            "system_prompt": CRITERIA_SYSTEM_PROMPT,
            "responses": judge_responses,
        },
    )
    _write(
        LABELS_RECORDING,
        {
            "recorded_via": "Written by the AI assistant that built the demonstration; "
            "simulated reviewer, not an expert",
            "labels": json.loads((source / "demo-labels.json").read_text()),
        },
    )
    print(f"{len(MODELS)} answer recordings, {len(judge_responses)} judge responses written.")
    return 0


if __name__ == "__main__":
    sys.exit(main(Path(sys.argv[1])))
