// 치입 확장 설정 — 서버 토큰 저장·연결 시험
const tokenInput = document.getElementById("token");
const msg = document.getElementById("msg");

chrome.storage.local.get("token").then(({ token }) => { tokenInput.value = token || ""; });

document.getElementById("save").addEventListener("click", async () => {
  await chrome.storage.local.set({ token: tokenInput.value.trim() });
  msg.textContent = "저장했습니다.";
});

document.getElementById("test").addEventListener("click", async () => {
  await chrome.storage.local.set({ token: tokenInput.value.trim() });
  try {
    const s = await chiipFetch("/api/summary");
    msg.textContent = `연결됨 — 실적 일정 ${s.earnings.length}건, 알림 ${s.alerts.length}건`;
  } catch (e) {
    msg.textContent = "실패: " + (e.message || e);
  }
});
