"""Windows desktop startup. No config rewrites, database maintenance, or email worker."""
from __future__ import annotations
import argparse
from contextlib import contextmanager
import ctypes
import hashlib
import importlib
import json
import os
from pathlib import Path
import re
import runpy
import secrets
import shutil
import socket
import ssl
import subprocess
import sys
import time
from urllib.parse import parse_qsl, quote, urlencode, urlsplit, urlunsplit
from urllib.request import Request, ProxyHandler, HTTPSHandler, build_opener

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'src'))
sys.path.insert(0, str(ROOT / 'superdeal_phase2_full'))
SECRET = 'SUPERDEAL_LAUNCH_WORKER_PASSWORD'
NONCE = 'SUPERDEAL_LAUNCH_NONCE'
READY_FILE = ROOT/'data'/'launcher-worker-ready.json'


class StartupError(RuntimeError):
    pass


def worker_uri(uri, password, database, username='superdeals_worker'):
    """Replace credentials only for the worker, preserving existing host/options."""
    parsed = urlsplit(uri)
    if parsed.scheme not in ('mongodb', 'mongodb+srv') or not parsed.netloc or not password:
        raise StartupError('Worker credentials or MongoDB configuration are missing.')
    host = parsed.netloc.rsplit('@', 1)[-1]
    query = [(k, v) for k, v in parse_qsl(parsed.query, keep_blank_values=True) if k.lower() != 'authsource']
    query.append(('authSource', database))
    return urlunsplit((parsed.scheme, quote(username, safe='') + ':' + quote(password, safe='') + '@' + host,
                      parsed.path, urlencode(query), parsed.fragment))


def service_environment(service, source, password=None):
    """The tunnel and Ollama never inherit application/database credentials."""
    common = {'PATH','PATHEXT','SYSTEMROOT','WINDIR','COMSPEC','TEMP','TMP','USERPROFILE',
              'APPDATA','LOCALAPPDATA','PROGRAMDATA','PSMODULEPATH','SSL_CERT_FILE','SSL_CERT_DIR'}
    result = {k:v for k,v in source.items() if k.upper() in common}
    if service in ('api', 'frontend', 'worker'):
        result.update({k:v for k,v in source.items() if k.startswith(('SUPERDEAL_', 'MONGODB_')) and k != SECRET})
    if service == 'worker':
        result.update({k:v for k,v in source.items() if k.startswith(('TELEGRAM_', 'OLLAMA_')) or
                       k in {'API_KEY_EARNKARO','HTTP_PROXY','HTTPS_PROXY','NO_PROXY','REQUESTS_CA_BUNDLE'}})
        if password:
            result[SECRET] = password
    if service == 'tunnel':
        result['SUPERDEAL_TUNNEL_NAME'] = source.get('SUPERDEAL_TUNNEL_NAME', 'superdeals')
    if service == 'ollama' and source.get('OLLAMA_HOST'):
        result['OLLAMA_HOST'] = source['OLLAMA_HOST']
    return result


def process_matches(service, process, root=ROOT, tunnel='superdeals'):
    name = (process.get('Name') or '').lower()
    command = (process.get('CommandLine') or '').lower()
    if service == 'worker' and name in ('python.exe','pythonw.exe'):
        return ('superdeal_local_live_worker.py' in command or
                ('start_pipeline.py' in command and '--service worker' in command and str(root).lower() in command))
    if service == 'tunnel' and name == 'cloudflared.exe':
        return 'tunnel' in command and 'run' in command and tunnel.lower() in command
    return False


def powershell(command):
    return subprocess.run(['powershell.exe','-NoLogo','-NoProfile','-Command',command],
                          capture_output=True, text=True, timeout=60)


def processes():
    result = powershell("Get-CimInstance Win32_Process -Filter \"Name='python.exe' OR Name='pythonw.exe' OR Name='cloudflared.exe'\" | Select-Object Name,ProcessId,CommandLine | ConvertTo-Json -Compress")
    if result.returncode:
        raise StartupError('Could not check running services; startup stopped to avoid duplicates.')
    value = json.loads(result.stdout.strip() or '[]')
    return value if isinstance(value, list) else [value]


def running(service):
    tunnel = os.getenv('SUPERDEAL_TUNNEL_NAME', 'superdeals')
    return any(process_matches(service, process, tunnel=tunnel) for process in processes())


