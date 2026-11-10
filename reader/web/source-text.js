/* Cache source indexes once per edit; caret moves only need a binary search. */
(() => {
  'use strict';
  const cache = new WeakMap();
  function index(source) {
    const lines = source.split('\n'),
      starts = [0];
    for (let i = 1; i < lines.length; i++) starts.push(starts[i - 1] + lines[i - 1].length + 1);
    let words = 0;
    const pattern = /[\p{L}\p{N}_\u200c]+/gu;
    while (pattern.exec(source)) words++;
    return { source, lines, starts, words, bytes: new TextEncoder().encode(source).length };
  }
  function get(owner) {
    const source = owner.value ?? owner.source ?? '';
    let value = cache.get(owner);
    if (value?.source !== source) {
      value = index(source);
      cache.set(owner, value);
    }
    return value;
  }
  function position(data, offset) {
    let low = 0,
      high = data.starts.length;
    while (low < high) {
      const middle = (low + high) >>> 1;
      if (data.starts[middle] <= offset) low = middle + 1;
      else high = middle;
    }
    const line = Math.max(0, low - 1);
    return { line, column: [...data.source.slice(data.starts[line], offset)].length };
  }
  const api = { index, get, position };
  if (typeof window !== 'undefined') window.ReaderSourceText = api;
  if (typeof module !== 'undefined') module.exports = api;
})();
