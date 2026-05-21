"""Unit tests for the GPG-signing wiring (C9).

Live mode reads ``EA_GPG_SIGNING_KEY`` from the environment, threads it through
the credential bundle, and applies it to the workspace via
``GitRunner.signing_key`` right after ``configure_user`` during live branch
publication. These tests cover the env -> credential -> adapter pipeline.
"""

from __future__ import annotations


import pytest

from execution_accelerator.adapters.delivery import DeliveryAdapter
from execution_accelerator.config.credentials import load_credentials


def test_load_credentials_reads_gpg_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("EA_GPG_SIGNING_KEY", "ABCDEF1234567890")
    credentials = load_credentials()
    assert credentials.gpg_signing_key == "ABCDEF1234567890"


def test_load_credentials_handles_missing_gpg_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("EA_GPG_SIGNING_KEY", raising=False)
    credentials = load_credentials()
    assert credentials.gpg_signing_key is None


def test_delivery_adapter_stores_signing_key() -> None:
    adapter = DeliveryAdapter(gpg_signing_key="DEADBEEF")
    assert adapter.gpg_signing_key == "DEADBEEF"


def test_delivery_adapter_default_signing_key_is_none() -> None:
    adapter = DeliveryAdapter()
    assert adapter.gpg_signing_key is None
