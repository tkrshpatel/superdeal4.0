"""Keep source provenance private while publishing only shopper-facing text."""
import re

PRIVATE_TEXT = re.compile(r'earn\s*karo|telegram|(?:https?://)?(?:t\.me|telegram\.me)/|@[A-Za-z0-9_]+|untrusted\s+merchant|merchant\s+page\s+research', re.I)
PRIVATE_KEYS = {'_sources','_conflicts','raw_text','source_excerpts','source','raw_id','response_text','response_payload','llm_response','analysis_summary','issues','message_issues','channel','channel_name','channel_username','telegram_channel','preview_source_raw_id'}
TEXT_KEYS = {'product_name','page_title','brand','merchant','ecommerce_platform','enriched_merchant','description','offer_type','instructions','conditions','coupon_codes','label','effective_price_condition'}

PUBLIC_DEAL_KEYS = {'id','product_name','page_title','brand','merchant','ecommerce_platform',
    'enriched_merchant','current_price','deal_price','mrp','original_price','discount_pct',
    'discount_percentage','page_discount_pct','affiliate_url','affiliate_urls','image_url',
    'deal_terms','offer_facts','click_count','hot','last_seen_at','first_seen_at','last_verified_at',
    'verified_price','fresh','enrichment_status','description','category','offer_type',
    'has_coupon','has_card_offer','has_cod','return_days'}
PUBLIC_TERM_KEYS = {'coupon_codes','has_coupon','has_bank_offer','instructions','conditions'}


def shopper_text(value):
    if not isinstance(value,str): return value
    return '\n'.join(line for line in value.splitlines() if not PRIVATE_TEXT.search(line)).strip()


def public_payload(value, key=None):
    if isinstance(value,dict):
        if 'id' in value and 'product_name' in value:
            value = {k:v for k,v in value.items() if k in PUBLIC_DEAL_KEYS}
        if key == 'offer_facts':
            from offer_evidence import public_facts
            value = public_facts(value)
            if isinstance(value.get('conditional_offers'),list):
                value['conditional_offers']=[{k:v for k,v in item.items() if k in {'label','kind'}}
                                             for item in value['conditional_offers'] if isinstance(item,dict)]
            if isinstance(value.get('advertised_discount'),dict):
                value['advertised_discount']={k:v for k,v in value['advertised_discount'].items() if k in {'value','kind'}}
        if key == 'deal_terms':
            value = dict(value)
            codes = list(value.get('coupon_codes') or [])
            for excerpt in value.get('source_excerpts') or []:
                clean = shopper_text(excerpt)
                match = re.fullmatch(r'coupon\s*:\s*([A-Za-z0-9][A-Za-z0-9_-]{1,29})', clean, re.I)
                if match and not match[1].isdigit() and match[1] not in codes:
                    codes.append(match[1])
            value['coupon_codes'] = codes
            value = {k:v for k,v in value.items() if k in PUBLIC_TERM_KEYS}
        return {k:public_payload(v,k) for k,v in value.items() if k not in PRIVATE_KEYS}
    if isinstance(value,list):
        output=[public_payload(v,key) for v in value]
        return [v for v in output if v != ''] if key in TEXT_KEYS else output
    if key == 'image_url' and isinstance(value,str):
        from http_security import safe_destination
        local_path = value.startswith('/') and not value.startswith('//') and '\\' not in value
        if PRIVATE_TEXT.search(value) or (not local_path and not safe_destination(value)):
            return None
    return shopper_text(value) if key in TEXT_KEYS else value