@contextmanager
def service_lock(name):
    """Prevent duplicate launchers and duplicate workers even after double-click races."""
    from ctypes import wintypes
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.CreateMutexW.argtypes = [ctypes.c_void_p, wintypes.BOOL, wintypes.LPCWSTR]
    kernel.CreateMutexW.restype = wintypes.HANDLE
    kernel.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
    kernel.WaitForSingleObject.restype = wintypes.DWORD
    kernel.ReleaseMutex.argtypes = [wintypes.HANDLE]
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    key = hashlib.sha256(str(ROOT).lower().encode()).hexdigest()[:16]
    handle = kernel.CreateMutexW(None, False, 'Local\\SuperDeals-' + key + '-' + name)
    acquired = False
    try:
        if not handle:
            raise StartupError('Could not acquire the service startup lock.')
        acquired = kernel.WaitForSingleObject(handle, 0) in (0, 0x80)
        if not acquired:
            raise StartupError('This SuperDeals service or launcher is already running.')
        yield
    finally:
        if acquired:
            kernel.ReleaseMutex(handle)
        if handle:
            kernel.CloseHandle(handle)


def configuration():
    from runtime_env import load_env
    from hosting import settings
    load_env()
    # runpy does not add the executed worker's directory to sys.path.
    # Import these before opening service windows, without connecting providers.
    for module in ('superdeal_telegram_capture', 'superdeal.telegram_user', 'telethon', 'requests', 'pymongo'):
        importlib.import_module(module)
    if not (ROOT / '.env').is_file():
        raise StartupError('The existing staging .env file is missing.')
    _, errors = settings(ROOT)
    if errors:
        raise StartupError(' '.join(errors))
    for name in ('caddy', 'cloudflared', 'powershell.exe'):
        if not shutil.which(name):
            raise StartupError('Missing executable: ' + name + '. Open a new Windows session after installing it.')
    if not (Path.home() / '.cloudflared' / 'config.yml').is_file():
        raise StartupError('The existing Cloudflare config.yml is missing.')
    host = os.getenv('SUPERDEAL_API_HOST','127.0.0.1')
    address = '['+host+']' if ':' in host else host
    return {
        'api': 'http://' + address + ':' + os.getenv('SUPERDEAL_API_PORT','8765'),
        'frontend': 'http://127.0.0.1:' + os.getenv('SUPERDEAL_FRONTEND_PORT','8080'),
        'domain': os.environ['SUPERDEAL_DOMAIN'],
        'public': os.environ['SUPERDEAL_PUBLIC_URL'].rstrip('/'),
        'ollama': os.getenv('OLLAMA_URL','http://127.0.0.1:11434/api/chat'),
        'model': os.getenv('OLLAMA_MODEL','mistral:instruct'),
        'database': os.getenv('MONGODB_DATABASE','superdeal'),
    }


def probe(url, headers=None):
    try:
        import certifi
        opener = build_opener(ProxyHandler({}), HTTPSHandler(context=ssl.create_default_context(cafile=certifi.where())))
        with opener.open(Request(url, headers=headers or {}), timeout=3) as response:
            if response.status != 200:
                return None
            return json.loads(response.read(1024*1024))
    except Exception:
        return None


def healthy(url, headers=None):
    return (probe(url, headers) or {}).get('status') == 'ok'


def wait_until(check, label, seconds=45):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if check():
            print('READY:', label, flush=True)
            return
        time.sleep(1)
    raise StartupError(label + ' did not become ready. Check its service window.')


class MonitorReady:
    """Tee console output; save only a startup nonce/PID, never Telegram text."""
    def __init__(self, stream, nonce, path=READY_FILE):
        self.stream, self.nonce, self.path = stream, nonce, path
        self.buffer, self.listening, self.monitoring = '', False, False

    def write(self, value):
        result = self.stream.write(value)
        self.buffer = (self.buffer + value)[-16384:]
        while '\n' in self.buffer:
            line, self.buffer = self.buffer.split('\n', 1)
            if line.startswith('LISTENING '):
                self.listening = True
            if 'MONITORING configured=' in line and 'capture_only=False' in line:
                self.monitoring = True
            if self.listening and self.monitoring and self.nonce:
                self.path.parent.mkdir(parents=True, exist_ok=True)
                temporary = self.path.with_suffix('.tmp')
                temporary.write_text(json.dumps({'nonce':self.nonce,'pid':os.getpid()}), encoding='utf-8')
                temporary.replace(self.path)
                self.nonce = None
        return result

    def flush(self):
        self.stream.flush()

    def __getattr__(self, name):
        return getattr(self.stream, name)


def worker_ready(nonce, path=READY_FILE):
    try:
        saved = json.loads(path.read_text(encoding='utf-8'))
        return saved.get('nonce') == nonce and any(p.get('ProcessId') == saved.get('pid')
            and process_matches('worker', p) for p in processes())
    except (OSError, ValueError, TypeError):
        return False


