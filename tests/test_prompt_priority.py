"""Guard source-precedence and brand rules against future prompt regressions."""
from superdeal_phase2_full.prompt import PROMPT


def test_earnkaro_precedes_playwright_for_all_fields():
    assert 'PRIMARY authority' in PROMPT
    assert 'SECONDARY' in PROMPT
    assert "preserve EarnKaro's" in PROMPT
    assert 'matched Playwright' in PROMPT


def test_explicit_brand_recognition_and_no_merchant_confusion():
    assert 'Playwright\'s brand field is null' in PROMPT
    assert 'Samsung, Sony, Apple, Nothing, boAt' in PROMPT
    assert 'Do NOT use the marketplace as brand' in PROMPT


def test_prices_keep_coupon_separate_and_links_remain_ids():
    assert 'Coupon, card, cashback, EMI, exchange' in PROMPT
    assert 'Only if absent use the matched merchant' in PROMPT
    assert '"link_ids": ["LINK_001"]' in PROMPT
    assert 'You do not return affiliate_urls' in PROMPT
