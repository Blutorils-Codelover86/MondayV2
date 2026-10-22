from pathlib import Path
import pytest
from monday.config import Config
from monday.bootstrap import build

@pytest.fixture
def cfg(tmp_path):
    root=tmp_path/'workspace'; root.mkdir()
    return Config(roots=(root,),data_dir=tmp_path/'state',ollama_model='',laya_path='',search_url='',search_provider='wikipedia')

@pytest.fixture
def agent(cfg): return build(cfg)

@pytest.fixture
def approved(cfg): return build(cfg,approve=lambda _:True)
