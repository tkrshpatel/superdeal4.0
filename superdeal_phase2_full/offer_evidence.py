"""Deterministic offer facts from converted deal text and exact-link browser evidence.
Private evidence is kept separate from the public numerical/display contract.
"""
import math
import re
from deal_terms import links, URL

NUMBER = r'((?:\d{1,3}(?:,\d{3})+|\d{1,2}(?:,\d{2})*,\d{3}|\d+)(?:\.\d{1,2})?)(?![\w,]|\.\d)'
CURRENCY = r'(?:₹\s*|(?:rs\.?|inr)\s*)'
MRP = re.compile(r'\b(?:mrp|m\.r\.p\.?|original\s*price|list\s*price)\s*[:=@-]?\s*(?:'+CURRENCY+r')?'+NUMBER, re.I)
PRICE = re.compile(r'\b(?:deal\s*price|selling\s*price|price|at|now|only)\s*[:=@-]?\s*(?:'+CURRENCY+r')?'+NUMBER, re.I)
AT_PRICE = re.compile(r'(?<![\w@])@\s*(?:'+CURRENCY+r')?'+NUMBER, re.I)
RUPEES = re.compile(CURRENCY+NUMBER, re.I)
STARTING = re.compile(r'\b(?:start(?:ing|s)?\s*(?:from|at)?|from)\s*[:=@-]?\s*(?:'+CURRENCY+r')?'+NUMBER, re.I)
PERCENT = re.compile(r'(?<![\w.])(?:(up\s*to|upto|flat|extra|additional)\s*)?(\d{1,3}(?:\.\d+)?)\s*%\s*(?:off|discount|cashback)\b|\b(?:discount\s*[:=-]\s*|save\s+)(\d{1,3}(?:\.\d+)?)\s*%', re.I)
CONDITIONAL = re.compile(r'coupon|promo|cashback|effective|after|using|subscription|new\s+users?|first\s+order|\bbogo\b|\bbuy\s*\d.*\bget\s*\d|\bbank\b|\bcard\b|credit|debit|exchange|\bemi\b|\bhdfc\b|\bsbi\b|\bicici\b|\baxis\b|\bextra\b|additional|\bon\s+(?:orders?|spend)\b|minimum\s+(?:order|spend)', re.I)
PUBLIC_KEYS = {'effective_price_condition','effective_price','starting_price','stated_savings','version','current_price','mrp','discount_pct','discount_kind','conditional_offers','advertised_discount'}


def number(value, maximum=100000000):
    if type(value) not in (int,float) or not math.isfinite(value) or not 0 < value <= maximum:
        return None
    return float(value)


def unique(values):
    values=set(values)
    return next(iter(values)) if len(values)==1 else None


def priced_link_rows(text):
    """Only accept a complete, unambiguous list of price: URL rows."""
    rows={}
    previous=0
    for found in URL.finditer(text):
        segment=text[previous:found.start()]
        match=re.search(r'(?:@\s*|\bat\s+)(?:'+CURRENCY+r')?'+NUMBER+r'[\s.:]*[\[(]*\s*$',segment,re.I)
        if match:
            value=number(float(match[1].replace(',','')))
            if value and found.group() not in rows:
                rows[found.group()]=value
        previous=found.end()
    if len(rows)>1 and set(rows)==links(text):
        return rows
    rows={}
    for line in text.splitlines():
        found=list(URL.finditer(line))
        if len(found)!=1:
            continue
        match=re.fullmatch(r'\s*(?:[-•]\s*)?(?:'+CURRENCY+r')?'+NUMBER+r'\s*:\s*[\[(]*\s*',line[:found[0].start()],re.I)
        if not match:
            # Descriptive option text may precede an explicit @ selling price.
            match=re.search(r'@\s*(?:'+CURRENCY+r')?'+NUMBER+r'\s*:\s*[\[(]*\s*$',line[:found[0].start()],re.I)
        if not match:
            continue
        value=number(float(match[1].replace(',','')))
        link=found[0].group()
        if not value or link in rows:
            return {}
        rows[link]=value
    return rows if len(rows)>1 and set(rows)==links(text) else {}


def split_priced_products(text, products):
    """Deterministic link/price rows override model grouping, never URLs."""
    rows=priced_link_rows(text)
    if not rows:
        return products
    result=[]
    for product in products:
        attached=product.get('affiliate_urls') or []
        for link in attached:
            label=''
            for line in text.splitlines():
                if links(line)=={link} and '@' in line:
                    label=line.split('@',1)[0].strip(' \t-*•')
                    break
            name=product['product_name']
            if label and label.casefold() not in name.casefold():
                name=name+' — '+label
            result.append({**product,'product_name':name,'affiliate_urls':[link]})
    return result


