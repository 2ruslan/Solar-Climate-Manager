"""Fixtures for the real HA integration test harness."""

import pytest


@pytest.fixture(autouse=True)
def custom_integrations(enable_custom_integrations):
    yield
