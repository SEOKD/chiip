"""시세·일봉 대체 라우터 — TradingView·Fiscal.ai 커넥터가 막힐 때 스크립트가 직접 부르는 키 API
(마스터 지시 2026-11-22 "Tingo, Twelvedata, Apify 모두 API Key를 넣어뒀다. TradingView, Fiscal.ai 등 커넥터가 막힐 경우 다른 대안으로 이를 쓰도록 하는 시스템을 설계하라")

순서(설정 config/data_sources.yaml 'market_data'):
  시세  quote   Tiingo IEX(여러 티커 1회, 미국) → Twelve Data /quote(8개씩·분당 8크레딧, 평균 거래량 포함) → EODHD real-time(무료 20회/일, 해외 종목 최후)
  일봉  history Tiingo daily(티커당 1회) → Twelve Data time_series → EODHD eod
  원천마다 하루 상한(state market_data)을 지키고, 실패·한도 응답이면 그날 그 원천을 건너뛴다. 빈 종목만 다음 원천이 채운다.
웹 시세 사이트(Yahoo·Finviz·Investing.com·MarketScreener·Stooq·Nasdaq·Cboe)는 robots·약관이 자동 수집을 막아 쓰지 않는다(2026-11-22 점검).
커넥터 상태: --status가 TradingView(훅 예산·막힘 시각), Fiscal.ai·Easyconomics(radar/state/channel_down.json)를 읽어 지금 쓸 길을 알려 준다.
  훅 .claude/hooks/tv_budget.py(거부 문구)·connector_watch.py(Fiscal.ai·Easyconomics 오류 뒤 안내)가 모델을 이 스크립트로 보낸다.
키: D:\\local-only\\secrets\\.env TIINGO_API_KEY·TWELVEDATA_API_KEY·EODHD_API_KEY(값은 출력하지 않는다). 개인·내부 사용 — 시세를 재배포하지 않는다.
사용: py radar/market_data.py --status
      py radar/market_data.py quote SPY NVDA LSE:RR.        → JSON {심볼: {price, change_pct, volume, avg_volume, at, src}}
      py radar/market_data.py history NVDA [일수=60]          → JSON [{date, open, high, low, close, volume}]
"""
import json
import re
import sys
import time
import urllib.error
import urllib.parse
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from pollers import common  # noqa: E402

STATE = "market_data"
DEFAULT = {"quote": ["tiingo", "twelvedata", "eodhd"], "history": ["tiingo", "twelvedata", "eodhd"],
           "daily_cap": {"tiingo": 900, "twelvedata": 700, "eodhd": 15}}
KEYS = {"tiingo": "TIINGO_API_KEY", "twelvedata": "TWELVEDATA_API_KEY", "eodhd": "EODHD_API_KEY"}
US_EX = {"NASDAQ", "NYSE", "AMEX", "ARCA", "BATS", "NYSEARCA", "US", ""}
EOD_EX = {"LSE": "LSE", "XETR": "XETRA", "TSE": "TSE", "KRX": "KO", "KOSDAQ": "KQ", "TWSE": "TW", "HKEX": "HK", "EURONEXT": "PA", "SIX": "SW"}


def cfg():
    c = (common.load_yaml("config/data_sources.yaml") or {}).get("market_data") or {}
    return {**DEFAULT, **c, "daily_cap": {**DEFAULT["daily_cap"], **(c.get("daily_cap") or {})}}


def split(sym):
    """'NASDAQ:NVDA' → ('NASDAQ', 'NVDA'), 'NVDA' → ('', 'NVDA'), 'RR.LSE' → ('LSE', 'RR')"""
    s = sym.strip()
    if ":" in s:
        ex, t = s.split(":", 1)
        return ex.upper(), t
    m = re.match(r"^(.+?)\.(LSE|XETRA|TSE|KO|KQ|TW|HK|PA|SW)$", s)
    return (m.group(2), m.group(1)) if m else ("", s)


