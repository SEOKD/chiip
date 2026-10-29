"""오늘 텐배거 리포트 종목 고르기 (예약 작업 chiip-tenbagger-report, 하루 3건 07·13·22시 — 2026-10-29 마스터 지시, 이전 23:00 1건)
같은 날 앞 회차가 --done으로 기록한 종목은 30일 규칙으로 빠지므로 회차마다 다른 종목이 나온다.

우선순위(같은 종목은 30일 안에 다시 쓰지 않는다 — outputs/tenbagger/reports/log.csv):
  1. 마스터 요청 대기열 knowledge/models/tenbagger/report_queue.txt (한 줄에 티커 또는 id, 먼저 쓴 것부터)
  1-2. 마스터 노션 Stocks — 오늘 ±7일 어닝콜 스크립트 + 컨센서스가 입력된 종목(콜 날짜가 가까운 순, 그 콜 이후 리포트가 없으면 30일 안이라도 다시 쓴다 — 2026-10-30 마스터 지시)
  2. 텐배거 추적 목록 watch.csv의 진행 중 후보 중 리포트가 없는 것
  3. 알파 잠재력 최신 점수(knowledge/models/alpha/latest.json) 5.0 이상, 점수 높은 순
  4. 마스터 보유 종목(config/portfolio.yaml) 중 오래 안 쓴 것
사용: py scripts/tenbagger/pick_report.py            → JSON 한 줄(id·name·ticker·reason)
      py scripts/tenbagger/pick_report.py --done <id> <ticker> <html 경로> <치입 판단 한 줄>   → log.csv에 기록, 대기열에서 제거
"""
import csv
import json
import sys
from datetime import date, timedelta
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
LOG = ROOT / "outputs" / "tenbagger" / "reports" / "log.csv"
QUEUE = ROOT / "knowledge" / "models" / "tenbagger" / "report_queue.txt"
FIELDS = ["date", "id", "ticker", "html", "view"]
REPEAT_DAYS = 30


def recent(today):
    if not LOG.exists():
        return set()
    cut = (today - timedelta(days=REPEAT_DAYS)).isoformat()
    with LOG.open(encoding="utf-8", newline="") as f:
        rows = [r for r in csv.DictReader(f) if r["date"] >= cut]
    return {r["id"] for r in rows} | {r["ticker"] for r in rows if r.get("ticker")}


def _universe():
    out = {}
    for p in ("config/valuation.yaml", "config/earnings_watch.yaml"):
        d = yaml.safe_load((ROOT / p).read_text(encoding="utf-8")) or {}
        for u in (d.get("universe") or []) + (d.get("extra") or []):
            code = u.get("code") or u.get("jp_code") or ""
            out.setdefault(u["id"], {"id": u["id"], "name": u.get("name"), "ticker": code.replace(".US", "") if code else None})
    disc = yaml.safe_load((ROOT / "config" / "discovery.yaml").read_text(encoding="utf-8")) if (ROOT / "config" / "discovery.yaml").exists() else {}
    for t in (disc or {}).get("themes") or []:   # Chiip Ten-bagger Discovery 후보(일본·대만·한국 포함, 2026-10-29)
        for c in t.get("candidates") or []:
            out.setdefault(c["id"], {"id": c["id"], "name": c["name"], "ticker": str(c.get("code")), "market": c.get("market")})
    return out


def notion_pick(today, uni):
    """마스터 노션 Stocks — 오늘 ±7일 안의 어닝콜 스크립트 + 컨센서스가 입력된 종목(scripts/tenbagger/notion_stocks.py 색인, 마스터 지시 2026-10-30).
    30일 재작성 금지 대신 '그 콜 날짜 이후에 이미 쓴 리포트가 없을 것' — 새 실적이 나왔으면 30일 안이라도 다시 쓴다"""
    import notion_stocks
    rows = []
    if LOG.exists():
        with LOG.open(encoding="utf-8", newline="") as f:
            rows = list(csv.DictReader(f))
    for p in notion_stocks.eligible(today):
        tk = p["ticker"].upper()
        u = next((x for x in uni.values() if (x.get("ticker") or "").upper() == tk), None)
        eid = (u or {}).get("id") or (f"us-{tk.lower()}" if not tk.isdigit() else tk)
        if any(r["date"] >= p["call_date"] and (r["id"] == eid or (r.get("ticker") or "").upper() == tk) for r in rows):
            continue
        return {"id": eid, "name": (u or {}).get("name") or p.get("company"), "ticker": tk,
                "reason": f"노션 Stocks — 어닝콜 {p['call_date']}({p.get('date_basis')})·컨센서스 입력" + (" · IB 내용 있음" if p.get("has_ib") else ""),
                "notion_page": p.get("page_id")}
    return None


