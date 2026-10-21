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
