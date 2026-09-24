# Producing a benchmark report

A benchmark report answers a narrow question in public: on this set of questions,
how often did each model meet the criteria experts wrote for them, under which
conditions, and how far can the grading be trusted. This page works backwards from
that report to what has to exist for Aegis to produce it.

The worked example is **GovCon Bench**: questions a small business asks when it
tries to win and perform federal contracts. It lives in `packs/bench-govcon.yaml`
(the evaluations) and `packs/bench-govcon-questions.yaml` (the questions).

## What the report contains, and where each part comes from

| Report section | Computed from | Built in |
| --- | --- | --- |
| Results: pass rate per model and condition | Criterion verdicts on every result | `rubric_criteria` evaluator, `aegis/benchmark.py` |
| Detail: criteria met/judged, not judged, cost per test, latency | Results' verdicts, token counts, latency; prices on the system version | `aegis/benchmark.py` |
| Effect of conditions | Pass rates paired by model across conditions | `_condition_effects` |
| Breakdowns by topic and phase | Scenario tags of the form `name:value` | `facets` in `aegis/benchmark.py` |
| Grading and agreement with experts | Judge verdicts vs. qualified experts' per-criterion labels | `judge_alignment`, the review screen |
| Example | One graded answer with mixed verdicts | `_example` |
| Methodology | Questions, criteria, splits, packs, approvers, required expertise | `_dataset` |
| Limitations | Thin facets, undecided criteria, unpriced tests, unmeasured judge | `reports/benchmark.py` |

Generate it with `POST /api/v1/projects/{id}/reports` and
`{"kind": "benchmark", "campaign_ids": [...]}`. It is stored with a SHA-256 like
every other report.

## The rules the numbers follow

- **Pass rate = criteria met ÷ criteria judged.** A criterion the judge did not
  decide is excluded from both and reported separately. It is never counted as met.
- **Missing is not zero.** A test with no declared price has no cost, and the
  report says *not recorded*.
- **The judge is measured, not trusted.** Its agreement with qualified experts is
  published next to its scores. With no expert labels the report says the
  agreement is *not measured* and that the scores are the judge's.
- **Calibration runs measure the judge and are not scores.** Their judgements
  carry `calibration: true` and are left out of every pass rate.
- **No composite score.** The pass rate is one measurement on one question set.

## The process

### 1. Write the questions (experts)

Each question is a scenario with:

- `input.prompt`: the question as a real user would ask it.
- `criteria`: about five checks a good answer must meet, each with a stable `id`.
  Each should be something two experts would mark the same way. "Good answer"
  fails that test. "States that the deadline is five business days" passes.
- Tags: `govcon-bench`, a `topic:` and a `phase:` (the report's breakdowns),
  `split:public` or `split:private`, and `calibration` on the subset experts will
  label.
- `required_expertise`: who is qualified to judge it.

Model-drafted questions carry `generated: true` and `approved: false`. The runner
will not select an unapproved scenario, so nothing a model wrote runs until an
expert has reviewed, corrected and approved it. The seed set of 24 questions is in
that state.

**Private questions do not go in this repository.** Put them in an organisation
pack directory (`AEGIS_PACK_DIR`) that is never published, tagged `split:private`.

### 2. Define the conditions (program)

Each model under each condition is its own system version. The condition is
`parameters.condition`, for example `baseline`, `web_search`, `multi_turn`. Put
prices on the system version as `price_per_mtok_in` and `price_per_mtok_out`
(US dollars per million tokens) if the report should show cost.

### 3. Run the campaign (platform)

Run `govcon-bench-criteria` and `govcon-bench-calibration` against every system
version, with a judge model configured on the campaign. Record which judge model
you chose and why, because the report names it.

### 4. Label the calibration set (experts)

Calibration results land in the review queue. A qualified expert labels every
criterion met, not met or can't tell. The judge's verdicts are not shown, so the
labels are independent of the thing they measure. With `require_expertise` on,
labels from outside the discipline are recorded but not counted.

Aim for at least 100 labelled criteria before publishing an agreement figure. The
report calls anything fewer *indicative*.

### 5. Generate, review and publish (program)

Generate the report and read its Limitations section first. The report states
measurements only. The publishing program writes the interpretation and
recommendations and publishes them alongside it.

## What is not built yet

- **Multi-turn with a simulated user.** A condition where another model plays the
  user and answers the system's follow-up questions. Today a condition is a system
  version's configuration; there is no auditor model in the loop.
- **Web search as a condition.** It depends on the connector exposing a search
  tool. The condition label and the comparison already work.
- **Charts.** The report is Markdown tables. The data behind it
  (`benchmark_data`) is structured for charting.
