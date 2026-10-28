import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import {JSDOM} from 'jsdom';
import {openShopLink} from '../src/shop-link.js';
import {priceFacts, displayRetailer, isHotDeal} from '../src/deal-facts.js';

const offers = [
  {id:'a',product_name:'LG washer',merchant:'Amazon',current_price:16490,mrp:28990,image_url:'https://images.example/washer.jpg',last_seen_at:new Date().toISOString(),category:'Appliances'},
  {id:'b',product_name:'Chocolate offer',merchant:'Flipkart',current_price:null,category:'Grocery'},
  {id:'c',product_name:'<script>bad()</script>',merchant:'amazon.in',current_price:299},
];
async function setup(fail=false, native=false) {
  const dom = new JSDOM('<div id="app"></div>',{url:'https://superdeal.example/',runScripts:'outside-only'});
  const w = dom.window;
  w.priceFacts = priceFacts;
  w.isHotDeal = isHotDeal;
  w.displayRetailer = displayRetailer;
  w.openShopLink = openShopLink;
  w.registerPlugin = () => ({open:async()=>({opened:false})});
  w.Browser = {open:async({url})=>{w.nativeBrowsed=url;}};
  w.Capacitor = {isNativePlatform:()=>native};
  w.SplashScreen = {hide:async()=>{}};
  w.mountPullRefresh = ({refresh,onPullStart,onCancel}) => {w.refreshFeed=refresh;w.startPull=onPullStart;w.cancelPull=onCancel;};
  w.scrollTo = () => {w.scrollY=0;};
  w.fetch = async()=> {if(fail) throw Error('offline'); return {ok:true,json:async()=>({deals:offers})};};
  w.API_BASE = '';
  w.apiFetch = (...args) => w.fetch(...args);
  w.open = url => {w.lastOpened=url;};
  w.eval(fs.readFileSync('src/deal-feed.js','utf8').replace('export async function', 'async function'));
  w.eval(fs.readFileSync('src/deal-alerts.js','utf8').replace('export function', 'function'));
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
  assert.ok(d.querySelector('.section-head #sort'));
  assert.ok(d.querySelector('.section-head #merchant-filter'));
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


test('hot badge, count and filter include recent up-to savings at 60 percent',async()=>{
  const dom=await setup(), w=dom.window, d=w.document;
  w.fetch=async()=>({ok:true,json:async()=>({deals:[
    {id:'hot',product_name:'Hot product',merchant:'Amazon',offer_facts:{version:1,current_price:null,mrp:null,discount_pct:60,discount_kind:'up_to'},last_seen_at:new Date(Date.now()-3*3600000).toISOString()},
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


test('store picker supports search, multiple selections, removable chips and reset',async()=>{
  const dom=await setup(),w=dom.window,d=w.document;
  assert.ok(d.querySelector('.section-head #store-picker'));
  assert.equal(d.querySelector('#store-label').textContent,'Stores');
  assert.equal(d.querySelector('#store-value').textContent,'All');
  assert.doesNotMatch(d.querySelector('#store-summary').textContent,/Stores:/);
  assert.ok(d.querySelector('.section-head .sort-control #sort'));
  assert.equal(d.querySelector('.store-chips'),null);
  d.querySelector('#store-summary').click();
  assert.equal(d.querySelector('#store-picker').open,true);
  d.querySelector('#store-search').value='flip';
  d.querySelector('#store-search').dispatchEvent(new w.Event('input'));
  assert.equal(d.querySelectorAll('#store-options input').length,1);
  const choose=name=>{
    const input=[...d.querySelectorAll('#store-options input')].find(i=>i.value===name);
    input.checked=true;input.dispatchEvent(new w.Event('change',{bubbles:true}));
  };
  choose('Flipkart');
  assert.equal(d.querySelectorAll('.deal-card').length,1);
  d.querySelector('#store-search').value='';d.querySelector('#store-search').dispatchEvent(new w.Event('input'));
  choose('Amazon');
  assert.equal(d.querySelectorAll('.deal-card').length,3);
  assert.equal(d.querySelectorAll('.selected-store').length,2);
  assert.match(d.querySelector('#store-summary').textContent,/2 selected/);
  d.querySelector('[data-remove-store="Amazon"]').click();
  assert.equal(d.querySelectorAll('.deal-card').length,1);
  d.querySelector('#store-picker').dispatchEvent(new w.KeyboardEvent('keydown',{key:'Escape',bubbles:true}));
  assert.equal(d.querySelector('#store-picker').open,false);
  d.querySelector('#reset-filters').click();
  await new Promise(resolve=>setTimeout(resolve,0));
  assert.equal(d.querySelector('#selected-stores').hidden,true);
  assert.match(d.querySelector('#store-summary').textContent,/All/);
  dom.window.close();
});

test('grid pagination renders 24 at a time and search reaches beyond the first 100',async()=>{
  const dom=await setup(),w=dom.window,d=w.document;
  const offers=Array.from({length:137},(_,i)=>({id:'page'+i,product_name:i===136?'Unique distant product':'Item '+i,merchant:'Amazon'}));
  w.fetch=async url=>{
    const q=new URL(url,'https://superdeal.example').searchParams;
    const offset=Number(q.get('offset')||0),limit=Number(q.get('limit'));
    return {ok:true,json:async()=>({deals:offers.slice(offset,offset+limit),has_more:offset+limit<offers.length,next_offset:offset+limit,as_of:new Date().toISOString()})};
  };
  d.querySelector('#sort').dispatchEvent(new w.Event('change'));
  await new Promise(resolve=>setTimeout(resolve,0));
  assert.equal(d.querySelectorAll('.deal-card').length,24);
  d.querySelector('#load-more-deals').click();
  assert.equal(d.querySelectorAll('.deal-card').length,48);
  const search=d.querySelector('#search');
  search.value='Unique distant';search.dispatchEvent(new w.Event('input'));
  assert.equal(d.querySelectorAll('.deal-card').length,1);
  assert.match(d.querySelector('.deal-card').textContent,/Unique distant product/);
  assert.equal(d.querySelector('#feed-pagination').hidden,true);
  dom.window.close();
});

test('first page is usable while later pages load and partial failures remain explicit',async()=>{
  const dom=await setup(),w=dom.window,d=w.document;
  let release;
  const waiting=new Promise(resolve=>{release=resolve;});
  w.fetch=async url=>{
    const offset=new URL(url,'https://superdeal.example').searchParams.get('offset');
    if (!offset) return {ok:true,json:async()=>({deals:[{id:'fast',product_name:'First batch product',merchant:'Amazon'}],has_more:true,next_offset:1})};
    await waiting;
    return {ok:false};
  };
  d.querySelector('#sort').dispatchEvent(new w.Event('change'));
  await new Promise(resolve=>setTimeout(resolve,0));
  assert.equal(d.querySelectorAll('.deal-card').length,1);
  assert.match(d.querySelector('.deal-card').textContent,/First batch product/);
  assert.equal(d.querySelector('.feed-more-label').textContent,'Loading...');
  assert.equal(d.querySelector('#load-more-deals').disabled,true);
  assert.equal(d.querySelector('#feed-status').hidden,true);
  d.querySelector('.title-button').click();
  assert.equal(d.querySelector('#detail').classList.contains('hidden'),false);
  release();
  await new Promise(resolve=>setTimeout(resolve,0));
  assert.equal(d.querySelectorAll('.deal-card').length,1);
  assert.match(d.querySelector('#feed-status').textContent,/Results may be incomplete/);
  assert.ok(d.querySelector('#feed-status [data-retry]'));
  dom.window.close();
});

test('one bottom control switches from loading to show more after the final page',async()=>{
  const dom=await setup(),w=dom.window,d=w.document;
  let release;
  const waiting=new Promise(resolve=>{release=resolve;});
  const first=Array.from({length:48},(_,i)=>({id:'switch'+i,product_name:'Product '+i,merchant:'Amazon'}));
  w.fetch=async url=>{
    if (!new URL(url,'https://superdeal.example').searchParams.has('offset')) {
      return {ok:true,json:async()=>({deals:first,has_more:true,next_offset:48})};
    }
    await waiting;
    return {ok:true,json:async()=>({deals:[{id:'last',product_name:'Last product'}],has_more:false})};
  };
  d.querySelector('#sort').dispatchEvent(new w.Event('change'));
  await new Promise(resolve=>setTimeout(resolve,0));
  const button=d.querySelector('#load-more-deals');
  assert.equal(d.querySelectorAll('#load-more-deals').length,1);
  assert.equal(button.disabled,true);
  assert.equal(button.textContent,'Loading...');
  assert.equal(d.querySelector('#feed-pagination').hidden,false);
  assert.equal(d.querySelector('#feed-status').hidden,true);
  release();
  await new Promise(resolve=>setTimeout(resolve,0));
  assert.equal(button.disabled,false);
  assert.equal(button.textContent,'Show more deals');
  assert.equal(d.querySelector('#feed-status').hidden,true);
  button.click();button.click();
  assert.equal(d.querySelectorAll('.deal-card').length,49);
  assert.equal(d.querySelector('#feed-pagination').hidden,true);
  dom.window.close();
});

test('cards/details preserve exact, up-to and conditional discount distinctions',async()=>{
  const dom=await setup(),w=dom.window,d=w.document;
  w.fetch=async()=>({ok:true,json:async()=>({deals:[
    {id:'exact',product_name:'Headphones',offer_facts:{version:1,current_price:null,mrp:null,discount_pct:60,discount_kind:'exact'}},
    {id:'upto',product_name:'Shoes',offer_facts:{version:1,current_price:499,mrp:null,discount_pct:80,discount_kind:'up_to'}},
    {id:'bank',product_name:'Watch',offer_facts:{version:1,current_price:500,mrp:1000,discount_pct:50,discount_kind:'calculated',conditional_offers:[{label:'Bank offer: 10% off'}]}}
  ]})});
  d.querySelector('#sort').dispatchEvent(new w.Event('change'));await new Promise(r=>setTimeout(r,0));
  const cards=d.querySelectorAll('.deal-card');
  assert.match(cards[0].textContent,/60% off/);assert.doesNotMatch(cards[0].textContent,/HOT/);
  assert.equal(cards[0].querySelector('s'),null);
  assert.match(cards[1].textContent,/Up to 80% off/);assert.doesNotMatch(cards[1].textContent,/HOT/);
  d.querySelector('[data-filter=discount]').click();
  assert.equal(d.querySelectorAll('.deal-card').length,2);
  d.querySelector('[data-filter=latest]').click();
  d.querySelector('[data-open=bank] .title-button').click();
  assert.match(d.querySelector('#detail').textContent,/10% off/);
  assert.doesNotMatch(d.querySelector('#detail').textContent,/Bank offer:/);
  assert.doesNotMatch(d.querySelector('#detail').textContent,/earnkaro|telegram/i);
  dom.window.close();
});

test('Eha headline shows Up to 52% off and From price alongside coupon badge',async()=>{
  const dom=await setup(),w=dom.window,d=w.document;
  w.fetch=async()=>({ok:true,json:async()=>({deals:[{id:'eha',product_name:'Eha Pots & Plants',
    deal_terms:{has_coupon:true,instructions:['Apply coupon']},
    offer_facts:{version:2,current_price:null,mrp:null,discount_pct:52,discount_kind:'up_to',starting_price:419,conditional_offers:[]}}]})});
  d.querySelector('#sort').dispatchEvent(new w.Event('change'));await new Promise(r=>setTimeout(r,0));
  const card=d.querySelector('.deal-card');
  assert.match(card.querySelector('.discount-badge').textContent,/Up to 52% off/);
  assert.match(card.textContent,/From ₹419/);
  assert.match(card.textContent,/Coupon available/);
  assert.doesNotMatch(card.textContent,/HOT/);
  card.querySelector('.title-button').click();
  assert.match(d.querySelector('#detail').textContent,/Apply coupon/);
  dom.window.close();
});

test('coupon percentage label omits Coupon offer prefix in cards and details',async()=>{
  const dom=await setup(),w=dom.window,d=w.document;
  w.fetch=async()=>({ok:true,json:async()=>({deals:[{id:'coupon',product_name:'Pots',
    offer_facts:{version:2,current_price:null,mrp:null,discount_pct:null,discount_kind:null,
    conditional_offers:[{label:'Coupon offer: 52% off',kind:'coupon_offer'}]}}]})});
  d.querySelector('#sort').dispatchEvent(new w.Event('change'));await new Promise(r=>setTimeout(r,0));
  const card=d.querySelector('.deal-card');
  assert.equal(card.querySelector('.discount-badge').textContent,'52% off');
  assert.doesNotMatch(card.textContent,/Coupon offer:/i);
  card.querySelector('.title-button').click();
  assert.match(d.querySelector('#detail').textContent,/52% off/);
  assert.doesNotMatch(d.querySelector('#detail').textContent,/Coupon offer:/i);
  dom.window.close();
});

for (const [label, expected] of [
  ['Bank offer: 20% off','20% off'],
  ['Coupon offer: ₹200','₹200 off'],
  ['Bank offer: Rs 500','Rs 500 off'],
  ['Additional offer: Up to ₹500','Up to ₹500 off'],
  ['₹200 off','₹200 off'],
  ['Additional offer: 10% off','10% off'],
  ['Cashback: Up to 15% cashback','Up to 15% cashback'],
  ['Cashback: ₹500','₹500 cashback']
]) {
  test('clean display label: '+label, async()=>{
    const dom=await setup(),w=dom.window,d=w.document;
    w.fetch=async()=>({ok:true,json:async()=>({deals:[{id:'clean',product_name:'Test product',
      offer_facts:{version:2,current_price:null,mrp:null,discount_pct:null,discount_kind:null,conditional_offers:[{label}]}}]})});
    d.querySelector('#sort').dispatchEvent(new w.Event('change'));
    await new Promise(r=>setTimeout(r,0));
    assert.equal(d.querySelector('.discount-badge').textContent,expected);
    dom.window.close();
  });
}


test('effective source price uses normal price typography and a separate qualifier',async()=>{
  const dom=await setup(),w=dom.window,d=w.document;
  w.fetch=async()=>({ok:true,json:async()=>({deals:[{id:'effective',product_name:'Orient Electric Ceiling Fan',
    offer_facts:{version:4,current_price:1500,effective_price:1255,mrp:2500,discount_pct:null,
      conditional_offers:[{label:'Coupon offer: 7% off'}]}}]})});
  d.querySelector('#sort').dispatchEvent(new w.Event('change'));
  await new Promise(r=>setTimeout(r,0));
  const card=d.querySelector('.deal-card'),price=card.querySelector('.price-row');
  assert.match(price.textContent,/1,255/);
  assert.doesNotMatch(price.textContent,/1,500|2,500|Effective|7%/);
  assert.equal(price.querySelector('.unknown-price'),null);
  assert.match(card.querySelector('.card-top').textContent,/Effective price/);
  card.querySelector('.title-button').click();
  assert.match(d.querySelector('#detail').textContent,/Effective price; apply/);
  dom.window.close();
});

test('native refresh resets to landing and displays the first batch before remaining pages finish',async()=>{
  const dom=await setup(false,true),w=dom.window,d=w.document;
  d.querySelector('#search').value='Washer';d.querySelector('#search').dispatchEvent(new w.Event('input'));
  d.querySelector('[data-filter=saved]').click();
  d.querySelector('#category-filter').value='Appliances';
  let release;
  const later=new Promise(resolve=>{release=resolve;});
  const first=Array.from({length:48},(_,i)=>({id:'new'+i,product_name:'New product '+i,merchant:'Amazon'}));
  w.fetch=async url=>{
    if(!new URL(url,'https://superdeal.example').searchParams.has('offset')) return {ok:true,json:async()=>({deals:first,has_more:true,next_offset:48})};
    await later;return {ok:true,json:async()=>({deals:[{id:'last',product_name:'Last product'}],has_more:false})};
  };
  w.startPull();
  const pending=w.refreshFeed();
  assert.equal(d.querySelector('#search').value,'');
  assert.equal(d.querySelector('[data-filter=latest]').getAttribute('aria-pressed'),'true');
  assert.equal(d.querySelector('#category-filter').value,'');
  await new Promise(r=>setTimeout(r,0));
  assert.equal(d.querySelectorAll('.deal-card').length,24);
  assert.match(d.querySelector('.deal-card').textContent,/New product/);
  assert.equal(d.querySelector('.feed-more-label').textContent,'Loading...');
  release();assert.equal(await pending,true);
  assert.equal(d.querySelector('.feed-more-label').textContent,'Show more deals');
  dom.window.close();
});

test('starting a pull aborts the active request and stale results cannot replace refreshed cards',async()=>{
  const dom=await setup(false,true),w=dom.window,d=w.document;
  let signal,finish;
  w.fetch=async(url,options)=>{signal=options.signal;return new Promise(resolve=>{finish=resolve;});};
  d.querySelector('#sort').dispatchEvent(new w.Event('change'));
  assert.equal(signal.aborted,false);
  assert.equal(w.startPull(),true);
  assert.equal(signal.aborted,true);
  w.fetch=async()=>({ok:true,json:async()=>({deals:[{id:'fresh',product_name:'Fresh landing product'}]})});
  assert.equal(await w.refreshFeed(),true);
  finish({ok:true,json:async()=>({deals:[{id:'stale',product_name:'Stale product'}]})});
  await new Promise(r=>setTimeout(r,0));
  assert.match(d.querySelector('.deal-card').textContent,/Fresh landing product/);
  assert.doesNotMatch(d.querySelector('#deals').textContent,/Stale product/);
  dom.window.close();
});

test('cancelled pull resumes an interrupted initial fetch',async()=>{
  const dom=await setup(false,true),w=dom.window,d=w.document;
  let requests=0;
  w.fetch=async()=>{requests++;return {ok:true,json:async()=>({deals:offers})};};
  w.cancelPull(true);await new Promise(r=>setTimeout(r,0));
  assert.ok(requests>0);assert.equal(d.querySelectorAll('.deal-card').length,3);
  dom.window.close();
});

test('sync milestone fires when the first 60 deals arrive while remaining pages continue loading',async()=>{
  const dom=await setup(false,true),w=dom.window,d=w.document;
  let finish,initialReady=0;
  const later=new Promise(resolve=>{finish=resolve;});
  const first=Array.from({length:60},(_,i)=>({id:'sixty'+i,product_name:'Product '+i,merchant:'Amazon'}));
  w.fetch=async url=>{
    const params=new URL(url,'https://superdeal.example').searchParams;
    if(!params.has('offset')) {
      assert.equal(params.get('limit'),'60');
      return {ok:true,json:async()=>({deals:first,has_more:true,next_offset:60})};
    }
    assert.equal(params.get('limit'),'48');
    await later;
    return {ok:true,json:async()=>({deals:[{id:'extra',product_name:'More product'}],has_more:false})};
  };
  const pending=w.refreshFeed({onInitialBatch:()=>{initialReady++;}});
  await new Promise(r=>setTimeout(r,0));
  assert.equal(initialReady,1);
  assert.equal(d.querySelectorAll('.deal-card').length,24);
  assert.equal(d.querySelector('.feed-more-label').textContent,'Loading...');
  finish();assert.equal(await pending,true);assert.equal(initialReady,1);
  dom.window.close();
});
