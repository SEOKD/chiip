"""Portfolio Buy Call (마스터 지시 2026-11-02 "Chiip Portfolio에서는 알파 점수가 높은 종목을 나에게 Buy Call을 주기로 한 구조" → 점검 뒤 "Portfolio Buy Call 구조 수정해")

리포트의 규칙 계산 등급을 현재가로 다시 잰다. Buy 이상이고 알파가 기준 이상이면 Portfolio 데일리에 올린다.
  등급: scripts/tenbagger/report_layout.py rating — 목표주가 업사이드·손익비·DCF. 모델이 바꾸지 않는다
  알파: knowledge/models/alpha/latest.json, 없으면 리포트 값
  리포트: 최신 양식 3이고 config/composite.yaml buy_call.report_days 안
  진입·해제는 knowledge/models/portfolio/buy_call_log.csv에 쌓아 성적표 재료로 쓴다
매매·비중·금액 지시가 아니다. 마스터 포지션을 읽지 않는다.
사용: py scripts/discovery/buy_call.py --symbols            # 시세를 받을 TradingView 종목
      py scripts/discovery/buy_call.py [--dry] [--killed 티커 ...]   # radar/state/composite_in.json 시세로 판정
"""
import argparse
import csv
import json
import re
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "tenbagger"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import composite  # noqa: E402
import report_layout  # noqa: E402

REP = ROOT / "outputs" / "tenbagger" / "reports"
SYMBOLS = ROOT / "config" / "tradingview_symbols.csv"
IN = ROOT / "radar" / "state" / "composite_in.json"
LATEST = ROOT / "knowledge" / "models" / "portfolio" / "buy_call_latest.json"
LOG = ROOT / "knowledge" / "models" / "portfolio" / "buy_call_log.csv"
LOG_FIELDS = ["date", "event", "ticker", "id", "grade", "price", "target", "upside", "rr", "alpha", "report", "why"]
KST = timezone(timedelta(hours=9))
FOOT = "규칙 계산 등급이며 매매·비중·금액 지시가 아님 · 공개 자료 기반 분석이며 투자 권유가 아님"
NUM = re.compile(r"[\d,]+(?:\.\d+)?")


def tile(d, key):
    return next((t.get("v") for t in d.get("tiles") or [] if t.get("k") == key), None)


def scenario(d):
    """리포트의 (발행가, 약세, 강세, DCF 값). 2026-11-02 뒤 리포트는 verdict에 있고, 그 전 리포트는 업사이드·손익비에서 되짚는다"""
    v = d.get("verdict") or {}
    if v.get("price") and v.get("bear") and v.get("bull"):
        return v["price"], v["bear"], v["bull"], (v["price"] * (1 + v["dcf_up"]) if v.get("dcf_up") is not None else None)   # None = DCF 산정 불가(ADR-039)
    m = NUM.search(str(tile(d, "주가") or ""))
    price = float(m.group().replace(",", "")) if m else None
    if not price or v.get("downside") is None or not v.get("rr"):
        return None
    down = abs(v["downside"])
    dcf = re.search(r"DCF 기준 업사이드는 기본 ([+\-−]?\d+)%", json.dumps(d, ensure_ascii=False))
    dcf_up = float(dcf.group(1).replace("−", "-")) / 100 if dcf else 0.0
    return price, price * (1 - down), price * (1 + v["rr"] * down), price * (1 + dcf_up)


def reports(root=REP):
    """{id: 리포트} — 종목별 가장 최근 양식 3 리포트"""
    path = root / "log.csv"
    if not path.exists():
        return {}
    with path.open(encoding="utf-8", newline="") as f:
        rows = [r for r in csv.DictReader(f) if r.get("id") and r.get("html")]
    latest = {r["id"]: r for r in rows}
    out = {}
    for cid, r in latest.items():
        p = (root / Path(r["html"]).name).with_suffix(".json")
        if not p.exists():
            continue
        d = json.loads(p.read_text(encoding="utf-8"))
        s = scenario(d)
        if d.get("format") != 3 or not s:
            continue
        v = d.get("verdict") or {}
        target = v.get("target") or s[0] * (1 + v.get("upside", 0))   # 목표주가 도입 전 리포트는 업사이드에서 되짚는다
        unit = NUM.sub("", str(tile(d, "주가") or "")).strip()
        out[cid] = {"id": cid, "ticker": str(d.get("ticker")), "company": d.get("company"), "date": str(d.get("date")), "stem": p.stem, "grade": v.get("rating"), "target": target,
                    "target_text": v.get("target_text") or f"{unit}{target:,.0f}", "alpha": v.get("alpha"), "rr": v.get("rr"), "price": s[0], "bear": s[1], "bull": s[2], "dcf": s[3],
                    "swing": next((b for a, b in v.get("points") or [] if a == "가를 것"), None)}
    return out


def regrade(r, price, cfg):
    """현재가 기준 (등급, 업사이드, 손익비)"""
    up = r["target"] / price - 1
    rr = report_layout.reward_risk(price, r["bull"], r["bear"])
    if rr is None:
        return "Neutral", up, 0.0
    return report_layout.rating(up, rr, r["dcf"] / price - 1 if r.get("dcf") is not None else None, cfg), up, rr


