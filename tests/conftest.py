from pathlib import Path
import pytest
import torch
from fastapi.testclient import TestClient
from tracelens.data import read_incidents
from tracelens.ml.model import Predictor
from tracelens.config import Settings
from tracelens.api import create_app

ROOT=Path(__file__).resolve().parents[1]
TOKEN="test-local-token-not-a-real-credential-123456"
torch.set_num_threads(2)

@pytest.fixture(scope="session")
def root():return ROOT
@pytest.fixture(scope="session")
def case():return read_incidents(ROOT/"data/demo-incidents.jsonl")[0]
@pytest.fixture(scope="session")
def predictor():return Predictor(ROOT/"artifacts")
@pytest.fixture
def settings(tmp_path):
    return Settings(ROOT,TOKEN,f"sqlite:///{tmp_path/'test.db'}",ROOT/"artifacts",ROOT/"data/demo-incidents.jsonl")
@pytest.fixture
def client(settings):
    with TestClient(create_app(settings)) as c:yield c
@pytest.fixture
def auth():return {"Authorization":f"Bearer {TOKEN}"}
