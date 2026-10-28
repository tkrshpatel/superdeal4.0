import test from 'node:test';
import assert from 'node:assert/strict';
import {createApiFetch,resolveApiBase,PRODUCTION_API} from '../src/native-api.js';

test('installed app ignores old PC addresses; website stays same origin',()=>{
  assert.equal(resolveApiBase(true,'http://192.168.1.10:8000'),PRODUCTION_API);
  assert.equal(resolveApiBase(false),'');
  assert.equal(resolveApiBase(false,'https://test.example/'),'https://test.example');
});
test('website retains browser fetch',async()=>{
  let args;
  const fetcher=createApiFetch({native:false,webFetch:async(...values)=>{args=values;return 'ok';}});
  assert.equal(await fetcher('/deals',{cache:'no-store'}),'ok');
  assert.equal(args[0],'/deals');
});
test('native alerts use HTTPS and preserve status/JSON',async()=>{
  let sent;
  const fetcher=createApiFetch({native:true,request:async options=>{sent=options;return {status:201,data:{saved:true}};}});
  const result=await fetcher(PRODUCTION_API+'/api/v1/alerts',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({product:'Headphones'})});
  assert.equal(result.status,201);assert.deepEqual(await result.json(),{saved:true});
  assert.equal(sent.headers.Origin,PRODUCTION_API);
  assert.deepEqual(sent.data,{product:'Headphones'});
  assert.equal(sent.readTimeout,20000);
});
test('native API rejects private hosts, other services and shop redirects',async()=>{
  const fetcher=createApiFetch({native:true,request:()=>assert.fail('must not connect')});
  for(const url of ['http://192.168.1.10/deals','https://evil.example/deals',PRODUCTION_API+'/go/a',PRODUCTION_API+'/api/v1/admin/logs']){
    await assert.rejects(fetcher(url),/Unsupported API address/);
  }
});
test('cancelled native feed stops publishing results',async()=>{
  let finish;
  const controller=new AbortController();
  const fetcher=createApiFetch({native:true,request:()=>new Promise(resolve=>{finish=resolve;})});
  const response=fetcher(PRODUCTION_API+'/deals',{signal:controller.signal});
  controller.abort();
  await assert.rejects(response,{name:'AbortError'});
  finish({status:200,data:{deals:[]}});
});
test('HTTP errors remain errors for feed and form handling',async()=>{
  const fetcher=createApiFetch({native:true,request:async()=>({status:429,data:{error:'limited'}})});
  const response=await fetcher(PRODUCTION_API+'/deals');
  assert.equal(response.ok,false);assert.equal(response.status,429);
});
