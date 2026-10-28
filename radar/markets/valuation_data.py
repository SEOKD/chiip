"""밸류에이션 데이터 수집 (L0) — EODHD 펀더멘털·EOD 가격 + 수동 컨센서스 (docs/valuation/framework.md §3)

하루 두 번(05:00~06:00 미국 마감 반영, 15:45~17:00 한국 마감 반영 KST) 유니버스(config/valuation.yaml)의
추정치(FY0·FY1 평균·최고·최저·애널리스트 수), EPS 추정 7·30·90일 전 값, 상·하향 건수, 서프라이즈, 멀티플,
가격 이력을 받아 knowledge/models/valuation/snapshots/YYYYMMDD.csv 와 prices/<code>.csv 에 저장한 뒤
계산 엔진(scripts/valuation/engine.py)을 돌린다. 모델을 부르지 않는다.
- 펀더멘털은 EODHD 'Fundamentals' 또는 'ALL-IN-ONE' 요금제가 있어야 온다. 없으면 가격만 받고 추정치 칸은 비운다(미확인).
- EODHD에 없는 종목·항목은 manual_consensus.csv(마스터 수동 입력)로 채운다. 출처를 source 열에 남긴다.

사용: py radar/markets/valuation_data.py            (시간대 안에서만, 시간대당 1회 — run_hourly가 30분마다 호출)
      py radar/markets/valuation_data.py --force    (지금 수집 + 계산)
      py radar/markets/valuation_data.py --compute  (수집 없이 계산만 — 내러티브 강도 등)
"""
import csv
import json
import sys
import urllib.error
import urllib.parse
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from pollers import common  # noqa: E402

CONFIG = "config/valuation.yaml"
VAL_DIR = common.ROOT / "knowledge" / "models" / "valuation"
SNAP_DIR = VAL_DIR / "snapshots"
PRICE_DIR = VAL_DIR / "prices"
MANUAL = VAL_DIR / "manual_consensus.csv"
API = "https://eodhd.com/api"
SNAP_COLS = ["date", "id", "code", "region", "sub", "currency", "price", "price_date", "mcap", "ev",
             "pe_ttm", "pe_fwd", "ps", "pb", "ev_sales", "ev_ebitda", "eps_ttm", "bvps",
             "op_margin", "roe", "gross_margin",
             "fy0_end", "fy1_end", "eps_fy0", "eps_fy0_lo", "eps_fy0_hi", "eps_fy0_n",
             "eps_fy1", "eps_fy1_lo", "eps_fy1_hi", "eps_fy1_n", "rev_fy0", "rev_fy1",
             "eps_fy0_7d", "eps_fy0_30d", "eps_fy0_90d", "eps_fy1_7d", "eps_fy1_30d", "eps_fy1_90d",
             "up7", "down7", "up30", "down30", "surprise_avg4", "beat_rate4", "beat_drop4",
             "target_price", "source"]
MANUAL_COLS = ["as_of", "id", "period", "fy_end", "eps_avg", "eps_low", "eps_high", "n_analysts", "rev_avg",
               "source", "note"]


def _key():
    key = common.load_env().get("EODHD_API_KEY")
    if not key:
        raise RuntimeError("EODHD_API_KEY 없음 (D:\\local-only\\secrets\\.env) — 밸류에이션 가격·추정치 미수집")
    return key


def _get(path, key, **params):
    params["api_token"] = key
    params.setdefault("fmt", "json")
    return json.loads(common.http_get(f"{API}/{path}?{urllib.parse.urlencode(params)}", timeout=60))


def _f(x):
    try:
        v = float(x)
        return v if v == v else None  # NaN 제외
    except (TypeError, ValueError):
        return None


def in_slot(now, cfg):
    hm = now.strftime("%H:%M")
    for s in cfg.get("slots", []):
        if s["from"] <= hm < s["to"]:
            return s["name"]
    return None


# ---------- 가격 ----------
def fetch_prices(key, code, days):
    start = (common.now_kst() - timedelta(days=days)).strftime("%Y-%m-%d")
    rows = _get(f"eod/{code}", key, **{"from": start})
    out = [(r["date"], _f(r.get("adjusted_close")) or _f(r.get("close"))) for r in rows if r.get("date")]
    return [(d, p) for d, p in out if p]


def save_prices(code, rows):
    PRICE_DIR.mkdir(parents=True, exist_ok=True)
    with (PRICE_DIR / f"{code}.csv").open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(["date", "close"])
        w.writerows(rows)


def load_prices(code):
    p = PRICE_DIR / f"{code}.csv"
    if not p.exists():
        return []
    with p.open(encoding="utf-8") as f:
        return [(r["date"], float(r["close"])) for r in csv.DictReader(f) if r.get("close")]


