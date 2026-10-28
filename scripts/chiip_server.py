"""치입 로컬 서버 — 크롬 확장(extension/chiip)의 데이터 창구 (마스터 지시 2026-10-28 '치입 크롬 봇')

127.0.0.1:8765에서만 열린다(외부 접속 불가). 모든 요청은 X-Chiip-Token 헤더가 맞아야 한다
(토큰: radar/state/ext_token.txt — 처음 실행 때 무작위 생성, 확장 설정 화면에 붙여 넣는다. 다른 웹사이트가 이 서버를 부르는 것을 막는다).
GET  /api/summary  시장 체제·실적 일정(알파 5.0 이상 표시)·알파 상위·포커스 상위·최근 텔레그램 알림
POST /api/send     {url,title,selection,note,action} — action 'radar'(레이더 판정 대기열) | 'notion'(⭐ 노션 기록 대기열)
API 비용 없음(모델을 부르지 않는다). 판정·기록은 기존 레이더·예약 작업이 처리한다.
사용: py scripts/chiip_server.py   (또는 scripts/start_chiip_server.ps1)
"""
import hashlib
import json
import re
import secrets
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "radar"))
from pollers import common  # noqa: E402

HOST, PORT = "127.0.0.1", 8765
TOKEN_FILE = common.STATE / "ext_token.txt"
SOURCE_ID = "src-chrome-ext"
MAX_BODY = 200_000


def token():
    if not TOKEN_FILE.exists():
        TOKEN_FILE.parent.mkdir(parents=True, exist_ok=True)
        TOKEN_FILE.write_text(secrets.token_urlsafe(24), encoding="utf-8")
    return TOKEN_FILE.read_text(encoding="utf-8").strip()


def _json(path):
    p = ROOT / path
    try:
        return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None
    except ValueError:
        return None


def recent_alerts(n=15):
    """outbox.log의 발송 기록 블록(첫 줄 시각·등급 + 이어지는 줄) 최근 n개"""
    p = common.STATE / "outbox.log"
    if not p.exists():
        return []
    head = re.compile(r"^(\d{4}-\d{2}-\d{2}T[\d:]+)\S* \[(발송됨|[^\]]+)\]\[([^\]]+)\] ?(.*)$")
    blocks = []
    for line in p.read_text(encoding="utf-8", errors="replace").splitlines():
        m = head.match(line)
        if m:
            blocks.append({"time": m.group(1), "status": m.group(2), "level": m.group(3), "text": m.group(4)})
        elif blocks:
            blocks[-1]["text"] += "\n" + line
    sent = [b for b in blocks if b["status"] == "발송됨"]
    for b in sent:
        b["text"] = b["text"][:600]
    return sent[-n:][::-1]


def summary():
    alpha = _json("knowledge/models/alpha/latest.json") or {"rows": {}, "pass": [], "threshold": 5.0}
    focus = _json("knowledge/models/focus/latest.json") or {}
    up = _json("knowledge/models/earnings/upcoming.json") or {"events": []}
    reg = _json("knowledge/models/valuation/regime/latest.json") or {}
    arow = alpha.get("rows", {})
    frows = focus.get("rows", [])
    frows = frows if isinstance(frows, list) else list(frows.values())
    today = common.now_kst().date().isoformat()
    events = []
    for e in up.get("events", []):
        if e["date"] < today:
            continue
        a = (arow.get(e["id"]) or {}).get("total")
        events.append({**e, "alpha": a, "alpha_pass": e["id"] in alpha.get("pass", [])})
    market = {k: {"value": v.get("value"), "date": v.get("date"), "chg_20": v.get("chg_20")} for k, v in (reg.get("market") or {}).items()}
    return {
        "updated": common.iso(common.now_kst()),
        "regime": {"rf_us": reg.get("rf_us"), "erp": reg.get("erp"), "as_of": reg.get("as_of"), "market": market, "alerts": reg.get("alerts", [])},
        "earnings": events[:40],
        "alpha_threshold": alpha.get("threshold", 5.0),
        "alpha_top": sorted(({"id": k, "name": r.get("name", k), "total": r["total"], "delta": r.get("delta")}
                             for k, r in arow.items() if r.get("total") is not None), key=lambda r: -r["total"])[:20],
        "focus_top": sorted(({"id": r["id"], "name": r["name"], "total": r["total"], "delta": r.get("delta")}
                             for r in frows if r.get("total") is not None), key=lambda r: -r["total"])[:20],
        "alerts": recent_alerts(),
    }


