"""Pack installation (sections 38, 39, 61).

A pack is a YAML document describing evaluations, scenarios, attacks or
framework references. Installing one is idempotent and recorded, so a program
can show which version of which pack produced a given evaluation.
"""

from __future__ import annotations

import logging
from pathlib import Path

import yaml
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..hashing import content_hash
from ..models import Evaluation, FrameworkRequirement, Pack, Scenario

log = logging.getLogger("aegis.packs")

# Where the shipped YAML packs live, found by walking up from this module.
#
# This used to be parents[4] / "packs", which is correct for the repository
# layout (apps/api/aegis/packs/loader.py -> <repo>/packs) and raises IndexError
# anywhere shallower. Installed into a container at /app/aegis/packs/loader.py
# there is no fourth parent, so the expression blew up while the module was
# still being imported and took the whole API down before it could serve
# anything -- including the health check that would have reported it.
#
# Walking up cannot overshoot in the same way. Two things make the search
# honest: this module's own directory is also called "packs", so it has to be
# skipped, and a directory only counts if it actually holds pack documents.
_MODULE_DIR = Path(__file__).resolve().parent


def _discover_pack_dir(start: Path) -> Path | None:
    """Nearest ancestor directory named 'packs' that contains pack documents."""
    for parent in start.parents:
        candidate = parent / "packs"
        if candidate == start:
            continue  # aegis/packs is this Python package, not the pack library
        if candidate.is_dir() and any(candidate.glob("*.y*ml")):
            return candidate
    return None


# Kept for callers that import it, but resolved defensively.
DEFAULT_PACK_DIR = _discover_pack_dir(_MODULE_DIR)

# Where the container image puts them, used when discovery finds nothing.
CONTAINER_PACK_DIR = Path("/packs")


def pack_directory() -> Path:
    import os

    override = os.getenv("AEGIS_PACK_DIR")
    if override:
        return Path(override)
    return DEFAULT_PACK_DIR or CONTAINER_PACK_DIR


def discover_packs(directory: Path | None = None) -> list[Path]:
    directory = directory or pack_directory()
    if not directory.exists():
        return []
    return sorted(p for p in directory.glob("*.y*ml") if p.is_file())


def load_pack_file(path: Path) -> dict:
    with open(path) as handle:
        document = yaml.safe_load(handle) or {}
    if not document.get("key"):
        raise ValueError(f"Pack {path.name} has no 'key'.")
    return document


def install_pack(db: Session, document: dict, *, source_path: str | None = None) -> dict:
    """Install or upgrade one pack. Returns a per-object count."""
    key = document["key"]
    kind = document.get("kind", "evaluation")
    version = str(document.get("version", "1.0.0"))
    digest = content_hash(document)

    pack = db.execute(select(Pack).where(Pack.key == key)).scalar_one_or_none()
    if pack and pack.content_hash == digest:
        return {"pack": key, "status": "unchanged", "version": pack.version}

    if pack is None:
        pack = Pack(key=key)
        db.add(pack)
    pack.name = document.get("name", key)
    pack.kind = kind
    pack.version = version
    pack.publisher = document.get("publisher")
    pack.description = document.get("description")
    pack.provenance = {
        **(document.get("provenance") or {}),
        "source_file": source_path,
        "installed_version": version,
    }
    pack.content_hash = digest
    db.flush()

    counts = {"evaluations": 0, "scenarios": 0, "framework_requirements": 0, "attacks": 0}

    for spec in document.get("evaluations") or []:
        counts["evaluations"] += _install_evaluation(db, spec, pack)
    for spec in document.get("scenarios") or []:
        counts["scenarios"] += _install_scenario(db, spec, pack)
    for framework in document.get("frameworks") or []:
        counts["framework_requirements"] += _install_framework(db, framework)
    counts["attacks"] = len(document.get("attacks") or [])

    db.flush()
    return {"pack": key, "status": "installed", "version": version, **counts}


