from pathlib import Path
import pytest
from monday.config import Config
from monday.bootstrap import build

@pytest.fixture(autouse=True)
def no_external_connections(monkeypatch):
    import ipaddress, socket
    connect=socket.socket.connect
    def local_only(sock,address):
        if sock.family in (socket.AF_INET,socket.AF_INET6):
            try: local=ipaddress.ip_address(address[0]).is_loopback
            except ValueError: local=False
            if not local: raise OSError('External connections are disabled in offline tests')
        return connect(sock,address)
    monkeypatch.setattr(socket.socket,'connect',local_only)

@pytest.fixture
def cfg(tmp_path):
    root=tmp_path/'workspace'; root.mkdir()
    return Config(roots=(root,),data_dir=tmp_path/'state',ollama_model='',laya_path='',search_url='',search_provider='wikipedia')

@pytest.fixture
def agent(cfg): return build(cfg)

@pytest.fixture
def approved(cfg): return build(cfg,approve=lambda _:True)
