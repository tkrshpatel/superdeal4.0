import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
test('service worker never intercepts APIs, admin responses, redirects or query URLs',()=>{
  const handlers={};
  vm.runInNewContext(fs.readFileSync('public/sw.js','utf8'),{
    self:{location:{origin:'https://shop.example'},addEventListener:(name,fn)=>{handlers[name]=fn;}},URL,
  });
  for(const path of ['/api/v1/admin/logs','/api/v1/deals','/deals?limit=100','/go/id','/health','/private?token=x']) {
    let intercepted=false;
    handlers.fetch({request:{method:'GET',url:'https://shop.example'+path,mode:'cors'},respondWith:()=>{intercepted=true;}});
    assert.equal(intercepted,false,path);
  }
});
