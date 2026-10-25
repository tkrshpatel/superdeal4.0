"""Compatibility contract for formats supplied by the SuperDeals owner."""
import pytest
from category_offers import normalize_category_products
from offer_evidence import split_priced_products, resolve_offers
from deal_terms import extract_deal_terms

A='https://example.com/a'
B='https://example.com/b'
C='https://example.com/c'
D='https://example.com/d'

@pytest.mark.parametrize('text,urls,prices,starts,effective,discount',[
 ('Headphones @252\n'+A,[A],[252],[None],[None],None),
 ('Headphones Rs 252 only\n'+A,[A],[252],[None],[None],None),
 ('86700\n\n11000 off Using Card\n\n'+A,[A],[86700],[None],[None],None),
 ('Samsung 163cm 65inches 4K Ultra HD QLED TV @1,21,740 Using Card\n'+A,[A],[None],[None],[121740],None),
 ("Myntra: Upto 86% Off on Roadster Men's Shirts Starts Rs.262\n\nLink : "+A,[A],[None],[262],[None],86),
 ('Amazon : Up to 52% Off on Eha Pots & Plants Starting @419 + Apply Coupon\n'+A,[A],[None],[419],[None],52),
 ('52% OFF: Orient Electric Ceiling Fans @ ₹1,255 [Effective Price] Apply 7% Coupon • Brown: '+A+' • White: '+B+' • Blue: '+C,
  [A,B,C],[None]*3,[None]*3,[1255]*3,None),
 ('Upto 50% Off On Crompton 1HP Water Pumps + Bank Offer\n\n4099 : '+A+'\n3699 : '+B+'\n4582 : '+C,
  [A,B,C],[4099,3699,4582],[None]*3,[None]*3,50),
 ('Grab : Upto 83% OFF Crompton LED Batten\n\nPack of 1 (20W) | 4 feet @129 : '+A+'\nPack of 1 (24W) @190 : '+B+'\nPack of 2 (36W) | 4 feet @599 : '+C,
  [A,B,C],[129,190,599],[None]*3,[None]*3,83),
 ('Price Drop : realme P4R 5G (4GB | 128GB) at 18749. '+A+' 6GB | 128GB at 21349 : '+B+' *COD Available | Buy Fast. *Price May Increase Anytime',
  [A,B],[18749,21349],[None]*2,[None]*2,None),
 ('Amazon: Upto 65% OFF on Elaris Home Decor + APPLY COUPON\n\nOwl Figurine Set (White & Gold) @799 : '+A+'\nBirds Sculpture (Black & White) @799 : '+B+'\nRibbed Ceramic Planter (White) @279 : '+C+'\nRibbed Ceramic Planter (Green) @279 ; '+D,
  [A,B,C,D],[799,799,279,279],[None]*4,[None]*4,65),
])
def test_earlier_message_contracts(text,urls,prices,starts,effective,discount):
    # Start with separate products; preserve each exact source link.
    products=[{'product_name':'Source product','affiliate_urls':[url]} for url in urls]
    products=split_priced_products(text,normalize_category_products(text,products))
    facts=resolve_offers(text,products)
    assert [p['affiliate_urls'] for p in products]==[[u] for u in urls]
    assert [f['current_price'] for f in facts]==prices
    assert [f['starting_price'] for f in facts]==starts
    assert [f['effective_price'] for f in facts]==effective
    if discount is not None:
        assert all(f['discount_pct']==discount and f['discount_kind']=='up_to' for f in facts)
    if 'Elaris' in text:
        terms=extract_deal_terms(text,products)
        assert all(t['has_coupon'] for t in terms)
