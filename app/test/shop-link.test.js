import test from 'node:test';
import assert from 'node:assert/strict';
import {openShopLink} from '../src/shop-link.js';

test('retailer app opens before the in-app browser',async()=>{
  const calls=[];
  await openShopLink('https://thesuperdeals.in/go/a',{native:true,handoff:async()=>{calls.push('app');return {opened:true};},browse:()=>calls.push('browser')});
  assert.deepEqual(calls,['app']);
});
test('missing app falls back inside SuperDeals with the unchanged affiliate URL',async()=>{
  const affiliate='https://amzn-to.co/x?tag=keep%2Bthis';
  let destination;
  await openShopLink('https://thesuperdeals.in/go/a',{native:true,handoff:async()=>({opened:false,fallbackUrl:affiliate}),browse:async({url})=>{destination=url;}});
  assert.equal(destination,affiliate);
});
test('handoff errors preserve the tracked URL for browser fallback',async()=>{
  let destination;
  await openShopLink('https://thesuperdeals.in/go/a',{native:true,handoff:async()=>{throw Error('unavailable');},browse:async({url})=>{destination=url;}});
  assert.equal(destination,'https://thesuperdeals.in/go/a');
});
test('website still opens the tracked URL normally',async()=>{
  let destination;
  await openShopLink('/go/a',{native:false,webOpen:url=>{destination=url;}});
  assert.equal(destination,'/go/a');
});
