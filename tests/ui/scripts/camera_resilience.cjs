const fs = require('node:fs');
const vm = require('node:vm');
const assert = require('node:assert/strict');
const timers = new Map(), intervals = new Map(); let id = 0;
const toggle = {checked:true,dataset:{},listeners:{},addEventListener(n,f){this.listeners[n]=f;}};
const image = {src:'',addEventListener(){}};
const bindings = new Map(); let requests=0, healthy=false;
const document = {readyState:'complete',querySelector(s){
 if(s.includes('slit-preview-enabled'))return toggle;
 if(s.includes('slit-preview-image'))return image;
 return null;
},querySelectorAll(s){
 if(!s.includes('data-bind'))return [];
 if(!bindings.has(s))bindings.set(s,[{textContent:''}]);return bindings.get(s);
}};
const context={document,AbortController,console,window:{addEventListener(){},
 setTimeout(f,ms){const n=++id;timers.set(n,{f,ms});return n;},clearTimeout(n){timers.delete(n);},
 setInterval(f,ms){const n=++id;intervals.set(n,{f,ms});return n;},clearInterval(n){intervals.delete(n);}},
 fetch:async(url,opts)=>{
 requests++;
 if(!healthy)return new Promise((resolve,reject)=>opts.signal.addEventListener('abort',()=>reject(new Error('timeout'))));
 return {ok:true,json:async()=>({slit_camera:{state:'suspended',preview_enabled:false,error:'failed; preview suspended'}})};
 }};
vm.runInNewContext(fs.readFileSync('src/justls/ics/app/ui/v7/camera_runtime.js','utf8'),context);
const flush=()=>new Promise(r=>setImmediate(r));
(async()=>{
 await flush();
 const statusPoll=[...intervals.values()].find(t=>t.ms===10000).f;
 statusPoll();statusPoll();await flush();assert.equal(requests,1,'status polls never overlap');
 const timeout=[...timers.values()].find(t=>t.ms===15000);assert.ok(timeout);timeout.f();await flush();
 healthy=true;statusPoll();await flush();assert.equal(requests,2,'poll can recover after timeout');
 assert.equal(toggle.checked,false);
 assert.equal(image.src,'','suspended camera does not request frames');
 assert.ok([...bindings.values()].some(nodes=>nodes[0].textContent.includes('suspended')));
 healthy=false;toggle.checked=true;toggle.listeners.change();await flush();assert.equal(toggle.disabled,true);
 [...timers.values()].find(t=>t.ms===15000).f();await flush();assert.equal(toggle.disabled,false,'preview button unlocks after timeout');
 console.log('Camera timeout, coalescing and suspended preview regression passed');
})().catch(e=>{console.error(e);process.exitCode=1;});
