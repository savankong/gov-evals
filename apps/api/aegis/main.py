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
from .db import init_db, session_scope
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
    )

    for router in ROUTERS:
        app.include_router(router, prefix="/api/v1")

    @app.get("/health", tags=["system"])
    def health() -> dict:
        from .runner import get_queue

        return {
            "status": "ok",
            "version": "0.1.0",
            "environment": settings.env,
            "database": "sqlite" if settings.is_sqlite else "external",
            "queue": {"backend": settings.queue_backend, "depth": get_queue().depth()},
            "evidence_backend": settings.evidence_backend,
            "egress_policy": settings.egress_policy,
            # Stated explicitly so an operator can confirm it at a glance.
            "telemetry_enabled": settings.telemetry_enabled,
        }

    @app.on_event("startup")
    def startup() -> None:
        init_db()
        from .seed import bootstrap

        with session_scope() as db:
            result = bootstrap(db)
        log.info("Startup complete: %s", result)

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
