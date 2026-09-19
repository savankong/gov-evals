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
