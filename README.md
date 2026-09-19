# Aegis Eval

Test AI for the mission, not the benchmark.

Aegis Eval evaluates AI systems against the missions, users, environments, risks
and adversaries they will actually encounter, and keeps the evidence behind every
result. It answers one question:

> What evidence justifies using this AI for this mission under these conditions?

A model can score well on a public benchmark and still fail on unfamiliar mission
data, under adversarial input, when connected to other systems, or in the hands of
an operator who trusts it more than the evidence supports. This platform is built
to find that out before deployment, and to keep finding out afterwards.

## Three rules the software enforces

These are not documentation. They are tested behaviour, and a change that breaks
one fails the suite.

**No magic number.** Results roll up per dimension — performance, robustness,
security, human factors, integration, Responsible AI, and the rest. There is no
composite trust score anywhere in the product. Weighting dimensions against
mission requirements is a program decision.

**Unknown is a valid result.** An untested property reports `NOT EVALUATED`. A run
that produced no judgement never counts as a pass, and a threshold like
`max_failures: 0` cannot be satisfied by a run that evaluated nothing. A gate with
an unmeasured criterion is undetermined, not passed — the CLI even has its own
exit code for it.

**Evidence over claims.** Every score resolves to the exact request, the source
material supplied, the output, the execution trace, each evaluator's judgement
with its own provenance, and a SHA-256 digest of the stored record.

## Quick start

```bash
docker compose up --build
```

- UI: http://localhost:3000
- API docs: http://localhost:8000/docs
- Sign in with `admin@aegis.local` / `aegis-dev-password`

The stack starts with SQLite, on-disk evidence and an in-process queue. It needs
no external service and makes no outbound call. A demonstration project is seeded
against an offline deterministic target, so the whole workflow — mission profile,
plan, campaign, findings, comparison, assurance case, report — is explorable
immediately with no model provider configured.

For local development without Docker:

```bash
make install
make api     # :8000
make web     # :3000
make test    # 133 tests
```

## How it works

An evaluation project pairs an AI capability with the mission it is meant for.

1. **Mission profile.** What the system is for: tasks, users, operational
   environment, acceptable errors, failures the program declares unacceptable,
   adversaries, latency requirements, oversight expectations. Every result is
   judged against this, which is what separates "how good is this model" from
   "how good is this model for this mission".

2. **System registry.** Each system version is an immutable configuration
   snapshot — model, prompt, parameters, retrieval architecture, tool access,
   guardrails — fingerprinted so a result can always name the exact configuration
   that produced it.

3. **Evaluation plan.** Drafted from the mission profile and system architecture,
   with a written reason for every evaluation included. Thresholds arrive marked
   unconfirmed: the program office sets the passing bar, and a plan cannot be
   approved while any threshold is a library default, while it covers no
   evaluations, or while any evaluation has no scenario matching its selector.

4. **Campaign.** Executes the plan against one or more system versions under
   identical conditions — the property that makes a procurement comparison
   defensible.

5. **Evidence.** Each execution stores the request, response, trace, judgements
   and a content hash. Failures cluster into findings; findings feed risks; risks
   and runs support or counter claims in an assurance case.

## What is in the box

| | |
| --- | --- |
| **Connectors** | OpenAI-compatible, Anthropic-compatible, generic REST, RAG application, offline deterministic target |
| **Evaluators** | 22 across four kinds: deterministic, model-based, human, external tool |
| **Evaluation packs** | GenAI Baseline, RAG Baseline, AI Agent Baseline, DoD Responsible AI Starter |
| **Attack library** | 15 techniques — injection, jailbreak, evasion, poisoning, exfiltration, agent abuse |
| **Scenario packs** | Acquisition document review, intelligence summarisation, agent missions |
| **Frameworks** | CDAO AI T&E, DoD RAI Pathway, DoD AI Ethical Principles, NIST AI RMF, NIST GenAI Profile |

Connectors speak wire protocols rather than naming vendors, so one adapter covers
many hosts and no evaluation depends on a single provider. Everything is a plugin
interface: `ModelAdapter`, `Evaluator`, `Reporter`, `FrameworkPack`, `AttackPack`.

## Evaluating a real system

```bash
export AEGIS_URL=https://aegis.example.mil
export AEGIS_TOKEN=...

aegis evaluate \
  --project $PROJECT \
  --system-version $VERSION \
  --suite genai-baseline \
  --threshold citation-accuracy='{"min_pass_rate":0.98}'

aegis gate --gate $GATE --campaign $CAMPAIGN
```

