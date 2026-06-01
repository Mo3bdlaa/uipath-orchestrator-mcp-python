"""
Environment → OrchestratorSettings loader.

Reads a `.env` file (if present) and validates that the required
variables are set for the chosen authentication strategy.
"""

import os
from dotenv import load_dotenv
from .schemas import OrchestratorSettings


def build_settings() -> OrchestratorSettings:
    """Construct validated settings from environment variables."""
    load_dotenv()

    strategy = os.getenv("UIPATH_AUTH_TYPE", "cloud-oauth").lower()
    base_url = os.getenv("UIPATH_URL")

    if not base_url:
        raise EnvironmentError("UIPATH_URL is required")

    # per-strategy validation
    if strategy == "cloud-oauth":
        _require("UIPATH_CLIENT_ID", "UIPATH_CLIENT_SECRET")
    elif strategy == "on-prem":
        _require("UIPATH_USERNAME", "UIPATH_PASSWORD")
    elif strategy == "cloud-pat":
        _require("UIPATH_PAT")
    else:
        raise ValueError(
            f"UIPATH_AUTH_TYPE='{strategy}' is not recognised. "
            "Choose from: on-prem, cloud-oauth, cloud-pat"
        )

    fid_raw = os.getenv("UIPATH_FOLDER_ID")
    folder_id = int(fid_raw) if fid_raw and fid_raw.isdigit() else None

    return OrchestratorSettings(
        auth_strategy=strategy,
        base_url=base_url,
        tenant=os.getenv("UIPATH_TENANT_NAME", "Default"),
        client_id=os.getenv("UIPATH_CLIENT_ID"),
        client_secret=os.getenv("UIPATH_CLIENT_SECRET"),
        username=os.getenv("UIPATH_USERNAME"),
        password=os.getenv("UIPATH_PASSWORD"),
        access_token=os.getenv("UIPATH_PAT"),
        folder_id=folder_id,
        skip_tls_verify=os.getenv("UIPATH_DISABLE_SSL_VERIFY") == "1",
        **_optional_float("UIPATH_REQUEST_TIMEOUT", "request_timeout"),
        **_optional_int("UIPATH_MAX_CONNECTIONS", "max_connections"),
    )


def _optional_float(env: str, field: str) -> dict:
    raw = os.getenv(env)
    try:
        return {field: float(raw)} if raw else {}
    except ValueError:
        raise EnvironmentError(f"{env} must be a number, got {raw!r}")


def _optional_int(env: str, field: str) -> dict:
    raw = os.getenv(env)
    try:
        return {field: int(raw)} if raw else {}
    except ValueError:
        raise EnvironmentError(f"{env} must be an integer, got {raw!r}")


def _require(*names: str) -> None:
    missing = [n for n in names if not os.getenv(n)]
    if missing:
        raise EnvironmentError(f"Missing required variable(s): {', '.join(missing)}")
