(() => {
  const result = parseJdPage(document.body?.innerText || '', location.href);
  chrome.runtime.sendMessage({type: 'JD_PAGE_RESULT', result}).catch(() => {});
})();
