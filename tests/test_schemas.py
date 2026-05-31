"""Tests for the Pydantic domain models."""

import pytest
from pydantic import ValidationError

from uipath_mcp_python.schemas import (
    Job,
    OrchestratorSettings,
    QueueItem,
    Release,
)


def test_settings_defaults():
    cfg = OrchestratorSettings(base_url="https://x/")
    assert cfg.auth_strategy == "cloud-oauth"
    assert cfg.tenant == "Default"
    assert cfg.skip_tls_verify is False
    assert cfg.folder_id is None


def test_settings_requires_base_url():
    with pytest.raises(ValidationError):
        OrchestratorSettings()


def test_job_rejects_unknown_state():
    with pytest.raises(ValidationError):
        Job(Id=1, Key="k", State="Exploded")


def test_job_accepts_known_state_and_round_trips():
    job = Job(Id=1, Key="abc", State="Successful", ReleaseName="Invoices")
    dumped = job.model_dump()
    assert dumped["State"] == "Successful"
    assert Job(**dumped) == job


def test_queue_item_rejects_unknown_status():
    with pytest.raises(ValidationError):
        QueueItem(Id=1, QueueDefinitionId=2, Status="Cooking")


def test_queue_item_priority_defaults_to_normal():
    item = QueueItem(Id=1, QueueDefinitionId=2, Status="New")
    assert item.Priority == "Normal"


def test_release_requires_key_and_name():
    with pytest.raises(ValidationError):
        Release(ProcessKey="proc")  # missing Key and Name
