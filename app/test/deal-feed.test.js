import test from 'node:test';
import assert from 'node:assert/strict';
import {fetchDealWindow} from '../src/deal-feed.js';

test('fetches beyond 100 deals using a shared snapshot and no total cap',async()=>{
  const requests=[], all=Array.from({length:137},(_,i)=>({id:String(i),product_name:'Product '+i}));
  const result=await fetchDealWindow(p=>p,'newest',async url=>{
    const q=new URL(url,'https://example.com').searchParams;
    requests.push(q);
    const offset=Number(q.get('offset')||0),limit=Number(q.get('limit'));
    return {ok:true,json:async()=>({deals:all.slice(offset,offset+limit),has_more:offset+limit<all.length,
      next_offset:offset+limit,as_of:'2026-10-25T12:00:00+00:00',counts:{fresh_30m:7,total_24h:137}})};
  });
  assert.equal(result.deals.length,137);
  assert.equal(result.deals.at(-1).id,'136');
  assert.equal(requests.length,3);
  assert.equal(requests[1].get('as_of'),'2026-10-25T12:00:00+00:00');
  assert.equal(requests[2].get('offset'),'96');
  assert.equal(result.counts.total_24h,137);
});

test('a broken/nonadvancing page fails instead of claiming complete search results',async()=>{
  await assert.rejects(fetchDealWindow(p=>p,'newest',async()=>({ok:true,json:async()=>({
    deals:[{id:'same'}],has_more:true,next_offset:1,as_of:'snapshot'})})),/Pagination did not advance/);
});

test('a later-page failure does not return a misleading partial catalog',async()=>{
  let calls=0;
  await assert.rejects(fetchDealWindow(p=>p,'newest',async()=> ++calls===1
    ? {ok:true,json:async()=>({deals:[{id:'1'}],has_more:true,next_offset:1})}
    : {ok:false}),/API unavailable/);
});

test('publishes the first batch before the remaining network request finishes', async()=>{
  let release, calls=0;
  const waiting=new Promise(resolve=>{release=resolve;});
  const pages=[];
  const pending=fetchDealWindow(p=>p,'newest',async()=>{
    if (++calls===1) return {ok:true,json:async()=>({deals:[{id:'first'}],has_more:true,next_offset:1})};
    await waiting;
    return {ok:true,json:async()=>({deals:[{id:'last'}],has_more:false})};
  }, {onPage:page=>pages.push(page)});
  await new Promise(resolve=>setTimeout(resolve,0));
  assert.deepEqual(pages.map(p=>p.deals.map(d=>d.id)), [['first']]);
  assert.equal(pages[0].has_more,true);
  release();
  const final=await pending;
  assert.deepEqual(final.deals.map(d=>d.id),['first','last']);
  assert.equal(pages.at(-1).has_more,false);
  assert.equal(pages[0].deals.length,1);
});

test('cancels obsolete pagination before requesting the next batch',async()=>{
  const controller=new AbortController();
  let calls=0;
  await assert.rejects(fetchDealWindow(p=>p,'newest',async()=>{
    calls++;
    return {ok:true,json:async()=>({deals:[{id:'first'}],has_more:true,next_offset:1})};
  }, {signal:controller.signal,onPage:()=>controller.abort()}), {name:'AbortError'});
  assert.equal(calls,1);
});
