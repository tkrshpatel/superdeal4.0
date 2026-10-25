"""Shared category-list context from converted EarnKaro text; no price logic."""
import re
from deal_terms import URL, links
from offer_evidence import PERCENT

def category_context(text):
    first=URL.search(text)
    if not first:
        return {}
    prefix=text[:first.start()]
    blocks=re.split(r'\n\s*\n',prefix)
    if len(blocks)<2:
        return {}
    header='\n'.join(blocks[:-1]).strip()
    context=re.search(r'\boff\s+on\s+(.+?)\s+(?:women[’\x27]?s?|men[’\x27]?s?|kids[’\x27]?|children[’\x27]?s?)\s+clothing\b',header,re.I)
    if not context:
        return {}
    brand=context[1].strip()
    rows={}
    for line in text.splitlines():
        matches=list(URL.finditer(line))
        if len(matches)!=1:
            continue
        label=line[:matches[0].start()].strip(' \t-*•')
        label=re.sub(r'[:;]\s*[\[(]*\s*$','',label).strip()
        if not re.fullmatch(r'dresses?|jeans|tops?|sweatshirts?|sweaters?|shirts?|co[- ]?ords?|trousers|skirts?|shorts|jackets?|kurtas?|t[- ]?shirts?',label,re.I):
            continue
        link=next(iter(links(line)))
        if link in rows:
            return {}
        rows[link]=brand+' '+label
    if len(rows)<2 or set(rows)!=links(text):
        return {}
    discount=PERCENT.search(header)
    value=float(discount[2] or discount[3]) if discount else None
    kind='up_to' if discount and re.sub(r'\s','',discount[1] or '').lower()=='upto' else 'exact'
    return {'names':rows,'brand':brand,'discount':value if value and value<=100 else None,'discount_kind':kind}

def normalize_category_products(text,products):
    context=category_context(text)
    if not context:
        return products
    output=[]
    for product in products:
        for link in product.get('affiliate_urls') or []:
            output.append({**product,'product_name':context['names'][link],
                           'brand':context['brand'],'affiliate_urls':[link]})
    return output
