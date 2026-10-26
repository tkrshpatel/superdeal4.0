import os
from pathlib import Path
import pytest
from runtime_env import load_env


def test_loads_values_like_telegram_runner(tmp_path, monkeypatch):
    path = tmp_path / '.env'
    path.write_text('\ufeff# settings\nMONGODB_URI="mongodb://example:27017/?replicaSet=rs0"\nMONGODB_DATABASE=custom_deals\nSUPERDEAL_API_PORT=8123\nINVALID LINE\n',encoding='utf-8')
    for key in ('MONGODB_URI','MONGODB_DATABASE','SUPERDEAL_API_PORT'):
        monkeypatch.delenv(key, raising=False)
    load_env(path)
    assert os.environ['MONGODB_DATABASE']=='custom_deals'
    assert os.environ['SUPERDEAL_API_PORT']=='8123'
    assert os.environ['MONGODB_URI']=='mongodb://example:27017/?replicaSet=rs0'


def test_terminal_settings_are_preserved(tmp_path, monkeypatch):
    path=tmp_path/'.env';path.write_text('MONGODB_DATABASE=from_file\n')
    monkeypatch.setenv('MONGODB_DATABASE','from_terminal')
    load_env(path)
    assert os.environ['MONGODB_DATABASE']=='from_terminal'


def test_missing_env_is_optional(tmp_path):
    load_env(tmp_path/'missing.env')


def test_connect_loads_dotenv_before_selecting_mongo(tmp_path, monkeypatch):
    import backend
    import runtime_env
    path=tmp_path/'.env';path.write_text('MONGODB_URI=mongodb://example:27017\nMONGODB_DATABASE=expected_db\n')
    monkeypatch.delenv('MONGODB_URI',raising=False);monkeypatch.delenv('MONGODB_DATABASE',raising=False)
    monkeypatch.setattr(runtime_env,'load_env',lambda:load_env(path))
    class Client:
        admin=None
        def __init__(self,uri,**kwargs):
            assert uri=='mongodb://example:27017';self.admin=self
        def command(self,value): assert value=='ping'
        def __getitem__(self,name):
            assert name=='expected_db';return 'selected_db'
    monkeypatch.setattr(backend,'MongoClient',Client)
    assert backend.connect().db=='selected_db'


def test_api_uses_env_host_and_port_without_overriding(tmp_path,monkeypatch):
    import api
    import runtime_env
    path=tmp_path/'.env';path.write_text('SUPERDEAL_API_HOST=127.0.0.1\nSUPERDEAL_API_PORT=8123\nSUPERDEAL_ADMIN_TOKEN=test_only\n')
    for key in ('SUPERDEAL_API_HOST','SUPERDEAL_API_PORT','SUPERDEAL_ADMIN_TOKEN'):
        monkeypatch.delenv(key,raising=False)
    monkeypatch.setattr(runtime_env,'load_env',lambda:load_env(path))
    backend=type('Backend',(),{'setup_public':lambda self:None})()
    monkeypatch.setattr(api,'connect',lambda:backend)
    class StopServer(Exception): pass
    class Server:
        def __init__(self,address,handler): assert address==('127.0.0.1',8123)
        def serve_forever(self): raise StopServer()
    monkeypatch.setattr(api,'BoundedHTTPServer',Server)
    with pytest.raises(StopServer): api.main()
