"""Deterministic offer facts from converted deal text and exact-link browser evidence.
Private evidence is kept separate from the public numerical/display contract.
"""
import math
import re
from deal_terms import links, URL

NUMBER = r'((?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d{1,2})?)(?![\d,.])'
CURRENCY = r'(?:₹\s*|(?:rs\.?|inr)\s*)'
MRP = re.compile(r'\b(?:mrp|m\.r\.p\.?|original\s*price|list\s*price)\s*[:=@-]?\s*(?:'+CURRENCY+r')?'+NUMBER, re.I)
PRICE = re.compile(r'\b(?:deal\s*price|selling\s*price|price|at|now|only)\s*[:=@-]?\s*(?:'+CURRENCY+r')?'+NUMBER, re.I)
RUPEES = re.compile(CURRENCY+NUMBER, re.I)
PERCENT = re.compile(r'(?<![\w.])(?:(up\s*to|upto|flat|extra|additional)\s*)?(\d{1,3}(?:\.\d+)?)\s*%\s*(?:off|discount|cashback)\b|\b(?:discount\s*[:=-]\s*|save\s+)(\d{1,3}(?:\.\d+)?)\s*%', re.I)
CONDITIONAL = re.compile(r'coupon|promo|cashback|\bbank\b|\bcard\b|credit|debit|exchange|\bemi\b|\bhdfc\b|\bsbi\b|\bicici\b|\baxis\b|\bextra\b|additional|\bon\s+(?:orders?|spend)\b|minimum\s+(?:order|spend)', re.I)
PUBLIC_KEYS = {'version','current_price','mrp','discount_pct','discount_kind','conditional_offers'}


def number(value, maximum=100000000):
    if type(value) not in (int,float) or not math.isfinite(value) or not 0 < value <= maximum:
        return None
    return float(value)


def unique(values):
    values=set(values)
    return next(iter(values)) if len(values)==1 else None


def product_evidence(text, products, product):
    attached=set(product.get('affiliate_urls') or [])
    all_links=links(text)
    if not attached or not attached <= all_links:
        return ''
    if any(attached & set(other.get('affiliate_urls') or []) for other in products if other is not product):
        return ''
    if len(products)==1 and attached==all_links:
        return text
    candidates=[p for p in re.split(r'\n\s*\n',text) if links(p)==attached]
    return candidates[0] if len(attached)==1 and len(candidates)==1 else ''


def extract(text):
    prices=[];mrps=[];discounts=[];conditional=[]
    for raw in re.split(r'[\n;|]+',text):
        line=URL.sub('',raw).strip()
        if not line:continue
        percent=list(PERCENT.finditer(line))
        if CONDITIONAL.search(line):
            # Do not promote effective/coupon/bank prices or percentages to base facts.
            for match in percent:
                value=float(match[2] or match[3])
                if 0 < value <= 100:
                    kind='up_to' if re.sub(r'\s', '', match[1] or '').lower() in ('upto',) else 'exact'
                    label=('Up to ' if kind=='up_to' else '')+f'{value:g}% off'
                    offer_type='Cashback' if re.search('cashback',line,re.I) else 'Bank offer' if re.search(r'card|bank|hdfc|sbi|icici|axis',line,re.I) else 'Coupon offer' if re.search('coupon|promo',line,re.I) else 'Additional offer'
                    if offer_type=='Cashback':label=('Up to ' if kind=='up_to' else '')+f'{value:g}% cashback'
                    item={'label':offer_type+': '+label,'kind':offer_type.lower().replace(' ','_')}
                    if item not in conditional:conditional.append(item)
            continue
        mrp_matches=list(MRP.finditer(line))
        for match in mrp_matches:
            value=number(float(match[1].replace(',','')))
            if value:mrps.append(value)
        # Mask the MRP span so its "price" or currency cannot be read as the selling price.
        clean=MRP.sub('',line)
        found=list(PRICE.finditer(clean))
        if not found:found=list(RUPEES.finditer(clean))
        for match in found:
            end=clean[match.end():].lstrip()
            if end.startswith('%'):continue
            value=number(float(match[1].replace(',','')))
            if value:prices.append(value)
        for match in percent:
            # A range such as 20–60% is not an exact 60% claim.
            if re.search(r'\d\s*[-–—]\s*$',line[:match.start()]):continue
            value=float(match[2] or match[3])
            if 0 < value <= 100:
                kind='up_to' if re.sub(r'\s', '', match[1] or '').lower()=='upto' else 'exact'
                discounts.append((value,kind))
    return {'current_price':unique(prices),'mrp':unique(mrps),'discount':unique(discounts),'conditional_offers':conditional,
            '_conflicts':(['AMBIGUOUS_SOURCE_PRICE'] if len(set(prices))>1 else [])+(['AMBIGUOUS_SOURCE_MRP'] if len(set(mrps))>1 else [])+(['AMBIGUOUS_SOURCE_DISCOUNT'] if len(set(discounts))>1 else [])}


def resolve_offers(text, products, research=None):
    output=[]
    for product in products:
        evidence=extract(product_evidence(text,products,product))
        attached=product.get('affiliate_urls') or []
        shared=any(set(attached) & set(other.get('affiliate_urls') or []) for other in products if other is not product)
        eligible=bool(attached) and set(attached)<=links(text)
        page=(research or {}).get(attached[0],{}) if len(attached)==1 and not shared and eligible else {}
        price=evidence['current_price'];mrp=evidence['mrp']
        sources={'current_price':'earnkaro' if price is not None else None,'mrp':'earnkaro' if mrp is not None else None}
        conflicts=list(evidence['_conflicts'])
        for key in ('current_price','mrp'):
            page_key='price' if key=='current_price' else 'mrp'
            browser=number(page.get(page_key)) if page.get(page_key+'_source') else None
            if key=='current_price':
                if price is None and 'AMBIGUOUS_SOURCE_PRICE' not in conflicts:price=browser;sources[key]='browser' if browser else None
                elif browser and price!=browser:conflicts.append('BROWSER_PRICE_DISAGREES')
            else:
                if mrp is None and 'AMBIGUOUS_SOURCE_MRP' not in conflicts:mrp=browser;sources[key]='browser' if browser else None
                elif browser and mrp!=browser:conflicts.append('BROWSER_MRP_DISAGREES')
        stated=evidence['discount']
        pct,kind=stated if stated else (None,None)
        if price is not None and mrp is not None and mrp<=price:
            conflicts.append('INVALID_PRICE_PAIR');mrp=None
        if price is not None and mrp is not None:
            calculated=(mrp-price)*100/mrp
            mismatch=stated and kind=='exact' and abs(calculated-pct)>1
            if mismatch and ('browser' in sources.values()):
                # An exact source claim outranks a conflicting borrowed price pair.
                conflicts.append('BORROWED_PAIR_DISAGREES');mrp=None
            else:
                if mismatch:conflicts.append('SOURCE_DISCOUNT_DISAGREES')
                pct,kind=calculated,'calculated'
        if mrp is not None and price is None:
            # Keep evidence privately, but do not publish an orphan struck-through MRP.
            mrp=None
        sources['discount']='calculated' if kind=='calculated' else 'earnkaro' if pct else None
        output.append({'version':1,'current_price':price,'mrp':mrp,'discount_pct':pct,'discount_kind':kind,
                       'conditional_offers':evidence['conditional_offers'],'_sources':sources,'_conflicts':conflicts})
    return output


def public_facts(facts):
    return {key:value for key,value in facts.items() if key in PUBLIC_KEYS}
