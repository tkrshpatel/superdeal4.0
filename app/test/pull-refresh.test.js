import test from 'node:test';
import assert from 'node:assert/strict';
import {JSDOM} from 'jsdom';
import {mountPullRefresh} from '../src/pull-refresh.js';

function setup({refresh=async()=>true,onPullStart=()=>false,onCancel=()=>{},height=800}={}) {
  const dom=new JSDOM('<html class="native-app"><body><div id="app"><div id="surface"></div><input id="input"></div></body></html>',{url:'https://localhost/'});
  const win=dom.window,doc=win.document;
  win.innerHeight=height;
  mountPullRefresh({refresh,onPullStart,onCancel,win,doc});
  const touch=(type,x,y,{target=doc.querySelector('#surface'),count=1}={})=>{
    const e=new win.Event(type,{bubbles:true,cancelable:true});
    Object.defineProperty(e,'touches',{value:Array.from({length:count},()=>({clientX:x,clientY:y}))});
    target.dispatchEvent(e);return e;
  };
  return {dom,win,doc,touch};
}
test('page follows the pull with a downward arrow and sync starts at half-screen before release',async()=>{
  let calls=0,stops=0,finish;
  const {dom,doc,touch}=setup({refresh:()=>{calls++;return new Promise(r=>{finish=r;});},onPullStart:()=>{stops++;return true;}});
  touch('touchstart',100,100);
  const move=touch('touchmove',100,140);
  assert.equal(move.defaultPrevented,true);
  assert.equal(stops,1);assert.equal(calls,0);
  assert.equal(doc.documentElement.style.getPropertyValue('--pull-distance'),'40px');
  assert.ok(doc.querySelector('.pull-refresh-arrow'));
  assert.match(doc.querySelector('.pull-refresh-label').textContent,/Pull down to refresh/);
  touch('touchmove',100,499);assert.equal(calls,0);
  touch('touchmove',100,500);assert.equal(calls,1);
  assert.equal(doc.documentElement.style.getPropertyValue('--pull-distance'),'0px');
  assert.equal(doc.querySelector('.pull-refresh').dataset.loading,'true');
  touch('touchend',100,500,{count:0});assert.equal(calls,1);
  finish(true);await Promise.resolve();await Promise.resolve();
  assert.match(doc.querySelector('.pull-refresh').textContent,/Deals updated/);
  dom.window.close();
});
test('half-screen threshold adapts to viewport height',()=>{
  for(const height of [600,1000]){
    let calls=0;const {dom,touch}=setup({height,refresh:async()=>{calls++;}});
    touch('touchstart',10,10);touch('touchmove',10,10+height/2-1);assert.equal(calls,0);
    touch('touchmove',10,10+height/2);assert.equal(calls,1);dom.window.close();
  }
});
test('short or cancelled pulls resume an interrupted feed without a landing refresh',()=>{
  let calls=0,resumed=0;const {dom,doc,touch}=setup({refresh:async()=>{calls++;},onPullStart:()=>true,onCancel:value=>{if(value)resumed++;}});
  touch('touchstart',10,10);touch('touchmove',10,100);touch('touchend',10,100,{count:0});
  assert.equal(calls,0);assert.equal(resumed,1);
  assert.equal(doc.documentElement.style.getPropertyValue('--pull-distance'),'0px');
  assert.equal(doc.querySelector('.pull-refresh').hidden,true);dom.window.close();
});
test('ordinary scrolling, horizontal swipes, controls, modals and multitouch do not refresh',()=>{
  let calls=0;const {dom,win,doc,touch}=setup({refresh:async()=>{calls++;}});
  const pull=(extra={})=>{touch('touchstart',10,10,extra);touch('touchmove',10,500,extra);touch('touchend',10,500,{...extra,count:0});};
  win.scrollY=200;pull();win.scrollY=0;
  touch('touchstart',10,10);touch('touchmove',500,20);touch('touchend',500,20,{count:0});
  pull({target:doc.querySelector('#input')});
  doc.body.classList.add('alert-modal-open');pull();doc.body.classList.remove('alert-modal-open');
  pull({count:2});assert.equal(calls,0);dom.window.close();
});
test('another pull can immediately supersede an in-flight sync without stale indicator updates',async()=>{
  let calls=0,stops=0;const finishes=[];
  const {dom,doc,touch}=setup({refresh:()=>{calls++;return new Promise(r=>finishes.push(r));},onPullStart:()=>{stops++;return true;}});
  const pull=()=>{touch('touchstart',10,10);touch('touchmove',10,410);};
  pull();pull();assert.equal(calls,2);assert.equal(stops,2);
  finishes[0](true);await Promise.resolve();await Promise.resolve();
  assert.equal(doc.querySelector('.pull-refresh').dataset.loading,'true');
  finishes[1](false);await Promise.resolve();await Promise.resolve();
  assert.match(doc.querySelector('.pull-refresh').textContent,/Couldn’t sync/);dom.window.close();
});
