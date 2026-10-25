function parseJdPage(text, url) {
  const page = String(text || '').replace(/\s+/g, ' ').trim();
  const paused = ['当前页面异常', '请登录', '滑块', '验证码', '配送至 香港'].find(value => page.includes(value));
  if (paused) return {status: 'paused', final_price: null, list_price: null, promotion_text: '', delivery_region: '', reason: paused};
  const price = page.match(/(?:预计到手价|到手价)\s*[¥￥]?\s*(\d+(?:\.\d{1,2})?)/);
  const promotion = page.match(/(满\d+(?:\.\d+)?减\d+(?:\.\d+)?|(?:PLUS|京贴|券)[^。；\n]{0,60})/);
  const region = page.match(/配送至\s*([^\s，。]{1,20})/);
  return {
    status: price ? 'available' : 'unavailable', final_price: price ? price[1] : null, list_price: null,
    promotion_text: promotion ? promotion[1] : '', delivery_region: region ? region[1] : '',
    reason: price ? null : '页面未显示明确券后价', url,
  };
}
globalThis.parseJdPage = parseJdPage;