def reaction(prices, report_date, timing):
    """실적 발표 반응: 장후 발표면 발표일 종가→다음 거래일 종가, 장전이면 전일 종가→발표일 종가"""
    dates = [d for d, _ in prices]
    if report_date not in dates:
        later = [d for d in dates if d > report_date]
        if not later:
            return None
        i = dates.index(later[0])
        timing = "BeforeMarket"  # 휴장일 발표는 다음 거래일 반응으로
    else:
        i = dates.index(report_date)
    if timing == "AfterMarket":
        return prices[i + 1][1] / prices[i][1] - 1 if i + 1 < len(prices) else None
    return prices[i][1] / prices[i - 1][1] - 1 if i >= 1 else None


# ---------- 펀더멘털 ----------
def _trend_rows(trend):
    """Earnings Trend: {날짜: {...}} 또는 v1.1 {'Annual': ..., 'Quarterly': ...} 둘 다 처리"""
    if not isinstance(trend, dict):
        return list(trend or [])
    rows = []
    for k, v in trend.items():
        if k in ("Annual", "Quarterly") and isinstance(v, (dict, list)):
            rows += list(v.values()) if isinstance(v, dict) else v
        elif isinstance(v, dict):
            rows.append(v)
    return rows


def parse_fundamentals(d, prices):
    hl, va = d.get("Highlights") or {}, d.get("Valuation") or {}
    out = {"currency": (d.get("General") or {}).get("CurrencyCode"),
           "mcap": _f(hl.get("MarketCapitalization")), "ev": _f(va.get("EnterpriseValue")),
           "pe_ttm": _f(va.get("TrailingPE")), "pe_fwd": _f(va.get("ForwardPE")), "ps": _f(va.get("PriceSalesTTM")),
           "pb": _f(va.get("PriceBookMRQ")), "ev_sales": _f(va.get("EnterpriseValueRevenue")),
           "ev_ebitda": _f(va.get("EnterpriseValueEbitda")), "eps_ttm": _f(hl.get("DilutedEpsTTM") or hl.get("EarningsShare")),
           "bvps": _f(hl.get("BookValue")), "op_margin": _f(hl.get("OperatingMarginTTM")), "roe": _f(hl.get("ReturnOnEquityTTM")),
           "target_price": _f(hl.get("WallStreetTargetPrice") or (d.get("AnalystRatings") or {}).get("TargetPrice"))}
    rev, gp = _f(hl.get("RevenueTTM")), _f(hl.get("GrossProfitTTM"))
    out["gross_margin"] = gp / rev if rev and gp is not None else None
    earn = d.get("Earnings") or {}
    for t in _trend_rows(earn.get("Trend")):
        tag = {"0y": "fy0", "+1y": "fy1"}.get(t.get("period"))
        if not tag:
            continue
        out.update({f"{tag}_end": t.get("date"), f"eps_{tag}": _f(t.get("earningsEstimateAvg")),
                    f"eps_{tag}_lo": _f(t.get("earningsEstimateLow")), f"eps_{tag}_hi": _f(t.get("earningsEstimateHigh")),
                    f"eps_{tag}_n": _f(t.get("earningsEstimateNumberOfAnalysts")), f"rev_{tag}": _f(t.get("revenueEstimateAvg")),
                    f"eps_{tag}_7d": _f(t.get("epsTrend7daysAgo")), f"eps_{tag}_30d": _f(t.get("epsTrend30daysAgo")),
                    f"eps_{tag}_90d": _f(t.get("epsTrend90daysAgo"))})
        if tag == "fy1":
            out.update(up7=_f(t.get("epsRevisionsUpLast7days")) or 0, down7=_f(t.get("epsRevisionsDownLast7days")) or 0,
                       up30=_f(t.get("epsRevisionsUpLast30days")) or 0, down30=_f(t.get("epsRevisionsDownLast30days")) or 0)
    today = common.now_kst().strftime("%Y-%m-%d")
    hist = [h for h in (earn.get("History") or {}).values()
            if isinstance(h, dict) and h.get("epsActual") is not None and (h.get("reportDate") or "") <= today]
    hist = sorted(hist, key=lambda h: h.get("reportDate") or "")[-4:]
    if hist:
        sur = [_f(h.get("surprisePercent")) for h in hist if _f(h.get("surprisePercent")) is not None]
        out["surprise_avg4"] = sum(sur) / len(sur) if sur else None
        out["beat_rate4"] = sum(1 for s in sur if s > 0) / len(sur) if sur else None
        beats = [(h, reaction(prices, h["reportDate"], h.get("beforeAfterMarket"))) for h in hist
                 if (_f(h.get("surprisePercent")) or 0) > 0 and h.get("reportDate")]
        beats = [(h, r) for h, r in beats if r is not None]
        out["beat_drop4"] = sum(1 for _, r in beats if r < 0) / len(beats) if beats else None
    return out


def fetch_fundamentals(key, code):
    try:
        return _get(f"fundamentals/{code}", key, filter="General,Highlights,Valuation,Earnings,AnalystRatings")
    except urllib.error.HTTPError as exc:
        if exc.code in (402, 403):  # 요금제에 펀더멘털 없음
            raise PermissionError("펀더멘털 요금제 아님") from exc
        raise


