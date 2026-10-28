// 치입 옆 패널 — 서버 요약 표시 + 현재 탭 보내기
const $ = (id) => document.getElementById(id);

function el(tag, text, cls) {
  const e = document.createElement(tag);
  if (text !== undefined) e.textContent = text;
  if (cls) e.className = cls;
  return e;
}

function delta(d) {
  if (d === null || d === undefined) return "";
  const s = d > 0 ? `+${d.toFixed(1)}` : d.toFixed(1);
  return ` (${s})`;
}

function fillScores(ul, rows) {
  ul.replaceChildren();
  if (!rows.length) { ul.append(el("li", "점수 없음", "muted")); return; }
  for (const r of rows) {
    const li = el("li");
    li.append(el("span", r.name));
    const sc = el("span", r.total.toFixed(1) + delta(r.delta), "score" + (r.delta > 0 ? " up" : r.delta < 0 ? " down" : ""));
    li.append(sc);
    ul.append(li);
  }
}

function render(s) {
  $("updated").textContent = "갱신 " + (s.updated || "").slice(5, 16).replace("T", " ");
  const r = s.regime || {};
  const reg = $("regime");
  reg.replaceChildren();
  if (r.rf_us != null) {
    const m = r.market || {};
    const parts = [
      `미 10년 ${(r.rf_us * 100).toFixed(2)}%`,
      r.erp != null ? `ERP ${(r.erp * 100).toFixed(2)}%` : null,
      m.hy_oas ? `하이일드 ${m.hy_oas.value}%` : null,
      m.usdkrw ? `원/달러 ${m.usdkrw.value}` : null
    ].filter(Boolean);
    reg.append(el("div", parts.join(" · ")));
    for (const a of r.alerts || []) reg.append(el("div", "⚠ " + a, "pass"));
  } else reg.append(el("div", "시장 체제 데이터 없음", "muted"));

  const eu = $("earnings");
  eu.replaceChildren();
  const evs = s.earnings || [];
  if (!evs.length) eu.append(el("li", "예정 일정 없음", "muted"));
  for (const e of evs) {
    const li = el("li");
    const left = el("span");
    if (e.alpha_pass) left.append(el("b", "● ", "pass"));
    left.append(document.createTextNode(`${e.date.slice(5)} ${e.time_kst || e.local || ""} ${e.name}`));
    li.append(left);
    li.append(el("span", e.alpha != null ? `알파 ${e.alpha.toFixed(1)}` : "미산정", "score muted"));
    eu.append(li);
  }

  fillScores($("alpha"), s.alpha_top || []);
  fillScores($("focus"), s.focus_top || []);

  const al = $("alerts");
  al.replaceChildren();
  const alerts = s.alerts || [];
  if (!alerts.length) al.append(el("li", "알림 기록 없음", "muted"));
  for (const a of alerts) {
    const li = el("li");
    li.append(el("div", `${a.time.slice(5, 16).replace("T", " ")} · ${a.level}`, "meta"));
    li.append(el("div", a.text));
    al.append(li);
  }
}

async function load() {
  $("error").hidden = true;
  try {
    render(await chiipFetch("/api/summary"));
  } catch (e) {
    $("error").hidden = false;
    $("error").textContent = "치입 서버에 연결하지 못했습니다: " + (e.message || e) +
      " — PC에서 scripts/start_chiip_server.ps1 을 실행하고, 설정에 토큰을 넣었는지 확인하세요.";
  }
}

async function currentTab() {
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  return tab;
}

async function selectionOf(tab) {
  try {
    const [res] = await chrome.scripting.executeScript({ target: { tabId: tab.id }, func: () => String(window.getSelection() || "") });
    return (res && res.result) || "";
  } catch (_) { return ""; }   // chrome:// 같은 페이지는 읽을 수 없음
}

async function showPage() {
  const tab = await currentTab();
  $("pageinfo").textContent = tab ? (tab.title || tab.url) : "";
}

async function sendCurrent(action) {
  const tab = await currentTab();
  if (!tab || !/^https?:/.test(tab.url || "")) { $("sendResult").textContent = "웹 페이지에서만 보낼 수 있습니다"; return; }
  $("sendResult").textContent = "보내는 중…";
  try {
    const r = await chiipSend({ url: tab.url, title: tab.title, selection: await selectionOf(tab), note: $("note").value.trim(), action });
    $("sendResult").textContent = "✓ " + r.message;
    $("note").value = "";
  } catch (e) {
    $("sendResult").textContent = "실패: " + (e.message || e);
  }
}

$("refresh").addEventListener("click", load);
$("sendRadar").addEventListener("click", () => sendCurrent("radar"));
$("sendNotion").addEventListener("click", () => sendCurrent("notion"));
chrome.tabs.onActivated.addListener(showPage);
chrome.tabs.onUpdated.addListener((_, info) => { if (info.title || info.url) showPage(); });

showPage();
load();
setInterval(load, 5 * 60 * 1000);   // 5분마다 갱신
