import test from 'node:test';import assert from 'node:assert/strict';import {scheduledSpecialCommand,assertScheduledSource} from './scheduled-special.mjs';
const p={id:'p',title:'Hass avocado',status:'published',thumbnail:'/media/real.jpg',metadata:{unit:'each',source_draft:'d',applied_version:2},variants:[{id:'v',inventory_items:[{inventory_item_id:'i'}],price_set:{prices:[{currency_code:'usd',amount:2}]}}]};
const m='Scheduled special: Hass avocado, each, $1.50, 4 available for online pickup; starts: 2099-10-06T09:00:00-07:00; ends: 2099-10-06T18:00:00-07:00';
test('dated proposal binds exact approved identity, price, dates and allocation',()=>{const f=scheduledSpecialCommand(m,[p]);assert.equal(f.price_minor,150);assert.equal(f.quantity,4);assert.equal(f.starts_at,'2099-10-06T16:00:00.000Z');assert.equal(f.photo,p.thumbnail);assert.doesNotThrow(()=>assertScheduledSource(f,p));assert.throws(()=>assertScheduledSource(f,{...p,metadata:{...p.metadata,applied_version:3}}),/changed/)});
test('missing timezone, dates, approved identity or discount never become offers',()=>{for(const s of [m.replace('2099-10-06T09:00:00-07:00','tomorrow'),m.replace('Hass avocado','Other'),m.replace('$1.50','$3'),m.replace('4 available','0 available'),m.replaceAll('2099','2000')])assert.throws(()=>scheduledSpecialCommand(s,[p]));assert.equal(scheduledSpecialCommand('Other message',[p]),null)});

import {offerTime} from './offer-time.mjs';
import {scheduledSpecialRoutes} from './scheduled-special-routes.mjs';
test('ordinary owner clock times use Los Angeles time without guessing daylight saving',()=>{assert.equal(offerTime('2026-10-06 9am'),'2026-10-06T16:00:00.000Z');assert.equal(offerTime('2026-11-06 09:30'),'2026-11-06T17:30:00.000Z');for(const s of ['2026-03-08 2:30am','2026-11-01 1:30am','2026-02-31 9am'])assert.throws(()=>offerTime(s));assert.equal(offerTime('2026-11-01T01:30:00-07:00'),'2026-11-01T08:30:00.000Z')});

test('dated percentage resolves from the reviewed base price',()=>{const f=scheduledSpecialCommand(m.replace('$1.50','25% off'),[p]);assert.equal(f.price_minor,150);assert.equal(f.discount_rule.basis_points,2500);assert.doesNotThrow(()=>assertScheduledSource(f,p));assert.throws(()=>assertScheduledSource({...f,price_minor:100},p),/rule/)});

test('approval retry reports published after a post-commit read failure',async()=>{
 const row={id:'special',version:1,state:'draft',fields:{...scheduledSpecialCommand(m,[p]),before_quantity:6}};
 const readError=new Error('post-commit read failed');
 let failNextRead=false;
 const db={async query(sql,args){
  if(sql.startsWith('SELECT * FROM avo.scheduled_specials')){
   if(failNextRead){failNextRead=false;throw readError}
   return {rows:[{...row}]};
  }
  if(sql.includes("SET state='applying'"))Object.assign(row,{state:'applying',fields:JSON.parse(args[1])});
  if(sql.includes('SET fields=$2'))row.fields=JSON.parse(args[1]);
  if(sql.includes("SET state='published'"))Object.assign(row,{state:'published',price_list_id:args[1]});
  if(sql.includes("SET state='exception'"))row.state='exception';
  if(sql==='COMMIT')failNextRead=true;
  return {rows:[]};
 }};
 let approve;
 scheduledSpecialRoutes({
  app:{post(path,_auth,handler){if(path.endsWith('/approve'))approve=handler}},
  auth:()=>()=>{},wrap:fn=>fn,db,locked:fn=>fn(db),
  assertVersion:(draft,version)=>assert.equal(draft.version,version),
  catalog:async()=>[p],settings:async()=>({location_id:'online'}),
  engine:async op=>{
   if(op==='stock')return {levels:[{stocked_quantity:6}]};
   if(op==='move-stock')return {};
   if(op==='scheduled-special')return {price_list_id:'list'};
   assert.fail(`Unexpected engine operation: ${op}`);
  }
 });
 const req={params:{id:row.id},body:{version:row.version}},res={json:body=>body};
 await assert.rejects(()=>approve(req,res),err=>err===readError);
 assert.equal(row.state,'published');
 const {draft}=await approve(req,res);
 assert.equal(draft.state,'published');
 assert.equal(draft.price_list_id,'list');
});