def _install_evaluation(db: Session, spec: dict, pack: Pack) -> int:
    key = spec["key"]
    existing = db.execute(
        select(Evaluation).where(Evaluation.key == key, Evaluation.project_id.is_(None))
    ).scalar_one_or_none()
    evaluation = existing or Evaluation(key=key)
    if existing is None:
        db.add(evaluation)

    evaluation.name = spec.get("name", key)
    evaluation.description = spec.get("description")
    evaluation.layer = spec.get("layer", "model")
    evaluation.domain = spec.get("domain", "performance")
    evaluation.system_types = spec.get("system_types") or []
    evaluation.mission_applicability = spec.get("mission_applicability") or []
    evaluation.evaluators = spec.get("evaluators") or []
    evaluation.aggregation = spec.get("aggregation", "all_must_pass")
    evaluation.metric = spec.get("metric")
    evaluation.default_threshold = spec.get("default_threshold") or {}
    evaluation.scenario_selector = spec.get("scenario_selector") or {}
    evaluation.dataset_ref = spec.get("dataset_ref")
    evaluation.framework_refs = spec.get("framework_refs") or []
    evaluation.risk_refs = spec.get("risk_refs") or []
    evaluation.pack_key = pack.key
    evaluation.provenance = {"pack": pack.key, "pack_version": pack.version, "publisher": pack.publisher}
    evaluation.version = str(spec.get("version", pack.version))
    evaluation.content_hash = content_hash(spec)
    return 1


def _install_scenario(db: Session, spec: dict, pack: Pack) -> int:
    key = spec["key"]
    existing = db.execute(
        select(Scenario).where(Scenario.key == key, Scenario.project_id.is_(None))
    ).scalar_one_or_none()
    scenario = existing or Scenario(key=key)
    if existing is None:
        db.add(scenario)

    scenario.title = spec.get("title", key)
    scenario.mission = spec.get("mission")
    scenario.task = spec.get("task")
    scenario.context = spec.get("context")
    scenario.input = spec.get("input") or {}
    scenario.expected_behavior = spec.get("expected_behavior") or []
    scenario.prohibited_behavior = spec.get("prohibited_behavior") or []
    scenario.rubric = spec.get("rubric")
    scenario.reference_answer = spec.get("reference_answer")
    scenario.reference_sources = spec.get("reference_sources") or []
    scenario.difficulty = spec.get("difficulty", "standard")
    scenario.threat_type = spec.get("threat_type")
    scenario.tags = spec.get("tags") or []
    scenario.source = pack.key
    scenario.version = str(spec.get("version", pack.version))
    scenario.classification = spec.get("classification", "UNCLASSIFIED")
    scenario.provenance = {"pack": pack.key, "pack_version": pack.version}
    # Library scenarios ship reviewed; only generated drafts start unapproved.
    scenario.approved = bool(spec.get("approved", True))
    scenario.content_hash = content_hash(
        {"key": key, "input": scenario.input, "version": scenario.version}
    )
    return 1


def _install_framework(db: Session, framework: dict) -> int:
    name = framework["framework"]
    installed = 0
    for requirement in framework.get("requirements") or []:
        ref = requirement["ref"]
        existing = db.execute(
            select(FrameworkRequirement).where(
                FrameworkRequirement.framework == name, FrameworkRequirement.ref == ref
            )
        ).scalar_one_or_none()
        row = existing or FrameworkRequirement(framework=name, ref=ref)
        if existing is None:
            db.add(row)
        row.framework_version = framework.get("framework_version")
        row.title = requirement.get("title", ref)
        row.text = requirement.get("text")
        row.url = requirement.get("url") or framework.get("url")
        # Never flipped on by an install. Only a customer with authority over a
        # requirement may assert that an evaluation satisfies it (section 37).
        if existing is None:
            row.compliance_claimable = False
        installed += 1
    return installed


def install_all(db: Session, directory: Path | None = None) -> list[dict]:
    results = []
    for path in discover_packs(directory):
        try:
            document = load_pack_file(path)
            results.append(install_pack(db, document, source_path=path.name))
        except Exception as exc:
            log.error("Failed to install pack %s: %s", path.name, exc)
            results.append({"pack": path.stem, "status": "error", "error": str(exc)})
    return results
