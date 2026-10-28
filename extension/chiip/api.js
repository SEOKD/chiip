// 치입 로컬 서버 호출 공통 (scripts/chiip_server.py)
const CHIIP_BASE = "http://127.0.0.1:8765";

async function chiipToken() {
  const { token } = await chrome.storage.local.get("token");
  return token || "";
}

async function chiipFetch(path, options = {}) {
  const token = await chiipToken();
  const res = await fetch(CHIIP_BASE + path, {
    ...options,
    headers: { "Content-Type": "application/json", "X-Chiip-Token": token, ...(options.headers || {}) }
  });
  const body = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(body.error || body.message || `HTTP ${res.status}`);
  return body;
}

async function chiipSend(payload) {
  return chiipFetch("/api/send", { method: "POST", body: JSON.stringify(payload) });
}
