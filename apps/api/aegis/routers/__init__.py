"""HTTP routers. Everything the UI does is available through these endpoints."""

from . import (
    assurance,
    auth,
    campaigns,
    catalog,
    dashboard,
    datasets,
    evaluations,
    experts,
    findings,
    onboarding,
    redteam,
    reports,
    scenarios,
    systems,
    tenancy,
    users,
)

ROUTERS = [
    auth.router,
    catalog.router,
    tenancy.router,
    systems.router,
    datasets.router,
    scenarios.router,
    evaluations.router,
    campaigns.router,
    experts.router,
    redteam.router,
    findings.router,
    assurance.router,
    reports.router,
    dashboard.router,
    onboarding.router,
    users.router,
]
