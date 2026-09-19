# Evaluation model

## Four layers

Evaluations are organised across CDAO's four AI T&E areas. The platform carries
the layer on each evaluation so coverage gaps are visible rather than implied.

| Layer | Question |
| --- | --- |
| Model T&E | Does the model do the task? |
| Human Systems Integration T&E | Can operators use it appropriately? |
| Systems Integration T&E | Does the whole capability work? |
| Operational T&E | Does it accomplish the mission in realistic conditions? |

## Eleven domains

Every campaign rolls up into these, and every one of them appears on the readiness
view whether or not it was tested:

Performance · Reliability · Robustness · Security · Safety · Responsible AI ·
Human Factors · Mission Effectiveness · Integration · Resilience · Traceability

## Evaluators

An evaluation carries a list of evaluators and an explicit aggregation rule,
because no single evaluator should be decisive.

**Deterministic.** Same input, same judgement, every time. Citation validity,
prohibited patterns, structured output, latency, tool authorisation, retrieval
recall and precision, sensitive disclosure, attack success. These are the strongest
single form of evidence the platform produces. Where a claim matters, a
deterministic check should back the model-based one rather than the reverse.

**Model-based.** Another model scores the output against a written rubric. Every
such judgement records the judge model, its version, the exact rubric and prompt,
the sampling temperature and the judge's own stated confidence, and is labelled
advisory wherever it appears. A pass returned with confidence below the configured
floor is downgraded to a warning rather than reported clean.

**Human.** Holds the result at `pending_human` until a qualified reviewer scores
it. Inter-rater agreement is reported when more than one reviewer scored the same
result. The platform does not infer a human judgement that has not been made.

**External tool.** A static analyser, security scanner, simulation or domain
validator, invoked over a command or an HTTP endpoint, with its identity and
version recorded.

### Aggregation

| Rule | Behaviour |
| --- | --- |
| `all_must_pass` | Any failure fails; outstanding human review keeps the result open |
| `worst_case` | Most severe status wins — the default for safety and security, where one breach is a breach |
| `majority` | Simple majority of judgements that reached a verdict |
| `weighted` | Weighted mean of scores |
| `any_pass` | One supporting judgement suffices — rarely appropriate |

If every judgement is `not_evaluated`, so is the result. Nothing is inferred.

## Thresholds

A threshold belongs to the customer's evaluation plan, never to the product.

A library evaluation ships a suggested default. When a plan is drafted, that
default is copied in and marked `library_default_unconfirmed`. A campaign built
from the plan ignores any threshold still carrying that marker, and the run reports
its measurements with a verdict of `NOT EVALUATED`. A plan cannot be approved while
any threshold is unconfirmed.

Where the mission profile states a requirement in measurable terms — a latency
budget, for instance — it is carried into the draft so a tester does not retype it.
It still arrives unconfirmed.

## Why a run reports NOT EVALUATED

Five distinct situations, each reported differently rather than collapsed:

1. No threshold is set, so there is no bar to measure against.
2. The selector matched no approved scenario.
3. Scenarios ran but no evaluator reached a judgement — commonly a model judge
   with no judge model configured.
4. A threshold names a metric that was not measured.
5. Human review is outstanding.

None of these is a pass, and a criterion like `max_failures: 0` cannot be satisfied
by a run that judged nothing.

## Scenarios

A scenario states its input, the behaviour expected of the system, the behaviour
prohibited, and the rubric a judge should answer. Selectors require **all** listed
tags by default: an evaluation asking for `[red-team, data_poisoning]` must not
collect every red-team scenario and attribute unrelated failures to itself. Pass
`tags_match: any` where a union is genuinely intended.

Generated scenarios are drafts. They carry `approved: false` and stay out of every
run until a person reads one and accepts it as a fair test.

## Red teaming

The attack library is data. Each technique names its vector (prompt, document,
tool output), its payload, the indicators that show the objective was met, and a
recommended mitigation. Attacks are crossed with the mission's own tasks, because
the same injection against a contracting task and an intelligence task are
different tests with different consequences.

An adaptive campaign follows attack → evaluate → learn → mutate → retest against an
explicit budget, and records every attempt including the ones that failed. When no
variant succeeds, the report says:

> No variant succeeded within N attempts. This bounds the result to the techniques
> and budget used; it is not evidence that the system is resistant to all variants
> of this technique.

That wording matters in an assurance case.

## Findings and assurance

A failure becomes a finding, clustered by the evaluator that rejected it, with the
reproduction rate recorded: `3 of 9 executions reproduced this failure` is a
different fact from `1 of 200`.

An assurance case decomposes a deployment claim into subclaims by domain, each
carrying the evidence that supports it, the evidence that counters it, and its
known limitations. Evidence takes one of three stances — supports, counters, or
inconclusive — because a run that reached no judgement is neither. A claim backed
partly by passing runs and partly by unevaluated ones is partially supported, not
supported.

A case is scoped to one system version. Residual risk is accepted by a named
authority; the platform records the decision and never makes it.
