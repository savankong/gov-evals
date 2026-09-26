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

## Worked example: Acquisition Bench (demonstration)

`packs/bench-acquisition.yaml` and `packs/bench-acquisition-questions.yaml` are the
government's side of the table: 30 questions a GS-1102 contract specialist or
contracting officer meets across the lifecycle (pre-award, solicitation, award,
post-award, cross-cutting), with five criteria each. Five `task:boundary` questions
ask the assistant to do something inherently governmental (FAR 7.503) or to disclose
protected information; a good answer helps with the work and declines the decision.

The questions are model-drafted and unapproved, like GovCon Bench's. To show the whole
report before an expert has reviewed them, the demonstration project runs approved,
project-scoped copies of them end to end:

- Claude Haiku 4.5 and Claude Sonnet 5 answered every question closed-book through
  Claude Code (not the API). Claude Opus 5.5 judged every answer criterion by
  criterion, without knowing which model wrote it.
- Those responses are recordings in `apps/api/aegis/recordings/`, replayed through the
  ordinary engine by the `recorded` connector. A request that was not recorded is an
  error, never an invented answer. Latency, tokens and cost were not recorded and are
  reported as such.
- The calibration labels come from a simulated reviewer who is not an expert, written
  by an instance of the judge's own model without sight of its verdicts. The agreement
  figure therefore shows how the measurement works, not how far to trust the judge.

Every campaign in the project carries a `demonstration` statement, and the report
prints it at the top and in Limitations. Build it with `make bench-demo`, which writes
`docs/examples/acquisition-bench-report.md` and the data behind it. The API seeds the
same project at startup when `AEGIS_SEED_DEMO` or `AEGIS_SEED_BENCHMARK_DEMO` is on.
`scripts/build_acquisition_bench_recordings.py` rebuilds the recordings from raw
answers, verdicts and labels.

To turn the demonstration into a benchmark you can publish: an acquisition expert
approves the questions, the models are run live with a configured judge, and qualified
experts label the calibration set. Nothing in the code changes.

## Public pages

`/public/benchmarks` and `/public/benchmarks/{id}` need no login. A benchmark report
appears there only after someone with `report:generate` on its project presses
**Publish** on the report page (`POST /api/v1/benchmarks/{id}/publish`), and only
while it is marked UNCLASSIFIED. **Unpublish** takes it down. Both are audited.

The public page is the same report with three things removed: questions not
tagged `split:public` (they still count in the pass rates, but their wording,
criteria and answers stay private), anything that links into the app (result and
campaign ids, the project id), and the sample answer if its question is held out.
The demonstration seed publishes its own report when it creates it.

## What is not built yet

- **Multi-turn with a simulated user.** A condition where another model plays the
  user and answers the system's follow-up questions. Today a condition is a system
  version's configuration; there is no auditor model in the loop.
- **Web search as a condition.** It depends on the connector exposing a search
  tool. The condition label and the comparison already work.
- **Charts in the app.** The report is Markdown tables. The data behind it
  (`benchmark_data`) is structured for charting, and `make bench-demo` writes it out.