def send(payload):
    """확장에서 보낸 페이지 처리 → (ok, 메시지)"""
    url = str(payload.get("url") or "").strip()
    if not re.match(r"^https?://", url):
        return False, "http(s) 주소만 받는다"
    title = str(payload.get("title") or url)[:300]
    selection = str(payload.get("selection") or "")[:2000]
    note = str(payload.get("note") or "")[:1000]
    action = payload.get("action", "radar")
    uid = hashlib.sha1(url.encode()).hexdigest()[:16]
    snippet = "\n".join(x for x in (f"[마스터 메모] {note}" if note else "", selection) if x)
    item = common.make_item(SOURCE_ID, uid, url, title, common.iso(common.now_kst()), "마스터 제보", "ko", snippet,
                            extra={"master_note": note, "master_selection": selection, "via": "chrome-ext"})  # snippet은 200자로 잘림
    if action == "notion":
        sys.path.insert(0, str(ROOT / "radar"))
        import notify
        import telegram_inbox
        ref = notify.remember_alert(item, "MASTER", what=title, impact=note or None)
        telegram_inbox.enqueue(ref, note or None)
        return True, "노션 기록 대기열에 넣었다(토큰이 있으면 즉시, 없으면 매일 06:40 반영)"
    # 레이더: 마스터 제보는 수집 관문(매체·포커스 제한)을 거치지 않고 바로 판정 대기열로
    seen = common.load_state("seen")
    if item["item_id"] in seen:
        return True, "이미 받은 페이지 — 판정 대기열에 있음"
    seen[item["item_id"]] = item["content_hash"]
    day = common.INBOX / common.now_kst().strftime("%Y%m%d")
    day.mkdir(parents=True, exist_ok=True)
    safe = re.sub(r"[^A-Za-z0-9_.-]", "_", item["item_id"])[:120]
    (day / f"{safe}.json").write_text(json.dumps(item, ensure_ascii=False, indent=1), encoding="utf-8")
    common.save_state("seen", seen)
    return True, "레이더 판정 대기열에 넣었다(다음 수집 주기에 판정 → 중요하면 텔레그램)"


class Handler(BaseHTTPRequestHandler):
    def _reply(self, code, obj):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        origin = self.headers.get("Origin", "")
        if origin.startswith("chrome-extension://"):
            self.send_header("Access-Control-Allow-Origin", origin)
            self.send_header("Access-Control-Allow-Headers", "Content-Type, X-Chiip-Token")
            self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _authed(self):
        return secrets.compare_digest(self.headers.get("X-Chiip-Token", ""), token())

    def do_OPTIONS(self):
        self._reply(204, {})

    def do_GET(self):
        if self.path == "/api/ping":
            return self._reply(200, {"ok": True})
        if not self._authed():
            return self._reply(401, {"error": "토큰 불일치 — 확장 설정에 radar/state/ext_token.txt 값을 넣어라"})
        if self.path == "/api/summary":
            return self._reply(200, summary())
        self._reply(404, {"error": "없음"})

    def do_POST(self):
        if not self._authed():
            return self._reply(401, {"error": "토큰 불일치"})
        if self.path != "/api/send":
            return self._reply(404, {"error": "없음"})
        n = int(self.headers.get("Content-Length", "0") or 0)
        if n <= 0 or n > MAX_BODY:
            return self._reply(400, {"error": "본문 크기"})
        try:
            payload = json.loads(self.rfile.read(n))
        except ValueError:
            return self._reply(400, {"error": "JSON 아님"})
        ok, msg = send(payload)
        self._reply(200 if ok else 400, {"ok": ok, "message": msg})

    def log_message(self, fmt, *args):   # 콘솔 잡음 줄이기
        pass


def main():
    token()
    print(f"치입 서버 http://{HOST}:{PORT}  (토큰 파일: {TOKEN_FILE})")
    ThreadingHTTPServer((HOST, PORT), Handler).serve_forever()


if __name__ == "__main__":
    main()
