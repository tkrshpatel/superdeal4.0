import json
import threading
from http.server import ThreadingHTTPServer
from urllib.request import urlopen, Request, build_opener, HTTPRedirectHandler
from urllib.error import HTTPError
import pytest
from api import make_handler
from http_security import safe_destination, RequestBudget

@pytest.mark.parametrize('url',[
    'javascript:alert(1)','data:text/html,hi','http://shop.example/a',
    'https://127.0.0.1/a','https://[::1]/','https://169.254.169.254/',
    'https://10.0.0.2/','https://localhost/','https://api.internal/',
    'https://user:password@shop.example/a','https://shop.example:8000/',
    'https://shop.example/\r\nX-Test: yes','https://shop.example/%0d%0aX-Test',
    'https://shop.example\\@127.0.0.1/', 'https://2130706433/','https://127.1/',
    'https://shop.example/a\t',None,
])
def test_reject_dangerous_redirects(url):
    assert not safe_destination(url)

def test_keep_exact_https_affiliate_destination():
    url='https://affiliate.example/a?campaign=abc%2F123&ref=SAVE10'
    assert safe_destination(url)


def test_budget_is_bounded_and_refills():
    clock=[0]
    budget=RequestBudget(burst=2,per_minute=60,max_peers=2,clock=lambda:clock[0])
    assert budget.allow('a') and budget.allow('a') and not budget.allow('a')
    clock[0]=1
    assert budget.allow('a')
    budget.allow('b');budget.allow('c')
    assert len(budget.peers)==2


class DB:
    def command(self,name): return {'ok':1}
class Stub:
    db=DB()
    destination='javascript:alert(1)'
    clicks=0
    def affiliate_destination(self,id): return self.destination
    def record_affiliate_click(self,id): self.clicks+=1
    def published_page(self,**kwargs):
        return {'items':[{'id':'p','product_name':'Phone','unexpected_secret':'do-not-publish',
                          'deal_terms':{'coupon_codes':['FT'],'debug_token':'secret'}}], 'has_more':False}


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self,*args): return None

@pytest.fixture
def server():
    backend=Stub()
    http=ThreadingHTTPServer(('127.0.0.1',0),make_handler(backend,admin_token='test-token'))
    t=threading.Thread(target=http.serve_forever,daemon=True);t.start()
    yield f'http://127.0.0.1:{http.server_port}',backend
    http.shutdown();t.join(timeout=3);http.server_close()


def response(base,path,headers=None):
    try: return build_opener(NoRedirect).open(Request(base+path,headers=headers or {}),timeout=3)
    except HTTPError as exc: return exc


def test_public_http_boundaries_and_headers(server):
    base,backend=server
    r=response(base,'/go/p')
    assert r.code==404 and backend.clicks==0
    backend.destination='https://affiliate.example/a?ref=x%2Fy'
    r=response(base,'/go/p')
    assert r.code==302 and r.headers['Location']==backend.destination
    assert r.headers['Referrer-Policy']=='no-referrer'
    assert r.headers['X-Frame-Options']=='DENY'
    assert 'Python' not in r.headers['Server']
    for path in ['/api/v1/deals?limit=1&limit=2','/api/v1/deals?q='+'x'*513,'/api/v1/deals?'+'&'.join('x'+str(i)+'=1' for i in range(17))]:
        assert response(base,path).code==400
    assert response(base,'/api/v1/admin/status').code==401
    assert response(base,'/.env').code==404
    assert response(base,'/.git/config').code==404
    public=json.load(response(base,'/api/v1/deals'))
    assert 'unexpected_secret' not in public['items'][0]
    assert 'debug_token' not in public['items'][0]['deal_terms']


def test_http_rate_limit_does_not_trust_forwarded_headers():
    http=ThreadingHTTPServer(('127.0.0.1',0),make_handler(Stub(),request_budget=RequestBudget(burst=1,per_minute=1)))
    t=threading.Thread(target=http.serve_forever,daemon=True);t.start()
    base=f'http://127.0.0.1:{http.server_port}'
    try:
        assert response(base,'/health').code==200
        r=response(base,'/health',headers={'X-Forwarded-For':'203.0.113.123'})
        assert r.code==429 and r.headers['Retry-After']=='30'
    finally:
        http.shutdown();t.join(timeout=3);http.server_close()


