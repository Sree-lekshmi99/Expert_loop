from pathlib import Path
import pytest
from fastapi.testclient import TestClient

from expertloop.app import create_app
from expertloop.service import Workbench


@pytest.fixture
def workbench(tmp_path: Path):
    w = Workbench(tmp_path / "workspace")
    yield w
    w.shutdown()


@pytest.fixture
def client(tmp_path: Path):
    with TestClient(create_app(tmp_path / "api-workspace")) as c:
        yield c
