"""Prices after URLs must stay with their own product, including mixed layouts."""
import pytest
from offer_evidence import post_link_prices, priced_link_rows, split_priced_products, resolve_offers

A='https://fkrt.cc/zBMHkSm'
B='https://fkrt.cc/z73Cag9'
C='https://fkrt.cc/zSIvGuG'
TEXT='Casio F91W Watch\n\n'+A+' 1099\n\nCasio Watch at 1609\n\n'+B+'\n\nCasio F94WA Watch\n\n'+C+' 1269'

def test_exact_casio_message_keeps_three_names_links_and_prices():
    grouped={'product_name':'Casio Watch','brand':'Casio','affiliate_urls':[A,B,C]}
    products=split_priced_products(TEXT,[grouped])
    assert [p['product_name'] for p in products]==['Casio F91W Watch','Casio Watch','Casio F94WA Watch']
    assert [p['affiliate_urls'] for p in products]==[[A],[B],[C]]
    facts=resolve_offers(TEXT,products)
    assert [f['current_price'] for f in facts]==[1099,1609,1269]
    assert all(f['mrp'] is None and f['discount_pct'] is None for f in facts)
    assert grouped['affiliate_urls']==[A,B,C]

@pytest.mark.parametrize('quote',['1099','Rs.1099','₹1,099','@1099','1099.50'])
def test_same_line_post_link_amount_formats(quote):
    rows,_=post_link_prices('Watch\n'+A+' '+quote)
    assert rows[A]==(1099.5 if '.' in quote and quote=='1099.50' else 1099)

@pytest.mark.parametrize('tail',['1100 off using card','1100 cashback','20% off','20W','USD 1099',''])
def test_conditions_or_measurements_after_link_are_not_prices(tail):
    assert post_link_prices(A+' '+tail)[0]=={}

def test_price_after_previous_link_is_not_borrowed_by_next_link():
    text='First watch\n'+A+' 1099\n\n'+B
    assert priced_link_rows(text)=={A:1099}
    products=[{'product_name':'Watch','affiliate_urls':[u]} for u in [A,B]]
    facts=resolve_offers(text,products)
    assert [f['current_price'] for f in facts]==[1099,None]

def test_conflicting_before_and_after_link_prices_are_not_guessed():
    assert priced_link_rows('Watch @999 : '+A+' 1099')=={}

def test_new_post_link_association_can_be_disabled_for_historical_reads():
    rows=priced_link_rows(TEXT,allow_post_link=False)
    assert A not in rows and C not in rows
    assert rows[B]==1609