def occupied(url):
    parsed = urlsplit(url)
    try:
        with socket.create_connection((parsed.hostname, parsed.port or 80), timeout=1):
            return True
    except OSError:
        return False


def open_service(service, password=None, extra_env=None):
    env = service_environment(service, os.environ, password)
    env.update(extra_env or {})
    subprocess.Popen(['powershell.exe','-NoLogo','-NoProfile','-ExecutionPolicy','Bypass','-File',
                      str(ROOT/'scripts'/'pipeline_service.ps1'),'-Service',service],
                     cwd=ROOT, env=env, creationflags=subprocess.CREATE_NEW_CONSOLE)
    print('STARTING:', service, flush=True)


def ensure_mongo():
    result = powershell("(Get-Service -Name MongoDB -ErrorAction Stop).Status.ToString()")
    if result.returncode:
        raise StartupError('Windows service MongoDB was not found.')
    if result.stdout.strip() == 'Running':
        print('REUSING: MongoDB service', flush=True)
        return
    command = "Start-Service -Name MongoDB -ErrorAction Stop"
    if ctypes.windll.shell32.IsUserAnAdmin():
        result = powershell(command)
    else:
        print('Windows may ask permission to start MongoDB only.', flush=True)
        result = powershell("$p=Start-Process -FilePath (Join-Path $PSHOME 'powershell.exe') -Verb RunAs -ArgumentList @('-NoProfile','-Command','Start-Service -Name MongoDB -ErrorAction Stop') -Wait -PassThru; exit $p.ExitCode")
    if result.returncode:
        raise StartupError('MongoDB could not start. Check the Windows service or approve its UAC prompt.')


def verify_mongo(uri, database, worker=False):
    from pymongo import MongoClient
    try:
        with MongoClient(uri, serverSelectionTimeoutMS=5000, connectTimeoutMS=3000, socketTimeoutMS=5000) as client:
            client.admin.command('ping')
            if worker:
                client[database].raw.find_one({}, {'_id':1})
    except Exception:
        raise StartupError(('Worker' if worker else 'API') + ' MongoDB login failed. Check the saved password/configuration; no configuration was changed.') from None


def mongo_ready(uri):
    from pymongo import MongoClient
    from pymongo.errors import OperationFailure, PyMongoError
    try:
        with MongoClient(uri, serverSelectionTimeoutMS=1500, connectTimeoutMS=1500) as client:
            client.admin.command('ping')
        return True
    except OperationFailure as exc:
        if exc.code == 18:
            raise StartupError('API MongoDB authentication failed. Check the existing .env credentials.') from None
        return False
    except PyMongoError:
        return False


def ensure_http(service, url, headers=None):
    if healthy(url+'/health', headers):
        print('REUSING:', service, flush=True)
        return
    if occupied(url):
        raise StartupError(service + ' port is occupied by a service that failed its health check. Nothing was stopped.')
    open_service(service)
    wait_until(lambda: healthy(url+'/health', headers), service)


def ensure_ollama(config):
    parsed = urlsplit(config['ollama'])
    origin = urlunsplit((parsed.scheme, parsed.netloc, '/api/tags', '', ''))
    data = probe(origin)
    if data is None:
        if parsed.hostname not in ('127.0.0.1','localhost','::1'):
            raise StartupError('The configured remote Ollama server is unavailable.')
        if occupied(origin):
            raise StartupError('Ollama port is occupied but /api/tags is unavailable.')
        if not shutil.which('ollama'):
            raise StartupError('Ollama is unavailable. Install/start your existing Ollama setup.')
        host = '['+parsed.hostname+']' if ':' in parsed.hostname else parsed.hostname
        open_service('ollama', extra_env={'OLLAMA_HOST':host+':'+str(parsed.port or (443 if parsed.scheme=='https' else 80))})
        wait_until(lambda: probe(origin) is not None, 'Ollama')
        data = probe(origin)
    normalize = lambda value: value if ':' in value else value+':latest'
    available = {normalize(item.get('name') or item.get('model') or '') for item in data.get('models', [])}
    if normalize(config['model']) not in available:
        raise StartupError('The configured Ollama model is missing. Run ollama pull for your OLLAMA_MODEL, then launch again.')
    print('READY: Ollama and configured model', flush=True)


