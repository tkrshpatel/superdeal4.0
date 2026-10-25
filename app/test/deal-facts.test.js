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
  assert.equal(displayRetailer({merchant:'EarnKaro',affiliate_url:'https://amz.cc/example'}),'SuperDeals Find');
  assert.equal(displayRetailer({merchant:'Flipkart',enriched_merchant:'Amazon'}),'Flipkart');
});


test('unrecognized retailer labels always use the discovery fallback',async()=>{
  const {displayRetailer}=await import('../src/deal-facts.js');
  for(const merchant of ['UNTRUSTED MERCHANT PAGE RESEARCH','@vintage_deals','Retailer','EarnKaro','random text','unknown.store',null,'']) {
    assert.equal(displayRetailer({merchant}),'SuperDeals Find');
  }
});


test('hot uses strict unrounded discount and requires a valid price pair',async()=>{
  const {isHotDeal}=await import('../src/deal-facts.js');
  assert.equal(isHotDeal({current_price:499,mrp:1000}),true);
  assert.equal(isHotDeal({current_price:500,mrp:1000}),false);
  assert.equal(isHotDeal({current_price:501,mrp:1000}),false);
  assert.equal(isHotDeal({current_price:200,discount_pct:80}),false);
});

const sourceFacts=(overrides={})=>({offer_facts:{version:1,current_price:null,mrp:null,discount_pct:null,discount_kind:null,conditional_offers:[],...overrides}});
test('exact source discount survives absent price/MRP and qualifies for HOT above 50',async()=>{
  const {isHotDeal}=await import('../src/deal-facts.js');
  const d=sourceFacts({discount_pct:60,discount_kind:'exact'});
  assert.deepEqual(priceFacts(d),{current:null,mrp:null,saving:null,discount:60});
  assert.equal(isHotDeal(d),true);
  assert.equal(isHotDeal(sourceFacts({discount_pct:50,discount_kind:'exact'})),false);
});
test('up-to discount displays as an offer but never qualifies as HOT',async()=>{
  const {isHotDeal}=await import('../src/deal-facts.js');
  const d=sourceFacts({discount_pct:80,discount_kind:'up_to'});
  assert.equal(priceFacts(d).discount,80);assert.equal(priceFacts(d).saving,null);assert.equal(isHotDeal(d),false);
});
test('authoritative empty evidence blocks invented legacy model values',()=>{
  const d={current_price:1,mrp:1000,discount_pct:99,...sourceFacts()};
  assert.deepEqual(priceFacts(d),{current:null,mrp:null,saving:null,discount:null});
});
test('conditional discounts are never added to calculated base discounts',async()=>{
  const {isHotDeal}=await import('../src/deal-facts.js');
  const d=sourceFacts({current_price:500,mrp:1000,discount_pct:50,discount_kind:'calculated',conditional_offers:[{label:'Bank offer: 10% off'}]});
  assert.equal(priceFacts(d).discount,50);assert.equal(priceFacts(d).saving,500);assert.equal(isHotDeal(d),false);
});

test('explicit monetary saving does not manufacture an original price',()=>{
  const f=priceFacts(sourceFacts({current_price:1000,stated_savings:500}));
  assert.deepEqual(f,{current:1000,mrp:null,saving:500,discount:null});
});
