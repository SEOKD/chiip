"""발굴 채널 TradingView 스크린 — 저관심 텐배거 조짐(7개 시장)·행동주의 표적 유사도 (마스터 지시 2026-11-15, 설정 config/channel_screens.yaml,
설계 knowledge/methods/discovery_engine.md)

흐름(수집·점수는 결정론, TradingView 호출만 모델 — 병렬 금지, 한 번에 하나씩):
  ① --plan [스크린]          : 오늘 돌릴 스크린·시장의 mcp-tv-run-screener 호출 사양(JSON). 시장은 순번으로 하루 per_run개 — 같은 날 다시 부르면 due=false
  ② --put <스크린> <TV 시장> <응답 파일> : radar/state/channel_screens/<스크린>_<시장>.json (응답의 data.rows 또는 rows, git 제외)
  ③ --score [스크린]         : 시장 안 백분위 가중합(0~10) + 관문·적신호 → 상위 top_n을 단서 장부(scripts/discovery/leads.py)에, 표 outputs/discovery/<스크린>_<날짜>.md
점수 요소(가중 = 등록부 prm-cscr-* 사전값, 근거는 config 주석):
  neglected(저관심 텐배거 조짐, 3~5년): FCF 수익률·가치(B/M·이익수익률)가 가장 크고, 작은 규모, 아직 안 뻗음(12개월 가격 위치·6개월 수익률이 낮을수록),
    소외(애널리스트 수 적음), 질(ROA·피오트로스키 F), 조용한 거래(회전율 낮음), 성장은 약하게 — Yartseva 2025 서열(조사 B §8)
  quant_alpha(IB 정량 복합, 3~12개월): 가치·질·12-1 모멘텀·52주 고점 근접·주식 수 감소·낮은 발생액·낮은 변동성·단기 반전 — 시장별 배수(일본 모멘텀 ×0.3 등)
  activist_target(행동주의 표적 유사도): 저평가(토빈 q·PBR 낮음)·현금 많음·자본 효율 낮음(ROE 낮음)·주주환원 적음·규모(중소형)·유동성(거래 가능)
관문: 거래대금 하한(시장별), 알트만 Z 부실 구간·적자 현금흐름 과다·희석은 감점 또는 제외. 모르는 값은 그 요소를 빼고 가중을 나눈다(빈칸을 0으로 치지 않는다).
금지 연결: 스크린 점수 → 경쟁우위가 아니다. 표적 유사도 → 행동주의 진입이 아니다. 점수는 연구 후보를 줄이는 보조이지 매수 권유가 아니다.
사용: py scripts/discovery/channel_screens.py --plan [neglected|quant_alpha|activist_target] | --put <스크린> <시장> <파일> | --score [스크린]
"""
import json
import math
import re
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))
DIR = ROOT / "radar" / "state" / "channel_screens"   # TradingView 원자료 — git 제외(아시아 스크린 원자료와 같게)
OUTD = ROOT / "outputs" / "discovery"
STATE = ROOT / "radar" / "state" / "channel_screens.json"
KST = timezone(timedelta(hours=9))


def cfg():
    return yaml.safe_load((ROOT / "config" / "channel_screens.yaml").read_text(encoding="utf-8"))


def today_kst():
    return datetime.now(KST).date()


