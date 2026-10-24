"""Read-only public-host smoke check after staging deployment; no redirect clicks."""
import argparse
import ssl
from urllib.request import Request, build_opener, HTTPRedirectHandler, HTTPSHandler
from urllib.error import HTTPError
from urllib.parse import urlsplit

class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self,*args): return None


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('base_url')
    args=parser.parse_args()
    parsed=urlsplit(args.base_url)
    if parsed.scheme!='https' or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment or parsed.path not in ('','/'):
        parser.error('Provide the HTTPS origin only, e.g. https://your-domain.example')
    base=args.base_url.rstrip('/')
    opener=build_opener(NoRedirect,HTTPSHandler(context=ssl.create_default_context()))
    failed=0
    for path in ['/','/health','/.env','/.git/config','/api/v1/admin/status','/api/v1/admin/logs']:
        try:
            response=opener.open(Request(base+path,headers={'User-Agent':'SuperDeals-readiness-check/1'}),timeout=15)
        except HTTPError as exc: response=exc
        with response:
            status=response.code
            if path in ('/','/health'):
                ok=status==200
                if path=='/':
                    headers=response.headers
                    ok &= all(headers.get(k) for k in ['Strict-Transport-Security','Content-Security-Policy','Referrer-Policy','X-Content-Type-Options'])
                    ok &= "frame-ancestors 'none'" in headers.get('Content-Security-Policy','')
                    ok &= headers.get('Referrer-Policy')=='no-referrer'
            else: ok=status in (401,403,404)
            print(('PASS' if ok else 'FAIL'),path,'HTTP',status)
            failed+=not ok
    print('This smoke check is not a penetration test or a complete security assessment.')
    return 1 if failed else 0

if __name__=='__main__': raise SystemExit(main())
