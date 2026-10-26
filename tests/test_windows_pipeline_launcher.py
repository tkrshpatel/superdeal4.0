import importlib.util
import io
import json
from pathlib import Path
import sys
import subprocess
from urllib.parse import parse_qs, unquote, urlsplit

import pytest

spec = importlib.util.spec_from_file_location('desktop_pipeline', Path(__file__).resolve().parents[1]/'scripts'/'start_pipeline.py')
launcher = importlib.util.module_from_spec(spec)
spec.loader.exec_module(launcher)


@pytest.mark.parametrize('uri', [
    'mongodb://api:old@127.0.0.1:27017/app?authSource=app&replicaSet=rs0&retryWrites=true',
    'mongodb://api:old@[::1]:27018/app?replicaSet=rs0',
    'mongodb+srv://api:old@cluster.example/app?retryWrites=true',
    'mongodb://host1:27017,host2:27017/app?replicaSet=rs0',
])
def test_worker_credentials_preserve_configured_mongo_hosts_and_options(uri):
    old = urlsplit(uri)
    result = urlsplit(launcher.worker_uri(uri, 'new:@ /#password', 'app'))
    assert result.netloc.rsplit('@',1)[-1] == old.netloc.rsplit('@',1)[-1]
    assert result.scheme == old.scheme and result.path == old.path
    assert unquote(result.password) == 'new:@ /#password'
    assert result.username == 'superdeals_worker'
    assert parse_qs(result.query)['authSource'] == ['app']
    assert all(parse_qs(result.query)[k] == v for k,v in parse_qs(old.query).items() if k != 'authSource')
    assert 'old' not in result.netloc


def test_worker_password_is_required():
    with pytest.raises(launcher.StartupError):
        launcher.worker_uri('mongodb://localhost/app', '', 'app')


