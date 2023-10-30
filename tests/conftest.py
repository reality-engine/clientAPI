import pytest
from fastapi.testclient import TestClient

from reapi import __version__
from reapi.main import app


@pytest.fixture
def version():
    return __version__


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c