def product_evidence(text, products, product):
    attached=set(product.get('affiliate_urls') or [])
    all_links=links(text)
    if not attached or not attached <= all_links:
        return ''
    if any(attached & set(other.get('affiliate_urls') or []) for other in products if other is not product):
        return ''
    rows=priced_link_rows(text)
    if len(attached)==1 and next(iter(attached)) in rows:
        # The header applies to every row; each price belongs only to its URL.
        first_url=URL.search(text)
        prefix=text[:first_url.start()] if first_url else ''
        markers=list(PRICE.finditer(prefix))+list(AT_PRICE.finditer(prefix))
        if markers:
            prefix=prefix[:min(m.start() for m in markers)]
        # Only a leading advertised discount is shared, never another row's price.
        headline=PERCENT.search(prefix)
        header=headline.group() if headline and not CONDITIONAL.search(prefix[:headline.end()]) else ''
        return header+'\nPrice: ₹'+str(rows[next(iter(attached))])
    if len(products)==1 and attached==all_links:
        return text
    # A single headline followed only by named colour links describes variants.
    matches=list(URL.finditer(text))
    if len(matches)>1:
        tail=URL.sub('',text[matches[0].end():])
        colours=r'(?:brown|white|blue|black|red|green|grey|gray|silver|gold|pink|yellow|orange|purple|beige)'
        if re.fullmatch(r'(?:[\s•:,*\[\]()\-–—/]|'+colours+r')*',tail,re.I):
            return text[:matches[0].start()]
    candidates=[p for p in re.split(r'\n\s*\n',text) if links(p)==attached]
    return candidates[0] if len(attached)==1 and len(candidates)==1 else ''


