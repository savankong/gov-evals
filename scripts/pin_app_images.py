#!/usr/bin/env python3
"""Point a live App Platform spec at images that have been signed and verified.

Why this reads the *live* spec rather than `.do/app.yaml`:

`.do/app.yaml` is the bootstrap spec. Its seven `type: SECRET` entries hold
placeholders like `${SPACES_KEY}`, because a real credential must never be
committed. Applying that file to a running app with `doctl apps update --spec`
would overwrite the live encrypted secrets with those literal strings and take
the deployment down -- the object store, the signing key and the bootstrap
password all at once.

`doctl apps spec get` returns secrets as encrypted `EV[1:...]` values that
round-trip safely. So the deploy pipeline fetches what is actually running,
changes only the image references, and applies that back. Everything this
script does not understand, it does not touch.

The change itself: a component built from GitHub source becomes a component
that runs a specific image by digest. That is the difference between "App
Platform built something from this commit" and "App Platform is running the
artifact this pipeline signed and verified".
"""

from __future__ import annotations

import argparse
import re
import sys

import yaml

# Which repository each component runs. The API and the worker share an image;
# they differ only in the command App Platform gives it.
COMPONENT_REPOSITORIES = {
    "api": "aegis-api",
    "worker": "aegis-api",
    "web": "aegis-web",
}

DIGEST = re.compile(r"^sha256:[0-9a-f]{64}$")

# Keys that describe building from source. A component that runs a prebuilt
# image must carry none of them, or App Platform has two conflicting answers to
# "where does this come from".
SOURCE_KEYS = ("github", "git", "gitlab", "dockerfile_path", "source_dir", "build_command")


def parse_reference(reference: str) -> str:
    """Take `registry/repo@sha256:...` or a bare digest, return the digest."""
    digest = reference.rsplit("@", 1)[-1].strip()
    if not DIGEST.match(digest):
        raise ValueError(
            f"{reference!r} does not end in a sha256 digest. Pin by digest, never by tag: "
            "a tag is a mutable pointer, so a signature over one says nothing about what it "
            "later resolves to."
        )
    return digest


def pin(spec: dict, digests: dict[str, str], registry: str | None = None) -> tuple[dict, list[str]]:
    """Return the spec with each known component pinned, and what changed.

    Unknown components are left exactly as they are rather than guessed at.
    """
    changed: list[str] = []

    for section in ("services", "workers", "jobs", "static_sites"):
        for component in spec.get(section) or []:
            name = component.get("name")
            repository = COMPONENT_REPOSITORIES.get(name)
            if repository is None:
                continue
            digest = digests.get(repository)
            if digest is None:
                continue

            for key in SOURCE_KEYS:
                component.pop(key, None)

            image = {
                "registry_type": "DOCR",
                "repository": repository,
                "digest": digest,
            }
            if registry:
                image["registry"] = registry
            component["image"] = image
            changed.append(f"{section[:-1]} {name} -> {repository}@{digest[:19]}…")

    return spec, changed


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("spec", help="Live spec from `doctl apps spec get <id> --format yaml`")
    parser.add_argument("--api", required=True, help="Verified aegis-api image reference")
    parser.add_argument("--web", required=True, help="Verified aegis-web image reference")
    parser.add_argument("--registry", default=None, help="DOCR registry name, when required")
    parser.add_argument("--out", default="-", help="Where to write the patched spec")
    args = parser.parse_args()

    try:
        digests = {
            "aegis-api": parse_reference(args.api),
            "aegis-web": parse_reference(args.web),
        }
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    with open(args.spec) as handle:
        spec = yaml.safe_load(handle)
    if not isinstance(spec, dict):
        print("error: the spec did not parse as a mapping.", file=sys.stderr)
        return 1

    spec, changed = pin(spec, digests, args.registry)
    if not changed:
        # Silence here would mean applying an unchanged spec and reporting
        # success, which is the shape of a control that has stopped working.
        print(
            "error: no component was pinned. Expected one of "
            f"{sorted(COMPONENT_REPOSITORIES)} in the spec.",
            file=sys.stderr,
        )
        return 1

    rendered = yaml.safe_dump(spec, sort_keys=False, width=100)
    if args.out == "-":
        sys.stdout.write(rendered)
    else:
        with open(args.out, "w") as handle:
            handle.write(rendered)

    for line in changed:
        print(f"pinned: {line}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
