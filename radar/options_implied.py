"""실적 발표 옵션 내재 변동폭 — ATM 스트래들 ÷ 주가 (마스터 지시 2026-11-14 "옵션 내재 변동폭도 만들어라", ADR-033)

결정론(모델 없음). 실적일 직후 만기의 ATM(주가에 가장 가까운 행사가) 콜·풋 중간가 합 = 스트래들, ÷ 주가 = 시장이 가격에 넣은 실적일 변동폭.
원천: Cboe 지연 시세 JSON(cdn-api.cboe.com/api/global/delayed_quotes/options/<티커>.json — 일반 요청으로 열리고 IV·호가가 있다).
      자동 수집은 약관 판단이 애매해 마스터에게 물었고 2026-11-14 승인("켜라") — config/ops_view.yaml options.enabled.
      프로젝트 User-Agent 그대로(꾸미지 않는다), 종목 사이 1초. 꺼도 --put으로 손으로 넣은 값은 쓴다.
저장: datapack "options_implied" = {"as_of", "spot", "expiry", "strike", "straddle", "iv", "source"} → scripts/tenbagger/ops_view.py implied_blocks
사용: py radar/options_implied.py --auto <id> [티커]      # 실적일(upcoming.json → datapack next_event)이 30일 안이면 받아 넣는다(gather 원천)
      py radar/options_implied.py --run                     # run_hourly: 실적일 14일 안 감시 종목 전부
      py radar/options_implied.py <id> <티커> <실적일 YYYY-MM-DD> [--session after|before]   # enabled일 때만 받는다
      py radar/options_implied.py --parse <cboe json 파일> <실적일> [--session after]          # 시험·수동
      py radar/options_implied.py --put <id> <json>                                            # 손으로 넣기
"""
import json
import re
import sys
from datetime import date, timedelta
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
from pollers import common  # noqa: E402

URL = "https://cdn-api.cboe.com/api/global/delayed_quotes/options/{t}.json"
SYM = re.compile(r"^([A-Z0-9]+?)(\d{6})([CP])(\d{8})$")


def cfg():
    return (yaml.safe_load((common.ROOT / "config" / "ops_view.yaml").read_text(encoding="utf-8")) or {}).get("options") or {}


def _mid(o):
    b, a = o.get("bid") or 0, o.get("ask") or 0
    return (a + b) / 2 if a and b else (o.get("last_trade_price") or None)


def parse(doc, earnings, session="after"):
    """Cboe 응답 → {expiry, strike, straddle, iv, spot}. 실적일 반응이 들어가는 첫 만기(장후 발표면 다음 날 이후)"""
    data = doc.get("data") or {}
    spot = data.get("current_price") or data.get("close")
    if not spot:
        return None
    e = date.fromisoformat(earnings) + timedelta(days=1 if session == "after" else 0)
    chain = {}
    for o in data.get("options") or []:
        m = SYM.match(str(o.get("option", "")))
        if not m:
            continue
        exp = date(2000 + int(m[2][:2]), int(m[2][2:4]), int(m[2][4:]))
        chain.setdefault(exp, {}).setdefault(int(m[4]) / 1000, {})[m[3]] = o
    exps = sorted(x for x in chain if x >= e)
    if not exps:
        return None
    exp = exps[0]
    strikes = [k for k, v in chain[exp].items() if "C" in v and "P" in v]
    if not strikes:
        return None
    k = min(strikes, key=lambda s: abs(s - spot))
    c, p = chain[exp][k]["C"], chain[exp][k]["P"]
    if _mid(c) is None or _mid(p) is None:
        return None
    ivs = [x.get("iv") for x in (c, p) if x.get("iv")]
    return {"spot": spot, "expiry": exp.isoformat(), "strike": k, "straddle": round(_mid(c) + _mid(p), 4),
            "iv": sum(ivs) / len(ivs) if ivs else None, "as_of": str(doc.get("timestamp", ""))[:16]}


def put(cid, rec):
    p = common.ROOT / "knowledge" / "models" / "companies" / cid / "datapack.json"
    dp = json.loads(p.read_text(encoding="utf-8"))
    dp["options_implied"] = rec
    p.write_text(json.dumps(dp, ensure_ascii=False, indent=1), encoding="utf-8")


def fetch(ticker):
    return json.loads(common.http_get(URL.format(t=ticker.upper()), timeout=30).decode("utf-8"))


def next_earnings(cid, today=None):
    """(날짜, session) — upcoming.json(Fiscal.ai 실적 일정)이 먼저, 없으면 datapack next_event"""
    today = today or date.today()
    try:
        ev = json.loads((common.ROOT / "knowledge" / "models" / "earnings" / "upcoming.json").read_text(encoding="utf-8")).get("events") or []
    except (OSError, ValueError):
        ev = []
    for e in ev:
        if e.get("id") == cid and e.get("date") and e["date"] >= today.isoformat():
            loc = str(e.get("local") or "")
            return e["date"], ("before" if "장전" in loc or "before" in loc.lower() else "after")
    try:
        ne = json.loads((common.ROOT / "knowledge" / "models" / "companies" / cid / "datapack.json").read_text(encoding="utf-8")).get("next_event") or {}
    except (OSError, ValueError):
        ne = {}
    if ne.get("date") and ne["date"] >= today.isoformat() and "미확정" not in str(ne.get("tag", "")):
        return ne["date"], "after"
    return None, None


