from backend import Backend
import pytest

VALID = {'products':[{'product_name':'Sony WH-1000XM5','brand':'Sony','ecommerce_platform':'Flipkart','deal_price':17489,'original_price':None,'discount_percentage':None,'affiliate_urls':['https://fktr.in/a'],'confidence':95,'issues':[]}], 'unassigned_urls':[], 'message_issues':[], 'analysis_summary':'one deal'}

def test_valid():
    assert Backend.validate(VALID, 'Sony https://fktr.in/a')['products'][0]['brand']=='Sony'

def test_missing_url_rejected():
    with pytest.raises(ValueError, match='URLs'):
        Backend.validate(VALID, 'Sony https://fktr.in/a https://fktr.in/b')

def test_unassigned_blocks():
    import copy
    bad=copy.deepcopy(VALID)
    bad['unassigned_urls']=['https://fktr.in/b']
    with pytest.raises(ValueError, match='Unassigned'):
        Backend.validate(bad, 'Sony https://fktr.in/a https://fktr.in/b')

def test_duplicate_url_rejected():
    import copy
    bad=copy.deepcopy(VALID)
    bad['products'].append(copy.deepcopy(bad['products'][0]))
    with pytest.raises(ValueError, match='URLs'):
        Backend.validate(bad, 'Sony https://fktr.in/a')

def test_malformed_json():
    with pytest.raises(ValueError):
        Backend.validate('{', 'Sony https://fktr.in/a')