def pick(today=None):
    today = today or date.today()
    done = recent(today)
    uni = _universe()
    if QUEUE.exists():
        for line in QUEUE.read_text(encoding="utf-8").splitlines():
            key = line.strip()
            if key and key not in done:
                hit = uni.get(key) or next((u for u in uni.values() if (u.get("ticker") or "").upper() == key.upper()), None)
                return {**(hit or {"id": key, "name": key, "ticker": key}), "reason": "마스터 요청 대기열"}
    hit = notion_pick(today, uni)
    if hit:
        return hit
    tb = ROOT / "knowledge" / "models" / "tenbagger" / "watch.csv"
    if tb.exists():
        with tb.open(encoding="utf-8", newline="") as f:
            for r in csv.DictReader(f):
                if r.get("status") != "종료" and r.get("cand_id") and r["cand_id"] not in done and (r.get("ticker") or "") not in done:   # 후보 번호(TB-…)와 티커 둘 다로 중복 확인(2026-10-30 INIO 재선택 버그)
                    return {"id": r["cand_id"], "name": r.get("company"), "ticker": r.get("ticker"), "reason": "텐배거 추적 후보"}
    cov = yaml.safe_load((ROOT / "config" / "coverage.yaml").read_text(encoding="utf-8")) if (ROOT / "config" / "coverage.yaml").exists() else {}
    for c in (cov or {}).get("companies") or []:   # 발굴 위원회 통과(커버리지 focus) — 아직 리포트가 없으면 우선
        if c.get("stage", "focus") == "focus" and c["id"] not in done:
            return {"id": c["id"], "name": c.get("name"), "ticker": str(c.get("code")), "market": c.get("market"), "reason": "Chiip Ten-bagger 커버리지"}
    al = ROOT / "knowledge" / "models" / "alpha" / "latest.json"
    if al.exists():
        d = json.loads(al.read_text(encoding="utf-8"))
        rows = sorted(((k, v) for k, v in (d.get("rows") or {}).items() if (v.get("total") or 0) >= float(d.get("threshold", 5.0))),
                      key=lambda kv: -(kv[1].get("total") or 0))
        for k, v in rows:
            if k not in done:
                u = uni.get(k, {})
                return {"id": k, "name": v.get("name") or u.get("name"), "ticker": u.get("ticker"), "reason": f"알파 {v.get('total')}(최고 순)"}
    pf = yaml.safe_load((ROOT / "config" / "portfolio.yaml").read_text(encoding="utf-8")) or {}
    for h in pf.get("holdings") or []:
        if h.get("status", "보유") == "보유" and h["id"] not in done and h["ticker"] not in done:
            return {"id": h["id"], "name": h["name"], "ticker": h["ticker"], "reason": "보유 종목"}
    return {"id": None, "reason": "후보 없음(모두 30일 안에 작성)"}


def done(eid, ticker, html_path, view, today=None):
    LOG.parent.mkdir(parents=True, exist_ok=True)
    new = not LOG.exists()
    with LOG.open("a", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        if new:
            w.writeheader()
        w.writerow({"date": (today or date.today()).isoformat(), "id": eid, "ticker": ticker, "html": html_path, "view": view})
    if QUEUE.exists():
        keep = [l for l in QUEUE.read_text(encoding="utf-8").splitlines() if l.strip() and l.strip() not in (eid, ticker)]
        QUEUE.write_text("\n".join(keep) + ("\n" if keep else ""), encoding="utf-8")


def main(argv):
    sys.stdout.reconfigure(encoding="utf-8")
    if argv and argv[0] == "--done":
        done(*argv[1:5])
        print("[텐배거 리포트] 기록 완료")
        return 0
    print(json.dumps(pick(), ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
