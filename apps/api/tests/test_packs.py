"""Locating the evaluation packs.

These exist because the pack directory was resolved with a fixed parent count,
`Path(__file__).resolve().parents[4]`, which is right for the repository layout
and raises IndexError anywhere shallower. Installed into the container at
/app/aegis/packs/loader.py there is no fourth parent, so the expression raised
while the module was still being imported and the API could not start at all --
it never got far enough to answer the health check that would have reported it.

The second failure was quieter and worse. The image carried no packs, because
they only ever arrived through a compose bind mount that App Platform has no
equivalent for. AEGIS_PACK_DIR named a directory that did not exist, every pack
resolved to nothing, and the result was a healthy instance with no evaluations,
no scenarios and no frameworks in it.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from aegis.config import adopt_platform_env
from aegis.packs.loader import (
    CONTAINER_PACK_DIR,
    _discover_pack_dir,
    _MODULE_DIR,
    pack_directory,
)


class TestDiscovery:
    def test_a_shallow_layout_does_not_raise(self):
        """The regression. In the image the module sits at /app/aegis/packs,
        which has fewer parents than the repository layout has."""
        found = _discover_pack_dir(Path("/app/aegis/packs"))
        assert found is None  # nothing to find there, but it must not raise

    def test_no_layout_is_shallow_enough_to_raise(self):
        """Walking up terminates at the root from any depth, including the
        root itself. A fixed parent index does not."""
        for start in (Path("/"), Path("/a"), Path("/a/b"), Path("/a/b/c/d/e/f")):
            assert _discover_pack_dir(start) is None or True  # must simply not raise

    def test_skips_the_python_package_of_the_same_name(self, tmp_path):
        """aegis/packs is this module's own directory. Returning it would find
        Python source where pack documents are expected."""
        module_dir = tmp_path / "aegis" / "packs"
        module_dir.mkdir(parents=True)
        (module_dir / "loader.py").write_text("# source, not a pack")
        assert _discover_pack_dir(module_dir) is None

    def test_ignores_a_directory_holding_no_pack_documents(self, tmp_path):
        """An empty packs/ is not the pack library, and treating it as one
        would install nothing while reporting success."""
        start = tmp_path / "apps" / "api" / "aegis" / "packs"
        start.mkdir(parents=True)
        (tmp_path / "packs").mkdir()
        assert _discover_pack_dir(start) is None

    def test_finds_the_library_from_the_repository_layout(self, tmp_path):
        start = tmp_path / "apps" / "api" / "aegis" / "packs"
        start.mkdir(parents=True)
        library = tmp_path / "packs"
        library.mkdir()
        (library / "genai-baseline.yaml").write_text("key: genai-baseline\n")
        assert _discover_pack_dir(start) == library

    def test_finds_the_real_shipped_packs(self):
        """The checkout this test runs in has the real library, so discovery
        must actually locate it rather than only handling the edge cases."""
        found = _discover_pack_dir(_MODULE_DIR)
        assert found is not None
        assert found.name == "packs"
        assert list(found.glob("*.y*ml"))


class TestPackDirectory:
    def test_environment_override_wins(self, monkeypatch, tmp_path):
        monkeypatch.setenv("AEGIS_PACK_DIR", str(tmp_path))
        assert pack_directory() == tmp_path

    def test_falls_back_to_the_container_location(self, monkeypatch):
        """With no override and nothing discovered, the image's own /packs is
        the answer -- not a crash, and not a silently empty path."""
        monkeypatch.delenv("AEGIS_PACK_DIR", raising=False)
        monkeypatch.setattr("aegis.packs.loader.DEFAULT_PACK_DIR", None)
        assert pack_directory() == CONTAINER_PACK_DIR


class TestPlatformEnvironmentAdoption:
    """Where the database URL comes from when several sources offer one.

    The container image set AEGIS_DATABASE_URL to a SQLite path so that
    `docker run` works with no configuration. Adoption treats an AEGIS_* value
    as the operator's explicit choice and lets it win, and an image ENV is
    indistinguishable from one -- so on App Platform the injected DATABASE_URL
    was ignored, the API fell back to SQLite, tripped its own
    ephemeral-filesystem guard and refused to start. Every deploy failed with
    DeployContainerExitNonZero.
    """

    def test_platform_url_beats_the_image_default(self):
        env = {
            "AEGIS_DEFAULT_DATABASE_URL": "sqlite:////data/aegis.db",
            "DATABASE_URL": "postgresql://u:p@host:25060/db",
        }
        adopt_platform_env(env)
        assert env["AEGIS_DATABASE_URL"] == "postgresql+psycopg://u:p@host:25060/db"

    def test_operator_url_beats_both(self):
        env = {
            "AEGIS_DATABASE_URL": "postgresql+psycopg://chosen/db",
            "AEGIS_DEFAULT_DATABASE_URL": "sqlite:////data/aegis.db",
            "DATABASE_URL": "postgresql://platform/db",
        }
        adopt_platform_env(env)
        assert env["AEGIS_DATABASE_URL"] == "postgresql+psycopg://chosen/db"

    def test_image_default_applies_when_nothing_else_is_offered(self):
        """`docker run` with no configuration still has to work."""
        env = {"AEGIS_DEFAULT_DATABASE_URL": "sqlite:////data/aegis.db"}
        adopt_platform_env(env)
        assert env["AEGIS_DATABASE_URL"] == "sqlite:////data/aegis.db"

    def test_the_image_never_sets_the_operator_variable(self):
        """The Dockerfile setting AEGIS_DATABASE_URL is the defect itself."""
        from pathlib import Path

        dockerfile = Path(__file__).resolve().parents[1] / "Dockerfile"
        for line in dockerfile.read_text().splitlines():
            stripped = line.strip()
            if stripped.startswith("ENV") or stripped.startswith("AEGIS_"):
                assert "AEGIS_DATABASE_URL=" not in stripped, (
                    "The image must not set AEGIS_DATABASE_URL; it outranks the "
                    "DATABASE_URL a managed host injects."
                )


class TestBootstrapGuardScope:
    """Who has to supply a bootstrap password.

    The production guard demanded a non-default AEGIS_BOOTSTRAP_PASSWORD from
    every process. The worker executes campaigns and authenticates nobody, so
    it is deliberately given none -- handing a credential to a component with
    no use for it is worse than not requiring one. It therefore inherited the
    shipped default, tripped the guard and exited non-zero on every deploy,
    while the API beside it served correctly. The failure surfaced only as
    DeployContainerExitNonZero with no component named.
    """

    def _settings(self, **kw):
        from aegis.config import Settings

        base = dict(env="production", secret_key="x" * 40, seed_demo=False)
        base.update(kw)
        return Settings(**base)

    def test_a_process_that_bootstraps_still_needs_a_real_password(self):
        from aegis.config import InsecureConfiguration, _validate

        settings = self._settings(bootstrap_local_admin=True)
        with pytest.raises(InsecureConfiguration, match="AEGIS_BOOTSTRAP_PASSWORD"):
            _validate(settings)

    def test_a_process_that_bootstraps_nothing_does_not(self):
        from aegis.config import _validate

        _validate(self._settings(bootstrap_local_admin=False))  # must not raise

    def test_the_opt_out_does_not_weaken_the_secret_key_guard(self):
        """Switching off local accounts must not switch off everything else."""
        from aegis.config import DEFAULT_SECRET, InsecureConfiguration, _validate

        settings = self._settings(bootstrap_local_admin=False, secret_key=DEFAULT_SECRET)
        with pytest.raises(InsecureConfiguration, match="AEGIS_SECRET_KEY"):
            _validate(settings)


class TestScenarioExpertise:
    """A scenario pack is where an expert program declares who may judge each
    case. The loader once dropped `required_expertise`, so every installed
    scenario was undeclared and an evaluation with `require_expertise` counted
    a review from any discipline -- the gate was on, with nothing behind it.
    """

    @staticmethod
    def _pack(version: str, **scenario) -> dict:
        return {
            "key": "expertise-test",
            "kind": "scenario",
            "version": version,
            "scenarios": [{"key": "exp-case", "title": "Case", **scenario}],
        }

    @staticmethod
    def _scenario(db):
        from sqlalchemy import select

        from aegis.models import Scenario

        return db.execute(select(Scenario).where(Scenario.key == "exp-case")).scalar_one()

    def test_declared_expertise_is_installed(self, db):
        from aegis.packs.loader import install_pack

        install_pack(db, self._pack("1.0.0", required_expertise=["acquisition"]))
        assert self._scenario(db).required_expertise == ["acquisition"]

    def test_a_single_discipline_written_as_a_string_is_not_split(self, db):
        """`required_expertise: acquisition` must not become eleven letters."""
        from aegis.packs.loader import install_pack

        install_pack(db, self._pack("1.0.0", required_expertise="acquisition"))
        assert self._scenario(db).required_expertise == ["acquisition"]

    def test_removing_the_declaration_clears_it_on_upgrade(self, db):
        """An upgrade that drops the requirement must not leave the old one
        silently enforced."""
        from aegis.packs.loader import install_pack

        install_pack(db, self._pack("1.0.0", required_expertise=["acquisition"]))
        install_pack(db, self._pack("1.0.1"))
        assert self._scenario(db).required_expertise == []
