import test from 'node:test';import assert from 'node:assert/strict';import {pickupCommand,assertPickupWindows} from './pickup-command.mjs';
test('pickup messages require an exact valid date and bounded close/reopen action',()=>{assert.deepEqual(pickupCommand('Close pickup on 2026-10-08'),{date:'2026-10-08',active:false});assert.deepEqual(pickupCommand('Reopen pickup 2028-02-29.'),{date:'2028-02-29',active:true});assert.throws(()=>pickupCommand('Close pickup tomorrow'),/exact/);assert.throws(()=>pickupCommand('Close pickup 2026-02-30'),/exact/);assert.equal(pickupCommand('Delete every order'),null);});

test('pickup approval binds the whole unexpired window set',()=>{const proposed=[{id:'a',version:1},{id:'b',version:2}];assert.doesNotThrow(()=>assertPickupWindows(proposed,[...proposed].reverse()));for(const current of [[],[proposed[0]],[...proposed,{id:'c',version:1}],[proposed[0],{id:'b',version:3}]])assert.throws(()=>assertPickupWindows(proposed,current),/changed or expired/)});

test('pickup approval rejects duplicate window IDs on either side',()=>{
 const a={id:'a',version:1}, b={id:'b',version:2};
 assert.throws(()=>assertPickupWindows([a,b],[a,{...a}]),{status:409});
 assert.throws(()=>assertPickupWindows([a,{...a}],[a]),{status:409});
});

test('pickup approval rejects an omitted ID even if another window takes its place',()=>{
 const a={id:'a',version:1}, b={id:'b',version:2};
 assert.throws(()=>assertPickupWindows([a,b],[a]),{status:409});
 assert.throws(()=>assertPickupWindows([a,b],[a,{id:'c'}]),{status:409});
});

test('pickup approval accepts the same three windows in a different order',()=>{
 const a={id:'a',version:1}, b={id:'b',version:2}, c={id:'c',version:1};
 assert.doesNotThrow(()=>assertPickupWindows([a,b,c],[c,a,b]));
});