def _j(p, d=None):
    try:
        return json.loads(Path(p).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {} if d is None else d


def fx(c):
    """통화 → USD — ECB 기준환율(scripts/tenbagger/bands.ecb_rates), 못 받으면 설정 fx_fallback"""
    out = dict(c.get("fx_fallback") or {})
    try:
        sys.path.insert(0, str(ROOT / "scripts" / "tenbagger"))
        import bands
        out.update({k: v for k, v in bands.ecb_rates().items() if v})
    except Exception:  # noqa: BLE001
        pass
    out["USD"] = 1.0
    return out


def plan(screen=None, today=None, force=False):
    """[{screen, market, due, args}] — args는 mcp-tv-run-screener에 그대로 넣는다"""
    today = today or today_kst()
    c = cfg()
    st = _j(STATE)
    rates = fx(c)
    out = []
    for name, s in (c.get("screens") or {}).items():
        if screen and name != screen:
            continue
        if today.weekday() not in (s.get("weekdays") or [0, 1, 2, 3, 4]):
            continue
        done_today = st.get(name, {}).get("date") == today.isoformat()
        rot = s["rotation"]
        i = st.get(name, {}).get("next", 0) % len(rot)
        picks = st.get(name, {}).get("picks") if done_today else [rot[(i + k) % len(rot)] for k in range(min(s.get("per_run", 2), len(rot)))]
        for m in picks or []:
            mk = c["markets"][m]
            ccy = mk["ccy"]
            rate = rates.get(ccy) or 1.0
            lo, hi = (s.get("mcap_usd_by_market") or {}).get(m) or s["mcap_usd"]
            filt = {"market_cap_basic": [round(lo / rate), round(hi / rate)], **(s.get("filters") or {})}
            out.append({"screen": name, "market": m, "due": not done_today or force,
                        "args": {"market": m, "filters": filt, "columns": s["columns"], "sort_by": s.get("sort_by", "market_cap_basic"),
                                 "sort_order": s.get("sort_order", "desc"), "limit": s.get("limit", 100)}})
        if not done_today:
            st[name] = {"date": today.isoformat(), "picks": picks, "next": (i + len(picks or [])) % len(rot)}
    STATE.parent.mkdir(parents=True, exist_ok=True)
    STATE.write_text(json.dumps(st, ensure_ascii=False), encoding="utf-8")
    return out


def put(screen, market, path, today=None):
    d = _j(path)
    rows = (d.get("data") or {}).get("rows") if isinstance(d.get("data"), dict) else d.get("rows")
    if rows is None and isinstance(d, list):
        rows = d
    if not isinstance(rows, list):
        raise SystemExit("응답에 rows가 없다 — mcp-tv-run-screener 응답 JSON을 그대로 저장한다")
    DIR.mkdir(parents=True, exist_ok=True)
    (DIR / f"{screen}_{market}.json").write_text(json.dumps({"as_of": str(today or today_kst()), "screen": screen, "market": market, "rows": rows},
                                                            ensure_ascii=False), encoding="utf-8")
    return len(rows)


# ---------- 점수 ----------
def _f(v):
    try:
        x = float(v)
        return x if math.isfinite(x) else None
    except (TypeError, ValueError):
        return None


def pct_rank(vals):
    """{key: 백분위 0~1} — None은 빼고, 같은 값은 평균 순위"""
    xs = sorted((v, k) for k, v in vals.items() if v is not None)
    n = len(xs)
    if n < 2:
        return {k: 0.5 for _, k in xs}
    out, i = {}, 0
    while i < n:
        j = i
        while j + 1 < n and xs[j + 1][0] == xs[i][0]:
            j += 1
        r = (i + j) / 2 / (n - 1)
        for t in range(i, j + 1):
            out[xs[t][1]] = r
        i = j + 1
    return out


def features(screen, r, usd, c, market=None):
    """요소별 원값(클수록 좋게 부호를 맞춘다). 없으면 None — 빠진 요소는 가중에서 빼고 나눈다.
    TradingView 칸 이름은 2026-11-15 조사 G가 값이 돌아오는 것으로 확인한 것만 쓴다(return_on_invested_capital — _ttm은 비어 온다)"""
    g = _f
    mcap = g(r.get("market_cap_basic"))
    mcap_usd = mcap * usd if mcap else None
    tv = g(r.get("AvgValue.Traded_30d")) or g(r.get("AvgValue.Traded_10d")) or 0
    val_usd = tv * usd / (100 if market == "uk" else 1)   # 영국 거래대금은 펜스(조사 G)
    turnover = (val_usd / mcap_usd) if mcap_usd and val_usd else None
    inv = lambda x: (1 / x) if x and x > 0 else None
    close, hi, lo = g(r.get("close")), g(r.get("price_52_week_high")), g(r.get("price_52_week_low"))
    rng = ((close - lo) / (hi - lo)) if close and hi and lo and hi > lo else ((close / hi) if close and hi else None)
    perf_y, perf_6m, perf_1m = g(r.get("Perf.Y")), g(r.get("Perf.6M")), g(r.get("Perf.1M"))
    fscore = g(r.get("piotroski_f_score_ttm")) if r.get("piotroski_f_score_ttm") is not None else g(r.get("piotroski_f_score_fy"))
    if screen == "neglected":   # 저관심 10배 전조(조사 G NMP + 조사 B 복합 B — Yartseva 2025 서열)
        g_fq, g_ttm = g(r.get("total_revenue_yoy_growth_fq")), g(r.get("total_revenue_yoy_growth_ttm"))
        gm_now, gm_fy = g(r.get("gross_margin")), g(r.get("gross_profit_margin_fy"))
        ebitda_g, asset_g = g(r.get("ebitda_yoy_growth_ttm")), g(r.get("total_assets_yoy_growth_fy"))
        eps_s = g(r.get("eps_surprise_percent_fq"))
        sz = math.log(mcap_usd) if mcap_usd else None
        return {
            "value": _wavg([(inv(g(r.get("price_free_cash_flow_ttm"))), 0.6), (inv(g(r.get("price_book_fq"))), 0.3), (inv(g(r.get("enterprise_value_ebitda_ttm"))), 0.1)]),
            "inflection": _avg([None if g_fq is None or g_ttm is None else min(g_fq, 300) - min(g_ttm, 300),
                                None if gm_now is None or gm_fy is None else gm_now - gm_fy,
                                None if eps_s is None else max(-100.0, min(100.0, eps_s))]),
            "quality": _avg([g(r.get("ebitda_margin_ttm")), g(r.get("return_on_invested_capital")), (fscore * 3) if fscore is not None else None,
                             None if ebitda_g is None or asset_g is None else (10.0 if ebitda_g >= asset_g else -10.0)]),
            "neglect": _avg([-(g(r.get("recommendation_total")) or 0.0), -turnover * 100 if turnover is not None else None]),
            "size": -abs(sz - math.log(c.get("size_peak_usd", 2.5e8))) if sz is not None else None,
            "not_extended": _avg([-rng if rng is not None else None, -(perf_6m / 100) if perf_6m is not None else None]),
        }, mcap_usd, val_usd
    if screen == "quant_alpha":   # IB 정량 복합(조사 B 복합 A — TradingView로 계산 가능한 부분)
        mom = (perf_y - perf_1m) if perf_y is not None and perf_1m is not None else None   # 12-1개월 근사
        sloan = g(r.get("sloan_ratio_ttm")) if r.get("sloan_ratio_ttm") is not None else g(r.get("sloan_ratio_fy"))
        return {
            "value": _avg([inv(g(r.get("enterprise_value_to_ebit_ttm"))), inv(g(r.get("price_free_cash_flow_ttm"))), inv(g(r.get("price_book_fq"))), g(r.get("earnings_yield"))]),
            "quality": _avg([g(r.get("return_on_assets_ttm")), g(r.get("return_on_invested_capital")), (fscore * 3) if fscore is not None else None]),
            "momentum": _avg([mom, (close / hi * 100) if close and hi else None]),
            "issuance": g(r.get("buyback_yield")),
            "accruals": -sloan if sloan is not None else None,
            "low_vol": -g(r.get("Volatility.M")) if g(r.get("Volatility.M")) is not None else None,
            "reversal": -perf_1m if perf_1m is not None else None,
        }, mcap_usd, val_usd
    if screen == "activist_target":
        tq = g(r.get("tobin_q_ratio_fy"))
        pb = g(r.get("price_book_fq"))
        cash = g(r.get("cash_n_short_term_invest_fq")) or g(r.get("cash_n_short_term_invest_fy"))
        cash_ratio = (cash / mcap) if cash and mcap else None
        roe = g(r.get("return_on_equity_ttm"))
        payout = _avg([g(r.get("dividend_payout_ratio_ttm")), (g(r.get("buyback_yield")) or 0) * 10 if r.get("buyback_yield") is not None else None])
        return {
            "cheap": _avg([-tq if tq is not None else None, -pb if pb is not None else None]),
            "cash_rich": cash_ratio,
            "low_roe": -roe if roe is not None else None,
            "low_payout": -payout if payout is not None else None,
            "lagging": -perf_y if perf_y is not None else None,
            "size": -abs(math.log(mcap_usd) - math.log(c.get("size_sweet_usd", 2e9))) if mcap_usd else None,
            "liquid": math.log(val_usd) if val_usd else None,
        }, mcap_usd, val_usd
    raise ValueError(screen)


def _wavg(pairs):
    xs = [(v, w) for v, w in pairs if v is not None]
    return sum(v * w for v, w in xs) / sum(w for _, w in xs) if xs else None


def _avg(xs):
    xs = [x for x in xs if x is not None]
    return sum(xs) / len(xs) if xs else None


def gates(screen, r, mcap_usd, val_usd, s, market):
    """제외 사유(없으면 None)·감점 목록 — 관문은 조사 G NMP(유동성·가격·부실·희석·현금 경로·복권형) + 스크린 필터 재적용
    (TradingView가 여러 칸의 필터를 알리지 않고 무시한다 — 조사 G: recommendation_total·price_book_fq·is_primary 등)"""
    g = _f
    if s.get("primary_only", True) and r.get("is_primary") is False:
        return "주 상장 아님(2차 상장)", []
    ex = s.get("exclude_industries")
    if ex and re.search(ex, str(r.get("industry") or ""), re.I):
        return "제외 업종(리츠·펀드 — 현금을 나눠 주는 구조라 재투자 복리 대상이 아님)", []
    for k, rng in (s.get("filters") or {}).items():
        lo, hi = rng
        v = g(r.get(k))
        if v is not None and ((lo is not None and v < lo) or (hi is not None and v > hi)):
            return f"필터 {k} 범위 밖", []
    lo_mc, hi_mc = (s.get("mcap_usd_by_market") or {}).get(market) or s["mcap_usd"]
    if mcap_usd is not None and not (lo_mc <= mcap_usd <= hi_mc):
        return "시총 범위 밖", []
    minv = (s.get("min_value_usd") or {}).get(market, (s.get("min_value_usd") or {}).get("default", 0))
    if val_usd < minv:
        return "거래대금 하한 미달", []
    minp = (s.get("min_price") or {}).get(market)
    if minp and (g(r.get("close")) or 0) < minp:
        return "주가 하한 미달", []
    pen = []
    z = g(r.get("altman_z_score_ttm")) if r.get("altman_z_score_ttm") is not None else g(r.get("altman_z_score_fy"))
    fcf = g(r.get("free_cash_flow_ttm"))
    fcfm = g(r.get("free_cash_flow_margin_ttm"))
    if screen == "neglected":
        if z is not None and z < s.get("altman_min", 1.1) and (fcf is not None and fcf < 0):
            return f"부실 구간(알트만 Z {z:.1f}·FCF 적자)", []
        if fcf is not None and fcf <= 0 and (fcfm is None or fcfm < s.get("fcf_margin_floor", -5)):
            return "현금 경로 없음(FCF 적자·FCF 마진 하한 미달)", []
        vm, p1 = g(r.get("Volatility.M")), g(r.get("Perf.1M"))
        if vm is not None and p1 is not None and p1 > s.get("lottery_1m", 100) and vm > s.get("lottery_vol", 15):
            return "복권형(1개월 +100% 넘고 변동성 최상위)", []
        if (g(r.get("Perf.Y")) or 0) > s.get("perf_y_max", 400):
            return "1년 수익률 과열", []
    by = g(r.get("buyback_yield"))
    if by is not None:
        if by <= -s.get("dilution_hard_pct", 20):
            return f"주식 수 증가 {-by:.0f}%(희석 상한)", []
        if by <= -s.get("dilution_max_pct", 10):
            pen.append(f"희석 {-by:.0f}%")
    sloan = g(r.get("sloan_ratio_ttm")) if r.get("sloan_ratio_ttm") is not None else g(r.get("sloan_ratio_fy"))
    if sloan is not None and abs(sloan) > s.get("sloan_max", 25):
        pen.append(f"발생액 비율 {sloan:.0f}%")
    return None, pen


def base_rate(c, market, mcap_usd=None):
    """10배·3배 기저율(조사 G TradingView 5년 생존 표본 — 시장별 값을 합동값으로 축소, 강도 200). 생존 편향으로 상한. c = 설정 전체(base_rates는 최상위)"""
    br = c.get("base_rates") or {}
    pool = br.get("pooled") or {}
    m = br.get(market) or {}
    if not m or not pool:
        return None
    k = br.get("shrink", 200)
    n = m.get("n", 0)
    return {x: round((n * m[x] + k * pool[x]) / (n + k), 4) for x in ("p3x", "p10x") if x in m and x in pool}


def score(screen=None, today=None, write=True):
    today = today or today_kst()
    c = cfg()
    rates = fx(c)
    res = {}
    for name, s in (c.get("screens") or {}).items():
        if screen and name != screen:
            continue
        w = s["weights"]
        pool, meta = {}, {}
        for p in sorted(DIR.glob(f"{name}_*.json")):
            d = _j(p)
            if not d or d.get("as_of", "") < (today - timedelta(days=s.get("stale_days", 21))).isoformat():
                continue
            m = d["market"]
            usd = rates.get(c["markets"][m]["ccy"]) or 1.0
            for r in d.get("rows") or []:
                f, mcap_usd, val_usd = features(name, r, usd, s, m)
                why, pen = gates(name, r, mcap_usd, val_usd, s, m)
                key = r.get("symbol") or f"{m}:{r.get('name')}"
                meta[key] = {"market": m, "row": r, "mcap_usd": mcap_usd, "val_usd": val_usd, "excluded": why, "pen": pen, "f": f}
                if not why:
                    pool.setdefault(m, {})[key] = f
        rows = []
        for m, items in pool.items():
            ranks = {k: pct_rank({key: f.get(k) for key, f in items.items()}) for k in w}
            mult = (s.get("market_mult") or {}).get(m) or {}
            wm = {k: wt * mult.get(k, 1.0) for k, wt in w.items()}   # 시장별 배수(예: 일본 모멘텀 ×0.3 — 조사 B, 모멘텀이 일본에서 약하다)
            for key in items:
                tot, ws, used = 0.0, 0.0, {}
                for k, wt in wm.items():
                    v = ranks[k].get(key)
                    if v is None:
                        continue
                    tot += wt * v
                    ws += wt
                    used[k] = round(v * 10, 1)
                if ws < s.get("min_weight_cover", 0.6):
                    continue
                sc = 10 * tot / ws - s.get("penalty_each", 0.7) * len(meta[key]["pen"])
                full = sum(wm.values())
                if ws < full - 1e-9:   # 빠진 요소가 있으면 완전성 배수(조사 G — 빈칸을 중립으로 부풀리지 않는다)
                    cf = s.get("completeness_floor", 0.85)
                    sc *= cf + (1 - cf) * ws / full
                rows.append({"symbol": key, "market": m, "score": round(max(0.0, sc), 2), "comp": used, "pen": meta[key]["pen"], "mcap_usd": meta[key]["mcap_usd"],
                             "row": meta[key]["row"], "base_rate": base_rate(c, c["markets"][m]["region"] if m in c["markets"] else m)})
        rows.sort(key=lambda x: -x["score"])
        top = []
        per_m = {}
        for r in rows:
            if per_m.get(r["market"], 0) >= s.get("top_n", 8):
                continue
            per_m[r["market"]] = per_m.get(r["market"], 0) + 1
            top.append(r)
        res[name] = {"rows": rows, "top": top, "excluded": sum(1 for v in meta.values() if v["excluded"])}
        if write:
            new = to_leads(name, s, top, c, today)
            res[name]["new_leads"] = len(new)
            OUTD.mkdir(parents=True, exist_ok=True)
            (OUTD / f"{name}_{today.strftime('%Y%m%d')}.md").write_text(render(name, s, res[name], c, today), encoding="utf-8")
    return res


def put_tv_fund(top, s, c, today):
    """단서가 된 종목의 펀더멘털 칸을 TradingView 스크린 값으로 채운다 — 발굴 선별 '② 선별 통과' 조건(펀더멘털 확보)을 해외 종목도 맞출 수 있게.
    Fiscal.ai 등 다른 원천 값이 있으면 건드리지 않는다(TradingView 값만 갱신). 이익률은 TradingView %를 비율로 바꾼다"""
    import channels
    fund_p = ROOT / "knowledge" / "models" / "discovery" / "fundamentals.json"
    d = _j(fund_p)
    n = 0
    for r in top:
        if r["score"] < s.get("lead_min", 7.0):
            continue
        raw = r["row"]
        cid = channels.sid(c["markets"][r["market"]]["region"], raw.get("name"))
        cur = d.get(cid) or {}
        if cur and not str(cur.get("source", "")).startswith("TradingView"):
            continue
        pfcf, gr, om, an = _f(raw.get("price_free_cash_flow_ttm")), _f(raw.get("total_revenue_yoy_growth_ttm")), _f(raw.get("operating_margin_ttm")), _f(raw.get("recommendation_total"))
        d[cid] = {"as_of": today.isoformat(), "currency": "USD", "mcap_usd": r["mcap_usd"], "rev_growth": None if gr is None else gr / 100,
                  "op_margin": None if om is None else om / 100, "pb": _f(raw.get("price_book_fq")), "fcf_yield": (1 / pfcf) if pfcf else None,
                  "n_analysts": int(an) if an is not None else 0, "industry": raw.get("industry"), "source": f"TradingView screener {r['symbol']}"}
        n += 1
    if n:
        fund_p.write_text(json.dumps(d, ensure_ascii=False, indent=1, sort_keys=True), encoding="utf-8")
    return n


def to_leads(name, s, top, c, today):
    import leads
    put_tv_fund(top, s, c, today)
    rows = []
    for r in top:
        if r["score"] < s.get("lead_min", 7.0):
            continue
        m = c["markets"][r["market"]]["region"]
        raw = r["row"]
        code = str(raw.get("name") or "")
        comp = ", ".join(f"{k} {v}" for k, v in sorted(r["comp"].items(), key=lambda x: -x[1])[:4])
        an = raw.get("recommendation_total")
        sig = (s.get("signal_head") or name) + f" {r['score']:.1f} — {comp}" + (f" · 애널리스트 {int(an) if an is not None else 0}명" if name == "neglected" else "") + \
              (f" · 감점 {', '.join(r['pen'])}" if r["pen"] else "")
        rows.append({"channel": s["channel"], "kind": s["kind"], "market": m, "ticker": code, "name": raw.get("description") or code, "tv": r["symbol"],
                     "date": today.isoformat(), "strength": round(min(10.0, r["score"]), 1), "signal": sig, "url": "",
                     "price": raw.get("close"), "mcap_usd": round(r["mcap_usd"]) if r["mcap_usd"] else "",
                     "extra": {"screen": name, "tv_market": r["market"], "industry": raw.get("industry"), "comp": r["comp"], "base_rate": r.get("base_rate")}})
    return leads.add(rows, today=today) if rows else []


def render(name, s, res, c, today):
    L = [f"# {s.get('title', name)} {today.isoformat()}", "", s.get("about", ""), "",
         f"후보 {len(res['rows'])} · 관문 제외 {res['excluded']} · 단서 문턱 {s.get('lead_min', 7.0)}", "",
         "| 순위 | 종목 | 시장 | 점수 | 시총 | 상위 요소 | 감점 |", "|---|---|---|---|---|---|---|"]
    for i, r in enumerate(res["top"], 1):
        raw = r["row"]
        mc = r["mcap_usd"]
        mcs = "—" if not mc else (f"${mc / 1e9:.1f}B" if mc >= 1e9 else f"${mc / 1e6:.0f}M")
        comp = ", ".join(f"{k} {v}" for k, v in sorted(r["comp"].items(), key=lambda x: -x[1])[:4])
        L.append(f"| {i} | {raw.get('description') or raw.get('name')}({r['symbol']}) | {r['market']} | **{r['score']:.1f}** | {mcs} | {comp} | {', '.join(r['pen']) or '-'} |")
    if name == "neglected":
        seen = {}
        for r in res["top"]:
            if r.get("base_rate") and r["market"] not in seen:
                seen[r["market"]] = r["base_rate"]
        if seen:
            L += ["", "기저율(조사 G — TradingView 5년 생존 표본, 시장별 값을 합동값으로 축소). 생존 편향으로 실제보다 높다:"]
            L += [f"- {m}: 5년 3배 {v.get('p3x', 0) * 100:.1f}% · 10배 {v.get('p10x', 0) * 100:.2f}%" for m, v in seen.items()]
    L += ["", "요소 값은 시장 안 백분위(0~10). 스크린 점수 → 경쟁우위가 아니다(금지표). 연구 후보이지 매수 권유 아님."]
    return "\n".join(L) + "\n"


def main(argv):
    sys.stdout.reconfigure(encoding="utf-8")
    if argv and argv[0] == "--plan":
        print(json.dumps(plan(argv[1] if len(argv) > 1 and not argv[1].startswith("--") else None, force="--force" in argv), ensure_ascii=False, indent=1))
    elif argv and argv[0] == "--put" and len(argv) >= 4:
        print(f"{argv[1]} {argv[2]} {put(argv[1], argv[2], argv[3])}행")
    elif argv and argv[0] == "--score":
        res = score(argv[1] if len(argv) > 1 else None)
        for k, v in res.items():
            print(f"[{k}] 후보 {len(v['rows'])} · 상위 {len(v['top'])} · 새 단서 {v.get('new_leads', 0)} · 상위: " + ", ".join(f"{r['row'].get('description')} {r['score']:.1f}" for r in v["top"][:5]))
    else:
        print(__doc__)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