def is_us(sym):
    return split(sym)[0] in US_EX


def _day():
    return common.now_kst().date().isoformat()


def _st():
    st = common.load_state(STATE, {})
    if st.get("day") != _day():
        st = {"day": _day(), "used": {}, "off": st.get("off") or {}}
    return st


def _ok(src, st, c, n=1):
    off = (st.get("off") or {}).get(src)
    if off and off >= _day():
        return False
    return st["used"].get(src, 0) + n <= int(c["daily_cap"].get(src, 10 ** 6))


def _spend(src, st, n=1):
    st["used"][src] = st["used"].get(src, 0) + n
    common.save_state(STATE, st)


def _off(src, st, why):
    st.setdefault("off", {})[src] = _day()
    st.setdefault("why", {})[src] = why[:120]
    common.save_state(STATE, st)


def _get(url):
    return json.loads(common.http_get(url, timeout=30).decode("utf-8"))


# ---------- 원천별 ----------
def tiingo_quote(key, syms, get=_get):
    us = [s for s in syms if is_us(s)]
    if not us:
        return {}, 0
    tick = {split(s)[1].lower().replace(".", "-"): s for s in us}
    out = {}
    for r in get(f"https://api.tiingo.com/iex/?tickers={','.join(tick)}&token={key}") or []:
        s = tick.get(str(r.get("ticker") or "").lower())
        last = r.get("last") or r.get("tngoLast")
        prev = r.get("prevClose")
        if s and last:
            out[s] = {"price": last, "change_pct": round((last / prev - 1) * 100, 3) if prev else None, "volume": None, "avg_volume": None,
                      "at": r.get("timestamp"), "src": "Tiingo IEX(거래량은 IEX 몫뿐이라 뺌)"}
    return out, 1


def twelvedata_quote(key, syms, get=_get, pause=61):
    us = [s for s in syms if is_us(s)]
    tick = {split(s)[1].upper(): s for s in us}
    names, out, calls = list(tick), {}, 0
    for i in range(0, len(names), 8):
        if i:
            time.sleep(pause)
        d = get(f"https://api.twelvedata.com/quote?symbol={','.join(names[i:i + 8])}&apikey={key}")
        calls += len(names[i:i + 8])
        if d.get("status") == "error":
            raise RuntimeError(str(d.get("message"))[:100])
        d = {names[i]: d} if "symbol" in d else d
        for k, r in d.items():
            s = tick.get(str(k).upper())
            if not s or not isinstance(r, dict) or r.get("close") in (None, ""):
                continue
            out[s] = {"price": float(r["close"]), "change_pct": float(r["percent_change"]) if r.get("percent_change") not in (None, "") else None,
                      "volume": float(r.get("volume") or 0) or None, "avg_volume": float(r.get("average_volume") or 0) or None,
                      "at": datetime.fromtimestamp(int(r["last_quote_at"] or r["timestamp"]), timezone.utc).isoformat() if r.get("timestamp") else None,
                      "src": "Twelve Data"}
    return out, calls


def _eod_code(sym):
    ex, t = split(sym)
    return f"{t.rstrip('.')}.{EOD_EX.get(ex, 'US') if ex not in US_EX else 'US'}"


def eodhd_quote(key, syms, get=_get):
    if not syms:
        return {}, 0
    codes = {_eod_code(s): s for s in syms}
    first, rest = list(codes)[0], list(codes)[1:]
    d = get(f"https://eodhd.com/api/real-time/{first}?fmt=json&api_token={key}" + (f"&s={','.join(rest)}" if rest else ""))
    rows = d if isinstance(d, list) else [d]
    out = {}
    for r in rows:
        s = codes.get(str(r.get("code") or ""))
        if s and r.get("close") not in (None, "NA"):
            out[s] = {"price": r["close"], "change_pct": r.get("change_p"), "volume": r.get("volume"), "avg_volume": None,
                      "at": datetime.fromtimestamp(int(r["timestamp"]), timezone.utc).isoformat() if str(r.get("timestamp") or "").isdigit() else None,
                      "src": "EODHD(지연 시세)"}
    return out, 1


