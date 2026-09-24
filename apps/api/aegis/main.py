"""Aegis Eval API.

Control plane for AI test, evaluation, verification, validation and assurance.
Starts with no external dependency: SQLite, on-disk evidence, in-process queue.
Nothing leaves the deployment unless an operator configures a connector that
does.
"""

from __future__ import annotations

import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import get_settings
from .db import session_scope
from .routers import ROUTERS

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
log = logging.getLogger("aegis")

settings = get_settings()

DESCRIPTION = """
Evaluate AI systems against the missions, users, environments, risks and
adversaries they will actually encounter.

Three properties hold across every endpoint:

* **No magic number.** Results are reported per dimension. There is no overall
  trust score.
* **Unknown is a valid result.** An untested property reports `not_evaluated`
  and is never inferred to be a pass.
* **Evidence over claims.** Every score resolves to the request, the response,
  the execution trace, each evaluator's judgement and a content hash.

This platform produces evaluation evidence. It is not an authorisation to
operate and does not substitute for the government's accreditation process.
"""


def create_app() -> FastAPI:
    app = FastAPI(
        title="Aegis Eval",
        description=DESCRIPTION,
        version="0.1.0",
        docs_url="/docs",
        openapi_url="/openapi.json",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        # A download's name and digest travel as headers; a browser on another
        # origin cannot read either unless they are named here.
        expose_headers=["Content-Disposition", "X-Content-SHA256"],
    )

    for router in ROUTERS:
        app.include_router(router, prefix="/api/v1")

    @app.get("/health", tags=["system"])
    def health() -> dict:
        from .classification import describe as describe_classification
        from .runner import get_queue

        return {
            "status": "ok",
            "version": "0.1.0",
            "environment": settings.env,
            "database": "sqlite" if settings.is_sqlite else "external",
            "queue": {"backend": settings.queue_backend, "depth": get_queue().depth()},
            "evidence_backend": settings.evidence_backend,
            "egress_policy": settings.egress_policy,
            # Stated explicitly so an operator can confirm them at a glance.
            "telemetry_enabled": settings.telemetry_enabled,
            "max_classification": describe_classification()["max_classification"],
            "ephemeral_filesystem": settings.ephemeral_filesystem,
        }

    @app.get("/health/storage", tags=["system"])
    def storage_health() -> dict:
        """Confirm the evidence store is reachable and writable.

        Separate from /health because it performs a round trip to the object
        store, which a liveness probe should not do on every check.
        """
        from .hashing import evidence_store

        result = evidence_store().check()
        return {"status": "ok" if result.get("writable") else "degraded", **result}

    @app.on_event("startup")
    def startup() -> None:
        from .migrate import upgrade_to_head

        upgrade_to_head()

        # Confirm the evidence store before accepting work. A campaign that
        # runs and then cannot store what it produced is worse than one that
        # never started.
        from .hashing import evidence_store

        storage = evidence_store().check()
        if storage.get("writable"):
            log.info("Evidence store ready: %s", storage.get("location"))
        else:
            log.error(
                "Evidence store is NOT writable (%s): %s. Evaluations will fail to store "
                "evidence until this is fixed.",
                storage.get("location"),
                storage.get("error"),
            )

        from .seed import bootstrap

        with session_scope() as db:
            result = bootstrap(db)
        log.info("Startup complete: %s", result)

        if settings.max_classification:
            log.info(
                "Classification ceiling: %s. Artifacts above this marking are refused.",
                settings.max_classification,
            )

        if settings.telemetry_enabled and settings.otlp_endpoint:
            _configure_telemetry(app)
        else:
            log.info("Telemetry disabled. No data leaves this deployment.")

    return app


def _configure_telemetry(app: FastAPI) -> None:  # pragma: no cover - optional dependency
    """Opt-in OpenTelemetry export to a customer-operated collector."""
    try:
        from opentelemetry import trace
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor

        provider = TracerProvider(resource=Resource.create({"service.name": "aegis-eval-api"}))
        provider.add_span_processor(
            BatchSpanProcessor(OTLPSpanExporter(endpoint=settings.otlp_endpoint))
        )
        trace.set_tracer_provider(provider)
        FastAPIInstrumentor.instrument_app(app)
        log.info("Telemetry exporting to %s", settings.otlp_endpoint)
    except ImportError:
        log.warning("Telemetry enabled but OpenTelemetry packages are not installed.")


app = create_app()
