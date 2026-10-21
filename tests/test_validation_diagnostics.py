"""Missing descriptive metadata is tolerated; commercial fields stay strict."""
import copy
import pytest

from superdeal_phase2_full.backend import Backend


URL = "https://example.com/affiliate?q=1"


def valid_model():
    return {
        "products": [{
            "product_name": "Example gadget",
            "brand": None,
            "ecommerce_platform": "Amazon",
            "deal_price": None,
            "original_price": None,
            "discount_percentage": None,
            "affiliate_urls": [URL],
            "confidence": 90,
            "issues": [],
        }],
        "unassigned_urls": [],
        "message_issues": [],
        "analysis_summary": "",
    }


def test_missing_summary_is_non_factual_and_can_be_normalized():
    model = valid_model()
    del model["analysis_summary"]
    result = Backend.validate(model, "Deal " + URL)
    assert result["analysis_summary"] == ""
    assert result["products"][0]["affiliate_urls"] == [URL]


def test_affiliate_url_mismatch_still_rejected():
    model = valid_model()
    model["products"][0]["affiliate_urls"] = ["https://example.com/other"]
    with pytest.raises(ValueError, match="Missing, invented, or duplicated affiliate URLs"):
        Backend.validate(model, "Deal " + URL)


def test_unknown_fields_and_missing_product_details_still_rejected():
    model = valid_model()
    model["products"][0].pop("product_name")
    with pytest.raises(ValueError, match="Invalid product schema"):
        Backend.validate(model, "Deal " + URL)


def test_unassigned_url_still_blocks_publication():
    model = valid_model()
    model["unassigned_urls"] = [URL]
    with pytest.raises(ValueError, match="Unassigned URLs"):
        Backend.validate(model, "Deal " + URL)
