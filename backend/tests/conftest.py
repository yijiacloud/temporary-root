import os
import pytest


@pytest.fixture
def mock_env(monkeypatch):
    monkeypatch.setenv("XPAD2_MOCK", "1")
    yield


@pytest.fixture
def clean_env(monkeypatch):
    monkeypatch.delenv("XPAD2_MOCK", raising=False)
    yield