def test_worker_dns_guard_checks_every_resolved_address(monkeypatch):
    import image_enrichment
    def address(ip): return (2,1,6,'',(ip,443))
    monkeypatch.setattr(image_enrichment.socket,'getaddrinfo',lambda *a,**k:[address('8.8.8.8'),address('127.0.0.1')])
    assert image_enrichment._public_dns('shop.example') is False
    monkeypatch.setattr(image_enrichment.socket,'getaddrinfo',lambda *a,**k:[address('8.8.8.8'),address('1.1.1.1')])
    assert image_enrichment._public_dns('shop.example') is True


def test_only_authenticated_loopback_proxy_can_set_client_identity(monkeypatch):
    from http_security import client_identity
    monkeypatch.setenv('SUPERDEAL_PROXY_TOKEN','s'*64)
    good={'X-Superdeal-Proxy-Token':'s'*64,'X-Superdeal-Client-IP':'198.51.100.12'}
    assert client_identity('127.0.0.1',good)=='198.51.100.12'
    assert client_identity('198.51.100.99',good)=='198.51.100.99'
    assert client_identity('127.0.0.1',{'X-Forwarded-For':'198.51.100.12'})=='127.0.0.1'
    assert client_identity('127.0.0.1',{**good,'X-Superdeal-Proxy-Token':'bad'})=='127.0.0.1'
    assert client_identity('127.0.0.1',{**good,'X-Superdeal-Client-IP':'1.1.1.1, 2.2.2.2'})=='127.0.0.1'


def test_head_redirect_does_not_record_a_click(server):
    base,backend=server
    backend.destination='https://affiliate.example/a'
    try:
        build_opener(NoRedirect).open(Request(base+'/go/p',method='HEAD'),timeout=3)
    except HTTPError as response:
        assert response.code==302
    assert backend.clicks==0


def test_public_allowlist_keeps_offer_evidence_but_not_private_nested_fields():
    from public_presentation import public_payload
    result=public_payload({'id':'p','product_name':'Watch','offer_facts':{
        'version':11,'current_price':1099,'discount_pct':80,'discount_kind':'exact',
        'effective_price':999,'effective_price_condition':'Using card',
        '_sources':{'source':'private'},'_conflicts':['private']},'debug_token':'secret'})
    assert result['offer_facts']['current_price']==1099
    assert result['offer_facts']['effective_price']==999
    assert 'debug_token' not in result and '_sources' not in result['offer_facts']


def test_bounded_http_server_rejects_excess_connection_without_new_thread():
    import socket
    from http_security import BoundedHTTPServer
    server=BoundedHTTPServer(('127.0.0.1',0),make_handler(Stub()),max_connections=1)
    assert server._slots.acquire(blocking=False)
    left,right=socket.socketpair()
    try:
        server.process_request(left,('127.0.0.1',1))
        assert b'503 Service Unavailable' in right.recv(1024)
    finally:
        right.close();server._slots.release();server.server_close()


def test_production_guards_reject_remote_bind_and_weak_shared_tokens(monkeypatch):
    from http_security import production_errors
    monkeypatch.setenv('SUPERDEAL_ADMIN_TOKEN','same')
    monkeypatch.setenv('SUPERDEAL_PROXY_TOKEN','same')
    assert len(production_errors('0.0.0.0'))==2
    monkeypatch.setenv('SUPERDEAL_ADMIN_TOKEN','a'*64)
    monkeypatch.setenv('SUPERDEAL_PROXY_TOKEN','b'*64)
    assert production_errors('127.0.0.1')==[]


def test_public_startup_does_not_initialize_worker_collections():
    import mongomock
    from backend import Backend
    db=mongomock.MongoClient().db
    Backend(db).setup_public()
    assert not set(db.list_collection_names()) & {'raw','ek_raw','playwright_raw','pipeline_status','pipeline_logs','fact_table','dedupe_guards','telegram_inbox'}
    assert {'deal_clicks','deal_alerts','alert_confirmations','alert_deliveries'} <= set(db.list_collection_names())


@pytest.mark.parametrize('url',['https://0x7f.0.0.1/','https://0177.0.0.1/','https://0x7f000001/'])
def test_mixed_numeric_loopback_encodings_are_rejected(url):
    assert not safe_destination(url)


def test_nested_offer_labels_do_not_leak_provider_or_arbitrary_metadata():
    from public_presentation import public_payload
    facts={'version':11,'conditional_offers':[{'label':'Telegram @private_channel','kind':'coupon','debug_secret':'secret'}],
           'advertised_discount':{'value':80,'kind':'up_to','private_token':'secret'}}
    public=public_payload({'id':'p','product_name':'Watch','offer_facts':facts})['offer_facts']
    assert public['conditional_offers']==[{'label':'','kind':'coupon'}]
    assert public['advertised_discount']=={'value':80,'kind':'up_to'}