Exit codes are the CI contract: `0` passed, `1` failed, `2` usage error,
`3` could not be determined. The last one exists because a gate whose criteria
could not be measured is a different answer from a gate that passed.

```python
from aegis_sdk import Aegis

with Aegis() as client:
    campaign = client.evaluate(
        project_id=PROJECT,
        system_version_ids=[V1, V2],   # compared under identical conditions
        suite="genai-baseline",
    )
    for run in campaign.unevaluated_runs:
        print(f"{run.evaluation} produced no judgement — not a pass")
```

## Deployment

| Environment | Notes |
| --- | --- |
| Local / air-gapped | SQLite, file evidence store, inline queue. No outbound call. |
| Single node | Docker Compose, as above. |
| Scaled | `docker compose --profile scale up` adds Postgres, Redis and worker replicas. |
| DigitalOcean | App Platform or a droplet. See [the guide](docs/deploy-digitalocean.md). |
| Customer cloud | Any SQLAlchemy database, any S3-compatible object store. |

### DigitalOcean

```bash
cd deploy/digitalocean && terraform init && terraform apply
doctl apps create --spec .do/app.yaml
```

Terraform provisions managed Postgres, managed Valkey and a private versioned
Space; the app spec wires them together and GitHub Actions deploys on green CI.

Two things that deployment enforces rather than documents. App Platform
containers have an ephemeral filesystem, so the API refuses to start on SQLite
or a local evidence directory when `AEGIS_EPHEMERAL_FILESYSTEM` is set —
evidence lost silently on a redeploy is the worst failure this product can
have. And because DigitalOcean is not FedRAMP authorized and carries no DoD
provisional authorization, the spec sets `AEGIS_MAX_CLASSIFICATION=UNCLASSIFIED`
and the API refuses artifacts marked above it. That path holds development and
unclassified data; CUI and IL4+ belong in a government cloud region under the
customer's own authorization.

Set `AEGIS_EGRESS_POLICY=deny` with an allowlist and a connector whose host is not
listed is refused before any request leaves the deployment. Telemetry is off unless
a customer points it at their own collector; the platform never phones home, and
evaluation data is never used to train anything.

Outside `development`, the platform refuses to start on shipped-default
credentials rather than running with a signing key everyone has.

### Supply chain

Every build records what went into it. CI generates a CycloneDX SBOM for the
API, the SDK and the web app; the deploy job generates one per image, signs both
images by digest with cosign keyless, and attaches the SBOM as an attestation.
It then verifies signature and attestation against a pinned certificate identity
**before** rolling out, so a failure stops the deployment rather than reporting
on one already serving.

Two checks stop that decaying into ritual: an SBOM that resolved nothing is
refused the same way a run that judged nothing is, and the pack validator fails
CI if the signing, the identity pinning or the verify-before-rollout ordering is
edited out. The pipeline has run: both images were signed and verified against a
real registry on 19 September 2026 before the rollout that followed. What it
still does not cover — the running container is App Platform's own build, not
the signed image — is in [the security notes](docs/security.md).

## Repository layout

```
apps/api        FastAPI control plane, evaluation engine, packs, reports
apps/web        Next.js interface
packages/sdk    Python SDK and the aegis CLI
packs/          Evaluation, scenario, attack and framework packs (YAML)
docs/           Architecture and requirement traceability
```

## What this is not

Aegis Eval produces evaluation evidence. It is not an authorisation to operate and
does not substitute for the government's accreditation process. A framework mapping
records which evaluations speak to a reference and what they found — it does not
assert compliance, and no requirement ships marked claimable.

A model-based judgement is advisory evidence recorded with the judge model and
rubric that produced it. It is never presented as ground truth and never outranks
the deterministic or human judgements beside it.

An adversarial campaign that found nothing has not shown a system is resistant. It
has shown that those techniques did not work within that budget, and the report
says so in those words.

## Documentation

- [Architecture](docs/architecture.md)
- [Evaluation model](docs/evaluation-model.md)
- [Writing a pack](docs/writing-packs.md)
- [Requirement traceability](docs/traceability.md)
- [Security posture](docs/security.md)
- [Deploying on DigitalOcean](docs/deploy-digitalocean.md)
