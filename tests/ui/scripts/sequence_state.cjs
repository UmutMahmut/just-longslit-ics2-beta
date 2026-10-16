const fs = require('node:fs');
const vm = require('node:vm');
const assert = require('node:assert/strict');
const callbacks = new Map(); let timerId = 0;
const bindings = new Map();
const buttons = new Map();
function button() { return {dataset:{},disabled:true,listeners:{},setAttribute(){},addEventListener(name,fn){this.listeners[name]=fn;}}; }
for (const name of ['preview','load','start','finish-step','stop-readout-step','pause','resume','retry-current-step','mark-failed','abort']) buttons.set('sequence-'+name,button());
const save = {checked:false,dataset:{},addEventListener(){}};
const autoAdvance = {checked:true,disabled:false};
const planInput = {value:'bias,0,zero\ndark,1,dark',dataset:{},addEventListener(){}};
const panel = {setAttribute(){},querySelector(selector) {
 if (selector.includes('sequence-auto-advance')) return autoAdvance;
 if (selector.includes('sequence-plan-steps')) return planInput;
 const match = selector.match(/data-action="([^"]+)"/); return match ? buttons.get(match[1]) : null;
},querySelectorAll(){return [...buttons.values()];}};
const observe = {dataset:{},querySelector(selector){ if(selector.includes('observe-save-products'))return save;return button();}, querySelectorAll(){return [];}};
const document = {readyState:'complete',querySelector(selector){ if(selector.includes('v7-observe-sequence-panel'))return panel;if(selector.includes('observe-save-products'))return save;return null;},
 getElementById(){return observe;},querySelectorAll(selector){if(!bindings.has(selector))bindings.set(selector,[{textContent:''}]);return bindings.get(selector);}};
let state = {state:'loaded',active_exposure:false,current_index:0,plan:{plan_id:'browser-test',exposures:[{frame_type:'test',exp_time_s:1},{frame_type:'test',exp_time_s:2},{frame_type:'test',exp_time_s:3}]},step_results:[]};
const requests=[];
const context={document,AbortController,CustomEvent:class {constructor(name,options){this.type=name;this.detail=options?.detail;}},console,
 window:{setTimeout(fn,delay){const id=++timerId;callbacks.set(id,{fn,delay});return id;},clearTimeout(id){callbacks.delete(id);},dispatchEvent(){},addEventListener(){}},
 fetch:async(url,options)=>{
 requests.push({url,body:options.body});
 if(url.endsWith('/start'))state={...state,active_exposure:true,state:'running'};
 const payload=JSON.parse(JSON.stringify(state));
 return {ok:true,headers:{get:()=> 'request-test'},json:async()=>url.endsWith('/status')?payload:{ok:true,sequence:payload}};
 }};
vm.runInNewContext(fs.readFileSync('src/justls/ics/app/ui/v7/sequence_runtime.js','utf8'),context);
const flush=()=>new Promise(resolve=>setImmediate(resolve));
(async()=>{
 await flush();assert.equal(buttons.get('sequence-start').disabled,false);
 for(let index=0;index<3;index++){
  buttons.get('sequence-start').listeners.click();await flush();assert.equal(buttons.get('sequence-start').disabled,true);
  state={...state,active_exposure:false,current_index:index+1,state:index===2?'completed':'running',step_results:[...state.step_results,{state:'completed'}]};
  const poll=[...callbacks.entries()].find(([,entry])=>entry.delay===750);assert.ok(poll,'active sequence schedules status polling');callbacks.delete(poll[0]);poll[1].fn();await flush();
  assert.equal(buttons.get('sequence-start').disabled,index===2,'next step becomes available after backend auto-readout');
 }
 assert.ok(requests.filter(request=>request.url.endsWith('/status')).length>=4);
 autoAdvance.checked=true;
 buttons.get('sequence-preview').listeners.click(); await flush();
 assert.equal(JSON.parse(requests.at(-1).body).auto_advance,true);
 autoAdvance.checked=false;
 buttons.get('sequence-load').listeners.click(); await flush();
 assert.equal(JSON.parse(requests.at(-1).body).auto_advance,false);

 console.log('Sequence browser state regression passed: three steps unlock via background polling');
})().catch(error=>{console.error(error);process.exitCode=1;});
