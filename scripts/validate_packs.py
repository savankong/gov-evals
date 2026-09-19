#!/usr/bin/env python3
"""Validate evaluation packs and deployment specifications.

Runs in CI with only PyYAML installed, so it does not import the application.
It catches the mistakes that are invisible until a campaign runs and produces
nothing: an evaluation whose selector matches no scenario, a threshold with no
recognised key, a framework reference nothing maps to.
"""

from __future__ import annotations

import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
PACKS = ROOT / "packs"

LAYERS = {"model", "human_systems", "systems_integration", "operational"}
DOMAINS = {
    "performance", "reliability", "robustness", "security", "safety",
    "responsible_ai", "human_factors", "mission_effectiveness", "integration",
    "resilience", "traceability",
}
THRESHOLD_KEYS = {
    "min_pass_rate", "max_failures", "max_latency_ms", "latency_statistic",
    "min_scores", "finding_severity", "min_recall", "min_precision",
    "min_groundedness", "min_consistency", "source",
}
SEVERITIES = {"critical", "high", "medium", "low", "info"}

# Tags the red-team materialiser produces at run time rather than shipping in a
# scenario pack. A selector using these is satisfied once attacks are built.
RUNTIME_TAGS = {"red-team", "agent", "prompt_injection", "data_poisoning",
                "agent_abuse", "exfiltration", "disclosure", "jailbreak",
                "evasion", "extraction"}

errors: list[str] = []
warnings: list[str] = []


def load(path: Path) -> dict:
    try:
        return yaml.safe_load(path.read_text()) or {}
    except yaml.YAMLError as exc:
        errors.append(f"{path.name}: not valid YAML: {exc}")
        return {}


def main() -> int:
    pack_files = sorted(PACKS.glob("*.y*ml"))
    if not pack_files:
        errors.append("No packs found in packs/")
        return report()

    scenarios: list[dict] = []
    evaluations: list[tuple[str, dict]] = []
    framework_refs: set[str] = set()
    keys_seen: dict[str, str] = {}

    for path in pack_files:
        doc = load(path)
        if not doc:
            continue

        for field in ("key", "kind", "version"):
            if not doc.get(field):
                errors.append(f"{path.name}: missing required field '{field}'")

        key = doc.get("key")
        if key in keys_seen:
            errors.append(f"{path.name}: pack key {key!r} already used by {keys_seen[key]}")
        elif key:
            keys_seen[key] = path.name

        for spec in doc.get("scenarios") or []:
            scenarios.append(spec)
            if not spec.get("key"):
                errors.append(f"{path.name}: a scenario has no key")
            if not (spec.get("input") or {}).get("prompt"):
                errors.append(f"{path.name}: scenario {spec.get('key')!r} has no input prompt")
            # A scenario without expectations cannot be argued with, which is
            # the whole point of stating them.
            if not spec.get("expected_behavior") and not spec.get("reference_answer"):
                warnings.append(
                    f"{path.name}: scenario {spec.get('key')!r} states no expected behaviour"
                )

        for spec in doc.get("evaluations") or []:
            evaluations.append((path.name, spec))

        for framework in doc.get("frameworks") or []:
            for requirement in framework.get("requirements") or []:
                framework_refs.add(requirement.get("ref"))

    scenario_tags = [set(s.get("tags") or []) for s in scenarios]

    for source, spec in evaluations:
        name = spec.get("key", "<unnamed>")

        if spec.get("layer") not in LAYERS:
            errors.append(f"{source}: {name} has layer {spec.get('layer')!r}, expected one of {sorted(LAYERS)}")
        if spec.get("domain") not in DOMAINS:
            errors.append(f"{source}: {name} has domain {spec.get('domain')!r}, expected one of {sorted(DOMAINS)}")
        if not spec.get("evaluators"):
            errors.append(f"{source}: {name} declares no evaluators")

        for entry in spec.get("evaluators") or []:
            if not entry.get("evaluator"):
                errors.append(f"{source}: {name} has an evaluator entry with no 'evaluator' key")

        threshold = spec.get("default_threshold") or {}
        for field in threshold:
            if field not in THRESHOLD_KEYS:
                errors.append(f"{source}: {name} threshold has unknown key {field!r}")
        severity = threshold.get("finding_severity")
        if severity and severity not in SEVERITIES:
            errors.append(f"{source}: {name} has finding_severity {severity!r}")

        # Selectors require every tag. An evaluation matching nothing reports
        # NOT EVALUATED, which is honest but useless, so catch it here.
        wanted = set((spec.get("scenario_selector") or {}).get("tags") or [])
        if wanted:
            if wanted & RUNTIME_TAGS:
                continue
            if not any(wanted <= tags for tags in scenario_tags):
                errors.append(
                    f"{source}: {name} selects tags {sorted(wanted)}, which no shipped scenario "
                    "carries. It would report NOT EVALUATED."
                )

        for ref in spec.get("framework_refs") or []:
            if ref not in framework_refs:
                errors.append(f"{source}: {name} maps to unknown framework reference {ref!r}")

    validate_deployment_specs()
    validate_container_entrypoints()
    validate_supply_chain()

    print(
        f"Checked {len(pack_files)} packs: {len(evaluations)} evaluations, "
        f"{len(scenarios)} scenarios, {len(framework_refs)} framework references."
    )
    return report()


