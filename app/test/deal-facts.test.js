import test from 'node:test';
import assert from 'node:assert/strict';
import {priceFacts} from '../src/deal-facts.js';
test('source price wins over browser and model fields',()=>{
  assert.equal(priceFacts({current_price:499,verified_price:599,llm_current_price:99}).current,499);
});
test('browser fills missing price but model cannot',()=>{
  assert.equal(priceFacts({verified_price:599}).current,599);
  assert.equal(priceFacts({llm_current_price:99}).current,null);
});
test('missing or invalid prices never produce invented savings',()=>{
  for(const current_price of [null,'',0,-1,'unknown',Infinity]) {
    assert.equal(priceFacts({current_price,mrp:999,discount_pct:90}).discount,null);
  }
  assert.equal(priceFacts({current_price:100,mrp:99}).saving,null);
});
test('savings are calculated from real price pair and rounded',()=>{
  assert.deepEqual(priceFacts({current_price:16490,mrp:28990}),{current:16490,mrp:28990,saving:12500,discount:43});
});

test('known store aliases collapse into canonical labels',async()=>{
  const {normalizeRetailer}=await import('../src/deal-facts.js');
  for (const value of ['amazon','Amazon',' AMAZON ','amazon.in','aamzon.in','amz.cc','https://www.amazon.in/product?ref=x']) {
    assert.equal(normalizeRetailer(value),'Amazon',value);
  }
  for (const value of ['flkt.cc','Flipkart','FLIPKART.COM','https://flkt.cc/abc']) {
    assert.equal(normalizeRetailer(value),'Flipkart',value);
  }
  assert.equal(normalizeRetailer('myntra.com'),'Myntra');
  assert.equal(normalizeRetailer('ajio'),'AJIO');
  assert.equal(normalizeRetailer('custom store'),normalizeRetailer('CUSTOM STORE'));
  assert.notEqual(normalizeRetailer('amazon.in.evil.example'),'Amazon');
});
test('affiliate provider does not masquerade as the destination store',async()=>{
  const {displayRetailer}=await import('../src/deal-facts.js');
  assert.equal(displayRetailer({merchant:'EarnKaro',enriched_merchant:'amazon.in'}),'Amazon');
  assert.equal(displayRetailer({merchant:'EarnKaro',affiliate_url:'https://amz.cc/example'}),'Retailer');
  assert.equal(displayRetailer({merchant:'Flipkart',enriched_merchant:'Amazon'}),'Flipkart');
});
