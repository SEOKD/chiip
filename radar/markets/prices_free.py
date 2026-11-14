"""무료 시세 수집 (마스터 결정 2026-10-28: EODHD 보류, 무료 조합 먼저)

대만: TWSE OpenAPI(STOCK_DAY_ALL, 상장) + TPEx OpenAPI(mainboard_daily_close_quotes, 장외) — 키 불필요, 2026-10-28 응답 확인.
한국: KRX OPEN API(KRX_API_KEY) / 미국: Finnhub(FINNHUB_API_KEY) — 키 입력 후 공식 문서로 접속 방식을 확인하고 붙인다(지금은 건너뜀).
대상: config/earnings_watch.yaml 감시 목록(valuation universe + extra)의 대만 코드(.TW·.TWO).
저장: knowledge/models/valuation/prices/<code>.csv (date,close,volume — git 제외), prices/latest_free.json
사용: py radar/markets/prices_free.py
      py radar/markets/prices_free.py --tv-symbols            # 동인 있는 종목의 TradingView 기호(50개씩)
      py radar/markets/prices_free.py --tv-put <응답.json> [--date YYYY-MM-DD]   # 일괄 종가 → prices/<종목 id>.csv(엔진이 더 새 가격을 쓴다)
"""
import csv
import json
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from pollers import common  # noqa: E402

TWSE = "https://openapi.twse.com.tw/v1/exchangeReport/STOCK_DAY_ALL"
TPEX = "https://www.tpex.org.tw/openapi/v1/tpex_mainboard_daily_close_quotes"
PRICES = common.ROOT / "knowledge" / "models" / "valuation" / "prices"
SOURCE_ID = "src-prices-free"


def tv_symbols():
    """동인이 있는 종목 → TradingView 기호(ADR-041 후속 — 77/96곳이 시세 파일 없이 데이터팩 스냅숏 가격을 썼다).
    우선순위: config/tradingview_symbols.csv entity_id → datapack companyKey('NYSE_LTH' → 'NYSE:LTH')"""
    out = {}
    ids = {p.parent.name for p in (common.ROOT / "knowledge" / "models" / "companies").glob("*/drivers.yaml")}
    tv = common.ROOT / "config" / "tradingview_symbols.csv"
    if tv.exists():
        with tv.open(encoding="utf-8", newline="") as fh:
            for r in csv.DictReader(fh):
                if r.get("entity_id") in ids and r.get("tv_symbol"):
                    out.setdefault(r["entity_id"], r["tv_symbol"])
    for p in sorted((common.ROOT / "knowledge" / "models" / "companies").glob("*/drivers.yaml")):
        eid = p.parent.name
        if eid in out:
            continue
        dp = p.parent / "datapack.json"
        try:
            d = json.loads(dp.read_text(encoding="utf-8")) if dp.exists() else {}
        except ValueError:
            d = {}
        key = ((d.get("raw") or {}).get("fiscal_profile") or {}).get("companyKey") or (d.get("quarters_hist") or {}).get("key")
        if key and "_" in key:
            out[eid] = key.replace("_", ":", 1)
    return out


def put_tv(path, day=None):
    """TradingView get_symbol_data_batch 응답(JSON: {"data": {기호: {"close": x}}} 또는 {기호: 종가}) → prices/<entity_id>.csv에 (날짜, 종가) 한 줄.
    run.resolve_market이 datapack 가격보다 새로우면 이 값을 쓴다. day = 종가 날짜(기본: 오늘 이전 마지막 평일)"""
    from datetime import timedelta
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    data = raw.get("data", raw)
    if day is None:
        d = date.today() - timedelta(days=1)
        while d.weekday() >= 5:
            d -= timedelta(days=1)
        day = d.isoformat()
    sym2e = {s: e for e, s in tv_symbols().items()}
    PRICES.mkdir(parents=True, exist_ok=True)
    n = 0
    for sym, v in data.items():
        close = _num(v.get("close") if isinstance(v, dict) else v)
        eid = sym2e.get(sym)
        if not eid or not close:
            continue
        f = PRICES / f"{eid}.csv"
        rows = []
        if f.exists():
            with f.open(encoding="utf-8", newline="") as fh:
                rows = list(csv.DictReader(fh))
        rows = [r for r in rows if r.get("date") != day] + [{"date": day, "close": close, "source": "TradingView"}]
        with f.open("w", encoding="utf-8", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=["date", "close", "source"], extrasaction="ignore")
            w.writeheader()
            w.writerows(sorted(rows, key=lambda r: r["date"]))
        n += 1
    return n, day


