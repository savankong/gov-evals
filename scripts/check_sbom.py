#!/usr/bin/env python3
"""Check that a generated SBOM actually describes the component it names.

A bill of materials that resolved nothing still writes a well-formed file and
still exits zero, which makes a supply-chain job look green while recording
nothing. That is the same failure this product refuses everywhere else: a run
that judged nothing is NOT EVALUATED, never a pass.

So this asserts three things rather than trusting the generator:

  * the document is CycloneDX and lists at least one component,
  * every component carries a name, since an unnamed entry cannot be looked up
    against an advisory feed later,
  * a dependency that must be present is present, which is what catches a
    scanner pointed at the wrong directory. That case is the dangerous one: it
    produces a plausible SBOM for the wrong thing.

Runs in CI with no third-party import, like scripts/validate_packs.py.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

# A direct dependency each component cannot be built without. If the scanner is
# aimed at the wrong directory, the SBOM is still valid and still non-empty --
# this is the assertion that notices.
EXPECTED: dict[str, str] = {
    "api": "fastapi",
    "sdk": "httpx",
    "web": "next",
}


def check(path: Path) -> list[str]:
    problems: list[str] = []
    try:
        doc = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        return [f"{path}: could not be read as JSON: {exc}"]

    if doc.get("bomFormat") != "CycloneDX":
        problems.append(f"{path}: bomFormat is {doc.get('bomFormat')!r}, expected 'CycloneDX'")

    components = doc.get("components") or []
    if not components:
        problems.append(
            f"{path}: lists no components. An empty bill of materials records nothing "
            "and must not pass."
        )
        return problems

    unnamed = sum(1 for c in components if not c.get("name"))
    if unnamed:
        problems.append(
            f"{path}: {unnamed} component(s) have no name and could not be matched "
            "against an advisory feed."
        )

    expected = EXPECTED.get(path.name.split(".")[0])
    if expected:
        names = {str(c.get("name", "")).lower() for c in components}
        if expected not in names:
            problems.append(
                f"{path}: {len(components)} components but none named {expected!r}. "
                "The scanner was probably pointed at the wrong directory."
            )

    if not problems:
        print(f"{path.name}: {len(components)} components")
    return problems


def main(argv: list[str]) -> int:
    paths = [Path(a) for a in argv[1:]]
    if not paths:
        print("usage: check_sbom.py <sbom.cdx.json> [...]", file=sys.stderr)
        return 2

    missing = [p for p in paths if not p.is_file()]
    if missing:
        for p in missing:
            print(f"error: {p} does not exist", file=sys.stderr)
        return 1

    problems = [problem for path in paths for problem in check(path)]
    for problem in problems:
        print(f"error: {problem}", file=sys.stderr)
    if problems:
        print(f"\n{len(problems)} problem(s).", file=sys.stderr)
        return 1

    print(f"{len(paths)} SBOM(s) valid.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
