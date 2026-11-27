import test from 'node:test';import assert from 'node:assert/strict';import {variantAvailability} from './availability.mjs';
test('display availability subtracts native holds and safety buffer exactly once',()=>{assert.equal(variantAvailability({inventory_items:[{inventory_item_id:'a'}]},[{inventory_item_id:'a',stocked_quantity:12,reserved_quantity:3}],{a:2}),7)});
test('box choices share exact component bottleneck and aggregate repeated links',()=>{const levels=[{inventory_item_id:'a',stocked_quantity:10,reserved_quantity:1},{inventory_item_id:'b',stocked_quantity:6,reserved_quantity:0}];assert.equal(variantAvailability({inventory_items:[{inventory_item_id:'a',required_quantity:3},{inventory_item_id:'b',required_quantity:2}]},levels),3);assert.equal(variantAvailability({inventory_items:[{inventory_item_id:'a',required_quantity:2},{inventory_item_id:'a',required_quantity:3}]},levels),1);assert.equal(variantAvailability({inventory_items:[{inventory_item_id:'missing'}]},levels),0);assert.throws(()=>variantAvailability({inventory_items:[{inventory_item_id:'a',required_quantity:.5}]},levels))});

test('box availability uses the smaller component capacity in either link order', () => {
  const levels = [
    { inventory_item_id: 'a', stocked_quantity: 11, reserved_quantity: 0 },
    { inventory_item_id: 'b', stocked_quantity: 8, reserved_quantity: 0 },
  ];
  const limited = { inventory_item_id: 'a', required_quantity: 4 }; // 2 complete boxes
  const ample = { inventory_item_id: 'b', required_quantity: 2 }; // 4 complete boxes
  assert.equal(variantAvailability({ inventory_items: [limited, ample] }, levels), 2, 'limiting component first');
  assert.equal(variantAvailability({ inventory_items: [ample, limited] }, levels), 2, 'limiting component last');
});

test('one missing level makes a box unavailable even when its other components are stocked', () => {
  const levels = [
    { inventory_item_id: 'a', stocked_quantity: 5, reserved_quantity: 0 },
    { inventory_item_id: 'b', stocked_quantity: 3, reserved_quantity: 0 },
  ];
  const variant = { inventory_items: [
    { inventory_item_id: 'a' },
    { inventory_item_id: 'missing' },
    { inventory_item_id: 'b' },
  ] };
  assert.equal(variantAvailability(variant, levels), 0);
});
