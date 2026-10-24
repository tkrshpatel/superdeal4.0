"""Keep source provenance private while publishing only shopper-facing text."""
import re

PRIVATE_TEXT = re.compile(r'earn\s*karo|telegram|(?:https?://)?(?:t\.me|telegram\.me)/|@[A-Za-z0-9_]+|untrusted\s+merchant|merchant\s+page\s+research', re.I)
PRIVATE_KEYS = {'raw_text','source_excerpts','source','raw_id','response_text','response_payload','llm_response','analysis_summary','issues','message_issues','channel','channel_name','channel_username','telegram_channel','preview_source_raw_id'}
TEXT_KEYS = {'product_name','page_title','brand','merchant','ecommerce_platform','enriched_merchant','description','offer_type','instructions','conditions','coupon_codes'}


def shopper_text(value):
    if not isinstance(value,str): return value
    return '\n'.join(line for line in value.splitlines() if not PRIVATE_TEXT.search(line)).strip()


def public_payload(value, key=None):
    if isinstance(value,dict):
        if key == 'deal_terms':
            value = dict(value)
            codes = list(value.get('coupon_codes') or [])
            for excerpt in value.get('source_excerpts') or []:
                clean = shopper_text(excerpt)
                match = re.fullmatch(r'coupon\s*:\s*([A-Za-z0-9][A-Za-z0-9_-]{1,29})', clean, re.I)
                if match and not match[1].isdigit() and match[1] not in codes:
                    codes.append(match[1])
            value['coupon_codes'] = codes
        return {k:public_payload(v,k) for k,v in value.items() if k not in PRIVATE_KEYS}
    if isinstance(value,list):
        output=[public_payload(v,key) for v in value]
        return [v for v in output if v != ''] if key in TEXT_KEYS else output
    if key == 'image_url' and isinstance(value,str) and PRIVATE_TEXT.search(value):
        return None
    return shopper_text(value) if key in TEXT_KEYS else value
