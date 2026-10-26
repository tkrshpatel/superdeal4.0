import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import {JSDOM} from 'jsdom';

function setup(hash = '', handler) {
  const dom = new JSDOM('<button id="get-notified">Get notified</button>', {url:`https://superdeal.example/${hash}`, runScripts:'outside-only'});
  const w = dom.window;
  w.requests = [];
  w.fetch = async (url, options) => {
    w.requests.push({url, body:JSON.parse(options.body), options});
    return handler ? handler() : {ok:true,json:async()=>({status:'saved',email_mode:'store-only'})};
  };
  w.eval(fs.readFileSync('src/deal-alerts.js','utf8').replace('export function', 'function'));
  w.mountDealAlerts({api:path=>path, product:()=> 'iPhone 17 Pro'});
  return dom;
}
const settle = () => new Promise(resolve => setTimeout(resolve, 0));
function fill(w) {
  w.document.querySelector('#get-notified').click();
  const form=w.document.querySelector('form');
  form.elements.email.value='buyer@example.com';
  form.elements.daily_limit.value='3';
  form.elements.days.value='14';
  form.elements.consent.checked=true;
  return form;
}

test('alert form prefills product and submits chosen limits with consent',async()=>{
  const dom=setup(),w=dom.window,form=fill(w);
  assert.equal(form.elements.product.value,'iPhone 17 Pro');
  form.dispatchEvent(new w.Event('submit',{bubbles:true,cancelable:true}));
  await settle();
  assert.equal(w.requests.length,1);
  assert.deepEqual(JSON.parse(JSON.stringify(w.requests[0].body)),{product:'iPhone 17 Pro',email:'buyer@example.com',daily_limit:3,days:14,consent:true});
  assert.equal(w.requests[0].options.cache,'no-store');
  assert.equal(w.document.querySelector('#alert-title').textContent,'SuperDEals');
  assert.equal(w.document.querySelector('.alert-intro').textContent,'Thank you!!');
  assert.equal(w.document.querySelector('.alert-status').textContent,'We have saved your response. We will notify you once the deals show up!');
  assert.equal(form.hidden,true);
  dom.window.close();
});

test('invalid email or missing consent does not submit',async()=>{
  const dom=setup(),w=dom.window,form=fill(w);
  form.elements.consent.checked=false;
  form.dispatchEvent(new w.Event('submit',{cancelable:true}));
  await settle();
  assert.equal(w.requests.length,0);
  form.elements.consent.checked=true;form.elements.email.value='invalid';
  form.dispatchEvent(new w.Event('submit',{cancelable:true}));
  await settle();assert.equal(w.requests.length,0);
  dom.window.close();
});

test('failed request keeps form and preferences available for retry',async()=>{
  const dom=setup('',()=>({ok:false,status:503,json:async()=>({})})),w=dom.window,form=fill(w);
  form.dispatchEvent(new w.Event('submit',{cancelable:true}));
  await settle();
  assert.equal(form.hidden,false);
  assert.equal(form.elements.days.value,'14');
  assert.equal(form.querySelector('[type=submit]').disabled,false);
  assert.match(w.document.querySelector('.alert-status').textContent,/couldn’t save your request/);
  dom.window.close();
});

for (const action of ['confirm','stop']) {
  test(`${action} token uses a fragment, requires an explicit click and is removed from URL`,async()=>{
    const token='A'.repeat(43),dom=setup(`#alert_${action}=${token}`),w=dom.window;
    assert.equal(w.location.hash,'');assert.equal(w.requests.length,0);
    assert.equal(w.document.querySelector('form').hidden,true);
    w.document.querySelector('#alert-link-action').click();await settle();
    assert.equal(w.requests[0].url,`/api/v1/alerts/${action}`);
    assert.equal(w.requests[0].body.token,token);
    assert.match(w.document.querySelector('.alert-status').textContent,action==='confirm'?/alert is active/:/unsubscribed/);
    dom.window.close();
  });
}

test('Escape closes alert dialog and restores focus',()=>{
  const dom=setup(),w=dom.window,trigger=w.document.querySelector('#get-notified');
  trigger.focus();trigger.click();
  w.document.activeElement.dispatchEvent(new w.KeyboardEvent('keydown',{key:'Escape',bubbles:true}));
  assert.equal(w.document.querySelector('.alert-overlay').hidden,true);
  assert.equal(w.document.activeElement,trigger);
  dom.window.close();
});

for (const [status, expected] of [[403,/website address/],[405,/Restart the updated MongoDB API/],[429,/Too many requests/]]) {
  test(`alert API HTTP ${status} gives actionable feedback`,async()=>{
    const dom=setup('',()=>({ok:false,status,json:async()=>({})})),w=dom.window,form=fill(w);
    form.dispatchEvent(new w.Event('submit',{cancelable:true}));await settle();
    assert.match(w.document.querySelector('.alert-status').textContent,expected);
    assert.match(w.document.querySelector('.alert-status').textContent,new RegExp('HTTP '+status));
    dom.window.close();
  });
}