def ticker_of(cid):
    try:
        t = json.loads((common.ROOT / "knowledge" / "models" / "companies" / cid / "datapack.json").read_text(encoding="utf-8")).get("ticker")
    except (OSError, ValueError):
        t = None
    if not t:
        import csv
        with (common.ROOT / "config" / "tradingview_symbols.csv").open(encoding="utf-8", newline="") as f:
            t = next((r["ticker"] for r in csv.DictReader(f) if r.get("entity_id") == cid and r.get("exchange") in ("NASDAQ", "NYSE", "AMEX")), None)
    return str(t or "").upper()


def auto(cid, ticker=None, today=None):
    """실적일이 window_days 안이면 받아서 datapack에 넣는다 — 상태 한 줄"""
    c = cfg()
    if not c.get("enabled"):
        return "해당 없음(옵션 수집 꺼짐)"
    today = today or date.today()
    d, sess = next_earnings(cid, today)
    if not d:
        return "해당 없음(확정 실적일 없음)"
    if (date.fromisoformat(d) - today).days > c.get("window_days", 30):
        return f"해당 없음(실적일 {d} — {c.get('window_days', 30)}일 밖)"
    t = ticker or ticker_of(cid)
    if not t.isalpha():
        return "해당 없음(미국 상장 옵션 아님)"
    rec = parse(fetch(t), d, sess)
    if not rec:
        return f"해당 없음({t} 실적일 뒤 만기·ATM 짝 없음)"
    p = common.ROOT / "knowledge" / "models" / "companies" / cid / "datapack.json"
    if p.exists():
        put(cid, {**rec, "earnings": d, "session": sess, "source": "Cboe 지연 시세(15분)"})
    st = common.load_state("options_implied", {})
    st[cid] = {**rec, "ticker": t, "earnings": d, "session": sess}
    common.save_state("options_implied", st)
    return f"ok {t} {d} 만기 {rec['expiry']} 스트래들 ±{rec['straddle'] / rec['spot'] * 100:.1f}%"


def run(now=None):
    """run_hourly — 실적일이 due_days 안인 감시 종목(upcoming.json)만, 종목 사이 1초"""
    import time
    c = cfg()
    if not c.get("enabled"):
        return "꺼짐", []
    today = (now or common.now_kst()).date()
    try:
        ev = json.loads((common.ROOT / "knowledge" / "models" / "earnings" / "upcoming.json").read_text(encoding="utf-8")).get("events") or []
    except (OSError, ValueError):
        ev = []
    ids = sorted({e["id"] for e in ev if e.get("id") and e.get("date") and 0 <= (date.fromisoformat(e["date"]) - today).days <= c.get("due_days", 14)})
    out, ok = [], 0
    for cid in ids:
        try:
            r = auto(cid, today=today)
        except Exception as exc:   # 한 종목 실패가 나머지를 막지 않는다
            r = f"실패: {type(exc).__name__}: {str(exc)[:60]}"
        ok += r.startswith("ok")
        out.append(f"{cid} {r}")
        time.sleep(1)
    common.record_health("options-implied", True, None)
    return f"{ok}/{len(ids)}종목", []


def main(argv):
    sys.stdout.reconfigure(encoding="utf-8")
    if len(argv) >= 2 and argv[0] == "--auto":
        print(auto(argv[1], argv[2] if len(argv) > 2 else None))
        return 0
    if argv and argv[0] == "--run":
        print(run())
        return 0
    sess = argv[argv.index("--session") + 1] if "--session" in argv else "after"
    if len(argv) >= 3 and argv[0] == "--parse":
        print(json.dumps(parse(json.loads(Path(argv[1]).read_text(encoding="utf-8")), argv[2], sess), ensure_ascii=False))
        return 0
    if len(argv) >= 3 and argv[0] == "--put":
        put(argv[1], json.loads(Path(argv[2]).read_text(encoding="utf-8")))
        print(f"[옵션 내재] {argv[1]} 저장")
        return 0
    if len(argv) >= 3:
        if not cfg().get("enabled"):
            print("옵션 수집 꺼짐(config/ops_view.yaml options.enabled: false — 원천 사용 마스터 승인 대기). --put으로 손으로 넣을 수 있다.")
            return 0
        rec = parse(fetch(argv[1 if len(argv) > 1 else 0]), argv[2], sess)
        if not rec:
            print("만기·ATM 짝 없음 — 값 없음")
            return 1
        put(argv[0], {**rec, "source": "Cboe 지연 시세(15분)"})
        print(json.dumps(rec, ensure_ascii=False))
        return 0
    print(__doc__)
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
