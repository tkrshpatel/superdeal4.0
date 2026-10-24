from public_presentation import public_payload


def test_public_response_drops_source_metadata_and_leaking_text():
    result=public_payload({'deals':[{'product_name':'@secret_channel Phone', 'description':'Useful specs\nJoin Telegram @secret_channel',
        'merchant':'EarnKaro', 'raw_text':'private message', 'channel':'Secret Channel',
        'deal_terms':{'source':'earnkaro','source_excerpts':['private source'], 'coupon_codes':['FT'],
                      'instructions':['Apply FT at checkout','Join t.me/secret'], 'conditions':['Minimum order ₹999']},
        'affiliate_url':'https://ek.example/affiliate'}]})
    deal=result['deals'][0]
    assert deal['product_name']=='' and deal['merchant']==''
    assert deal['description']=='Useful specs'
    assert 'raw_text' not in deal and 'channel' not in deal
    assert deal['deal_terms']=={'coupon_codes':['FT'],'instructions':['Apply FT at checkout'],'conditions':['Minimum order ₹999']}
    assert deal['affiliate_url']=='https://ek.example/affiliate'


def test_older_coupon_excerpt_is_recovered_before_source_is_removed():
    result=public_payload({'deal_terms':{'source':'earnkaro','source_excerpts':['Coupon : FT'], 'coupon_codes':[]}})
    assert result['deal_terms']=={'coupon_codes':['FT']}