def test_launcher_exposes_root_worker_modules_from_an_unrelated_directory(tmp_path):
    script = str(Path(launcher.__file__).resolve())
    code = ('import runpy,importlib.util; '
            'runpy.run_path('+repr(script)+",run_name='launcher_path_check'); "
            "assert importlib.util.find_spec('superdeal_telegram_capture') is not None; "
            "assert importlib.util.find_spec('superdeal') is not None; "
            "assert importlib.util.find_spec('backend') is not None")
    result = subprocess.run([sys.executable,'-I','-c',code], cwd=tmp_path, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize('service', ['api','frontend','tunnel','ollama'])
def test_worker_secret_is_not_passed_to_other_services(service):
    source = {'PATH':'tools', 'USERPROFILE':'home', 'MONGODB_URI':'private-uri',
              launcher.SECRET:'parent-secret', 'SUPERDEAL_ADMIN_TOKEN':'admin-secret',
              'TELEGRAM_API_HASH':'telegram-secret', 'API_KEY_EARNKARO':'ek-secret'}
    result = launcher.service_environment(service, source, password='worker-secret')
    assert launcher.SECRET not in result
    if service in ('tunnel','ollama'):
        assert 'MONGODB_URI' not in result and 'SUPERDEAL_ADMIN_TOKEN' not in result
        assert 'TELEGRAM_API_HASH' not in result and 'API_KEY_EARNKARO' not in result
    assert source[launcher.SECRET] == 'parent-secret'


def test_worker_receives_only_the_explicit_new_password():
    env = launcher.service_environment('worker', {launcher.SECRET:'stale','MONGODB_URI':'api-uri'}, password='fresh')
    assert env[launcher.SECRET] == 'fresh'
    assert env['MONGODB_URI'] == 'api-uri'


def test_recognizes_manual_and_desktop_workers_without_counting_idle_windows():
    root = r'C:\Users\Home\superdeal-staging'
    assert launcher.process_matches('worker', {'Name':'python.exe','CommandLine':'python superdeal_local_live_worker.py --confirm-monitor'})
    assert launcher.process_matches('worker', {'Name':'python.exe','CommandLine':root+r'\scripts\start_pipeline.py --service worker'}, root=root)
    assert not launcher.process_matches('worker', {'Name':'powershell.exe','CommandLine':'pipeline_service.ps1 -Service worker'})
    assert not launcher.process_matches('worker', {'Name':'python.exe','CommandLine':'start_pipeline.py --worker-running'})
    assert not launcher.process_matches('worker', {'Name':'python.exe','CommandLine':'unrelated.py'})


def test_tunnel_matching_uses_configured_name():
    assert launcher.process_matches('tunnel', {'Name':'cloudflared.exe','CommandLine':'cloudflared tunnel run superdeals'})
    assert not launcher.process_matches('tunnel', {'Name':'cloudflared.exe','CommandLine':'cloudflared tunnel run other-site'})


def test_ready_file_requires_actual_listening_and_publication_and_contains_no_messages(tmp_path):
    stream = io.StringIO()
    path = tmp_path/'ready.json'
    tee = launcher.MonitorReady(stream, 'fresh-run', path)
    tee.write('LISTENING private-channel (telegram:123)\n')
    assert not path.exists()
    tee.write('MONITORING configured=3 active=1 capture_only=False reconcile_seconds=20\n')
    saved = json.loads(path.read_text())
    assert saved == {'nonce':'fresh-run','pid':launcher.os.getpid()}
    assert 'private-channel' not in path.read_text()
    assert 'LISTENING' in stream.getvalue()


def test_capture_only_cannot_report_publication_ready(tmp_path):
    path = tmp_path/'ready.json'
    tee = launcher.MonitorReady(io.StringIO(), 'new', path)
    tee.write('LISTENING channel\nMONITORING configured=1 active=1 capture_only=True\n')
    assert not path.exists()


def test_worker_ready_rejects_stale_marker_and_dead_process(tmp_path, monkeypatch):
    path = tmp_path/'ready.json'
    path.write_text(json.dumps({'nonce':'old','pid':123}))
    monkeypatch.setattr(launcher, 'processes', lambda: [])
    assert not launcher.worker_ready('new', path)
    assert not launcher.worker_ready('old', path)
    path.write_text(json.dumps({'nonce':'new','pid':123}))
    monkeypatch.setattr(launcher, 'processes', lambda:[{'ProcessId':123,'Name':'python.exe','CommandLine':'superdeal_local_live_worker.py'}])
    assert launcher.worker_ready('new', path)


def test_healthy_existing_api_is_reused_without_spawning(monkeypatch):
    monkeypatch.setattr(launcher, 'healthy', lambda *args:True)
    monkeypatch.setattr(launcher, 'open_service', lambda *args:pytest.fail('Must reuse existing API'))
    launcher.ensure_http('api', 'http://127.0.0.1:8766')


def test_occupied_unhealthy_port_is_not_replaced_or_killed(monkeypatch):
    monkeypatch.setattr(launcher, 'healthy', lambda *args:False)
    monkeypatch.setattr(launcher, 'occupied', lambda *args:True)
    monkeypatch.setattr(launcher, 'open_service', lambda *args:pytest.fail('Must not duplicate a listener'))
    with pytest.raises(launcher.StartupError, match='Nothing was stopped'):
        launcher.ensure_http('api', 'http://127.0.0.1:8766')


def test_service_command_line_never_contains_worker_password(monkeypatch):
    calls = []
    monkeypatch.setattr(launcher.subprocess, 'CREATE_NEW_CONSOLE', 16, raising=False)
    monkeypatch.setattr(launcher.subprocess, 'Popen', lambda args, **kwargs:calls.append((args,kwargs)))
    launcher.open_service('worker', password='unique-private-password')
    args, kwargs = calls[0]
    assert 'unique-private-password' not in ' '.join(args)
    assert kwargs['env'][launcher.SECRET] == 'unique-private-password'
    assert kwargs['creationflags'] == 16


@pytest.mark.skipif(sys.platform != 'win32', reason='Actual Windows named mutex')
def test_windows_service_lock_blocks_another_thread_and_recovers_after_release():
    from concurrent.futures import ThreadPoolExecutor
    from uuid import uuid4
    name = 'test-' + uuid4().hex
    def second_start():
        with pytest.raises(launcher.StartupError, match='already running'):
            with launcher.service_lock(name):
                pass
    with launcher.service_lock(name):
        with ThreadPoolExecutor(max_workers=1) as executor:
            executor.submit(second_start).result(timeout=5)
    with launcher.service_lock(name):
        pass
