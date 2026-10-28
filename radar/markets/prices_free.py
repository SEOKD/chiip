"""무료 시세 수집 (마스터 결정 2026-10-28: EODHD 보류, 무료 조합 먼저)

대만: TWSE OpenAPI(STOCK_DAY_ALL, 상장) + TPEx OpenAPI(mainboard_daily_close_quotes, 장외) — 키 불필요, 2026-10-28 응답 확인.
한국: KRX OPEN API(KRX_API_KEY) / 미국: Finnhub(FINNHUB_API_KEY) — 키 입력 후 공식 문서로 접속 방식을 확인하고 붙인다(지금은 건너뜀).
대상: config/earnings_watch.yaml 감시 목록(valuation universe + extra)의 대만 코드(.TW·.TWO).
저장: knowledge/models/valuation/prices/<code>.csv (date,close,volume — git 제외), prices/latest_free.json
사용: py radar/markets/prices_free.py
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
