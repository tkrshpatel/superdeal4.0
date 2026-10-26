"""Exercise actual Caddy -> HTTP API boundaries with a private synthetic backend."""
import importlib.util
import json
import os
from pathlib import Path
import secrets
import shutil
import socket
import subprocess
import threading
import time
from urllib.error import HTTPError
from urllib.request import Request, urlopen
import mongomock
import pytest
from api import make_handler
from http_security import BoundedHTTPServer

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('superdeal_hosting',ROOT/'scripts'/'hosting.py')
hosting=importlib.util.module_from_spec(spec);spec.loader.exec_module(hosting)


def test_hosting_uses_existing_api_settings_without_printing_credentials(monkeypatch,tmp_path):
    (tmp_path/'app'/'dist').mkdir(parents=True)
    (tmp_path/'app'/'dist'/'index.html').write_text('<html>test</html>')
    values={'SUPERDEAL_DOMAIN':'deals.example.com','SUPERDEAL_PUBLIC_URL':'https://deals.example.com',
            'SUPERDEAL_ALERT_ORIGINS':'https://deals.example.com','SUPERDEAL_PRODUCTION':'1',
            'SUPERDEAL_API_HOST':'127.0.0.1','SUPERDEAL_API_PORT':'8127',
            'SUPERDEAL_PROXY_TOKEN':'a'*64,'SUPERDEAL_ADMIN_TOKEN':'b'*64}
    for key,value in values.items():monkeypatch.setenv(key,value)
    config,errors=hosting.settings(tmp_path)
    assert not errors
    assert config['SUPERDEAL_API_UPSTREAM']=='127.0.0.1:8127'
    assert not any(k in config for k in ('SUPERDEAL_ADMIN_TOKEN','MONGODB_URI','API_KEY_EARNKARO'))
    (tmp_path/'app'/'dist'/'.env').write_text('secret')
    assert hosting.settings(tmp_path)[1]


class SyntheticBackend:
    def __init__(self):self.db=mongomock.MongoClient().db
    def published_page(self,**kwargs):return {'items':[],'has_more':False}


def free_port():
    with socket.socket() as sock:
        sock.bind(('127.0.0.1',0));return sock.getsockname()[1]


def test_real_reverse_proxy_allows_alerts_and_blocks_private_paths(monkeypatch,tmp_path):
    executable=os.getenv('CADDY_BINARY') or shutil.which('caddy')
    if not executable:pytest.skip('Set CADDY_BINARY to exercise real production proxy')
    if not (ROOT/'app'/'dist'/'index.html').exists():pytest.skip('Build app/dist for proxy test')
    token=secrets.token_hex(32)
    monkeypatch.setenv('SUPERDEAL_PROXY_TOKEN',token)
    monkeypatch.setenv('SUPERDEAL_EMAIL_MODE','dry-run')
    monkeypatch.setenv('SUPERDEAL_PUBLIC_URL','https://shop.example')
    monkeypatch.setenv('SUPERDEAL_ALERT_ORIGINS','https://shop.example')
    backend=SyntheticBackend()
    api=BoundedHTTPServer(('127.0.0.1',0),make_handler(backend,admin_token='test-admin'))
    thread=threading.Thread(target=api.serve_forever,daemon=True);thread.start()
    port=free_port()
    env={**os.environ,'SUPERDEAL_DOMAIN':'shop.example',
         'SUPERDEAL_DIST':str(ROOT/'app'/'dist'),
         'SUPERDEAL_API_UPSTREAM':f'127.0.0.1:{api.server_port}',
         'SUPERDEAL_PROXY_TOKEN':token,'SUPERDEAL_FRONTEND_PORT':str(port)}
    log=(tmp_path/'caddy.log').open('wb')
    process=subprocess.Popen([executable,'run','--config',str(ROOT/'deploy'/'Caddyfile.tunnel'),'--adapter','caddyfile'],env=env,stdout=log,stderr=log)
    base=f'http://127.0.0.1:{port}'
    def request(path,body=None,headers=None):
        data=json.dumps(body).encode() if body is not None else None
        extra={'Content-Type':'application/json','Origin':'https://shop.example'}
        extra.update(headers or {})
        try:return urlopen(Request(base+path,data=data,headers=extra),timeout=3)
        except HTTPError as exc:return exc
    try:
        for _ in range(50):
            try:
                with request('/health') as r:
                    if r.code==200:break
            except OSError:time.sleep(.1)
        else:raise AssertionError('Caddy did not start')
        with request('/') as r:
            assert r.code==200
            assert b'SuperDeal' in r.read()
            assert r.headers['Referrer-Policy']=='no-referrer'
            assert "frame-ancestors 'none'" in r.headers['Content-Security-Policy']
        for path in ('/.env','/.git/config','/data/private.eml','/api/v1/admin/status','/api/v1/admin/logs'):
            with request(path) as r:assert r.code==404,path
        with request('/api/v1/deals?limit=20') as r:assert r.code==200
        # Same signed loopback client identity is shared by the three alert routes.
        body={'product':'Headphones','email':'synthetic@example.com','daily_limit':1,'days':2,'consent':True}
        with request('/api/v1/alerts',body) as r:assert r.code==202
        assert backend.db.deal_alerts.count_documents({})==1
        with request('/api/v1/alerts/confirm',{'token':'invalid'}) as r:assert r.code==400
        with request('/api/v1/alerts/stop',{'token':'invalid'}) as r:assert r.code==400
        with request('/deals',{}) as r:assert r.code==405
        # A forged proxy token/client identity supplied from outside Caddy is overwritten.
        for _ in range(9):
            with request('/api/v1/alerts',body,{'X-Superdeal-Proxy-Token':'forged','X-Superdeal-Client-IP':'8.8.8.8'}) as r:assert r.code==202
        with request('/api/v1/alerts',body) as r:assert r.code==429
        assert backend.db.deal_alerts.count_documents({})==1
    finally:
        process.terminate()
        try:process.wait(timeout=5)
        except subprocess.TimeoutExpired:process.kill();process.wait()
        log.close();api.shutdown();thread.join(timeout=3);api.server_close()
