"""Check/serve the built website using existing .env API settings, not Vite."""
from __future__ import annotations
import argparse
import ipaddress
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
from urllib.parse import urlsplit

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'superdeal_phase2_full'))


def settings(root=ROOT):
    errors=[]
    domain=os.getenv('SUPERDEAL_DOMAIN','').strip().lower()
    if not re.fullmatch(r'(?:[a-z0-9](?:[a-z0-9-]*[a-z0-9])?\.)+[a-z]{2,63}',domain) or domain.endswith(('.example','.test','.invalid','.localhost')):
        errors.append('Set SUPERDEAL_DOMAIN to your real public hostname.')
    host=os.getenv('SUPERDEAL_API_HOST','127.0.0.1')
    if host not in ('127.0.0.1','localhost','::1'):
        errors.append('The production API must bind to loopback.')
    try:
        api_port=int(os.getenv('SUPERDEAL_API_PORT','8765'))
        front_port=int(os.getenv('SUPERDEAL_FRONTEND_PORT','8080'))
        if not 1<=api_port<=65535 or not 1024<=front_port<=65535 or front_port==api_port:
            raise ValueError
    except ValueError:
        errors.append('Check the existing API port and distinct frontend port.');api_port=8765;front_port=8080
    token=os.getenv('SUPERDEAL_PROXY_TOKEN','')
    admin=os.getenv('SUPERDEAL_ADMIN_TOKEN','')
    if len(token)<32 or 'REPLACE' in token or len(admin)<32 or token==admin:
        errors.append('Set distinct random ADMIN and PROXY tokens, each at least 32 characters.')
    origin=os.getenv('SUPERDEAL_PUBLIC_URL','').rstrip('/')
    if origin!='https://'+domain:
        errors.append('SUPERDEAL_PUBLIC_URL must be https:// plus SUPERDEAL_DOMAIN.')
    allowed={v.strip().rstrip('/') for v in os.getenv('SUPERDEAL_ALERT_ORIGINS','').split(',') if v.strip()}
    if origin not in allowed:
        errors.append('Add the public HTTPS origin to SUPERDEAL_ALERT_ORIGINS.')
    if os.getenv('SUPERDEAL_PRODUCTION')!='1':
        errors.append('Set SUPERDEAL_PRODUCTION=1 for the production API guards.')
    dist=(root/'app'/'dist').resolve()
    if not (dist/'index.html').is_file():
        errors.append('Build the frontend first: npm.cmd run build in app.')
    if dist.is_dir() and any(p.is_file() and (p.name.startswith('.env') or p.suffix in ('.session','.pem','.key','.eml','.map')) for p in dist.rglob('*')):
        errors.append('Private files or source maps found in app/dist; rebuild a clean frontend.')
    address='['+host+']' if ':' in host else host
    # The only upstream derives from existing API settings. Never reset .env.
    return {'SUPERDEAL_DOMAIN':domain,'SUPERDEAL_DIST':str(dist),
            'SUPERDEAL_API_UPSTREAM':f'{address}:{api_port}',
            'SUPERDEAL_PROXY_TOKEN':token,'SUPERDEAL_FRONTEND_PORT':str(front_port)},errors


def main():
    from runtime_env import load_env
    load_env()
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',choices=('check','validate','serve'))
    parser.add_argument('--mode',choices=('tunnel','direct'),default='tunnel')
    parser.add_argument('--caddy',default='caddy')
    args=parser.parse_args()
    config,errors=settings()
    if errors:
        for error in errors:print('FAIL:',error)
        return 1
    print('PASS: static build and production configuration. API upstream:',config['SUPERDEAL_API_UPSTREAM'])
    print('This does not verify DNS, TLS, Mongo authentication, SMTP, firewall or backups.')
    if args.action=='check':return 0
    executable=shutil.which(args.caddy)
    if not executable:
        print('FAIL: install Caddy or pass --caddy with its executable path.');return 1
    # Do not pass Telegram, Mongo, EarnKaro or SMTP credentials to the web server.
    env={k:v for k,v in os.environ.items() if k.upper() in {'PATH','SYSTEMROOT','WINDIR','TEMP','TMP','HOME','USERPROFILE','APPDATA','LOCALAPPDATA','XDG_DATA_HOME','XDG_CONFIG_HOME','SSL_CERT_FILE','SSL_CERT_DIR'}}
    env.update(config)
    file=ROOT/'deploy'/('Caddyfile.tunnel' if args.mode=='tunnel' else 'Caddyfile')
    validate=subprocess.run([executable,'validate','--config',str(file),'--adapter','caddyfile'],env=env,cwd=ROOT/'deploy')
    if validate.returncode or args.action=='validate':return validate.returncode
    return subprocess.call([executable,'run','--config',str(file),'--adapter','caddyfile'],env=env,cwd=ROOT/'deploy')

if __name__=='__main__':raise SystemExit(main())