def roc_date(s):
    """민국 연도 '1151027' → 2026-10-27"""
    s = str(s).strip()
    return date(int(s[:-4]) + 1911, int(s[-4:-2]), int(s[-2:])).isoformat()


def _num(x):
    try:
        return float(str(x).replace(",", "").replace("+", ""))
    except (TypeError, ValueError):
        return None


def watch_codes():
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import earnings_calendar
    return {w["code"]: w for w in earnings_calendar.watch() if (w.get("code") or "").endswith((".TW", ".TWO"))}


def parse_twse(rows):
    return {f"{r['Code']}.TW": {"date": roc_date(r["Date"]), "close": _num(r.get("ClosingPrice")), "volume": _num(r.get("TradeVolume"))}
            for r in rows if r.get("Code")}


def parse_tpex(rows):
    return {f"{r['SecuritiesCompanyCode']}.TWO": {"date": roc_date(r["Date"]), "close": _num(r.get("Close")), "volume": _num(r.get("TradingShares"))}
            for r in rows if r.get("SecuritiesCompanyCode")}


def append(code, rec):
    PRICES.mkdir(parents=True, exist_ok=True)
    p = PRICES / f"{code}.csv"
    have = set()
    if p.exists():
        with p.open(encoding="utf-8", newline="") as f:
            have = {r["date"] for r in csv.DictReader(f)}
    if rec["date"] in have or rec["close"] is None:
        return False
    new = not p.exists()
    with p.open("a", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["date", "close", "volume", "source"])
        if new:
            w.writeheader()
        w.writerow({**rec, "source": "TWSE/TPEx OpenAPI"})
    return True


def run():
    codes = watch_codes()
    quotes, errors = {}, []
    for url, parser in ((TWSE, parse_twse), (TPEX, parse_tpex)):
        try:
            quotes.update(parser(json.loads(common.http_get(url, timeout=60))))
        except Exception as exc:
            errors.append(f"{url.split('/')[2]}: {type(exc).__name__}")
    got = {c: quotes[c] for c in codes if c in quotes}
    added = sum(append(c, r) for c, r in got.items())
    env = common.load_env()
    pending = [k for k in ("KRX_API_KEY", "FINNHUB_API_KEY") if not env.get(k)]
    PRICES.mkdir(parents=True, exist_ok=True)
    (PRICES / "latest_free.json").write_text(json.dumps({"updated": common.iso(common.now_kst()), "quotes": got,
                                                         "missing": sorted(set(codes) - set(got)), "keys_pending": pending},
                                                        ensure_ascii=False, indent=1), encoding="utf-8")
    common.record_health(SOURCE_ID, bool(got), "; ".join(errors) or None)
    return len(got), added, errors


def main(argv):
    sys.stdout.reconfigure(encoding="utf-8")
    if "--tv-symbols" in argv:   # TradingView get_symbol_data_batch(columns ["close"])로 받을 기호(50개씩)
        syms = sorted(set(tv_symbols().values()))
        for i in range(0, len(syms), 50):
            print(json.dumps(syms[i:i + 50]))
        return 0
    if "--tv-put" in argv:
        i = argv.index("--tv-put")
        day = argv[argv.index("--date") + 1] if "--date" in argv else None
        n, day = put_tv(argv[i + 1], day)
        print(f"[무료 시세] TradingView 종가 {n}종목 → prices/<종목 id>.csv ({day})")
        return 0
    n, added, errors = run()
    print(f"[무료 시세] 대만 감시 종목 {n}개(신규 행 {added})" + (f", 실패: {'; '.join(errors)}" if errors else ""))
    data = json.loads((PRICES / "latest_free.json").read_text(encoding="utf-8"))
    for c, r in data["quotes"].items():
        print(f"- {c}: {r['close']} ({r['date']})")
    if data["missing"]:
        print("없음:", ", ".join(data["missing"]))
    if data["keys_pending"]:
        print("키 대기:", ", ".join(data["keys_pending"]))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
