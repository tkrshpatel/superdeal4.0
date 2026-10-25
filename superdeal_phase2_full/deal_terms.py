"""Evidence-only extraction of EarnKaro coupon instructions and conditions.

No LLM calls, price arithmetic or affiliate URL rewriting. Unclear associations
are omitted. Multiple-product messages require a self-contained paragraph with
exactly one unique EarnKaro URL; explicit shared headline instructions apply to every product.
"""
import re

URL = re.compile(r'https?://[^\s<>"\']+')
CODE = re.compile(r'\b(?:coupon\s*[:=\-]|promo\s*[:=\-]|coupon\s+code|promo\s+code|use\s+(?:coupon\s+)?code|apply\s+(?:coupon\s+)?code|code\s*:)\s*[:=\-]?\s*[`"\']?([A-Za-z0-9][A-Za-z0-9_-]{1,29})\b', re.I)
SIGNAL = re.compile(r'\bcoupon\b|\bpromo\b|\bcode\b|cashback|bank\s+offer|\b(?:credit|debit)\s+card\b', re.I)
STEP = re.compile(r'\bapply\b|\buse\s+(?:coupon\s+)?code\b|checkout|add\s+to\s+cart|collect\s+(?:the\s+)?coupon|\bredeem\b|\bactivate\b|\bselect\b|\bclick\b', re.I)
CONDITION = re.compile(r'minimum|min\.?\s+(?:order|spend)|orders?\s+(?:above|over)|\b(?:credit|debit)\s+card\b|bank\s+offer|cashback|app[ -]only|new\s+users?|first\s+order|valid\s+(?:until|till)|expires?|expiry|maximum|max\.?\s+(?:discount|cashback)', re.I)
REJECT_CODES = {'at', 'the', 'this', 'coupon', 'code', 'checkout', 'available', 'required', 'applicable', 'only', 'not', 'none', 'here', 'and', 'off', 'for', 'get', 'with', 'is', 'on', 'to'}


def links(text):
    return {m.group().rstrip('.,;!?)') for m in URL.finditer(text)}


def extract_deal_terms(converted_text, products):
    """Return a separate immutable terms object per product, or None."""
    all_links = links(converted_text)
    paragraphs = re.split(r'\n\s*\n', converted_text)
    # A detached paragraph before the first product block is a shared header.
    first=URL.search(converted_text)
    prefix=converted_text[:first.start()] if first else ''
    blocks=re.split(r'\n\s*\n',prefix)
    header='\n'.join(blocks[:-1])
    shared='\n'.join(line for line in header.splitlines()
                     if SIGNAL.search(line) and not links(line))
    output = []
    for product in products:
        attached = set(product.get('affiliate_urls') or [])
        if not attached or not attached <= all_links:
            output.append(None)
            continue
        if len(products) == 1 and len(all_links) == 1 and attached == all_links:
            evidence = converted_text
        elif len(attached) == 1:
            candidates = [p for p in paragraphs if links(p) == attached]
            # Repeated links in separate paragraphs may describe distinct offers.
            evidence = candidates[0] if len(candidates) == 1 else ''
        else:
            evidence = ''
        # One URL shared by several parsed products does not prove code eligibility.
        if any(attached & set(other.get('affiliate_urls') or []) for other in products if other is not product):
            evidence = ''
        evidence='\n'.join(part for part in (shared,evidence) if part)
        codes, steps, conditions, excerpts = [], [], [], []
        has_bank_offer = False
        has_coupon = False
        for raw_line in evidence.splitlines():
            line = URL.sub('', raw_line).strip(' \t-*•')
            if not line or len(line) > 600:
                continue
            matches = [m.group(1) for m in CODE.finditer(line)]
            matches = [c for c in matches if c.lower() not in REJECT_CODES and not c.isdigit()]
            step, condition = bool(STEP.search(line)), bool(CONDITION.search(line))
            if not (matches or SIGNAL.search(line) or step or condition):
                continue
            has_bank_offer |= bool(re.search(r'bank\s+offer|\b(?:credit|debit)\s+card\b', line, re.I))
            has_coupon |= not bool(re.search(r'no\s+coupon|without\s+(?:a\s+)?coupon', line, re.I)) and bool(re.search(r'\bcoupon\b|\bpromo\b', line, re.I) or matches)
            codes.extend(c for c in matches if c not in codes)
            if step and line not in steps: steps.append(line)
            if condition and line not in conditions: conditions.append(line)
            if line not in excerpts: excerpts.append(line)
        output.append({'source': 'earnkaro', 'coupon_codes': codes, 'has_coupon': has_coupon, 'has_bank_offer': has_bank_offer,
                       'instructions': steps, 'conditions': conditions, 'source_excerpts': excerpts}
                      if excerpts else None)
    return output