def launch():
    password = os.environ.pop(SECRET, None)
    config = configuration()
    with service_lock('launcher'):
        worker_exists = running('worker')
        if not worker_exists and not password:
            raise StartupError('Start using Start-SuperDeals.bat so the hidden worker-password prompt is shown.')
        ensure_mongo()
        wait_until(lambda: mongo_ready(os.environ.get('MONGODB_URI','mongodb://127.0.0.1:27017')), 'MongoDB replica set')
        verify_mongo(os.environ.get('MONGODB_URI','mongodb://127.0.0.1:27017'), config['database'])
        if not worker_exists:
            verify_mongo(worker_uri(os.environ['MONGODB_URI'], password, config['database'],
                os.getenv('SUPERDEAL_WORKER_MONGO_USER','superdeals_worker')), config['database'], worker=True)
        ensure_http('api', config['api'])
        ensure_http('frontend', config['frontend'], {'Host':config['domain']})
        if running('tunnel'):
            print('REUSING: Cloudflare tunnel', flush=True)
        else:
            open_service('tunnel')
        if worker_exists:
            print('REUSING: Telegram publication worker', flush=True)
        else:
            if not os.getenv('API_KEY_EARNKARO'):
                raise StartupError('API_KEY_EARNKARO is missing. Publication cannot start; capture-only was not silently enabled.')
            session = Path(os.getenv('TELEGRAM_SESSION','data/telegram_user_fresh'))
            if not str(session).endswith('.session'):
                session = Path(str(session)+'.session')
            if not session.is_absolute():
                session = ROOT/session
            if not session.is_file():
                raise StartupError('The configured Telegram session file is missing. Restore/re-authorize that session first.')
            ensure_ollama(config)
            nonce = secrets.token_hex(16)
            open_service('worker', password=password, extra_env={NONCE:nonce})
            password = None
            wait_until(lambda: worker_ready(nonce), 'Telegram listening with publication enabled', seconds=60)
        wait_until(lambda: healthy(config['public']+'/health'), 'public HTTPS website')
        print('\nOpen '+config['public']+'\nKeep the service windows open. No email worker or database cleanup was run.', flush=True)
    return 0


def run_service(service):
    os.chdir(ROOT)
    with service_lock(service):
        if service in ('api', 'worker'):
            from runtime_env import load_env
            load_env()
            if service == 'worker':
                password = os.environ.pop(SECRET, '')
                os.environ['MONGODB_URI'] = worker_uri(os.environ['MONGODB_URI'], password,
                    os.getenv('MONGODB_DATABASE','superdeal'), os.getenv('SUPERDEAL_WORKER_MONGO_USER','superdeals_worker'))
                password = None
                target, args = ROOT/'superdeal_local_live_worker.py', ['--confirm-monitor']
            else:
                target, args = ROOT/'superdeal_phase2_full'/'api.py', []
            sys.argv = [str(target), *args]
            stream = sys.stdout
            if service == 'worker':
                sys.stdout = MonitorReady(stream, os.environ.pop(NONCE, ''))
            try:
                runpy.run_path(str(target), run_name='__main__')
            finally:
                sys.stdout = stream
            return 0
        commands = {
            'frontend': [sys.executable,str(ROOT/'scripts'/'hosting.py'),'serve','--mode','tunnel'],
            'tunnel': ['cloudflared','tunnel','run',os.getenv('SUPERDEAL_TUNNEL_NAME','superdeals')],
            'ollama': ['ollama','serve'],
        }
        return subprocess.call(commands[service], cwd=ROOT)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true')
    parser.add_argument('--worker-running', action='store_true')
    parser.add_argument('--service', choices=['api','frontend','worker','tunnel','ollama'])
    args = parser.parse_args()
    if sys.platform != 'win32':
        print('This launcher runs on your Windows hosting PC.')
        return 1
    try:
        if args.service:
            return run_service(args.service)
        if args.check:
            configuration()
            print('PASS: existing configuration, frontend build and startup tools. No settings changed.')
            return 0
        if args.worker_running:
            from runtime_env import load_env
            load_env()
            return 0 if running('worker') else 1
        return launch()
    except KeyboardInterrupt:
        return 130
    except StartupError as exc:
        print('STOP:', exc, flush=True)
        return 1
    except ModuleNotFoundError as exc:
        name = exc.name if re.fullmatch(r'[A-Za-z_][A-Za-z0-9_.]*', exc.name or '') else 'unknown'
        print('STOP: missing Python module: '+name+'. Check the staging installation and launcher paths.', flush=True)
        return 1
    except Exception as exc:
        print('STOP: startup failed ('+type(exc).__name__+'). Check the service windows; credentials are not printed.', flush=True)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
