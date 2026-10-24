from deal_terms import extract_deal_terms

A='https://ek.example/a'
B='https://ek.example/b'
def p(url): return {'affiliate_urls':[url]}
def terms(text, products=None): return extract_deal_terms(text, products or [p(A)])

def test_explicit_code_and_conditions_preserve_source():
    text=f'Phone at 12999\n{A}\nApply coupon code SAVE100 at checkout. Minimum order ₹999.'
    result=terms(text)[0]
    assert result['coupon_codes']==['SAVE100']
    assert result['instructions']==result['conditions']==result['source_excerpts']
    assert result['source']=='earnkaro'

def test_coupon_without_code_does_not_invent_one():
    result=terms(f'Phone\n{A}\nCollect ₹100 off coupon at checkout')[0]
    assert result['has_coupon'] and result['coupon_codes']==[]

def test_numeric_and_prose_are_not_codes():
    for line in ['Use code at checkout', 'Coupon code: 100', 'Coupon code available']:
        assert terms(f'Phone\n{A}\n{line}')[0]['coupon_codes']==[]

def test_separate_product_paragraphs_are_associated():
    text=f'Phone\n{A}\nUse code PHONE10\n\nShoes\n{B}\nUse code SHOE20'
    result=terms(text,[p(A),p(B)])
    assert result[0]['coupon_codes']==['PHONE10']
    assert result[1]['coupon_codes']==['SHOE20']

def test_detached_or_ambiguous_instructions_not_assigned():
    text=f'Phone\n{A}\n\nShoes\n{B}\n\nUse code GLOBAL10'
    assert terms(text,[p(A),p(B)])==[None,None]
    assert terms(f'Phone {A}\nShoes {B}\nUse code GLOBAL10',[p(A),p(B)])==[None,None]

def test_unknown_or_shared_link_is_not_evidence():
    assert terms(f'Use code SAVE10\n{B}')==[None]
    assert terms(f'Use code SAVE10\n{A}',[p(A),p(A)])==[None,None]

def test_price_only_has_no_terms_and_no_mutation():
    products=[p(A)]
    assert terms(f'Phone at 12999\n{A}',products)==[None]
    assert products==[p(A)]

def test_bank_and_app_only_conditions_are_retained():
    result=terms(f'Phone\n{A}\nPay with HDFC credit card for cashback\nApp only. New users only.')[0]
    assert len(result['conditions'])==2
    assert result['coupon_codes']==[]


def test_no_coupon_does_not_add_a_coupon_badge():
    result=terms(f'Phone\n{A}\nNo coupon required at checkout')[0]
    assert not result['has_coupon']


def test_short_colon_coupon_code():
    result=terms(f'Phone\n{A}\nCoupon : FT')[0]
    assert result['coupon_codes']==['FT']