QUOTE = {"tiingo": tiingo_quote, "twelvedata": twelvedata_quote, "eodhd": eodhd_quote}


def tiingo_history(key, sym, start, get=_get):
    if not is_us(sym):
        return None
    t = split(sym)[1].lower().replace(".", "-")
    rows = get(f"https://api.tiingo.com/tiingo/daily/{t}/prices?startDate={start}&token={key}")
    return [{"date": r["date"][:10], "open": r.get("adjOpen"), "high": r.get("adjHigh"), "low": r.get("adjLow"), "close": r.get("adjClose"),
             "volume": r.get("volume")} for r in rows or []]


def twelvedata_history(key, sym, start, get=_get):
    if not is_us(sym):
        return None
    d = get(f"https://api.twelvedata.com/time_series?symbol={split(sym)[1]}&interval=1day&start_date={start}&apikey={key}")
    if d.get("status") == "error":
        raise RuntimeError(str(d.get("message"))[:100])
    return sorted(({"date": v["datetime"][:10], "open": float(v["open"]), "high": float(v["high"]), "low": float(v["low"]), "close": float(v["close"]),
                    "volume": float(v.get("volume") or 0)} for v in d.get("values") or []), key=lambda r: r["date"])


def eodhd_history(key, sym, start, get=_get):
    rows = get(f"https://eodhd.com/api/eod/{_eod_code(sym)}?from={start}&fmt=json&api_token={key}")
    return [{"date": r["date"], "open": r.get("open"), "high": r.get("high"), "low": r.get("low"), "close": r.get("adjusted_close") or r.get("close"),
             "volume": r.get("volume")} for r in rows or []]


HISTORY = {"tiingo": tiingo_history, "twelvedata": twelvedata_history, "eodhd": eodhd_history}


# ---------- 라우터 ----------
def quote(syms, env=None, fns=None):
    """→ ({심볼: 값}, {원천: 사유}) — 원천 순서대로, 빈 심볼만 다음 원천이 채운다"""
    c, st = cfg(), _st()
    env = env if env is not None else common.load_env()
    fns = fns or QUOTE
    out, why = {}, {}
    for src in c["quote"]:
        left = [s for s in syms if s not in out]
        if not left:
            break
        if not env.get(KEYS[src]):
            why[src] = "키 없음"
            continue
        if not _ok(src, st, c, 1):
            why[src] = "오늘 상한·막힘"
            continue
        try:
            got, calls = fns[src](env[KEYS[src]], left)
            _spend(src, st, calls)
            out.update(got)
        except urllib.error.HTTPError as e:
            if e.code in (401, 402, 403, 429):
                _off(src, st, f"HTTP {e.code}")
            why[src] = f"HTTP {e.code}"
        except Exception as e:   # 원천 하나가 실패해도 다음 원천으로
            why[src] = f"{type(e).__name__}: {str(e)[:60]}"
    return out, why


def history(sym, days=60, env=None, fns=None):
    c, st = cfg(), _st()
    env = env if env is not None else common.load_env()
    fns = fns or HISTORY
    start = (common.now_kst().date() - timedelta(days=int(days * 1.5) + 5)).isoformat()
    why = {}
    for src in c["history"]:
        if not env.get(KEYS[src]):
            why[src] = "키 없음"
            continue
        if not _ok(src, st, c, 1):
            why[src] = "오늘 상한·막힘"
            continue
        try:
            rows = fns[src](env[KEYS[src]], sym, start)
            if rows is None:
                why[src] = "이 시장 미지원"
                continue
            _spend(src, st, 1)
            if rows:
                return rows[-days:], src, why
            why[src] = "빈 응답"
        except urllib.error.HTTPError as e:
            if e.code in (401, 402, 403, 429):
                _off(src, st, f"HTTP {e.code}")
            why[src] = f"HTTP {e.code}"
        except Exception as e:
            why[src] = f"{type(e).__name__}: {str(e)[:60]}"
    return [], None, why