def validate_deployment_specs() -> None:
    """The App Platform spec is a deployment contract; a typo is an outage."""
    spec_path = ROOT / ".do" / "app.yaml"
    if not spec_path.exists():
        return
    spec = load(spec_path)

    names = [s.get("name") for s in spec.get("services") or []]
    if "api" not in names or "web" not in names:
        errors.append(".do/app.yaml: expected services named 'api' and 'web'")

    components = (spec.get("services") or []) + (spec.get("workers") or [])
    for component in components:
        envs = {e.get("key"): e for e in component.get("envs") or []}

        # App Platform containers have an ephemeral filesystem. Any component
        # holding state must be told, so it refuses to start on local disk.
        if "AEGIS_EVIDENCE_BACKEND" in envs:
            if envs["AEGIS_EVIDENCE_BACKEND"].get("value") != "s3":
                errors.append(
                    f".do/app.yaml: {component.get('name')} must use the s3 evidence backend; "
                    "App Platform storage does not survive a deploy."
                )
            if envs.get("AEGIS_EPHEMERAL_FILESYSTEM", {}).get("value") != "true":
                errors.append(
                    f".do/app.yaml: {component.get('name')} sets an evidence backend but not "
                    "AEGIS_EPHEMERAL_FILESYSTEM=true, so the startup guard is disabled."
                )
            if not envs.get("AEGIS_S3_REGION", {}).get("value"):
                errors.append(
                    f".do/app.yaml: {component.get('name')} has no AEGIS_S3_REGION. SigV4 signs "
                    "with it and a mismatch fails opaquely."
                )

        # App Platform strips the matched prefix before forwarding unless a
        # route says otherwise. The API serves absolute paths and does not know
        # it is mounted under anything, so /health reached it as / and every
        # API path returned 404 from a container that was running fine.
        if component.get("name") == "api":
            for route in component.get("routes") or []:
                if route.get("path") not in (None, "/") and not route.get(
                    "preserve_path_prefix"
                ):
                    errors.append(
                        f".do/app.yaml: api route {route.get('path')!r} does not set "
                        "preserve_path_prefix, so the prefix is stripped and the API "
                        "will 404 on it."
                    )

        # In production the API refuses to start on the shipped bootstrap
        # password. A component that is given neither a real one nor the
        # opt-out exits non-zero at startup, which is how the worker failed
        # every deploy while the API beside it served fine.
        if (
            envs.get("AEGIS_ENV", {}).get("value") not in (None, "development")
            and "AEGIS_BOOTSTRAP_PASSWORD" not in envs
            and envs.get("AEGIS_BOOTSTRAP_LOCAL_ADMIN", {}).get("value") != "false"
        ):
            errors.append(
                f".do/app.yaml: {component.get('name')} sets no AEGIS_BOOTSTRAP_PASSWORD and "
                "does not set AEGIS_BOOTSTRAP_LOCAL_ADMIN=false, so it will refuse to start "
                "on the shipped default."
            )

        for key in ("AEGIS_SECRET_KEY", "AEGIS_S3_SECRET_KEY", "AEGIS_BOOTSTRAP_PASSWORD"):
            if key in envs and envs[key].get("type") != "SECRET":
                errors.append(f".do/app.yaml: {component.get('name')} must mark {key} as SECRET")

        if envs.get("AEGIS_SEED_DEMO", {}).get("value") == "true":
            errors.append(
                f".do/app.yaml: {component.get('name')} enables demo seeding, which must not "
                "run outside development."
            )


