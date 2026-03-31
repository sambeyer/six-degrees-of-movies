"""
Integration test configuration.

Run against different environments:

  # Local dev server (default)
  pytest tests/integration/

  # Explicit local
  pytest tests/integration/ --base-url http://localhost:8000

  # GCP / live
  pytest tests/integration/ --base-url https://sixdegreesofmovies.com

The --base-url option can also be set via the INTEGRATION_BASE_URL environment variable.
"""

import os

import httpx
import pytest


def pytest_addoption(parser):
    parser.addoption(
        "--base-url",
        default=os.environ.get("INTEGRATION_BASE_URL", "http://localhost:8000"),
        help=(
            "Base URL of the server under test. "
            "Defaults to $INTEGRATION_BASE_URL or http://localhost:8000."
        ),
    )


@pytest.fixture(scope="session")
def base_url(request) -> str:
    return request.config.getoption("--base-url").rstrip("/")


@pytest.fixture(scope="session")
def client(base_url):
    """Session-scoped httpx client pointed at the server under test."""
    with httpx.Client(base_url=base_url, timeout=30.0, follow_redirects=True) as c:
        yield c
