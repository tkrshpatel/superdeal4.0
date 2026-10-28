"""Source-level exclusions: retain raw messages, never enrich or publish them."""
import re

EXCLUDED_DOMAIN = 'web.lehlah.club'
DOMAIN_REFERENCE = re.compile(r'(?<![\w.-])web\.lehlah\.club(?![\w-]|\.[\w-])', re.I)


def excluded_deal(text):
    return isinstance(text, str) and bool(DOMAIN_REFERENCE.search(text))
