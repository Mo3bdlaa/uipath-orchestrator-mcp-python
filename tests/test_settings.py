"""Tests for the environment -> settings loader."""

import pytest

from uipath_mcp_python import settings as settings_mod
from uipath_mcp_python.settings import build_settings

UIPATH_VARS = [
    "UIPATH_AUTH_TYPE", "UIPATH_URL", "UIPATH_TENANT_NAME",
    "UIPATH_CLIENT_ID", "UIPATH_CLIENT_SECRET",
    "UIPATH_USERNAME", "UIPATH_PASSWORD", "UIPATH_PAT",
    "UIPATH_FOLDER_ID", "UIPATH_DISABLE_SSL_VERIFY",
]


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    """Isolate every test from the host environment and any local .env file."""
    monkeypatch.setattr(settings_mod, "load_dotenv", lambda *a, **k: False)
    for var in UIPATH_VARS:
        monkeypatch.delenv(var, raising=False)


def test_cloud_oauth_happy_path(monkeypatch):
    monkeypatch.setenv("UIPATH_URL", "https://cloud.uipath.com/acme/Default/")
    monkeypatch.setenv("UIPATH_CLIENT_ID", "cid")
    monkeypatch.setenv("UIPATH_CLIENT_SECRET", "secret")

    cfg = build_settings()

    assert cfg.auth_strategy == "cloud-oauth"  # default
    assert cfg.tenant == "Default"  # default
    assert cfg.client_id == "cid"
    assert cfg.client_secret == "secret"


def test_on_prem_happy_path(monkeypatch):
    monkeypatch.setenv("UIPATH_AUTH_TYPE", "on-prem")
    monkeypatch.setenv("UIPATH_URL", "https://orch.corp.internal/")
    monkeypatch.setenv("UIPATH_USERNAME", "admin")
    monkeypatch.setenv("UIPATH_PASSWORD", "pw")

    cfg = build_settings()

    assert cfg.auth_strategy == "on-prem"
    assert cfg.username == "admin"
    assert cfg.password == "pw"


def test_cloud_pat_happy_path(monkeypatch):
    monkeypatch.setenv("UIPATH_AUTH_TYPE", "cloud-pat")
    monkeypatch.setenv("UIPATH_URL", "https://cloud.uipath.com/acme/Default/")
    monkeypatch.setenv("UIPATH_PAT", "rt_token")

    cfg = build_settings()

    assert cfg.auth_strategy == "cloud-pat"
    assert cfg.access_token == "rt_token"


def test_auth_type_is_lowercased(monkeypatch):
    monkeypatch.setenv("UIPATH_AUTH_TYPE", "Cloud-OAuth")
    monkeypatch.setenv("UIPATH_URL", "https://x/")
    monkeypatch.setenv("UIPATH_CLIENT_ID", "cid")
    monkeypatch.setenv("UIPATH_CLIENT_SECRET", "secret")

    assert build_settings().auth_strategy == "cloud-oauth"


def test_missing_url_raises(monkeypatch):
    monkeypatch.setenv("UIPATH_CLIENT_ID", "cid")
    monkeypatch.setenv("UIPATH_CLIENT_SECRET", "secret")

    with pytest.raises(EnvironmentError, match="UIPATH_URL"):
        build_settings()


def test_missing_oauth_credentials_raises(monkeypatch):
    monkeypatch.setenv("UIPATH_URL", "https://x/")
    monkeypatch.setenv("UIPATH_CLIENT_ID", "cid")  # secret missing

    with pytest.raises(EnvironmentError, match="UIPATH_CLIENT_SECRET"):
        build_settings()


def test_unknown_strategy_raises(monkeypatch):
    monkeypatch.setenv("UIPATH_AUTH_TYPE", "magic")
    monkeypatch.setenv("UIPATH_URL", "https://x/")

    with pytest.raises(ValueError, match="not recognised"):
        build_settings()


def test_numeric_folder_id_parsed(monkeypatch):
    monkeypatch.setenv("UIPATH_URL", "https://x/")
    monkeypatch.setenv("UIPATH_CLIENT_ID", "cid")
    monkeypatch.setenv("UIPATH_CLIENT_SECRET", "secret")
    monkeypatch.setenv("UIPATH_FOLDER_ID", "42")

    assert build_settings().folder_id == 42


def test_non_numeric_folder_id_becomes_none(monkeypatch):
    monkeypatch.setenv("UIPATH_URL", "https://x/")
    monkeypatch.setenv("UIPATH_CLIENT_ID", "cid")
    monkeypatch.setenv("UIPATH_CLIENT_SECRET", "secret")
    monkeypatch.setenv("UIPATH_FOLDER_ID", "not-a-number")

    assert build_settings().folder_id is None


def test_disable_ssl_verify_flag(monkeypatch):
    monkeypatch.setenv("UIPATH_URL", "https://x/")
    monkeypatch.setenv("UIPATH_CLIENT_ID", "cid")
    monkeypatch.setenv("UIPATH_CLIENT_SECRET", "secret")
    monkeypatch.setenv("UIPATH_DISABLE_SSL_VERIFY", "1")

    assert build_settings().skip_tls_verify is True
