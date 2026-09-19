"""Pinning a live App Platform spec to verified image digests.

These matter more than their size suggests. The script edits the spec of a
running production app, and the failure mode it exists to avoid -- wiping the
live encrypted secrets by applying the committed bootstrap spec -- takes the
deployment down rather than merely failing.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "scripts"))

from pin_app_images import pin, parse_reference  # noqa: E402

API_DIGEST = "sha256:" + "a" * 64
WEB_DIGEST = "sha256:" + "b" * 64
DIGESTS = {"aegis-api": API_DIGEST, "aegis-web": WEB_DIGEST}


def live_spec() -> dict:
    """Shaped like `doctl apps spec get` output, secrets already encrypted."""
    return {
        "name": "aegis-eval",
        "region": "nyc",
        "services": [
            {
                "name": "api",
                "dockerfile_path": "apps/api/Dockerfile",
                "source_dir": "/",
                "github": {"repo": "savankong/gov-evals", "branch": "main", "deploy_on_push": True},
                "envs": [
                    {"key": "AEGIS_ENV", "value": "production"},
                    {"key": "AEGIS_SECRET_KEY", "type": "SECRET", "value": "EV[1:abc:ciphertext]"},
                ],
                "health_check": {"http_path": "/health"},
            },
            {
                "name": "web",
                "dockerfile_path": "apps/web/Dockerfile",
                "source_dir": "apps/web",
                "github": {"repo": "savankong/gov-evals", "branch": "main"},
            },
        ],
        "workers": [
            {
                "name": "worker",
                "dockerfile_path": "apps/api/Dockerfile",
                "github": {"repo": "savankong/gov-evals", "branch": "main"},
                "run_command": "python worker.py",
            }
        ],
        "databases": [{"name": "aegis-db", "cluster_name": "aegis-pg"}],
    }


class TestReferences:
    def test_a_full_reference_yields_its_digest(self):
        assert (
            parse_reference(f"registry.digitalocean.com/aegis/aegis-api@{API_DIGEST}")
            == API_DIGEST
        )

    def test_a_bare_digest_is_accepted(self):
        assert parse_reference(API_DIGEST) == API_DIGEST

    @pytest.mark.parametrize(
        "reference",
        ["registry.digitalocean.com/aegis/aegis-api:latest", "aegis-api:v1", "sha256:short", ""],
    )
    def test_a_tag_is_refused(self, reference):
        """A tag is a mutable pointer; a signature over one says nothing later."""
        with pytest.raises(ValueError, match="digest"):
            parse_reference(reference)


class TestPinning:
    def test_every_known_component_is_pinned(self):
        spec, changed = pin(live_spec(), DIGESTS)
        assert len(changed) == 3
        assert spec["services"][0]["image"] == {
            "registry_type": "DOCR",
            "repository": "aegis-api",
            "digest": API_DIGEST,
        }
        assert spec["services"][1]["image"]["repository"] == "aegis-web"
        # The worker runs the API image with a different command.
        assert spec["workers"][0]["image"]["repository"] == "aegis-api"
        assert spec["workers"][0]["run_command"] == "python worker.py"

    def test_encrypted_secrets_survive(self):
        """The whole reason this reads the live spec instead of the repo's.

        Applying .do/app.yaml would write the literal string ${SPACES_KEY} over
        a real credential.
        """
        spec, _ = pin(live_spec(), DIGESTS)
        secret = next(
            e for e in spec["services"][0]["envs"] if e["key"] == "AEGIS_SECRET_KEY"
        )
        assert secret["value"] == "EV[1:abc:ciphertext]"
        assert secret["type"] == "SECRET"

    def test_source_build_settings_are_removed(self):
        """A component cannot both build from source and run a fixed image."""
        spec, _ = pin(live_spec(), DIGESTS)
        for component in spec["services"] + spec["workers"]:
            for key in ("github", "dockerfile_path", "source_dir"):
                assert key not in component, key

    def test_deploy_on_push_goes_with_the_github_block(self):
        """Deliberate: the workflow becomes the only path to production.

        Auto-deploying from a push would put an unsigned build back in front of
        traffic, which is the gap this closes.
        """
        spec, _ = pin(live_spec(), DIGESTS)
        assert "deploy_on_push" not in str(spec)

    def test_everything_else_is_left_alone(self):
        spec, _ = pin(live_spec(), DIGESTS)
        assert spec["databases"] == [{"name": "aegis-db", "cluster_name": "aegis-pg"}]
        assert spec["services"][0]["health_check"] == {"http_path": "/health"}
        assert spec["region"] == "nyc"

    def test_an_unknown_component_is_not_guessed_at(self):
        spec = live_spec()
        spec["services"].append({"name": "grafana", "github": {"repo": "someone/else"}})
        patched, changed = pin(spec, DIGESTS)
        assert len(changed) == 3
        assert patched["services"][-1] == {"name": "grafana", "github": {"repo": "someone/else"}}

    def test_pinning_twice_is_stable(self):
        """Re-running on an already-pinned spec must not corrupt it."""
        once, _ = pin(live_spec(), DIGESTS)
        twice, changed = pin(once, DIGESTS)
        assert len(changed) == 3
        assert twice == once

    def test_a_missing_digest_leaves_that_component_untouched(self):
        spec, changed = pin(live_spec(), {"aegis-api": API_DIGEST})
        assert len(changed) == 2
        assert "image" not in spec["services"][1]
        assert spec["services"][1]["github"]["repo"] == "savankong/gov-evals"
