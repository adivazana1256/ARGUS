"""Shared fixtures for API integration tests.

Keeps structlog's global config + contextvars from leaking across tests so each
case is deterministic and context cleanup can be asserted honestly.
"""

from collections.abc import Iterator

import pytest
import structlog
from fastapi import FastAPI

from argus.api.app import create_app
from argus.config import load_settings


@pytest.fixture(autouse=True)
def _reset_structlog() -> Iterator[None]:
    structlog.contextvars.clear_contextvars()
    yield
    structlog.contextvars.clear_contextvars()
    structlog.reset_defaults()


@pytest.fixture
def app() -> FastAPI:
    # production => JSON logs, so request-log assertions can parse stdout.
    return create_app(load_settings(_env_file=None, environment="production"))
