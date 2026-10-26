"""Small HTTP boundary controls; production still requires a TLS reverse proxy."""
import ipaddress
import re
import time
from collections import OrderedDict
from threading import Lock
from urllib.parse import urlsplit


def safe_destination(value):
    """Validate a stored outbound URL, preserving its exact affiliate bytes."""
    if not isinstance(value,str) or not value or len(value)>4096:
        return False
    if re.search(r'[\x00-\x20\x7f\\]|%(?:0[0-9a-f]|1[0-9a-f]|7f)',value,re.I):
        return False
    try:
        p=urlsplit(value)
        host=(p.hostname or '').lower().rstrip('.')
        if p.scheme!='https' or not host or p.username is not None or p.password is not None or p.port not in (None,443):
            return False
        if host in ('localhost','metadata.google.internal') or host.endswith(('.local','.internal','.localhost','.test','.invalid')):
            return False
        try:
            return ipaddress.ip_address(host).is_global
        except ValueError:
            # Reject legacy numeric IP encodings (e.g. 2130706433, 127.1).
            if all(re.fullmatch(r'(?:0x[0-9a-f]+|[0-9]+)',part) for part in host.split('.')): return False
            return '.' in host and bool(re.fullmatch(r'[a-z0-9](?:[a-z0-9.-]*[a-z0-9])?',host))
    except (ValueError,TypeError):
        return False


class RequestBudget:
    """Bounded per-peer token bucket; never trusts client Forwarded headers."""
    def __init__(self, *, burst=120, per_minute=240, max_peers=4096, clock=time.monotonic):
        self.burst=burst;self.per_minute=per_minute;self.max_peers=max_peers
        self.clock=clock;self.peers=OrderedDict();self.lock=Lock()

    def allow(self,peer):
        at=self.clock()
        with self.lock:
            tokens,last=self.peers.pop(peer,(self.burst,at))
            tokens=min(self.burst,tokens+max(0,at-last)*self.per_minute/60)
            allowed=tokens>=1
            self.peers[peer]=(tokens-1 if allowed else tokens,at)
            while len(self.peers)>self.max_peers: self.peers.popitem(last=False)
            return allowed


def client_identity(peer, headers):
    """Trust one canonical IP only from our authenticated loopback proxy."""
    import hmac
    import os
    secret = os.getenv('SUPERDEAL_PROXY_TOKEN', '')
    supplied = headers.get('X-Superdeal-Proxy-Token', '')
    try:
        local = ipaddress.ip_address(peer).is_loopback
        if local and len(secret) >= 32 and hmac.compare_digest(secret, supplied):
            return str(ipaddress.ip_address(headers.get('X-Superdeal-Client-IP', '')))
    except (ValueError, TypeError):
        pass
    return peer


from http.server import ThreadingHTTPServer
from threading import BoundedSemaphore


class BoundedHTTPServer(ThreadingHTTPServer):
    """Cap API worker threads; a reverse proxy is still mandatory in production."""
    daemon_threads = True
    request_queue_size = 64

    def __init__(self, *args, max_connections=32, **kwargs):
        self._slots = BoundedSemaphore(max_connections)
        super().__init__(*args, **kwargs)

    def process_request(self, request, client_address):
        if not self._slots.acquire(blocking=False):
            try:
                request.settimeout(1)
                request.sendall(b'HTTP/1.1 503 Service Unavailable\r\nContent-Length: 0\r\nConnection: close\r\nRetry-After: 3\r\n\r\n')
            except OSError:
                pass
            finally:
                self.shutdown_request(request)
            return
        try:
            super().process_request(request, client_address)
        except BaseException:
            self._slots.release()
            raise

    def process_request_thread(self, request, client_address):
        try:
            super().process_request_thread(request, client_address)
        finally:
            self._slots.release()


def production_errors(host):
    """Fail closed only when the operator explicitly selects production mode."""
    import os
    errors=[]
    if host not in ('127.0.0.1','localhost','::1'):
        errors.append('Production API must bind to loopback behind the proxy')
    admin=os.getenv('SUPERDEAL_ADMIN_TOKEN','')
    proxy=os.getenv('SUPERDEAL_PROXY_TOKEN','')
    if len(admin)<32 or len(proxy)<32 or admin==proxy or 'REPLACE' in proxy:
        errors.append('Production requires distinct random admin and proxy tokens of at least 32 characters')
    return errors