def judge(r, price, alpha, c, cfg, today, killed=()):
    """(통과 행 또는 None, 탈락 이유)"""
    b = c["buy_call"]
    grade, up, rr = regrade(r, price, cfg)
    row = {**r, "grade_now": grade, "price_now": price, "upside": up, "rr_now": rr, "alpha": alpha}
    if r["ticker"] in killed:
        return None, "킬 조건 발동"
    if grade not in b["grades"]:
        return None, f"현재가 기준 {grade}(업사이드 {up:+.0%}, 손익비 {rr:.1f})"
    if alpha is None or alpha < b["alpha_min"]:
        return None, f"알파 {alpha if alpha is not None else '미산정'} < {b['alpha_min']}"
    if (today - date.fromisoformat(r["date"])).days > b["report_days"]:
        return None, f"리포트 {r['date']}, {b['report_days']}일 경과"
    return row, ""


def prices(path=IN):
    """{티커: 현재가} — Portfolio 데일리가 저장한 시세"""
    if not path.exists():
        return {}
    rows = json.loads(path.read_text(encoding="utf-8")).get("rows") or []
    return {str(x.get("ticker")).split(":")[-1]: (x.get("tv") or {}).get("close") for x in rows if (x.get("tv") or {}).get("close")}


def alpha_of(r, alphas):
    row = alphas.get(r["id"])
    return row["total"] if row and row.get("total") is not None else r["alpha"]


def run(today=None, killed=(), px=None, reps=None, alphas=None, prev=None):
    today = today or datetime.now(KST).date()
    c, cfg = composite.cfg(), report_layout.config()
    reps = reports() if reps is None else reps
    alphas = composite.alpha_rows() if alphas is None else alphas
    px = prices() if px is None else px
    prev = (json.loads(LATEST.read_text(encoding="utf-8")).get("calls") or {} if LATEST.exists() else {}) if prev is None else prev
    calls, why = {}, {}
    for cid, r in reps.items():
        price = px.get(r["ticker"]) or r["price"]
        row, reason = judge(r, price, alpha_of(r, alphas), c, cfg, today, killed)
        if row:
            row["stale"] = r["ticker"] not in px
            row["new"] = cid not in prev
            calls[cid] = row
        else:
            why[cid] = reason
    dropped = [{**prev[cid], "why": why.get(cid, "리포트 없음")} for cid in prev if cid not in calls]
    return {"as_of": today.isoformat(), "calls": calls, "dropped": dropped}


def line(x):
    tag = "🆕 " if x.get("new") else ""
    px = " · 시세 미갱신" if x.get("stale") else ""
    return (f"· {tag}{x['company']}({x['ticker']}) **{x['grade_now']}** · 목표주가 {x['target_text']} · 업사이드 {x['upside']:+.0%} · 손익비 {x['rr_now']:.1f} · 알파 {x['alpha']:.1f}{px}"
            + (f"\n  가를 것: {x['swing']}" if x.get("swing") else ""))


def text(out):
    """Portfolio 데일리 절. 없으면 빈 문자열"""
    rows = sorted(out["calls"].values(), key=lambda x: (not x.get("new"), -x["upside"]))
    if not rows and not out["dropped"]:
        return ""
    body = [line(x) for x in rows] + [f"· 해제 {x['company']}({x['ticker']}) — {x['why']}" for x in out["dropped"]]
    return "**■ Buy Call**\n" + "\n".join(body) + f"\n{FOOT}"


def record(out, path=LOG):
    new = not path.exists()
    with path.open("a", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=LOG_FIELDS)
        if new:
            w.writeheader()
        for x, event in [(x, "진입") for x in out["calls"].values() if x.get("new")] + [(x, "해제") for x in out["dropped"]]:
            w.writerow({"date": out["as_of"], "event": event, "ticker": x["ticker"], "id": x["id"], "grade": x.get("grade_now"), "price": x.get("price_now"), "target": x["target"],
                        "upside": round(x["upside"], 4), "rr": round(x["rr_now"], 2), "alpha": x["alpha"], "report": x["stem"], "why": x.get("why", "")})


def symbols(reps=None, path=SYMBOLS):
    """{'symbols': [...], 'missing': [...]} — 시세를 받을 종목"""
    reps = reports() if reps is None else reps
    with path.open(encoding="utf-8", newline="") as f:
        table = {r["entity_id"]: r["tv_symbol"] for r in csv.DictReader(f)}
    found = {r["id"]: table[r["id"]] for r in reps.values() if r["id"] in table}
    return {"symbols": sorted(found.values()), "missing": sorted(r["ticker"] for r in reps.values() if r["id"] not in found)}


def main(argv):
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbols", action="store_true")
    ap.add_argument("--dry", action="store_true", help="기록하지 않는다")
    ap.add_argument("--killed", nargs="*", default=[])
    a = ap.parse_args(argv)
    if a.symbols:
        print(json.dumps(symbols(), ensure_ascii=False))
        return 0
    out = run(killed=a.killed)
    print(text(out) or "[Buy Call] 해당 없음")
    if not a.dry:
        LATEST.write_text(json.dumps({"as_of": out["as_of"], "calls": out["calls"]}, ensure_ascii=False, indent=1), encoding="utf-8")
        record(out)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
