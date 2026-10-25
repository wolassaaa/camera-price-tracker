const API = 'http://localhost:8000/api';
const pending = new Map();

async function post(result, productId) {
  await fetch(`${API}/browser-quotes`, {method: 'POST', headers: {'content-type': 'application/json'}, body: JSON.stringify({...result, product_id: productId})});
}
async function check() {
  const watches = await fetch(`${API}/browser-watches?platform=jd`).then(response => response.json());
  for (const watch of watches) {
    const tab = await chrome.tabs.create({url: watch.url, active: false});
    pending.set(tab.id, watch);
    setTimeout(async () => {
      if (pending.has(tab.id)) { await post({url: watch.url, status: 'unavailable', reason: '页面加载超时'}, watch.product_id); pending.delete(tab.id); await chrome.tabs.remove(tab.id).catch(() => {}); }
    }, 20000);
  }
}
chrome.runtime.onMessage.addListener((message, sender) => {
  if (message.type !== 'JD_PAGE_RESULT' || !sender.tab || !pending.has(sender.tab.id)) return;
  const watch = pending.get(sender.tab.id); pending.delete(sender.tab.id);
  post(message.result, watch.product_id).finally(() => chrome.tabs.remove(sender.tab.id).catch(() => {}));
});
chrome.runtime.onInstalled.addListener(() => chrome.alarms.create('coupon-check', {periodInMinutes: 60}));
chrome.alarms.onAlarm.addListener(alarm => { if (alarm.name === 'coupon-check') check().catch(() => {}); });