def extract(text):
    prices, mrps, discounts, conditional, savings, starts, effective = [], [], [], [], [], [], []
    effective_conditions=[]
    text = URL.sub('', text)
    # A separate "+ Apply Coupon" instruction does not qualify every prior headline.
    for raw in re.split(r'[\n;|]+|\s*\+\s*(?=(?:apply|use|collect|extra|additional|bank)\b)', text, flags=re.I):
        line = URL.sub('', raw).strip()
        if not line:
            continue
        percent = list(PERCENT.finditer(line))
        if not re.search(r'[$€£]|\b(?:USD|EUR|GBP|AED)\b',line,re.I):
            for amount in list(AT_PRICE.finditer(line))+list(PRICE.finditer(line)):
                if re.match(r'\s*(?:using|with)\s+(?:(?:a|an|the)\s+)?(?:(?:credit|debit)\s+)?card\b',line[amount.end():],re.I):
                    value=number(float(amount[1].replace(',','')))
                    if value:
                        effective.append(value)
                        effective_conditions.append('Using card')
        if re.search(r'\beffective\s*price\b',line,re.I) and not re.search(r'[$€£]|\b(?:USD|EUR|GBP|AED)\b',line,re.I):
            # Preserve an explicitly quoted effective price, never calculate it.
            candidates=list(AT_PRICE.finditer(line))+list(RUPEES.finditer(line))
            if not candidates:
                candidates=list(PRICE.finditer(line))
            for amount in candidates:
                if not re.match(r'\s*(?:%|off\b|cashback\b)',line[amount.end():],re.I):
                    value=number(float(amount[1].replace(',','')))
                    if value: effective.append(value)
        if CONDITIONAL.search(line):
            offer_type = ('Cashback' if re.search('cashback', line, re.I)
                          else 'Bank offer' if re.search(r'card|bank|hdfc|sbi|icici|axis', line, re.I)
                          else 'Coupon offer' if re.search('coupon|promo', line, re.I)
                          else 'Additional offer')
            for match in percent:
                if re.search(r'\d\s*[-–—]\s*$', line[:match.start()]):
                    continue
                value = float(match[2] or match[3])
                if not 0 < value <= 100:
                    continue
                qualifier = 'Up to ' if re.sub(r'\s', '', match[1] or '').lower() == 'upto' else ''
                suffix = 'cashback' if offer_type == 'Cashback' else 'off'
                item = {'label': offer_type + ': ' + qualifier + f'{value:g}% {suffix}',
                        'kind': offer_type.lower().replace(' ', '_')}
                if item not in conditional:
                    conditional.append(item)
            if not percent:
                amounts=list(RUPEES.finditer(line))+list(re.finditer(r'(?<![\w.,])'+NUMBER+r'(?=\s+off\b)',line,re.I))
                for amount in amounts:
                    value = number(float(amount[1].replace(',', '')))
                    prefix, tail = line[:amount.start()], line[amount.end():]
                    if value and (re.match(r'\s*(?:off|cashback)\b', tail, re.I)
                                  or re.search(r'cashback|save', prefix, re.I)):
                        qualifier = 'Up to ' if re.search(r'(?:up\s*to|upto|max(?:imum)?)\s*$', prefix, re.I) else ''
                        item = {'label': offer_type + ': ' + qualifier + f'₹{value:g}',
                                'kind': 'conditional_amount'}
                        if item not in conditional:
                            conditional.append(item)
            continue
        foreign = bool(re.search(r'[$€£]|\b(?:USD|EUR|GBP|AED)\b', line, re.I))
        for match in ([] if foreign else STARTING.finditer(line)):
            value = number(float(match[1].replace(',', '')))
            if value: starts.append(value)
        for match in ([] if foreign else MRP.finditer(line)):
            value = number(float(match[1].replace(',', '')))
            if value:
                mrps.append(value)
        # Keep original-price amounts out of selling-price extraction.
        clean = '' if foreign else STARTING.sub('', MRP.sub('', line))
        found = list(PRICE.finditer(clean)) + list(AT_PRICE.finditer(clean))
        # A whole line containing only an amount is an explicit price quote.
        standalone=re.fullmatch(r'\s*'+NUMBER+r'\s*',clean)
        if standalone:
            prices.append(float(standalone[1].replace(',','')))

        if not found and not re.search(r'save|saving|discount|\boff\b', clean, re.I):
            found = list(RUPEES.finditer(clean))
        for amount in RUPEES.finditer(clean):
            if (re.search(r'save|saving', clean[:amount.start()], re.I)
                    or re.match(r'\s*off\b', clean[amount.end():], re.I)):
                value = number(float(amount[1].replace(',', '')))
                if value:
                    savings.append(value)
        for match in found:
            if re.match(r'\s*(?:%|off\b)', clean[match.end():], re.I):
                continue
            value = number(float(match[1].replace(',', '')))
            if value:
                prices.append(value)
        for match in percent:
            if re.search(r'\d\s*[-–—]\s*$', line[:match.start()]):
                continue
            value = float(match[2] or match[3])
            if 0 < value <= 100:
                kind = 'up_to' if re.sub(r'\s', '', match[1] or '').lower() == 'upto' else 'exact'
                discounts.append((value, kind))
    conflicts = []
    for values, code in ((prices, 'AMBIGUOUS_SOURCE_PRICE'), (mrps, 'AMBIGUOUS_SOURCE_MRP'),
                         (discounts, 'AMBIGUOUS_SOURCE_DISCOUNT')):
        if len(set(values)) > 1:
            conflicts.append(code)
    return {'effective_price_condition': unique(effective_conditions) if unique(effective) else None, 'effective_price': unique(effective), 'current_price': unique(prices), 'mrp': unique(mrps), 'discount': unique(discounts),
            'conditional_offers': conditional, 'starting_price': unique(starts), 'stated_savings': unique(savings), '_conflicts': conflicts}


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
        output.append({'version':10,'effective_price_condition':evidence['effective_price_condition'],'effective_price':evidence['effective_price'],'current_price':price,'mrp':mrp,'discount_pct':pct,'discount_kind':kind,
                       'conditional_offers':evidence['conditional_offers'],'starting_price':evidence['starting_price'],'stated_savings':evidence['stated_savings'],
                       'advertised_discount':{'value':stated[0],'kind':stated[1]} if stated and stated[1]=='up_to' else None,'_sources':sources,'_conflicts':conflicts})
    return output


def public_facts(facts):
    return {key:value for key,value in facts.items() if key in PUBLIC_KEYS}


def is_hot(facts):
    if facts.get('discount_kind')=='up_to':
        return False
    if facts.get('discount_kind')=='exact':
        pct=number(facts.get('discount_pct'),100)
        return pct is not None and pct>75
    price,mrp=number(facts.get('current_price')),number(facts.get('mrp'))
    return price is not None and mrp is not None and price<mrp/4
