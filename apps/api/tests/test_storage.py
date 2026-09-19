"""Evidence storage and the classification ceiling.

The S3 path used to be excluded from coverage entirely, which is how it came to
be missing the region that SigV4 signing needs. It is exercised here against a
recording fake, so the request the backend actually builds is asserted rather
than assumed.
"""

from __future__ import annotations

import pytest

from aegis.classification import describe, enforce, exceeds_ceiling, rank
from aegis.config import InsecureConfiguration, Settings, _validate
from aegis.enums import Classification
from aegis.storage import FileBackend, S3Backend, StorageError, build_backend


class FakeS3Client:
    """Records calls and behaves like the slice of the S3 API we use."""

    def __init__(self, fail_on: str | None = None) -> None:
        self.puts: list[dict] = []
        self.deletes: list[dict] = []
        self.objects: dict[tuple[str, str], bytes] = {}
        self.fail_on = fail_on

    def put_object(self, **kwargs):
        if self.fail_on == "put":
            raise RuntimeError("AccessDenied")
        self.puts.append(kwargs)
        self.objects[(kwargs["Bucket"], kwargs["Key"])] = kwargs["Body"]
        return {}

    def get_object(self, **kwargs):
        if self.fail_on == "get":
            raise RuntimeError("NoSuchKey")
        body = self.objects[(kwargs["Bucket"], kwargs["Key"])]

        class _Body:
            @staticmethod
            def read():
                return body

        return {"Body": _Body}

    def delete_object(self, **kwargs):
        self.deletes.append(kwargs)
        self.objects.pop((kwargs["Bucket"], kwargs["Key"]), None)
        return {}


def spaces_backend(fake: FakeS3Client, **overrides) -> S3Backend:
    """An S3Backend configured the way a DigitalOcean Space is."""
    backend = S3Backend(
        **{
            "bucket": "aegis-evidence",
            "endpoint_url": "https://nyc3.digitaloceanspaces.com",
            "region": "nyc3",
            "access_key": "key",
            "secret_key": "secret",
            **overrides,
        }
    )
    backend._client = fake
    return backend


class TestFileBackend:
    def test_round_trip(self, tmp_path):
        backend = FileBackend(str(tmp_path))
        uri = backend.put("runs/a/result.json", b'{"a":1}', "application/json")
        assert uri.startswith("file://")
        assert backend.get(uri) == b'{"a":1}'

    def test_check_reports_writable(self, tmp_path):
        assert FileBackend(str(tmp_path)).check()["writable"] is True

    def test_check_reports_an_unwritable_path(self, tmp_path):
        blocked = tmp_path / "file-not-a-dir"
        blocked.write_text("x")
        result = FileBackend(str(blocked / "nested")).check()
        assert result["writable"] is False
        assert "error" in result

    def test_probe_file_is_cleaned_up(self, tmp_path):
        backend = FileBackend(str(tmp_path))
        backend.check()
        assert not (tmp_path / ".aegis-write-probe").exists()