# ---------- 수동 컨센서스 ----------
def load_manual():
    if not MANUAL.exists():
        return []
    with MANUAL.open(encoding="utf-8") as f:
        return [r for r in csv.DictReader(f) if r.get("id") and r.get("as_of")]


def manual_fill(row, manual, today):
    """EODHD에 추정치가 없을 때 수동 입력으로 채움. 30·90일 전 값은 그 시점 이전 최신 입력"""
    mine = [r for r in manual if r["id"] == row["id"]]
    if not mine or row.get("eps_fy1") is not None:
        return False

    def latest(period, before):
        c = [r for r in mine if r["period"] == period and r["as_of"] <= before]
        return max(c, key=lambda r: r["as_of"]) if c else None

    for period, tag in (("0y", "fy0"), ("+1y", "fy1")):
        cur = latest(period, today)
        if not cur:
            continue
        row.update({f"{tag}_end": cur.get("fy_end"), f"eps_{tag}": _f(cur.get("eps_avg")),
                    f"eps_{tag}_lo": _f(cur.get("eps_low")), f"eps_{tag}_hi": _f(cur.get("eps_high")),
                    f"eps_{tag}_n": _f(cur.get("n_analysts")), f"rev_{tag}": _f(cur.get("rev_avg"))})
        for days, suf in ((7, "7d"), (30, "30d"), (90, "90d")):
            old = latest(period, (date.fromisoformat(today) - timedelta(days=days)).isoformat())
            row[f"eps_{tag}_{suf}"] = _f(old.get("eps_avg")) if old and old["as_of"] != cur["as_of"] else None
    row["source"] = (row.get("source") or "") + "+manual"
    return True


# ---------- 수집 ----------
def collect(today=None):
    cfg = common.load_yaml(CONFIG) or {}
    today = today or common.now_kst().strftime("%Y-%m-%d")
    manual = load_manual()
    key = None
    try:
        key = _key()
    except RuntimeError:
        if not manual:
            raise
    rows, missing, fund_ok = [], [], True
    for u in cfg.get("universe", []):
        row = {"date": today, "id": u["id"], "code": u.get("code") or "", "region": u.get("region"),
               "sub": u.get("sub"), "source": ""}
        if key and u.get("code"):
            try:
                prices = fetch_prices(key, u["code"], cfg.get("price_history_days", 400))
                save_prices(u["code"], prices)
                if prices:
                    row.update(price=prices[-1][1], price_date=prices[-1][0])
                row["source"] = "eodhd-eod"
            except Exception as exc:  # 종목 하나 실패는 기록만
                missing.append(f"{u['id']}:가격:{type(exc).__name__}")
                prices = load_prices(u["code"])
            if fund_ok:
                try:
                    row.update({k: v for k, v in parse_fundamentals(fetch_fundamentals(key, u["code"]), prices).items()
                                if v is not None})
                    row["source"] += "+eodhd-fund"
                except PermissionError:
                    fund_ok = False  # 요금제 문제 — 나머지 종목도 같은 결과라 더 부르지 않음
                    missing.append("펀더멘털:요금제 아님")
                except Exception as exc:
                    missing.append(f"{u['id']}:펀더멘털:{type(exc).__name__}")
        elif not u.get("code"):
            missing.append(f"{u['id']}:코드 미확인")
        manual_fill(row, manual, today)
        rows.append(row)
    SNAP_DIR.mkdir(parents=True, exist_ok=True)
    path = SNAP_DIR / f"{today.replace('-', '')}.csv"
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=SNAP_COLS, extrasaction="ignore", lineterminator="\n")
        w.writeheader()
        w.writerows(rows)
    got = sum(1 for r in rows if r.get("price") is not None)
    common.record_health("src-valuation", bool(got) or bool(manual), f"누락 {missing[:8]}" if missing else None)
    return got, missing


def compute():
    sys.path.insert(0, str(common.ROOT / "scripts" / "valuation"))
    import engine  # noqa: E402
    return engine.compute()


def run():  # run_hourly 진입점
    cfg = common.load_yaml(CONFIG) or {}
    now = common.now_kst()
    slot = in_slot(now, cfg)
    state = common.load_state("valuation_data")
    tag = f"{now:%Y%m%d}-{slot}"
    if not slot or state.get("last") == tag:
        return 0, 0
    note = None
    got = 0
    try:
        got, missing = collect()
    except RuntimeError as exc:
        note = str(exc)
    n = compute()
    state.update(last=tag, at=common.iso(now), note=note)
    common.save_state("valuation_data", state)
    if note:
        raise RuntimeError(f"{note} (내러티브 강도만 계산: {n}종목)")
    return got, n


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    if "--compute" in sys.argv:
        print("계산", compute())
    elif "--force" in sys.argv:
        try:
            print("수집", collect())
        except RuntimeError as exc:
            print(f"수집 건너뜀 — {exc}")
        print("계산", compute())
    else:
        print(run())
