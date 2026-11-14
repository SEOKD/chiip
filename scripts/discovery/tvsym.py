"""종목 → TradingView 기호(EXCHANGE:TICKER) — 발굴 채널 단서의 성적표 시세용 (2026-11-15, scripts/discovery/leads.py)

미국: SEC company_tickers_exchange.json(티커·거래소, 주 1회 캐시 radar/state/sec_ticker_exchange.json) → Nasdaq→NASDAQ, NYSE→NYSE, CBOE→CBOE, OTC→OTC.
  SEC 표는 NYSE American을 NYSE로 묶는다 — TradingView가 'missing'으로 돌려주면 leads가 AMEX로 바꿔 다시 묻는다(alt()).
  종류주 'BRK-B'는 TradingView 'BRK.B'.
한국 KRX:<6자리>(코스피·코스닥 같은 접두) · 일본 TSE:<4자리> · 대만 TWSE:/TPEX:<코드> · 홍콩 HKEX:<앞 0 뺀 코드> · 영국 LSE:<티커>.
"""
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "radar"))
from pollers import common  # noqa: E402

SEC_MAP = "https://www.sec.gov/files/company_tickers_exchange.json"
CACHE = ROOT / "radar" / "state" / "sec_ticker_exchange.json"
PREFIX = {"Nasdaq": "NASDAQ", "NYSE": "NYSE", "CBOE": "CBOE", "OTC": "OTC", "TXSE": "TXSE"}
CACHE_DAYS = 7


def _ua():
    try:
        from pollers import sec_filings
        return sec_filings._ua()
    except Exception:  # noqa: BLE001
        return common.UA


def sec_table(force=False):
    """{티커: [cik, 이름, 거래소]} — 캐시가 7일 안이면 그대로"""
    if not force and CACHE.exists() and time.time() - CACHE.stat().st_mtime < CACHE_DAYS * 86400:
        return json.loads(CACHE.read_text(encoding="utf-8"))
    try:
        d = json.loads(common.http_get(SEC_MAP, headers={"User-Agent": _ua()}, timeout=60))
    except Exception:  # noqa: BLE001 — 못 받으면 옛 캐시라도 쓴다
        return json.loads(CACHE.read_text(encoding="utf-8")) if CACHE.exists() else {}
    out = {str(r[2]).upper(): [r[0], r[1], r[3]] for r in d.get("data") or [] if r[2]}
    CACHE.parent.mkdir(parents=True, exist_ok=True)
    CACHE.write_text(json.dumps(out, ensure_ascii=False), encoding="utf-8")
    return out


def us(ticker, table=None):
    t = str(ticker or "").upper().strip()
    if not t:
        return ""
    tab = table if table is not None else sec_table()
    ex = (tab.get(t) or tab.get(t.replace("/", "-").replace(".", "-")) or [None, None, None])[2]   # OpenFIGI 'BRK/B' ↔ SEC 'BRK-B'
    return f"{PREFIX.get(ex, 'NYSE' if ex else 'NASDAQ')}:{t.replace('-', '.').replace('/', '.')}" if ex or t else ""


def us_exchange(ticker, table=None):
    tab = table if table is not None else sec_table()
    return (tab.get(str(ticker or "").upper()) or [None, None, None])[2]


def cik_of(ticker, table=None):
    tab = table if table is not None else sec_table()
    v = tab.get(str(ticker or "").upper())
    return str(v[0]) if v else ""


def of(market, code, exchange=None):
    """시장 코드(us·jp·kr·tw·hk·uk·eu) + 종목 코드 → TradingView 기호. 유럽은 거래소 접두가 있어야 한다(exchange)"""
    c = str(code or "").strip()
    if not c:
        return ""
    if ":" in c:
        return c
    if market == "us":
        return us(c)
    if market == "kr":
        return f"KRX:{c.zfill(6) if c.isdigit() else c}"
    if market == "jp":
        return f"TSE:{c}"
    if market == "tw":
        return f"{(exchange or 'TWSE').upper()}:{c}"
    if market == "hk":
        return f"HKEX:{c.lstrip('0') or c}"
    if market == "uk":
        return f"LSE:{c}"
    if market == "eu" and exchange:
        return f"{exchange.upper()}:{c}"
    return ""


def alt(sym):
    """TradingView가 못 찾은 기호의 다음 후보 — NYSE American·NYSE Arca가 SEC 표에서 NYSE로 묶인 경우"""
    ex, _, t = str(sym).partition(":")
    return {"NYSE": f"AMEX:{t}", "AMEX": f"NYSEARCA:{t}"}.get(ex, "")
