# Requirement traceability

What is built, what is partial, and what is not. Ordered by the PRD's own sections
so a reviewer can walk it.

Legend: **Built** works end to end and is covered by tests · **Partial** works with
a stated limit · **Not built** is absent.

## P0 — the MVP (PRD section 58)

| # | Requirement | State | Where |
| --- | --- | --- | --- |
| 1 | Organizations / projects | Built | `routers/tenancy.py` |
| 2 | Mission Profile | Built | `models.MissionProfile`, drives plan generation |
| 3 | System registry | Built | `routers/systems.py`, immutable fingerprinted versions |
| 4 | OpenAI-compatible connector | Built | `connectors/builtin.py` |
| 5 | Generic REST connector | Built | JSON-path response mapping |
| 6 | Dataset upload | Built | JSONL, JSON, CSV, TSV, text, with quality analysis |
| 7 | Scenario library | Built | 19 shipped scenarios across three packs |
| 8 | Evaluation library | Built | 29 evaluations across four packs |
| 9 | Deterministic evaluators | Built | 16 |
| 10 | LLM-as-judge evaluator | Built | Records judge model, rubric, prompt, temperature |
| 11 | Human evaluator | Built | Holds results at `pending_human`; inter-rater agreement |
| 12 | Batch evaluation runner | Built | `runner/engine.py` |
| 13 | Basic red-team pack | Built | 15 techniques crossed with mission tasks |
| 14 | RAG evaluation | Built | Retrieval and generation measured separately |
| 15 | Findings | Built | Clustered by failing evaluator, reproduction rate recorded |
| 16 | Evaluation dashboard | Built | Per-dimension readiness; no composite score |
| 17 | Model comparison | Built | Identical conditions, no winner column |
| 18 | Regression comparison | Built | Matched on (evaluation, system version) |
| 19 | Evidence storage | Built | File or S3-compatible, SHA-256 digests |
| 20 | Report generation | Built | Five kinds, hashed, downloadable |
| 21 | Audit logs | Built | Hash-chained, tamper-evident, verifiable |
| 22 | API | Built | 82 paths, 102 operations; the UI uses no private path |
| 23 | Docker deployment | Built | Compose, single node and scaled profile |
| 24 | No mandatory telemetry | Built | Off by default; state shown on `/health` |

## P1 (PRD section 59)

| Requirement | State | Note |
| --- | --- | --- |
| Assurance case builder | Built | Drafts from evidence; three evidence stances; scoped to one system version |
| Continuous evaluation | Partial | Triggers are modelled and fire on demand via the API. **No scheduler runs cron expressions** — an external scheduler must call the fire endpoint. |
| CI/CD integration | Built | CLI with distinct exit codes, including 3 for undetermined |
| AI agent evaluation | Built | Tool authorisation, loops, unauthorised actions, from the execution trace |
| Advanced red teaming | Built | Adaptive mutate-and-retest with an explicit budget and an honest null result |
| Framework mapping | Built | Five frameworks, 35 references; nothing ships claimable |
| Responsible AI pack | Built | Seven evaluations mapped to CDAO and NIST topics |
| CAC/PIV authentication | Partial | Accepts a verified subject from a terminating proxy. The platform does not validate certificate chains, by design. |
| Disconnected deployment | Built | SQLite, file evidence, inline queue, deny-egress policy, offline target |
| Systems integration testing | Partial | Latency, retrieval, tool authorisation and interoperability through the generic REST adapter. No infrastructure failover testing. |
| Evaluator plugins | Built | `@register_evaluator` |
| Scenario generation | Built | Deterministic mission expansion and model-assisted; both produce unapproved drafts |
| Risk register | Built | Customer-defined scoring matrix; acceptance records the authority |

## P2 (PRD section 60)

| Requirement | State | Note |
| --- | --- | --- |
| Human Systems Integration studies | Partial | `HumanStudySession` is modelled and trust calibration is computed and visualised. No study-execution workflow. |
| Operational evaluation workflows | Partial | The layer, domains and scenarios exist. No dedicated operational test workflow. |
| Simulation integration | Not built | The external-tool evaluator is the hook. |
| Evaluation marketplace | Not built | Packs carry publisher, version and provenance; there is no distribution or signing. |
| Multimodal evaluation | Not built | The dataset model accepts a modality; no multimodal evaluators. |
| Computer vision evaluation | Not built | — |
| Predictive model evaluation | Not built | — |
| Autonomous system evaluation | Not built | The `autonomy` system kind exists; no evaluators. |
| Federated evaluation | Not built | — |
| Cross-domain support | Not built | — |

