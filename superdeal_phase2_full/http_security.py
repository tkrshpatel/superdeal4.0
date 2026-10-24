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
            if re.fullmatch(r'(?:0x[0-9a-f]+|[0-9.]+)',host): return False
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
