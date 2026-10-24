import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import {JSDOM} from 'jsdom';
import {priceFacts, displayRetailer, isHotDeal} from '../src/deal-facts.js';

const offers = [
  {id:'a',product_name:'LG washer',merchant:'Amazon',current_price:16490,mrp:28990,image_url:'https://images.example/washer.jpg',last_seen_at:new Date().toISOString(),category:'Appliances'},
  {id:'b',product_name:'Chocolate offer',merchant:'Flipkart',current_price:null,category:'Grocery'},
  {id:'c',product_name:'<script>bad()</script>',merchant:'amazon.in',current_price:299},
];
async function setup(fail=false) {
  const dom = new JSDOM('<div id="app"></div>',{url:'https://superdeal.example/',runScripts:'outside-only'});
  const w = dom.window;
  w.priceFacts = priceFacts;
  w.isHotDeal = isHotDeal;
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


test('EarnKaro terms show scoped coupon, conditions, source and copy action',async()=>{
  const dom=await setup(), w=dom.window, d=w.document;
  let copied='';
  Object.defineProperty(w.navigator,'clipboard',{value:{writeText:async value=>{copied=value;}}});
  w.fetch=async()=>({ok:true,json:async()=>({deals:[{
    id:'coupon',product_name:'Phone',merchant:'Amazon',current_price:12999,
    deal_terms:{source:'earnkaro',has_coupon:true,coupon_codes:['SAVE100'],
      instructions:['Apply SAVE100 at checkout'],conditions:['Minimum order ₹999'],
      source_excerpts:['<script>not executable</script>']}
  }]})});
  d.querySelector('#sort').dispatchEvent(new w.Event('change'));
  await new Promise(resolve=>setTimeout(resolve,0));
  assert.equal(d.querySelector('.coupon-badge').textContent,'Coupon available');
  d.querySelector('.title-button').click();
  assert.match(d.querySelector('.deal-terms').textContent,/Minimum order ₹999/);
  assert.equal(d.querySelector('.deal-terms script'),null);
  assert.match(d.querySelector('.detail-sheet .price-row').textContent,/12,999/);
  d.querySelector('[data-copy-code]').click();
  await new Promise(resolve=>setTimeout(resolve,0));
  assert.equal(copied,'SAVE100');
  assert.equal(d.querySelector('[data-copy-code]').textContent,'Copied');
  dom.window.close();
});


test('old coupon excerpts render FT without exposing providers or channel metadata',async()=>{
  const dom=await setup(), w=dom.window, d=w.document;
  w.fetch=async()=>({ok:true,json:async()=>({deals:[{
    id:'private',product_name:'@private_channel Phone',page_title:'Phone',merchant:'Telegram',
    description:'Nice phone\nJoin Telegram @private_channel',current_price:999,
    deal_terms:{source:'earnkaro',has_coupon:true,coupon_codes:[],instructions:[],conditions:[],
      source_excerpts:['Coupon : FT','Join Telegram @private_channel']}
  }]})});
  d.querySelector('#sort').dispatchEvent(new w.Event('change'));
  await new Promise(resolve=>setTimeout(resolve,0));
  d.querySelector('.title-button').click();
  assert.match(d.querySelector('.deal-terms').textContent,/Below are details:/);
  assert.equal(d.querySelector('.coupon-code code').textContent,'FT');
  assert.doesNotMatch(d.body.textContent,/earnkaro|telegram|private_channel|Coupon mentioned|Eligibility and final|Confirm the final price|From the/i);
  assert.equal(d.querySelector('.detail-cta').textContent,'Get deal ↗');
  dom.window.close();
});


test('hot badge, count and filter use discounts above 50 percent',async()=>{
  const dom=await setup(), w=dom.window, d=w.document;
  w.fetch=async()=>({ok:true,json:async()=>({deals:[
    {id:'hot',product_name:'Hot product',merchant:'Amazon',current_price:499,mrp:1000},
    {id:'half',product_name:'Half price',merchant:'Amazon',current_price:500,mrp:1000,click_count:100},
    {id:'missing',product_name:'Unknown saving',merchant:'Amazon',current_price:299,discount_pct:90}
  ]})});
  d.querySelector('#sort').dispatchEvent(new w.Event('change'));
  await new Promise(resolve=>setTimeout(resolve,0));
  assert.equal(d.querySelectorAll('.hot-badge').length,1);
  assert.equal(d.querySelector('#hot-count').textContent,'1');
  d.querySelector('[data-filter=hot]').click();
  assert.equal(d.querySelectorAll('.deal-card').length,1);
  assert.match(d.querySelector('.deal-card').textContent,/Hot product/);
  dom.window.close();
});


test('fresh/24-hour counter uses server totals, not the loaded card count',async()=>{
  const dom=await setup(), w=dom.window, d=w.document;
  w.fetch=async()=>({ok:true,json:async()=>({deals:offers,counts:{fresh_30m:20,total_24h:266}})});
  d.querySelector('#sort').dispatchEvent(new w.Event('change'));
  await new Promise(resolve=>setTimeout(resolve,0));
  assert.equal(d.querySelector('#fresh-count').textContent,'20/266');
  assert.equal(d.querySelector('#fresh-count').nextElementSibling.textContent,'Fresh / 24-hour deals');
  d.querySelector('[data-filter=saved]').click();
  assert.equal(d.querySelector('#fresh-count').textContent,'20/266');
  dom.window.close();
});
