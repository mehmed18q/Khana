const { test } = require('node:test');
const assert = require('node:assert/strict');
const { interpolate } = require('../reader/web/scroll-sync.js');
test('different block heights map in both directions', () => {
  const points = [
    [0, 0],
    [50, 300],
    [150, 350],
    [200, 900],
  ];
  assert.equal(interpolate(points, 100), 325);
  assert.equal(interpolate(points, 325, 1), 100);
  assert.equal(interpolate(points, -20), 0);
  assert.equal(interpolate(points, 2000), 900);
});
test('empty and shared positions do not produce NaN', () => {
  assert.equal(interpolate([], 20), 0);
  assert.equal(
    interpolate(
      [
        [0, 0],
        [0, 20],
        [10, 30],
      ],
      5
    ),
    25
  );
});
