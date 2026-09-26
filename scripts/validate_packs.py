#!/usr/bin/env python3
"""Validate evaluation packs and deployment specifications.

Runs in CI with only PyYAML installed, so it does not import the application.
It catches the mistakes that are invisible until a campaign runs and produces
nothing: an evaluation whose selector matches no scenario, a threshold with no
recognised key, a framework reference nothing maps to.
"""

from __future__ import annotations

import re
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


def validate_criteria(spec: dict) -> list[str]:
    """Grading criteria must each be identifiable and say something.

    The criterion id is what an expert's label and the judge's verdict are
    matched on. A missing or repeated id makes that match silently wrong: two
    verdicts land on one criterion, or an expert label lands on nothing, and
    the published judge-agreement figure is computed over the wrong pairs.
    """
    if "criteria" not in spec:
        return []
    key = spec.get("key")
    criteria = spec.get("criteria")
    if not isinstance(criteria, list) or not criteria:
        return [f"scenario {key!r} declares criteria but lists none"]
    problems, seen = [], set()
    for index, criterion in enumerate(criteria, start=1):
        if not isinstance(criterion, dict):
            problems.append(f"scenario {key!r} criterion {index} is not a mapping with id and text")
            continue
        cid = criterion.get("id")
        if not cid:
            problems.append(f"scenario {key!r} criterion {index} has no id")
        elif cid in seen:
            problems.append(f"scenario {key!r} repeats criterion id {cid!r}")
        seen.add(cid)
        if not str(criterion.get("text") or "").strip():
            problems.append(f"scenario {key!r} criterion {cid or index} has no text")
    return problems


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
            errors.extend(f"{path.name}: {e}" for e in validate_criteria(spec))
            # Knowledge area is what a weakness is found in and a delivery is
            # binned and priced by. A list or a blank here is a bin nobody can
            # sell; absent is fine and is reported as undeclared.
            if "knowledge_area" in spec and not (
                isinstance(spec["knowledge_area"], str) and spec["knowledge_area"].strip()
            ):
                errors.append(
                    f"{path.name}: scenario {spec.get('key')!r} has a knowledge_area that is not "
                    "a non-empty string"
                )
            if "required_expertise" in spec and not (
                isinstance(spec["required_expertise"], list)
                and all(isinstance(d, str) and d.strip() for d in spec["required_expertise"])
            ):
                errors.append(
                    f"{path.name}: scenario {spec.get('key')!r} required_expertise must be a list "
                    "of discipline slugs"
                )
            # A scenario without expectations cannot be argued with, which is
            # the whole point of stating them. Criteria are expectations too.
            if not (
                spec.get("expected_behavior") or spec.get("reference_answer") or spec.get("criteria")
            ):
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
    validate_build_sources()
    validate_container_entrypoints()
    validate_pinned_base_images()
    validate_deterministic_installs()
    validate_supply_chain()
    validate_web_build_args()
    validate_schema_migrations()
    validate_no_accent_rules()
    validate_readable_type()

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


