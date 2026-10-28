// 치입 확장 서비스 워커 — 툴바 아이콘으로 옆 패널 열기, 우클릭 메뉴로 페이지·선택 영역 보내기
importScripts("api.js");

chrome.sidePanel.setPanelBehavior({ openPanelOnActionClick: true }).catch((e) => console.error(e));

chrome.runtime.onInstalled.addListener(() => {
  chrome.contextMenus.create({ id: "chiip-radar", title: "치입에게 보내기 (레이더 판정)", contexts: ["page", "selection", "link"] });
  chrome.contextMenus.create({ id: "chiip-notion", title: "치입: ⭐ 노션 기록", contexts: ["page", "selection", "link"] });
  chrome.contextMenus.create({ id: "chiip-panel", title: "치입 패널 열기", contexts: ["all"] });
});

chrome.contextMenus.onClicked.addListener(async (info, tab) => {
  if (info.menuItemId === "chiip-panel") {
    chrome.sidePanel.open({ windowId: tab.windowId });
    return;
  }
  const action = info.menuItemId === "chiip-notion" ? "notion" : "radar";
  const url = info.linkUrl || info.pageUrl || (tab && tab.url);
  const payload = { url, title: info.linkUrl ? info.linkUrl : (tab && tab.title) || url, selection: info.selectionText || "", note: "", action };
  try {
    const r = await chiipSend(payload);
    notify("치입", r.message || "보냈습니다");
  } catch (e) {
    notify("치입 — 실패", String(e.message || e) + " (치입 서버가 켜져 있는지, 설정의 토큰을 확인)");
  }
});

function notify(title, message) {
  chrome.action.setBadgeText({ text: title.includes("실패") ? "!" : "✓" });
  chrome.action.setBadgeBackgroundColor({ color: title.includes("실패") ? "#DC2626" : "#0891B2" });
  chrome.action.setTitle({ title: `${title}: ${message}` });
  setTimeout(() => chrome.action.setBadgeText({ text: "" }), 4000);
}
