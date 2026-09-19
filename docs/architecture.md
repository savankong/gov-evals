# Architecture

## Shape

```
                        Web UI (Next.js)
                              │
                     API / control plane (FastAPI)
                              │
        ┌─────────────────────┼─────────────────────┐
        │                     │                     │
 Evaluation manager    Evidence graph      Policy / framework
        │                     │                  engine
        │                     │
 Evaluation queue      Evidence store
        │
 ┌──────┴──────────────────────────────────────┐
 │              Evaluation runners              │
 ├────────────┬───────────┬────────────┬───────┤
 │ Model eval │ Red team  │ Human eval │ Tools │
 └─────┬──────┴─────┬─────┴────────────┴───────┘
       │            │
 Model adapters   External systems
       │
 ┌─────┼──────────────────────────────────────┐
 API  Local        RAG         Agent      Custom
 LLM  model        system      system     system
```

Nothing in the control plane depends on a commercial service. The default
deployment is SQLite, a directory of evidence files and an in-process queue.

## Components

**Control plane** (`apps/api/aegis`). FastAPI over SQLAlchemy. Everything the UI
does is an API call; there is no private path.

**Evaluation engine** (`aegis/runner/engine.py`). Resolves scenarios, invokes the
target through an adapter, collects judgements from each configured evaluator,
aggregates them, stores evidence, and measures the run against the plan's
threshold. Two rules shape the file: a threshold is never invented, and every
number is traceable.

**Queue** (`aegis/runner/queue.py`). `inline` executes on a bounded thread pool
inside the API process — what a single node or an air-gapped laptop uses. `redis`
hands campaigns to worker containers. The interface is identical, so scaling up
changes no code above this layer.

**Evidence store** (`aegis/hashing.py`). Writes an artifact and returns a URI and
digest. `file` keeps everything on local disk; `s3` targets any S3-compatible
endpoint, including MinIO on premises.

**Audit log** (`aegis/audit.py`). Append-only and hash-chained: each event stores
the digest of the previous one, so an edit or deletion inside the application
breaks the chain and `GET /audit/verify` reports where.

## Extension points

Adding a capability is a registration, not a fork.

| Interface | Registered with | Purpose |
| --- | --- | --- |
| `ModelAdapter` | `@register_adapter` | Connect a new kind of target system |
| `Evaluator` | `@register_evaluator` | Add a new judgement method |
| Framework pack | YAML in `packs/` | Add references evaluations map to |
| Attack pack | YAML in `packs/` | Add adversarial techniques |
| Evaluation pack | YAML in `packs/` | Add reusable evaluations |

A new adapter is one class:

```python
from aegis.connectors import ModelAdapter, TargetRequest, TargetResponse, register_adapter

@register_adapter
class MyGatewayAdapter(ModelAdapter):
    key = "my_gateway"
    label = "Internal inference gateway"

    def invoke(self, request: TargetRequest) -> TargetResponse:
        ...  # self.endpoint, self.parameters and self.secret are already resolved
        return TargetResponse(text=answer, latency_ms=elapsed, trace=steps)
```

`self._check_egress(url)` before any outbound call enforces the deployment's
egress policy. Secrets are referenced by `credential_ref` (`env:NAME` or
`file:/path`), never stored in the database.

## Data model

The tables follow the evidence graph:

```
Organization
 └── Program
      └── Project
           ├── MissionProfile          the operational context
           ├── Requirement             what the program must show
           ├── System → SystemVersion  immutable configuration snapshots
           ├── Dataset → DatasetVersion → DatasetItem
           ├── Scenario                the fundamental test object
           ├── EvaluationPlan → EvaluationPlanItem
           └── Campaign → Run → Result → Evidence
                                   ├── HumanReview
                                   └── Finding → Risk
AssuranceCase → AssuranceClaim → AssuranceEvidenceLink
```

Two design choices carry weight.

**SystemVersion is immutable and fingerprinted.** `config_hash` covers everything
that changes behaviour — connector, model, parameters, system prompt, retrieval
architecture, tools, guardrails — and deliberately excludes descriptive fields, so
two versions that behave identically hash identically. Every run records it.

**Status vocabularies are string constants, not database enums.** A customer can
extend a severity scale, a classification banner or a risk matrix without a schema
migration. Risk scoring in particular belongs to the organization: the shipped
scale is a fallback used only when none is configured.

## Reproducibility

Every run stores what is needed to recreate it: platform and Python version,
system version id and config hash, model name and version, prompt hash, model
parameters, random seed where the target exposes one, evaluation version and hash,
the evaluator list, the aggregation rule, the threshold, and the dataset version.

The offline `echo` target is deterministic — behaviour is seeded from the prompt —
so the platform can demonstrate and test reproducibility without a model provider.

## Request path

```
POST /campaigns/{id}/execute
  → queue.enqueue(campaign_id)
  → execute_campaign
      for each run:
        resolve_scenarios      selector → approved scenarios only
        build_adapter          from the immutable SystemVersion
        for each scenario:
          adapter.invoke       one request to the target
          evaluators           one judgement each, with provenance
          aggregate            per the evaluation's rule
          store evidence       hashed, written to the evidence store
        compute metrics
        compare to threshold   or report NOT EVALUATED
      open findings            clustered by failing evaluator
      summarise by domain      never into a single score
```