def validate_build_sources() -> None:
    """Every component must build from a branch that contains its build inputs.

    App Platform resolves `github.branch` at build time, not from whatever
    branch a person happened to push. A spec naming a branch without the
    Dockerfile still builds something -- a buildpack fallback over whatever is
    there -- and the resulting container exits immediately with no application
    log output, because there is no application in it. The deploy reports
    DeployContainerExitNonZero and says nothing about the cause.

    This check is the reason that is now a CI failure instead of a deployment
    that has to be diagnosed against a live app.
    """
    import subprocess

    spec_path = ROOT / ".do" / "app.yaml"
    if not spec_path.exists():
        return
    spec = load(spec_path)

    def git(*args) -> subprocess.CompletedProcess:
        # check=False throughout: a non-zero exit is the answer here, not an
        # error. `cat-file -e` returning 1 is exactly how absence is reported.
        return subprocess.run(
            ["git", *args], cwd=ROOT, capture_output=True, text=True, check=False
        )

    if git("rev-parse", "--git-dir").returncode != 0:
        warnings.append("Not a git checkout, so spec build sources were not verified.")
        return

    components = [("service", c) for c in spec.get("services") or []]
    components += [("worker", c) for c in spec.get("workers") or []]

    for kind, component in components:
        name = component.get("name")
        branch = (component.get("github") or {}).get("branch")
        dockerfile = component.get("dockerfile_path")
        if not branch or not dockerfile:
            continue

        # Prefer the remote ref: it is what App Platform will fetch.
        ref = None
        for candidate in (f"origin/{branch}", branch):
            if git("rev-parse", "--verify", "--quiet", candidate).returncode == 0:
                ref = candidate
                break
        if ref is None:
            warnings.append(
                f".do/app.yaml: {kind} {name} builds from {branch!r}, which is not available "
                "in this checkout, so its contents were not verified. Fetch it to check "
                "(actions/checkout needs fetch-depth: 0)."
            )
            continue

        required = [dockerfile]
        # A component built from the repository root also needs the evaluation
        # packs, which the image copies in because App Platform mounts nothing.
        if component.get("source_dir") in ("/", "", None):
            required.append("packs")

        for path in required:
            if git("cat-file", "-e", f"{ref}:{path}").returncode != 0:
                errors.append(
                    f".do/app.yaml: {kind} {name} builds from branch {branch!r}, which does "
                    f"not contain {path!r}. Applying this spec would build a container with "
                    "no application in it, which exits immediately and logs nothing."
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


def validate_pinned_base_images() -> None:
    """Every FROM must name a digest, not a tag.

    A tag is a moving pointer. Two builds of the same commit a week apart can
    sit on different bases, and every layer above changes with it -- which is
    what happened here: an unchanged apps/web context produced a different image
    digest between two deploys.

    That matters more than untidiness, because these images are signed. A
    signature over an artifact whose inputs nobody recorded attests that this
    pipeline built something at that time, not that this source yields this
    artifact. Pinning does not make the build bit-reproducible -- layer
    timestamps and checkout mtimes still vary -- but it makes the inputs known,
    which is the part a reader of the signature is entitled to.
    """
    for relative in ("apps/api/Dockerfile", "apps/web/Dockerfile"):
        path = ROOT / relative
        if not path.exists():
            continue
        for number, line in enumerate(path.read_text().splitlines(), start=1):
            stripped = line.strip()
            if not stripped.upper().startswith("FROM "):
                continue
            image = stripped.split()[1]
            # A stage reference (FROM build AS x) carries no registry path and
            # is resolved inside the file, so it needs no digest.
            if "/" not in image and ":" not in image and "@" not in image:
                continue
            if "@sha256:" not in image:
                errors.append(
                    f"{relative}:{number} builds FROM {image}, which is a tag rather than a "
                    "digest. These images are signed; a signature over an artifact whose base "
                    "nobody recorded says when it was built, not what from. Pin it as "
                    "name:tag@sha256:<digest>."
                )


def validate_deterministic_installs() -> None:
    """The web build must not be able to fall back to an unlocked install.

    `npm ci || npm install` reads as a safety net and behaves as a hole: a
    lockfile that does not match package.json silently becomes a fresh
    resolution of whatever was newest that day -- a dependency change nobody
    reviewed, inside a build that is then signed and attested. A stale lockfile
    should stop the build.
    """
    path = ROOT / "apps" / "web" / "Dockerfile"
    if not path.exists():
        return
    text = path.read_text()

    for number, line in enumerate(text.splitlines(), start=1):
        stripped = line.strip()
        if stripped.startswith("#"):
            continue
        if "npm ci" in stripped and "npm install" in stripped:
            errors.append(
                f"apps/web/Dockerfile:{number} falls back from `npm ci` to `npm install`. "
                "That turns a lockfile mismatch into an unreviewed dependency resolution "
                "inside an image this pipeline signs."
            )
        # `package-lock.json*` globs to nothing when the lockfile is absent,
        # letting the build proceed without one.
        if stripped.upper().startswith("COPY ") and "package-lock.json*" in stripped:
            errors.append(
                f"apps/web/Dockerfile:{number} copies `package-lock.json*`, which matches "
                "nothing if the lockfile is missing rather than failing. Copy it by name."
            )

    if not (ROOT / "apps" / "web" / "package-lock.json").exists():
        errors.append(
            "apps/web/package-lock.json is missing, so `npm ci` cannot pin the web "
            "dependency tree."
        )


def validate_web_build_args() -> None:
    """The web image that serves is built by the deploy workflow, not by App
    Platform from .do/app.yaml: the workflow signs it, verifies it and pins the
    live spec to its digest. Next.js bakes NEXT_PUBLIC_* in at build time, so a
    value set only in the spec never reaches production -- the spec reads as
    though the product tour is on while the served bundle has it off.

    Every NEXT_PUBLIC_* build-time value on the web component must therefore
    also be a --build-arg of the workflow's web build, and a literal value must
    match.
    """
    spec_path = ROOT / ".do" / "app.yaml"
    deploy_path = ROOT / ".github" / "workflows" / "deploy-digitalocean.yml"
    if not spec_path.exists() or not deploy_path.exists():
        return
    import re

    spec = load(spec_path)
    web = next((s for s in spec.get("services") or [] if s.get("name") == "web"), None)
    if web is None:
        return
    wanted = {
        e.get("key"): str(e.get("value"))
        for e in web.get("envs") or []
        if str(e.get("key", "")).startswith("NEXT_PUBLIC_") and e.get("scope") == "BUILD_TIME"
    }

    text = deploy_path.read_text()
    build = re.search(r"docker build \\\n(?:.*\\\n)*?.*apps/web\s*$", text, re.MULTILINE)
    if not build:
        errors.append(
            "deploy-digitalocean.yml: could not find the web image's docker build, so the "
            "NEXT_PUBLIC_* values in .do/app.yaml cannot be checked against it."
        )
        return
    passed = dict(re.findall(r'--build-arg\s+(NEXT_PUBLIC_\w+)=("?[^"\s]*"?)', build.group(0)))

    for key, value in sorted(wanted.items()):
        if key not in passed:
            errors.append(
                f"deploy-digitalocean.yml: the web build does not pass {key}. .do/app.yaml "
                "sets it at build time, but the image that serves is built by this workflow, "
                "so production would be built without it."
            )
            continue
        given = passed[key].strip('"')
        # Values the spec takes from App Platform (${APP_URL}) are supplied by a
        # repository variable in the workflow; only literals can be compared.
        if "${" not in value and "${{" not in given and given != value:
            errors.append(
                f"deploy-digitalocean.yml: the web build passes {key}={given} but .do/app.yaml "
                f"sets {value}. The spec and the served image must agree."
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

    # "latest" is resolved by an unauthenticated API call; rate limited, the
    # action falls back to a 2023 doctl that cannot parse a digest-pinned spec.
    for step in steps:
        if "action-doctl" not in str(step.get("uses") or ""):
            continue
        version = str((step.get("with") or {}).get("version") or "")
        if not re.fullmatch(r"\d+\.\d+\.\d+", version):
            errors.append(
                "deploy-digitalocean.yml: action-doctl is not pinned to an exact version "
                f"(version: {version or 'unset'}). Unpinned, a rate-limited lookup installs "
                "doctl 1.98.1, which rejects the digest-pinned spec at rollout."
            )
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

    # The rollout is whichever command actually starts a deployment. Both
    # spellings count: keying on one of them is how this check silently stopped
    # applying when the rollout switched from `create-deployment` to
    # `apps update --spec`, which is the failure mode this whole function is
    # about.
    def is_rollout(body: str) -> bool:
        return "create-deployment" in body or ("apps update" in body and "--spec" in body)

    rollout_at = first_index(is_rollout)
    if rollout_at is None:
        errors.append(
            "deploy-digitalocean.yml: no rollout step found. Expected either "
            "`doctl apps create-deployment` or `doctl apps update --spec`."
        )
    if verify_at is not None and rollout_at is not None and verify_at > rollout_at:
        errors.append(
            "deploy-digitalocean.yml: signatures are verified after the rollout step. "
            "A failed verification must stop the deployment, not report on it."
        )

    # Pinning the live spec to the verified digests is what makes the running
    # container the artifact that was signed. Doing it before verification would
    # point production at something unchecked.
    pin_at = first_index(lambda b: "pin_app_images.py" in b)
    if pin_at is not None:
        if verify_at is not None and pin_at < verify_at:
            errors.append(
                "deploy-digitalocean.yml: the app spec is pinned to image digests before "
                "those images are verified. Production would be pointed at an unchecked "
                "artifact."
            )
        if rollout_at is not None and pin_at > rollout_at:
            errors.append(
                "deploy-digitalocean.yml: the spec is pinned after the rollout, so the "
                "rollout would deploy the previous spec."
            )

    # Applying the committed spec to a running app overwrites its encrypted
    # secrets with the placeholders that file carries.
    for body in bodies:
        if is_rollout(body) and ".do/app.yaml" in body:
            errors.append(
                "deploy-digitalocean.yml: the rollout applies .do/app.yaml to the running "
                "app. That spec holds placeholders for its SECRET values, so this would "
                "overwrite the live credentials. Patch the spec from `doctl apps spec get`."
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


def validate_schema_migrations() -> None:
    """A long-lived database must be brought up by migrations, not by create_all.

    `Base.metadata.create_all` creates tables that are missing and does nothing
    to tables that are present. It cannot add a column. Both long-lived
    processes -- the API and the worker -- called it at startup, so the deployed
    schema froze at the models of the day the database was created. Seven
    columns added later were never applied, and every endpoint that selected one
    of those rows returned 500 while the tables all looked present and correct.

    Three things are checked, because each of them alone was once true while the
    schema was still wrong: the services call the migration runner; the
    revisions form one unbroken chain; and alembic is actually a dependency of
    the image that has to run them.
    """
    migrations = ROOT / "apps" / "api" / "aegis" / "migrations" / "versions"
    if not migrations.exists():
        errors.append(
            "apps/api/aegis/migrations/versions does not exist. Without migrations a deployed "
            "database freezes at the models of the day it was created."
        )
        return

    for relative in ("apps/api/aegis/main.py", "apps/api/worker.py"):
        path = ROOT / relative
        if not path.exists():
            continue
        body = path.read_text()
        # Startup code only -- a docstring naming init_db is not a call to it.
        calls = [
            line.strip()
            for line in body.splitlines()
            if not line.strip().startswith("#") and "init_db()" in line
        ]
        if calls:
            errors.append(
                f"{relative} calls init_db() at startup. create_all never adds a column to a "
                "table that already exists, so a deployed database stops receiving model "
                "changes silently. Call aegis.migrate.upgrade_to_head instead."
            )
        if "upgrade_to_head" not in body:
            errors.append(
                f"{relative} never brings the schema up. It has to call "
                "aegis.migrate.upgrade_to_head before serving, or it will run against "
                "whatever schema happens to be there."
            )

    revisions: dict[str, str | None] = {}
    for script in sorted(migrations.glob("[0-9]*.py")):
        text = script.read_text()
        revision = down = None
        for line in text.splitlines():
            if line.startswith("revision = "):
                revision = line.split("=", 1)[1].strip().strip("\"'")
            elif line.startswith("down_revision = "):
                raw = line.split("=", 1)[1].strip()
                down = None if raw == "None" else raw.strip("\"'")
        if revision is None:
            errors.append(f"{script.name}: no revision identifier")
            continue
        revisions[revision] = down

    if not revisions:
        errors.append("apps/api/aegis/migrations/versions holds no revisions.")
        return

    roots = [rev for rev, down in revisions.items() if down is None]
    if len(roots) != 1:
        errors.append(
            f"The revision history has {len(roots)} starting points ({sorted(roots)}). "
            "It must have exactly one, or `upgrade head` is ambiguous."
        )

    parents = {down for down in revisions.values() if down is not None}
    heads = sorted(set(revisions) - parents)
    if len(heads) != 1:
        errors.append(
            f"The revision history has {len(heads)} heads ({heads}). Alembic refuses to "
            "upgrade a branched history, so startup would fail."
        )

    for revision, down in sorted(revisions.items()):
        if down is not None and down not in revisions:
            errors.append(
                f"Revision {revision!r} follows {down!r}, which does not exist."
            )

    pyproject = (ROOT / "apps" / "api" / "pyproject.toml").read_text()
    if "alembic" not in pyproject:
        errors.append(
            "apps/api/pyproject.toml does not depend on alembic, so the image that has to run "
            "the migrations at startup will not have it installed."
        )


def validate_no_accent_rules() -> None:
    """No block is flagged by a heavier rule down one of its sides.

    A rule can only be darker or lighter, so it says "pay attention" and
    nothing more, and every kind of aside ended up wearing the same one: an
    error, a caution and a footnote about model-based judgements were all a
    line in the margin. Worse, the error's rule was red -- the colour this
    product reserves for a verdict about the system under evaluation, read off
    five-pixel squares in dense tables.

    Asides are marked by a glyph that names what they are, coloured by how much
    they matter: `Note` and `ErrorNote` in components/ui.tsx. Hairline borders
    that divide a table, a panel edge or a nesting level are structure, not
    emphasis, and are not what this refuses.
    """
    web = ROOT / "apps" / "web" / "src"
    if not web.exists():
        return

    # A rule is an accent when it is thicker than a hairline, or when a
    # single-side hairline is drawn in a colour that carries meaning.
    import re

    thick = re.compile(r"border-(?:l|r|t|b)-2\b")
    coloured = re.compile(r"border-(?:l|r|t|b) border-(?:fail|warn|pass|pending|accent|ink|line-strong)\b")

    for path in sorted(web.rglob("*.tsx")):
        for number, line in enumerate(path.read_text().splitlines(), 1):
            hit = thick.search(line) or coloured.search(line)
            if not hit:
                continue
            errors.append(
                f"{path.relative_to(ROOT)}:{number}: {hit.group(0)!r} flags a block with a rule "
                "down one side. Use Note or ErrorNote from components/ui.tsx -- the glyph says "
                "what kind of aside it is and its colour says how much it matters, which a line "
                "cannot."
            )


# The smallest text the interface may set, at the default root size.
MIN_TEXT_REM = 0.75
# WCAG 2.x AA for body-size text.
MIN_CONTRAST = 4.5
TEXT_TOKENS = ("ink", "ink-soft", "muted", "faint")
SURFACE_TOKENS = ("canvas", "panel", "sunken")


def _luminance(rgb: tuple[int, int, int]) -> float:
    def channel(value: int) -> float:
        c = value / 255
        return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4

    r, g, b = (channel(v) for v in rgb)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast(a: tuple[int, int, int], b: tuple[int, int, int]) -> float:
    high, low = sorted((_luminance(a), _luminance(b)), reverse=True)
    return (high + 0.05) / (low + 0.05)


def validate_readable_type() -> None:
    """Text is large enough to read and dark enough to see, in both themes.

    The interface shipped with its body text at 12px, secondary text at 11px
    and labels at 10px, all in px so nothing grew on a large monitor, and with
    `faint` -- the colour of every label and secondary line -- at about 2.5:1.
    Each looked fine in a screenshot on a laptop. Read at arm's length on a
    27-inch screen, the product was small grey print.

    Three things are refused: a font size set in px (it cannot follow the root
    size up on a large screen), a size below 12px, and any text token below
    4.5:1 against any surface token, in the light or the dark theme.
    """
    import re

    web = ROOT / "apps" / "web"
    config = web / "tailwind.config.ts"
    css = web / "src" / "app" / "globals.css"
    if not config.exists() or not css.exists():
        return

    text = config.read_text()
    block = re.search(r"fontSize:\s*{(.*?)\n\s*},", text, re.S)
    if not block:
        errors.append(f"{config.relative_to(ROOT)}: no fontSize scale found to check")
    else:
        sizes = re.findall(r'"?([\w-]+)"?:\s*\[\s*"([\d.]+)(px|rem)"', block.group(1))
        if not sizes:
            errors.append(f"{config.relative_to(ROOT)}: fontSize scale could not be read")
        for name, value, unit in sizes:
            if unit != "rem":
                errors.append(
                    f"{config.relative_to(ROOT)}: text-{name} is {value}{unit}. Set sizes in rem "
                    "so they follow the root size up on a large monitor."
                )
            elif float(value) < MIN_TEXT_REM:
                errors.append(
                    f"{config.relative_to(ROOT)}: text-{name} is {value}rem, below the "
                    f"{MIN_TEXT_REM}rem (12px) floor."
                )

    for match in re.finditer(r"text-\[(\d+(?:\.\d+)?)px\]", "\n".join(
        p.read_text() for p in sorted((web / "src").rglob("*.tsx"))
    )):
        errors.append(
            f"apps/web/src: arbitrary text-[{match.group(1)}px] bypasses the type scale. Use a "
            "step from tailwind.config.ts."
        )

    styles = css.read_text()
    themes = {
        "light": re.search(r":root\s*{(.*?)}", styles, re.S),
        "dark": re.search(r"\.dark\s*{(.*?)}", styles, re.S),
    }
    for theme, found in themes.items():
        if not found:
            errors.append(f"{css.relative_to(ROOT)}: no {theme} theme tokens found")
            continue
        tokens = {
            name: tuple(int(v) for v in rgb)
            for name, *rgb in re.findall(r"--([\w-]+):\s*(\d+)\s+(\d+)\s+(\d+);", found.group(1))
        }
        for surface in SURFACE_TOKENS:
            for ink in TEXT_TOKENS:
                if surface not in tokens or ink not in tokens:
                    errors.append(f"{css.relative_to(ROOT)}: {theme} theme is missing --{surface} or --{ink}")
                    continue
                ratio = contrast(tokens[ink], tokens[surface])
                if ratio < MIN_CONTRAST:
                    errors.append(
                        f"{css.relative_to(ROOT)}: {theme} --{ink} on --{surface} is {ratio:.2f}:1, "
                        f"below {MIN_CONTRAST}:1. Text in this colour is hard to read."
                    )


if __name__ == "__main__":
    raise SystemExit(main())