def validate_container_entrypoints() -> None:
    """Every script a component is told to run must be inside its image.

    The worker is configured with `run_command: python worker.py` in the App
    Platform spec and `command: ["python", "worker.py"]` in compose, but the
    Dockerfile never copied worker.py. Both exited immediately with "can't open
    file '/app/worker.py'". Nothing caught it: the API image built, started and
    served, so the only visible symptom was campaigns that never executed.
    """
    dockerfile = ROOT / "apps" / "api" / "Dockerfile"
    if not dockerfile.exists():
        return

    # Only COPY instructions count. Matching the file as one string would let a
    # comment mentioning worker.py satisfy the check -- which it did, on the
    # first version of this function, while the COPY was missing.
    copied = " ".join(
        line.strip()
        for line in dockerfile.read_text().splitlines()
        if line.strip().upper().startswith(("COPY ", "ADD "))
    )

    wanted: set[tuple[str, str]] = set()

    spec_path = ROOT / ".do" / "app.yaml"
    if spec_path.exists():
        spec = load(spec_path)
        for comp in (spec.get("services") or []) + (spec.get("workers") or []):
            command = comp.get("run_command") or ""
            for token in str(command).split():
                if token.endswith(".py"):
                    wanted.add((token, f".do/app.yaml: {comp.get('name')}"))

    compose_path = ROOT / "docker-compose.yml"
    if compose_path.exists():
        compose = load(compose_path)
        for name, service in (compose.get("services") or {}).items():
            command = service.get("command")
            tokens = command.split() if isinstance(command, str) else list(command or [])
            for token in tokens:
                if str(token).endswith(".py"):
                    wanted.add((str(token), f"docker-compose.yml: {name}"))

    for script, source in sorted(wanted):
        if script not in copied:
            errors.append(
                f"{source} runs {script}, but apps/api/Dockerfile never copies it into the "
                f"image. That container exits immediately with 'can't open file'."
            )


def validate_supply_chain() -> None:
    """SBOM and signing are build-pipeline controls, so nothing in the test
    suite can protect them. They are one edit away from becoming decorative in
    ways that still go green: dropping the verify step, or keeping it but
    letting it accept a signature from anybody.

    So the shape is asserted here, the same way the ephemeral-filesystem guard
    in the App Platform spec is.
    """
    ci_path = ROOT / ".github" / "workflows" / "ci.yml"
    deploy_path = ROOT / ".github" / "workflows" / "deploy-digitalocean.yml"

    if ci_path.exists():
        ci = load(ci_path)
        jobs = ci.get("jobs") or {}
        if "sbom" not in jobs:
            errors.append("ci.yml: no 'sbom' job. Every build must record what went into it.")
        else:
            body = yaml.safe_dump(jobs["sbom"])
            if "check_sbom.py" not in body:
                errors.append(
                    "ci.yml: the sbom job does not run scripts/check_sbom.py, so an SBOM "
                    "that resolved nothing would still pass."
                )

    if not deploy_path.exists():
        return
    deploy = load(deploy_path)
    job = (deploy.get("jobs") or {}).get("deploy")
    if not job:
        errors.append("deploy-digitalocean.yml: no 'deploy' job")
        return

    permissions = job.get("permissions") or {}
    if permissions.get("id-token") != "write":
        errors.append(
            "deploy-digitalocean.yml: the deploy job needs 'id-token: write'. Keyless "
            "signing cannot get an OIDC token without it."
        )

    steps = job.get("steps") or []
    bodies = [str(s.get("run") or "") for s in steps]
    joined = "\n".join(bodies)

    for fragment, message in (
        ("cosign sign", "nothing signs the images"),
        ("cosign attest", "no SBOM is attested to the images"),
        ("cosign verify", "nothing verifies what was signed"),
    ):
        if fragment not in joined:
            errors.append(f"deploy-digitalocean.yml: {message} ({fragment!r} not found)")

    # An unpinned `cosign verify` accepts a valid signature from any identity,
    # which is the usual way this check ends up proving nothing.
    if "cosign verify" in joined and "--certificate-identity" not in joined:
        errors.append(
            "deploy-digitalocean.yml: cosign verify does not pin --certificate-identity, "
            "so it would accept a signature from any identity."
        )

    # Verifying after the rollout tells you about something already serving.
    def first_index(predicate) -> int | None:
        for i, body in enumerate(bodies):
            if predicate(body):
                return i
        return None

    verify_at = first_index(lambda b: "cosign verify" in b)
    rollout_at = first_index(lambda b: "create-deployment" in b)
    if verify_at is not None and rollout_at is not None and verify_at > rollout_at:
        errors.append(
            "deploy-digitalocean.yml: signatures are verified after the rollout step. "
            "A failed verification must stop the deployment, not report on it."
        )

    # Signing a tag is signing a mutable pointer.
    if "cosign sign" in joined and "@" not in joined.split("cosign sign")[1][:400]:
        warnings.append(
            "deploy-digitalocean.yml: cosign sign may be operating on a tag rather than "
            "a digest. A tag can be repointed after signing."
        )


def report() -> int:
    for warning in warnings:
        print(f"warning: {warning}")
    for error in errors:
        print(f"error: {error}", file=sys.stderr)
    if errors:
        print(f"\n{len(errors)} error(s).", file=sys.stderr)
        return 1
    print("All packs and deployment specs valid.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