class TestS3Backend:
    def test_put_and_get_round_trip(self):
        fake = FakeS3Client()
        backend = spaces_backend(fake)
        uri = backend.put("runs/a/result.json", b"payload", "application/json")
        assert uri == "s3://aegis-evidence/runs/a/result.json"
        assert backend.get(uri) == b"payload"

    def test_objects_are_written_private(self):
        """Evidence is never world-readable, whatever the bucket default is."""
        fake = FakeS3Client()
        spaces_backend(fake).put("k", b"x", "application/json")
        assert fake.puts[0]["ACL"] == "private"

    def test_content_type_is_preserved(self):
        fake = FakeS3Client()
        spaces_backend(fake).put("r.md", b"# report", "text/markdown")
        assert fake.puts[0]["ContentType"] == "text/markdown"

    def test_prefix_scopes_keys(self):
        """One bucket can hold several deployments without collision."""
        fake = FakeS3Client()
        backend = spaces_backend(fake, prefix="staging")
        uri = backend.put("runs/a.json", b"x", "application/json")
        assert uri == "s3://aegis-evidence/staging/runs/a.json"
        assert fake.puts[0]["Key"] == "staging/runs/a.json"

    def test_prefix_slashes_are_normalised(self):
        fake = FakeS3Client()
        backend = spaces_backend(fake, prefix="/staging/")
        backend.put("a.json", b"x", "application/json")
        assert fake.puts[0]["Key"] == "staging/a.json"

    def test_check_probes_and_cleans_up(self):
        fake = FakeS3Client()
        result = spaces_backend(fake, prefix="staging").check()
        assert result["writable"] is True
        assert result["region"] == "nyc3"
        assert fake.puts[0]["Key"] == "staging/.aegis-write-probe"
        # The probe must not be left behind as a stray object.
        assert fake.deletes[0]["Key"] == "staging/.aegis-write-probe"
        assert fake.objects == {}

    def test_check_reports_a_failure_rather_than_raising(self):
        """Startup asks whether the store works; it must get an answer."""
        result = spaces_backend(FakeS3Client(fail_on="put")).check()
        assert result["writable"] is False
        assert "AccessDenied" in result["error"]

    def test_write_failure_names_the_object(self):
        backend = spaces_backend(FakeS3Client(fail_on="put"))
        with pytest.raises(StorageError) as exc:
            backend.put("runs/a.json", b"x", "application/json")
        assert "s3://aegis-evidence/runs/a.json" in str(exc.value)

    def test_a_bucket_is_required(self):
        with pytest.raises(StorageError) as exc:
            S3Backend(bucket="")
        assert "AEGIS_S3_BUCKET" in str(exc.value)

    def test_client_is_built_once_and_reused(self):
        """Client construction resolves credentials and loads service models.
        Repeating it per artifact would dominate the cost of a campaign."""
        backend = S3Backend(bucket="b", region="nyc3")
        calls = {"n": 0}

        def build():
            calls["n"] += 1
            return FakeS3Client()

        backend._build_client = build
        backend.client()
        backend.client()
        backend.client()
        assert calls["n"] == 1

    def test_signing_region_reaches_the_client(self):
        """A region mismatch surfaces as an opaque SignatureDoesNotMatch, so
        the value must actually be passed through."""
        backend = S3Backend(bucket="b", endpoint_url="https://ams3.digitaloceanspaces.com",
                            region="ams3", access_key="k", secret_key="s")
        client = backend.client()
        assert client.meta.region_name == "ams3"
        assert "ams3.digitaloceanspaces.com" in client.meta.endpoint_url

    def test_path_addressing_is_used(self):
        """Spaces and MinIO serve paths, not virtual-hosted subdomains."""
        backend = S3Backend(bucket="b", region="nyc3", access_key="k", secret_key="s")
        assert backend.client().meta.config.s3["addressing_style"] == "path"


class TestBackendSelection:
    def test_file_is_the_default(self, tmp_path):
        backend = build_backend(Settings(evidence_path=str(tmp_path)))
        assert backend.name == "file"

    def test_s3_is_built_from_settings(self):
        backend = build_backend(
            Settings(
                evidence_backend="s3",
                s3_bucket="aegis-evidence",
                s3_region="sfo3",
                s3_endpoint_url="https://sfo3.digitaloceanspaces.com",
            )
        )
        assert backend.name == "s3"
        assert backend.region == "sfo3"

    def test_an_unknown_backend_is_refused(self):
        with pytest.raises(StorageError) as exc:
            build_backend(Settings(evidence_backend="dropbox"))
        assert "Unknown evidence backend" in str(exc.value)


class TestEphemeralFilesystemGuard:
    """Losing evidence quietly is the worst failure this product can have."""

    def _settings(self, **overrides):
        return Settings(
            env="production",
            secret_key="k" * 48,
            bootstrap_password="a-real-password",
            seed_demo=False,
            ephemeral_filesystem=True,
            **overrides,
        )

    def test_sqlite_on_an_ephemeral_filesystem_is_refused(self):
        with pytest.raises(InsecureConfiguration) as exc:
            _validate(self._settings(evidence_backend="s3", s3_bucket="b"))
        assert "database is SQLite" in str(exc.value)

    def test_file_evidence_on_an_ephemeral_filesystem_is_refused(self):
        with pytest.raises(InsecureConfiguration) as exc:
            _validate(
                self._settings(
                    database_url="postgresql+psycopg://u:p@host/db", evidence_backend="file"
                )
            )
        assert "evidence backend is 'file'" in str(exc.value)

    def test_managed_database_and_object_storage_is_accepted(self):
        _validate(
            self._settings(
                database_url="postgresql+psycopg://u:p@host/db",
                evidence_backend="s3",
                s3_bucket="aegis-evidence",
            )
        )

    def test_a_durable_host_is_left_alone(self):
        """A droplet with a real volume keeps SQLite and file evidence."""
        _validate(
            Settings(
                env="production",
                secret_key="k" * 48,
                bootstrap_password="a-real-password",
                seed_demo=False,
                ephemeral_filesystem=False,
            )
        )


