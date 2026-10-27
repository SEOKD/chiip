"""글로벌 증시 주간 상승률 수집 — EODHD 스크리너 API (위클리 리뷰 · Dean's Ticker 형식)

지역(US·US 중소형·Europe·Japan·Korea)별로 5거래일 상승률 상위 종목을 받아 시총·거래량·종목 유형으로 거른 뒤
knowledge/models/weekly_movers/YYYY-Www.csv 에 저장한다. 모델을 부르지 않는다.
한글 회사명·업종 표기는 위클리 리뷰(모델)가 붙인다.

사용: py radar/markets/weekly_movers.py            (토요일 06:00~09:00 KST에만 실행, 주 1회 — run_hourly가 30분마다 호출)
      py radar/markets/weekly_movers.py --force    (시간·중복 무시하고 지금 실행)
      py radar/markets/weekly_movers.py --exchanges   (EODHD 지원 거래소 목록에서 일본·한국·유럽 코드 확인)
"""
import csv
import json
import re
import sys
import urllib.parse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from pollers import common  # noqa: E402

CONFIG = "config/weekly_movers.yaml"
OUT_DIR = common.ROOT / "knowledge" / "models" / "weekly_movers"
API = "https://eodhd.com/api"
COLS = ["region", "rank", "pct_change", "name_en", "ticker", "exchange", "currency", "market_cap_usd",
        "sector", "industry", "last_day", "as_of"]


def _key():
    key = common.load_env().get("EODHD_API_KEY")
    if not key:
        raise RuntimeError("EODHD_API_KEY 없음 (D:\\local-only\\secrets\\.env)")
    return key


def _get(path, key, **params):
    params["api_token"] = key
    params.setdefault("fmt", "json")
    raw = common.http_get(f"{API}/{path}?{urllib.parse.urlencode(params)}", timeout=60)
    return json.loads(raw)


def fx_rates(key, cfg):
    """통화 → 1 USD당 단위. EODHD 환율 실패 시 설정값"""
    rates = dict(cfg.get("fx_fallback_per_usd", {}))
    for cur in [c for c in rates if c not in ("USD", "GBX")]:
        try:
            d = _get(f"real-time/USD{cur}.FOREX", key)
            if float(d.get("close") or 0) > 0:
                rates[cur] = float(d["close"])
        except Exception:  # 환율 하나 실패는 설정값으로
            pass
    if "GBP" in rates:
        rates["GBX"] = rates["GBP"] * 100  # 런던 시세는 펜스(GBX) 단위가 섞임
    return rates


def screen(key, exchange, limit):
    filters = json.dumps([["exchange", "=", exchange]])
    d = _get("screener", key, filters=filters, sort="refund_5d_p.desc", limit=limit)
    return d.get("data", d) if isinstance(d, dict) else d


def to_usd(value, currency, rates):
    try:
        return float(value) / rates[currency]
    except (KeyError, TypeError, ValueError, ZeroDivisionError):
        return None


def pick(rows, region, cfg, rates):
    excl = re.compile(cfg.get("exclude_name_pattern", r"$^"), re.I)
    lo, hi = region.get("market_cap_usd_min", 0), region.get("market_cap_usd_max")
    seen, out = set(), []
    for r in sorted(rows, key=lambda r: float(r.get("refund_5d_p") or -1e9), reverse=True):
        name = (r.get("name") or "").strip()
        if not name or excl.search(name) or not (r.get("sector") or r.get("industry")):
            continue  # 업종 없는 행은 대부분 ETF·펀드
        if float(r.get("avgvol_200d") or 0) < cfg.get("min_avg_volume_200d", 0):
            continue
        cap = to_usd(r.get("market_capitalization"), r.get("currency_symbol") or r.get("currency"), rates)
        if cap is None or cap < lo or (hi and cap >= hi):
            continue
        norm = re.sub(r"\W+", "", name.lower())[:30]
        if norm in seen:  # 여러 거래소 중복 상장
            continue
        seen.add(norm)
        out.append({"pct_change": round(float(r["refund_5d_p"]), 1), "name_en": name, "ticker": r.get("code"),
                    "exchange": r.get("exchange"), "currency": r.get("currency_symbol") or r.get("currency"),
                    "market_cap_usd": round(cap), "sector": r.get("sector") or "", "industry": r.get("industry") or "",
                    "last_day": r.get("last_day_data_date") or ""})
        if len(out) >= region["count"]:
            break
    return out


def week_id(dt=None):
    y, w, _ = (dt or common.now_kst()).isocalendar()
    return f"{y}-W{w:02d}"


def collect(force=False):
    now = common.now_kst()
    wid = week_id(now)
    state = common.load_state("weekly_movers")
    if not force and (now.weekday() != 5 or not 6 <= now.hour < 9 or state.get("last_week") == wid):
        return 0, 0  # 토요일 06~09시 KST, 주 1회
    cfg = common.load_yaml(CONFIG) or {}
    key = _key()
    rates = fx_rates(key, cfg)
    rows_out, missing = [], []
    for region in cfg.get("regions", []):
        if not region.get("exchanges"):
            missing.append(region["key"])
            continue
        rows = []
        for ex in region["exchanges"]:
            try:
                rows += screen(key, ex, cfg.get("fetch_limit", 100))
            except Exception as exc:  # 거래소 하나 실패는 기록만
                missing.append(f"{region['key']}:{ex}:{type(exc).__name__}")
        for i, r in enumerate(pick(rows, region, cfg, rates), 1):
            rows_out.append({"region": region["key"], "rank": i, **r, "as_of": common.iso(now)})
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    path = OUT_DIR / f"{wid}.csv"
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=COLS, lineterminator="\n")
        w.writeheader()
        w.writerows(rows_out)
    state.update(last_week=wid, last_file=str(path.name), missing=missing)
    common.save_state("weekly_movers", state)
    common.record_health("src-weekly-movers", True, f"누락 {missing}" if missing else None)
    return len(rows_out), len(rows_out)


def run():  # run_hourly 진입점
    return collect()


def list_exchanges():
    d = _get("exchanges-list/", _key())
    for e in d:
        if e.get("CountryISO2") in ("JP", "KR", "GB", "DE", "FR", "NL", "IT", "ES", "CH", "SE", "DK", "FI", "BE", "NO", "US"):
            print(f"{e.get('Code'):8} {e.get('CountryISO2')} {e.get('Currency'):4} {e.get('Name')}")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    if "--exchanges" in sys.argv:
        list_exchanges()
    else:
        print(collect(force="--force" in sys.argv))
