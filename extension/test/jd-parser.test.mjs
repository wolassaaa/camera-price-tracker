import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
const context = {};
vm.runInNewContext(fs.readFileSync(new URL('../content/jd-parser.js', import.meta.url), 'utf8'), context);
const { parseJdPage } = context;

test('extracts an explicit estimated final price', () => {
  const result = parseJdPage('配送至 上海 满10000减500 预计到手价 ¥28499.00', 'https://item.jd.com/2.html');
  assert.equal(result.status, 'available');
  assert.equal(result.final_price, '28499.00');
  assert.equal(result.promotion_text, '满10000减500');
});
test('pauses on an abnormal account page', () => {
  assert.equal(parseJdPage('当前页面异常 请刷新或切换账户', 'https://item.jd.com/2.html').status, 'paused');
});