## Product principles (PRD sections 70–73)

These are the ones worth checking, because they are easy to claim and easy to
violate quietly.

| Principle | How it is enforced | Test |
| --- | --- | --- |
| No magic number (§70) | No composite score exists in any model, endpoint or view. Campaigns summarise per domain. | `test_full_workflow` asserts all eleven domains appear |
| Unknown is a valid result (§71) | `not_evaluated` is a first-class status. A run that judged nothing returns it regardless of threshold. Gates report undetermined. | `test_nothing_scoreable_never_passes_vacuously`, `test_unmeasured_criterion_is_undetermined_not_a_pass` |
| Evidence over claims (§72) | Each result stores request, response, trace, per-evaluator judgements and a digest, with an endpoint that returns all of it. | `test_executes_and_stores_evidence`, `test_results_are_hashed` |
| Evaluation is continuous (§73) | The evaluated object is system + version + mission + environment + time. Versions are immutable; triggers re-run suites; reports state that a change invalidates results. | `test_records_reproducibility` |
| Thresholds are the customer's (§34) | Library defaults arrive unconfirmed and are ignored until confirmed. A plan cannot be approved while any remain. | `test_plan_cannot_be_approved_with_unconfirmed_thresholds` |
| Model judges are not ground truth (§20) | Every model judgement carries judge provenance and an advisory flag, and is badged in the UI. | `test_records_judge_provenance` |
| No compliance claims (§37) | Every framework reference installs with `compliance_claimable: false`. | `test_framework_mappings_never_claim_compliance` |
| Generated scenarios need approval (§17) | Drafts carry `approved: false`; the runner selects only approved scenarios. | `test_unapproved_scenarios_never_run` |

## Deliberate omissions

Things the PRD lists that were **not** built, said plainly:

- **No scheduler.** Continuous triggers fire through the API. Running them on a
  cron expression needs an external scheduler. Building an in-process scheduler
  into a system that must survive air-gapped restarts deserved more thought than
  this iteration allowed.
- **No marketplace.** Packs carry the provenance and versioning a marketplace would
  need, but distribution, signing and trust are unsolved here and doing them badly
  would be worse than not doing them.
- **No non-text modality evaluators.** Repeated here because the data model
  accepting a modality is easy to mistake for support.

## Supply chain

| Requirement | State | Where |
| --- | --- | --- |
| SBOM | Built | CycloneDX per component in CI (`sbom` job) and per image at deploy. `scripts/check_sbom.py` fails a bill of materials that resolved nothing, carries unnamed components, or was produced by a scanner pointed at the wrong directory. |
| Artifact signing | Partial | Both images are signed by digest with cosign, keyless through the workflow's GitHub OIDC identity, and carry a CycloneDX attestation. The deploy job verifies signature and attestation against a pinned certificate identity **before** rolling out, so a failure stops the deployment. |

Two limits, because they are the difference between a control and a ritual:

**The signature does not yet cover the running container.** `.do/app.yaml`
sources its components from GitHub, so App Platform rebuilds from the
repository and runs its own output. The signed images are an attested artifact
of record for the commit, not the artifact serving traffic. Closing that gap
means pointing the spec at `image:` with the verified digest, which needs a
paid container registry.

**This has now been exercised against a real registry.** On 19 September 2026,
commit `f874391`, both images were pushed to DigitalOcean Container Registry,
signed by digest, attested with a CycloneDX SBOM, and verified against the
pinned workflow identity before the rollout step ran. `scripts/validate_packs.py`
asserts the shape of that pipeline — it fails CI if signing, attestation,
identity pinning or the verify-before-rollout ordering is edited out, confirmed
against four deliberate breakages — and the pipeline has now also run.

What remains partial is the paragraph above, not this one: the signed images
are an artifact of record for the commit, and the container serving traffic is
still App Platform's own build of the same source.

## Known limits of what is built

- The `weighted` aggregation rule compares against a fixed 0.5 midpoint rather than
  a configurable one.
- Dataset-driven runs bypass the scenario library, so scenario-level expected and
  prohibited behaviour is unavailable for them.
- The evidence graph endpoint returns the whole project graph with no pagination;
  it will not scale to very large projects without one.
- Adaptive red teaming mutates mechanically across eight strategies rather than
  using a model to generate variants, which bounds the campaign but also bounds
  what it can find.
