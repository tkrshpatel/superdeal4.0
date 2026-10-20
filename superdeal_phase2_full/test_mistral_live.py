"""Opt-in, read-only live Ollama checks. Run: python -m pytest superdeal_mongo_backend/test_mistral_live.py -v -s"""
import json
import os
import sys
from pathlib import Path

import pytest
import requests

sys.path.insert(0, str(Path(__file__).resolve().parent))
from backend import Backend

SAMPLES = [
    ("Sony", "Sony WH-CH520 Wireless Headphones now Rs 2,999 (MRP Rs 5,990). Buy: https://example.com/sony520", 1),
    ("boAt", "boAt Airdopes 141 earbuds Rs 999. Shop: https://example.com/boat141", 1),
    ("multi", "Samsung Galaxy M35 Rs 15,999 https://example.com/galaxym35\nMarshall Emberton II speaker Rs 9,999 https://example.com/emberton2", 2),
    ("generic", "Men's plain cotton t-shirt Rs 399 https://example.com/cottonshirt", 1),
]

@pytest.fixture(scope="module")
def ollama_ready():
    endpoint = os.getenv("OLLAMA_URL", "http://127.0.0.1:11434/api/chat")
    base = endpoint.rsplit('/api/chat', 1)[0]
    try:
        response = requests.get(base + '/api/tags', timeout=8)
        response.raise_for_status()
        models = [m.get('name', '') for m in response.json().get('models', [])]
    except requests.RequestException as exc:
        pytest.fail(f"Ollama unavailable at {base}: {exc}")
    model = os.getenv('OLLAMA_MODEL', 'mistral:instruct')
    if model not in models:
        pytest.fail(f"Model {model!r} not found in Ollama. Installed: {models}. Run: ollama pull {model}")
    return model

@pytest.mark.parametrize('case,text,expected_count', SAMPLES)
def test_real_mistral(case, text, expected_count, ollama_ready):
    print(f"\nCASE: {case}\nINPUT: {text}", flush=True)
    try:
        output = Backend._ollama(text)
    except Exception as exc:
        pytest.fail(f"Ollama request failed: {type(exc).__name__}: {exc}")
    print('MODEL OUTPUT:', output, flush=True)
    parsed = Backend.validate(output, text)
    assert len(parsed['products']) == expected_count, f"Expected {expected_count} products"
    if case == 'Sony':
        assert parsed['products'][0]['brand'] and 'sony' in parsed['products'][0]['brand'].lower()
    if case == 'boAt':
        assert parsed['products'][0]['brand'] and 'boat' in parsed['products'][0]['brand'].lower()
    if case == 'multi':
        brands = {str(p['brand']).lower() for p in parsed['products']}
        assert any('samsung' in b for b in brands) and any('marshall' in b for b in brands)
    if case == 'generic':
        assert parsed['products'][0]['brand'] is None, 'Generic product must not have invented brand'