class TestClassificationCeiling:
    def test_rank_orders_the_vocabulary(self):
        assert rank(Classification.UNCLASSIFIED) < rank(Classification.CUI)
        assert rank(Classification.CUI) < rank(Classification.SECRET)
        assert rank(Classification.SECRET) < rank(Classification.TOP_SECRET)

    def test_rank_reads_through_a_caveat(self):
        assert rank("SECRET//NOFORN") == rank(Classification.SECRET)
        assert rank("TOP SECRET//SI//TK") == rank(Classification.TOP_SECRET)

    def test_no_ceiling_permits_everything(self, monkeypatch):
        monkeypatch.setattr("aegis.classification.ceiling", lambda: None)
        assert exceeds_ceiling(Classification.TOP_SECRET) is False
        assert enforce(Classification.SECRET) == Classification.SECRET

    def test_a_ceiling_refuses_anything_above_it(self, monkeypatch):
        from fastapi import HTTPException

        monkeypatch.setattr("aegis.classification.ceiling", lambda: Classification.UNCLASSIFIED)
        assert exceeds_ceiling(Classification.CUI) is True
        with pytest.raises(HTTPException) as exc:
            enforce(Classification.CUI)
        assert exc.value.status_code == 422
        assert "UNCLASSIFIED" in exc.value.detail

    def test_a_ceiling_permits_its_own_level_and_below(self, monkeypatch):
        monkeypatch.setattr("aegis.classification.ceiling", lambda: Classification.CUI)
        assert enforce(Classification.CUI) == Classification.CUI
        assert enforce(Classification.UNCLASSIFIED) == Classification.UNCLASSIFIED
        assert exceeds_ceiling(Classification.SECRET) is True

    def test_describe_lists_what_is_permitted(self, monkeypatch):
        monkeypatch.setattr("aegis.classification.ceiling", lambda: Classification.CUI)
        described = describe()
        assert described["max_classification"] == Classification.CUI
        assert described["permitted"] == [Classification.UNCLASSIFIED, Classification.CUI]

    def test_an_unknown_ceiling_is_refused_at_startup(self):
        with pytest.raises(InsecureConfiguration) as exc:
            _validate(
                Settings(
                    env="production",
                    secret_key="k" * 48,
                    bootstrap_password="a-real-password",
                    seed_demo=False,
                    max_classification="SORT OF SECRET",
                )
            )
        assert "not a known marking" in str(exc.value)


class TestPlatformEnvironment:
    """Managed hosts inject connection strings under their own names.

    Getting this wrong fails at startup with a driver error that says nothing
    about the cause, so each translation is pinned.
    """

    def test_digitalocean_postgres_url_names_the_psycopg_driver(self):
        from aegis.config import normalize_database_url

        assert normalize_database_url(
            "postgresql://user:pass@db-postgresql-nyc3-1.b.db.ondigitalocean.com:25060/aegis"
        ) == (
            "postgresql+psycopg://user:pass@db-postgresql-nyc3-1.b.db.ondigitalocean.com"
            ":25060/aegis"
        )

    def test_legacy_postgres_scheme_is_handled(self):
        from aegis.config import normalize_database_url

        assert normalize_database_url("postgres://u:p@host/db") == "postgresql+psycopg://u:p@host/db"

    def test_an_explicit_driver_is_left_alone(self):
        from aegis.config import normalize_database_url

        url = "postgresql+asyncpg://u:p@host/db"
        assert normalize_database_url(url) == url

    def test_sqlite_is_untouched(self):
        from aegis.config import normalize_database_url

        assert normalize_database_url("sqlite:///./data/aegis.db") == "sqlite:///./data/aegis.db"

    def test_platform_vars_are_adopted(self):
        from aegis.config import adopt_platform_env

        env = {
            "DATABASE_URL": "postgresql://u:p@host:25060/aegis",
            "REDIS_URL": "rediss://default:p@valkey.ondigitalocean.com:25061",
        }
        adopted = adopt_platform_env(env)
        assert env["AEGIS_DATABASE_URL"] == "postgresql+psycopg://u:p@host:25060/aegis"
        assert env["AEGIS_REDIS_URL"] == "rediss://default:p@valkey.ondigitalocean.com:25061"
        assert adopted == {"AEGIS_DATABASE_URL": "DATABASE_URL", "AEGIS_REDIS_URL": "REDIS_URL"}

    def test_an_explicit_setting_wins(self):
        """An operator who names a URL means it."""
        from aegis.config import adopt_platform_env

        env = {
            "AEGIS_DATABASE_URL": "postgresql+psycopg://chosen/db",
            "DATABASE_URL": "postgresql://injected/db",
        }
        adopt_platform_env(env)
        assert env["AEGIS_DATABASE_URL"] == "postgresql+psycopg://chosen/db"

    def test_absent_platform_vars_change_nothing(self):
        from aegis.config import adopt_platform_env

        env: dict = {}
        assert adopt_platform_env(env) == {}
        assert env == {}
