import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import {JSDOM} from 'jsdom';
import {priceFacts, displayRetailer} from '../src/deal-facts.js';

const offers = [
  {id:'a',product_name:'LG washer',merchant:'Amazon',current_price:16490,mrp:28990,image_url:'https://images.example/washer.jpg',last_seen_at:new Date().toISOString(),category:'Appliances'},
  {id:'b',product_name:'Chocolate offer',merchant:'Flipkart',current_price:null,category:'Grocery'},
  {id:'c',product_name:'<script>bad()</script>',merchant:'amazon.in',current_price:299},
];
async function setup(fail=false) {
  const dom = new JSDOM('<div id="app"></div>',{url:'https://superdeal.example/',runScripts:'outside-only'});
  const w = dom.window;
  w.priceFacts = priceFacts;
  w.displayRetailer = displayRetailer;
  w.Capacitor = {isNativePlatform:()=>false};
  w.fetch = async()=> {if(fail) throw Error('offline'); return {ok:true,json:async()=>({deals:offers})};};
  w.open = url => {w.lastOpened=url;};
  w.eval(fs.readFileSync('src/main.js','utf8').replace(/^import .*;\n/gm,''));
  await new Promise(resolve=>setTimeout(resolve,0));
  return dom;
}
test('shopping flow filters, saves, opens details, restores focus and preserves redirect', async()=>{
  const dom=await setup(), w=dom.window, d=w.document;
  assert.equal(d.querySelectorAll('.deal-card').length,3);
  assert.deepEqual([...d.querySelector('#merchant-filter').options].map(o=>o.textContent), ['All stores','Amazon','Flipkart']);
  assert.equal(d.querySelectorAll('.image-fallback').length,2);
  assert.equal(d.querySelectorAll('img[data-brand-fallback]').length,2);
  assert.equal(d.querySelectorAll('.offer-type').length,0);
  assert.equal(d.querySelectorAll('.deal-card script').length,0);
  assert.doesNotMatch(d.body.textContent,/commission|affiliate links/i);
  assert.ok(d.querySelector('.filter-panel #sort'));
  assert.ok(d.querySelector('.filter-panel #merchant-filter'));
  assert.match(d.body.textContent,/Save ₹12,500/);
  assert.match(d.body.textContent,/View price at website/);
  assert.doesNotMatch(d.body.textContent,/0 people clicked|44.44/);
  const merchant=d.querySelector('#merchant-filter');
  merchant.value='Flipkart';merchant.dispatchEvent(new w.Event('change'));
  assert.equal(d.querySelectorAll('.deal-card').length,1);
  d.querySelector('[data-save]').click();
  assert.equal(JSON.parse(w.localStorage.getItem('superdeal-saved'))[0],'b');
  const title=d.querySelector('.title-button');title.focus();title.click();
  assert.equal(d.querySelector('[role=dialog]').getAttribute('aria-modal'),'true');
  assert.equal(d.activeElement.getAttribute('data-close'),'');
  assert.doesNotMatch(d.querySelector('#detail').textContent,/commission|affiliate links/i);
  d.dispatchEvent(new w.KeyboardEvent('keydown',{key:'Escape'}));
  assert.equal(d.activeElement,title);
  d.querySelector('[data-go]').click();
  assert.equal(w.lastOpened,'/go/b');
  merchant.value='';merchant.dispatchEvent(new w.Event('change'));
  d.querySelector('[data-filter=under499]').click();
  assert.equal(d.querySelectorAll('.deal-card').length,1);
  assert.match(d.querySelector('.deal-card').textContent,/<script>bad/);
  d.querySelector('#reset-filters').click();
  await new Promise(resolve=>setTimeout(resolve,0));
  assert.equal(d.querySelectorAll('.deal-card').length,3);
  assert.equal(d.querySelector('#merchant-filter').value,'');
  assert.equal(d.querySelector('[data-filter=latest]').getAttribute('aria-pressed'),'true');
  dom.window.close();
});
test('image failures degrade gracefully and loading errors offer retry',async()=>{
  const dom=await setup(), d=dom.window.document;
  d.querySelector('.deal-card img').dispatchEvent(new dom.window.Event('error'));
  assert.equal(d.querySelector('.deal-card img').getAttribute('src'),'/brand/superdeals-logo.png');
  d.querySelector('.deal-card img').dispatchEvent(new dom.window.Event('error'));
  assert.equal(d.querySelector('.fallback-brand-text').textContent,'SuperDeals');
  dom.window.close();
  const offline=await setup(true);
  assert.ok(offline.window.document.querySelector('[data-retry]'));
  offline.window.close();
});

test('unknown retailers cannot leak diagnostic labels or oversized buttons',async()=>{
  const dom=await setup(), d=dom.window.document;
  // Reload with an untrusted merchant label, retaining the normal published fields.
  dom.window.fetch=async()=>({ok:true,json:async()=>({deals:[{id:'x',product_name:'Wall clock',merchant:'UNTRUSTED MERCHANT PAGE RESEARCH',current_price:318}]})});
  d.querySelector('#sort').dispatchEvent(new dom.window.Event('change'));
  await new Promise(resolve=>setTimeout(resolve,0));
  assert.equal(d.querySelector('.merchant').textContent,'SuperDeals Find');
  assert.equal(d.querySelector('.get-deal').textContent,'Get deal ↗');
  assert.doesNotMatch(d.querySelector('.deal-card').textContent,/UNTRUSTED|Product deal|Retailer/);
  assert.equal(d.querySelector('#merchant-filter').options[1].textContent,'SuperDeals Find');
  dom.window.close();
});
