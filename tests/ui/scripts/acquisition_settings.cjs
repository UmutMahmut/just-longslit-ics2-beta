const fs = require('node:fs'); const vm = require('node:vm'); const assert = require('node:assert/strict');
class Element {
 constructor(tag) { this.tag=tag;this.children=[];this.dataset={};this.listeners={};this._value='';this.textContent=''; }
 set value(value){this._value=String(value);} get value(){return this._value;}
 append(child){child.parent=this;this.children.push(child);} remove(){this.parent.children=this.parent.children.filter(child=>child!==this);}
 addEventListener(name,fn){this.listeners[name]=fn;}
 querySelectorAll(selector){const tags=selector.split(',').map(value=>value.trim());return this.children.flatMap(child=>[...(tags.includes(child.tag)?[child]:[]),...child.querySelectorAll(selector)]);}
 querySelector(selector){return this.querySelectorAll(selector)[0]||null;}
}
const host=new Element('div');let failedGuide=false;const puts=[];
const base={device_id:'test-camera',driver:'simulated',gain:120,offset:30,binning:1,width:512,height:512,preview_exposure_ms:100,pixel_format:'MONO16',limits:{gain:{min:0,max:600},offset:{min:0,max:100},binning:[1,2],cooling:false}};
const values={science:{...base},slit:{...base}};
const context={document:{querySelector:()=>host,createElement:tag=>new Element(tag)},AbortSignal,console,
 window:{addEventListener(){}},fetch:async(url,options)=>{
 const role=url.split('/')[4];
 if(options.method==='PUT'){
  const changes=JSON.parse(options.body);puts.push({role,changes});
  if(changes.binning){values[role].width=256;values[role].height=256;}
  Object.assign(values[role],changes);
 } else if(role==='slit'&&!failedGuide){failedGuide=true;return {ok:false,json:async()=>({detail:'temporarily unavailable'})};}
 return {ok:true,json:async()=>JSON.parse(JSON.stringify(values[role]))};
}};
vm.runInNewContext(fs.readFileSync('src/justls/ics/app/ui/v7/acquisition_settings.js','utf8'),context);
const flush=()=>new Promise(resolve=>setImmediate(resolve));
(async()=>{
 await flush(); const [science,guide]=host.children;
 assert.equal(guide.querySelector('button').textContent,'Read Settings');
 await guide.querySelector('button').onclick();await flush();assert.ok(guide.querySelectorAll('input').length>0);
 science.querySelectorAll('input').find(input=>input.name==='gain').value='121';
 await science.listeners.submit({preventDefault(){}});assert.deepEqual(puts.at(-1),{role:'science',changes:{gain:121}});
 science.querySelectorAll('select')[0].value='2';await science.listeners.submit({preventDefault(){}});
 assert.deepEqual(puts.at(-1).changes,{binning:2});assert.equal(science.querySelectorAll('input').find(input=>input.name==='width').value,'256');
 console.log('Camera settings UI logic passed: retry loading, gain apply, binning effective ROI');
})().catch(error=>{console.error(error);process.exitCode=1;});