def connectors(now=None):
    """커넥터 상태 — TradingView(훅 예산 상태), Fiscal.ai·Easyconomics(channel_down), 키 API 사용량"""
    now = now or common.now_kst()
    out = {}
    tv = common.load_state("tv_budget", {})
    try:
        tvc = common.load_yaml("config/tv_budget.yaml") or {}
    except Exception:
        tvc = {}
    bu = tv.get("blocked_until")
    blocked = bool(bu and datetime.fromisoformat(bu) > now)
    out["tradingview"] = {"ok": not blocked and tv.get("used", 0) < int(tvc.get("daily_budget", 25)),
                          "note": f"막힘 {bu[5:16]}까지" if blocked else f"오늘 {tv.get('used', 0)}/{tvc.get('daily_budget', '?')}건"}
    down = common.load_state("channel_down", {})
    for ch in ("fiscal", "easyconomics"):
        until = down.get(ch)
        bad = bool(until and datetime.fromisoformat(until) > now)
        out[ch] = {"ok": not bad, "note": f"막힘 {until[5:16]}까지" if bad else "정상(기록상)"}
    st, c, env = _st(), cfg(), common.load_env()
    for src in KEYS:
        out[src] = {"ok": bool(env.get(KEYS[src])) and _ok(src, st, c), "note": f"오늘 {st['used'].get(src, 0)}/{c['daily_cap'].get(src)}" +
                    ("" if env.get(KEYS[src]) else " · 키 없음") + (f" · 막힘({(st.get('why') or {}).get(src)})" if (st.get('off') or {}).get(src) == _day() else "")}
    return out


FALLBACK = {   # 막힌 커넥터 → 대신 쓸 길(모델 안내문). config/data_sources.yaml connector_fallback와 같은 내용
    "tradingview": "시세·등락·거래량 = py radar/market_data.py quote <심볼…> · 일봉 = py radar/market_data.py history <심볼> [일수] · "
                   "ETF 시세 = Easyconomics etf_list · 스크리너 = Easyconomics screener_scan · 일본 컨센서스는 대체 없음('한도로 못 함')",
    "fiscal": "재무·추정 = Easyconomics company_financial_statements·company_profile·earnings_summary(2순위, scripts/fiscal/source_router.py next) · "
              "주가·일봉 = py radar/market_data.py history <심볼> · 어닝콜 = Easyconomics earnings_call_transcript·py radar/alphavantage.py --transcript",
    "easyconomics": "주가·일봉 = py radar/market_data.py · 재무 = Fiscal.ai(1순위) · 추정 = Zacks(Fiscal.ai company_analyst_estimates)",
}


def main(argv):
    sys.stdout.reconfigure(encoding="utf-8")
    if not argv or argv[0] == "--status":
        st = connectors()
        for k, v in st.items():
            print(f"{'정상' if v['ok'] else '막힘'}  {k:13} {v['note']}")
        for k in ("tradingview", "fiscal", "easyconomics"):
            if not st[k]["ok"]:
                print(f"→ {k} 대신: {FALLBACK[k]}")
        return 0
    if argv[0] == "quote":
        q, why = quote(argv[1:])
        print(json.dumps({"quotes": q, "missing": [s for s in argv[1:] if s not in q], "why": why}, ensure_ascii=False, indent=1))
        return 0 if q else 2
    if argv[0] == "history":
        rows, src, why = history(argv[1], int(argv[2]) if len(argv) > 2 else 60)
        print(json.dumps({"symbol": argv[1], "src": src, "rows": rows, "why": why}, ensure_ascii=False))
        return 0 if rows else 2
    raise SystemExit(__doc__)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
