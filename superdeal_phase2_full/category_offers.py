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
    context=re.search(r'\boff\s+on\s+([^\n]+)',header,re.I)
    if not context:
        return {}
    scope=re.split(r'\s*\+\s*',context[1],maxsplit=1)[0].strip(' .:;!')
    # Audience qualifiers separate the brand from its collection description.
    # Without one, retain the explicit collection title rather than guess a brand.
    audience=re.search(r'\s+(?:women[’\x27]?s?|men[’\x27]?s?|kids[’\x27]?|children[’\x27]?s?)\s+',scope,re.I)
    prefix=scope[:audience.start()].strip() if audience else scope
    brand=prefix if audience else None
    if not prefix or len(prefix)>120 or re.search(r'[@₹]|\b(?:coupon|cashback|using|bank)\b',prefix,re.I):
        return {}
    rows={}
    for line in text.splitlines():
        matches=list(URL.finditer(line))
        if len(matches)!=1:
            continue
        label=line[:matches[0].start()].strip(' \t-*•')
        label=re.sub(r'[:;]\s*[\[(]*\s*$','',label).strip()
        if label and not re.fullmatch(r'[^\W\d_][^\W\d_ \t]*(?:[\w\s&’\x27()/\-]*[^\W\d_])?',label,re.UNICODE) or len(label)>80 or re.search(r'\d|@|₹',label):
            continue
        link=next(iter(links(line)))
        if link in rows:
            return {}
        if not label:
            name=scope
        elif label.casefold() in {'men','women','kids','children'}:
            # Audience rows qualify the collection, not replace its name.
            qualifier={'men':"Men's",'women':"Women's",'kids':"Kids'",'children':"Children's"}[label.casefold()]
            base,noun=(scope.rsplit(' ',1) if ' ' in scope else ('',scope))
            name=' '.join(p for p in (base,qualifier,noun) if p)
        else:
            name=prefix+' '+label
        rows[link]=name
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
            name=context['names'][link]
            existing=product.get('product_name','')
            if existing.casefold().startswith(name.casefold()):
                name=existing
            output.append({**product,'product_name':name,
                           'brand':context['brand'] or product.get('brand'),'affiliate_urls':[link]})
    return output
