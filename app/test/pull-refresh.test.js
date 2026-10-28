import test from 'node:test';
import assert from 'node:assert/strict';
import {JSDOM} from 'jsdom';
import {mountPullRefresh} from '../src/pull-refresh.js';

function setup(refresh = async () => true, busy = () => false) {
  const dom = new JSDOM('<body><div id="surface"></div><input id="input"></body>',{url:'https://localhost/'});
  const win=dom.window, doc=win.document;
  mountPullRefresh({refresh,busy,win,doc});
  const touch=(type,x,y,{target=doc.querySelector('#surface'),count=1}={})=>{
    const e=new win.Event(type,{bubbles:true,cancelable:true});
    Object.defineProperty(e,'touches',{value:Array.from({length:count},()=>({clientX:x,clientY:y}))});
    target.dispatchEvent(e);return e;
  };
  return {dom,win,doc,touch};
}
test('vertical pull at top shows a spinner and refreshes once on release',async()=>{
  let calls=0,finish;
  const {dom,doc,touch}=setup(()=>{calls++;return new Promise(resolve=>{finish=resolve;});});
  touch('touchstart',100,100);const move=touch('touchmove',100,185);
  assert.equal(move.defaultPrevented,true);
  assert.match(doc.querySelector('.pull-refresh').textContent,/Release to refresh/);
  touch('touchend',100,185,{count:0});
  assert.equal(calls,1);assert.equal(doc.querySelector('.pull-refresh').dataset.loading,'true');
  touch('touchstart',100,100);touch('touchmove',100,200);touch('touchend',100,200,{count:0});
  assert.equal(calls,1);
  finish(true);await Promise.resolve();await Promise.resolve();
  assert.match(doc.querySelector('.pull-refresh').textContent,/Deals updated/);
  dom.window.close();
});
test('ordinary scrolling, horizontal swipes, short pulls and cancellation do not refresh',()=>{
  let calls=0;const {dom,win,touch}=setup(async()=>{calls++;});
  win.scrollY=200;touch('touchstart',10,10);touch('touchmove',10,100);touch('touchend',10,100,{count:0});
  win.scrollY=0;
  for(const [x,y] of [[10,0],[100,30],[10,50]]){touch('touchstart',10,10);touch('touchmove',x,y);touch('touchend',x,y,{count:0});}
  touch('touchstart',10,10);touch('touchmove',10,100);touch('touchcancel',10,100,{count:0});
  assert.equal(calls,0);dom.window.close();
});
test('controls, modals, multi-touch and existing feed loads block the gesture',()=>{
  let calls=0,busy=false;
  const {dom,doc,touch}=setup(async()=>{calls++;},()=>busy);
  const pull=(extra={})=>{touch('touchstart',10,10,extra);touch('touchmove',10,100,extra);touch('touchend',10,100,{...extra,count:0});};
  pull({target:doc.querySelector('#input')});
  busy=true;pull();busy=false;
  doc.body.classList.add('alert-modal-open');pull();doc.body.classList.remove('alert-modal-open');
  pull({count:2});
  assert.equal(calls,0);dom.window.close();
});
test('failed refresh reports failure and allows another pull',async()=>{
  let calls=0;const {dom,doc,touch}=setup(async()=>{calls++;return false;});
  const pull=()=>{touch('touchstart',10,10);touch('touchmove',10,100);touch('touchend',10,100,{count:0});};
  pull();await Promise.resolve();await Promise.resolve();
  assert.match(doc.querySelector('.pull-refresh').textContent,/Couldn’t refresh/);
  pull();assert.equal(calls,2);dom.window.close();
});
