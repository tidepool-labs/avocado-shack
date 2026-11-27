import test from 'node:test';import assert from 'node:assert/strict';import {bufferAvailable} from './safety-buffer.mjs';
test('buffer subtracts current engine reservations once without changing physical stock',()=>{const level={stocked_quantity:12,reserved_quantity:4};assert.equal(bufferAvailable(level,2),6);assert.equal(bufferAvailable(level,20),0);assert.equal(level.stocked_quantity,12);assert.equal(bufferAvailable(level),8);assert.throws(()=>bufferAvailable(level,-1));assert.throws(()=>bufferAvailable(level,1.5));assert.throws(()=>bufferAvailable({stocked_quantity:12,reserved_quantity:NaN},0));});

for(const field of ['stocked_quantity','reserved_quantity']){
 for(const value of [null,'',' \t',true,false]){
  test(`buffer rejects ${field}=${JSON.stringify(value)}`,()=>{
   const level={stocked_quantity:12,reserved_quantity:4,[field]:value};
   assert.throws(()=>bufferAvailable(level),/Inventory availability needs review\./);
  });
 }
}

test('buffer accepts numeric strings for stock and reservations',()=>{
 assert.equal(bufferAvailable({stocked_quantity:'3',reserved_quantity:1}),2);
 assert.equal(bufferAvailable({stocked_quantity:12,reserved_quantity:'3'}),9);
});
