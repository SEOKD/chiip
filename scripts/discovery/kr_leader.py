"""국장 주도주 생애 단계(생·로·병·사) — 마스터 지시 2026-11-15 "국장 종목 분석 시 위 리포트의 메커니즘을 반영하도록 해라"
(DB금융투자 「주도주의 생로병사」 2018-10-17. 방법·반대 검증: knowledge/methods/kr_leader_lifecycle.md, 상수: config/kr_leader.yaml · 등록부 prm-krld-*)

메커니즘(리포트 → 규칙):
  장세   KOSPI 10주선 > 40주선이면 상승 장세, 마지막 골든크로스 주가 장세 시작(실시간 대리 규칙 — 리포트는 사후 장기 사이클로 나눴다)
  생     장세 시작 첫 3개월 누적 수익률 KOSPI 200 상위 5% · 직전 장세 주도주가 아님 · 실적은 선별 조건이 아니다(상관 거의 0)
  로     수익률 순위가 늘 상위권(장세 1·3·6·12개월 상위 36.8·23.5·19.8·16.4% 안) · 고점 대비 −30% 넘는 조정 없음 · 돌파 주에 거래량 증가 ·
         매출·영업이익이 늘기만 하면 된다(최상위일 필요 없음)
  병     10주선이 40주선 아래로 교차(주도주는 빨리 오르고 천천히 내려 교차가 고점 가까이에서 난다) — 지위 상실 가능성이 커진다
  사     장세 중 고점 대비 −30% 넘게 하락 — 주도주가 아니라고 가정하고 대응(역대 주도주의 약 95%는 그만큼 빠지지 않았다)
  정점   최대 PER·최대 상승률·상승 일수로는 정점을 못 잡는다 — 쓰지 않는다

자료(수집은 TradingView 호출만 모델, 판정은 결정론):
  py scripts/discovery/kr_leader.py --spec [KRX:코드 …]       # 받을 호출 사양(KOSPI 주봉 · KOSPI 200 수익률 스냅숏 · 종목 주봉)
  py scripts/discovery/kr_leader.py --put-index <응답.json>    # get-ohlcv KRX:KOSPI 1W → radar/state/kr_leader/index.csv
  py scripts/discovery/kr_leader.py --put-universe <응답.json> [YYYY-MM-DD]   # run-screener KOSPI 200 → knowledge/models/discovery/kr_leader/universe_<날짜>.csv
  py scripts/discovery/kr_leader.py --put-weekly <응답.json> <KRX:코드>       # get-ohlcv 1W → radar/state/kr_leader/w_<코드>.csv
  py scripts/discovery/kr_leader.py --put-rank <코드> <창 perf_3m 등> <그 값 이상 종목 수> <전체 수>   # 스냅숏 없이 한 종목 순위만(작은 호출 2개, --spec 참고)
  py scripts/discovery/kr_leader.py --about <회사 id|코드>      # 한 종목 판정(gather.py 원천 kr_leader)
  py scripts/discovery/kr_leader.py --scan                      # KOSPI 200 상위 순위 종목 판정 → outputs/discovery/kr_leader_<날짜>.md
주봉 파일이 없으면 회사 폴더 ohlcv.csv(일봉)를 주봉으로 묶어 쓴다. 금지 연결: 생애 단계는 가격 판정이다 — 펀더멘털 변화나 매수·매도 지시가 아니다.
"""
import csv
import json
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
STATE = ROOT / "radar" / "state" / "kr_leader"
UNIV = ROOT / "knowledge" / "models" / "discovery" / "kr_leader"
COMPANIES = ROOT / "knowledge" / "models" / "companies"
OUTD = ROOT / "outputs" / "discovery"
KST = timezone(timedelta(hours=9))
UCOLS = ["name", "description", "Perf.1M", "Perf.3M", "Perf.6M", "Perf.Y", "Perf.YTD", "market_cap_basic",
         "total_revenue_yoy_growth_ttm", "operating_income_yoy_growth_ttm"]
WINDOWS = ((1.5, "perf_1m", 1), (4.5, "perf_3m", 3), (9.0, "perf_6m", 6), (99.0, "perf_y", 12))   # 장세 나이(개월) → 순위 창


def cfg():
    return yaml.safe_load((ROOT / "config" / "kr_leader.yaml").read_text(encoding="utf-8"))


def _f(x):
    try:
        return None if x is None or x == "" else float(x)
    except (TypeError, ValueError):
        return None


# ---------- 자료 ----------
def bars_from(resp):
    """get-ohlcv 응답(rows 또는 columns) → [{date, h, c, v}] (주 마지막 날 기준 날짜는 TradingView 주봉 시작일)"""
    b = resp.get("bars", resp)
    if isinstance(b, dict):
        n = len(b.get("t") or [])
        rows = [{k: (b.get(k) or [None] * n)[i] for k in ("t", "o", "h", "l", "c", "v")} for i in range(n)]
    else:
        rows = b or []
    out = []
    for r in rows:
        if r.get("c") is None or r.get("t") is None:
            continue
        out.append({"date": datetime.fromtimestamp(int(r["t"]), tz=timezone.utc).date().isoformat(), "h": float(r.get("h") or r["c"]),
                    "c": float(r["c"]), "v": float(r.get("v") or 0)})
    return sorted(out, key=lambda x: x["date"])


def write_series(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, ["date", "h", "c", "v"])
        w.writeheader()
        w.writerows(rows)


def read_series(path):
    if not path.exists():
        return []
    with path.open(encoding="utf-8", newline="") as fh:
        return [{"date": r["date"], "h": float(r["h"]), "c": float(r["c"]), "v": float(r.get("v") or 0)} for r in csv.DictReader(fh)]


def weekly_from_daily(days):
    """일봉 → 주봉(ISO 주 단위: 주의 첫 거래일 날짜, 최고가·마지막 종가·거래량 합)"""
    weeks = {}
    for d in days:
        y, w, _ = date.fromisoformat(d["date"]).isocalendar()
        k = (y, w)
        if k not in weeks:
            weeks[k] = {"date": d["date"], "h": d["h"], "c": d["c"], "v": 0.0}
        x = weeks[k]
        x["h"], x["c"], x["v"] = max(x["h"], d["h"]), d["c"], x["v"] + d["v"]
    return [weeks[k] for k in sorted(weeks)]


def stock_weekly(code, entity=None):
    s = read_series(STATE / f"w_{code}.csv")
    if s:
        return s, "TradingView 주봉"
    if entity:
        sys.path.insert(0, str(ROOT / "scripts" / "tenbagger"))
        import flow
        d = flow.load_ohlcv(entity)
        if d:
            return weekly_from_daily(d), "회사 폴더 일봉 → 주봉"
    return [], None


def universe(day=None):
    """가장 최근(또는 day 이전 최근) KOSPI 200 스냅숏 → (날짜, {코드: 행})"""
    files = sorted(UNIV.glob("universe_*.csv"))
    if day:
        files = [f for f in files if f.stem.split("_", 1)[1] <= str(day)]
    if not files:
        return None, {}
    f = files[-1]
    with f.open(encoding="utf-8", newline="") as fh:
        return f.stem.split("_", 1)[1], {r["code"]: r for r in csv.DictReader(fh)}


def put_universe(path, day=None):
    d = json.loads(Path(path).read_text(encoding="utf-8"))
    rows = (d.get("data") or {}).get("rows") if isinstance(d.get("data"), dict) else d.get("rows")
    if not isinstance(rows, list):
        raise SystemExit("응답에 rows가 없다 — mcp-tv-run-screener 응답 JSON을 그대로 저장한다")
    day = str(day or datetime.now(KST).date())
    UNIV.mkdir(parents=True, exist_ok=True)
    keys = ["code", "name", "perf_1m", "perf_3m", "perf_6m", "perf_y", "perf_ytd", "mcap", "rev_g", "op_g"]
    with (UNIV / f"universe_{day}.csv").open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, keys)
        w.writeheader()
        for r in rows:
            w.writerow({"code": str(r.get("name") or "").strip(), "name": r.get("description") or "", "perf_1m": _f(r.get("Perf.1M")), "perf_3m": _f(r.get("Perf.3M")),
                        "perf_6m": _f(r.get("Perf.6M")), "perf_y": _f(r.get("Perf.Y")), "perf_ytd": _f(r.get("Perf.YTD")), "mcap": _f(r.get("market_cap_basic")),
                        "rev_g": _f(r.get("total_revenue_yoy_growth_ttm")), "op_g": _f(r.get("operating_income_yoy_growth_ttm"))})
    return len(rows), day


# ---------- 판정 ----------
def sma(xs, n):
    return [None if i + 1 < n else sum(xs[i + 1 - n:i + 1]) / n for i in range(len(xs))]


def regime(index_w, c=None):
    """KOSPI 주봉 → {'up': bool, 'start': 날짜, 'age_weeks', 'prev': (시작, 끝) 직전 상승 구간}"""
    c = c or cfg()["regime"]
    cl = [b["c"] for b in index_w]
    f, s = sma(cl, c["fast_weeks"]), sma(cl, c["slow_weeks"])
    state = [None if a is None or b is None else a > b for a, b in zip(f, s)]
    segs, start = [], None
    for i, st in enumerate(state):
        if st and (i == 0 or not state[i - 1]):
            start = i
        if start is not None and (not st) and state[i - 1]:
            segs.append((start, i - 1))
            start = None
    cur_up = bool(state and state[-1])
    if cur_up:
        segs.append((start, len(state) - 1))
    if not segs:
        return {"up": cur_up, "start": None, "age_weeks": None, "prev": None, "last_seg": None}
    last = segs[-1]
    prev = segs[-2] if cur_up and len(segs) >= 2 else (segs[-1] if not cur_up else None)
    d = lambda i: index_w[i]["date"]
    return {"up": cur_up, "start": d(last[0]) if cur_up else None, "age_weeks": (len(state) - 1 - last[0]) if cur_up else None,
            "prev": (d(prev[0]), d(prev[1])) if prev else None, "last_seg": (d(last[0]), d(last[1])),
            "index_now": cl[-1], "fast": f[-1], "slow": s[-1]}


def window(age_months):
    for lim, col, months in WINDOWS:
        if age_months <= lim:
            return col, months
    return WINDOWS[-1][1], WINDOWS[-1][2]


def put_rank(code, col, at_or_above, total):
    STATE.mkdir(parents=True, exist_ok=True)
    d = {"date": datetime.now(KST).date().isoformat(), "col": col, "pct": int(at_or_above) / int(total), "n": int(total)}
    (STATE / f"rank_{code}.json").write_text(json.dumps(d), encoding="utf-8")
    return d


def rank_file(code, col):
    p = STATE / f"rank_{code}.json"
    if not p.exists():
        return None
    d = json.loads(p.read_text(encoding="utf-8"))
    return d if d.get("col") == col else None


def rank_pct(univ, code, age_months):
    """장세 나이에 맞는 수익률 창으로 KOSPI 200 안 순위(상위 %). 창은 고정(1·3·6·12개월) — 장세 시작일과 정확히 맞지 않는 근사"""
    col, months = window(age_months)
    vals = [(k, _f(r.get(col))) for k, r in univ.items() if _f(r.get(col)) is not None]
    me = _f((univ.get(code) or {}).get(col))
    if me is None or not vals:
        return None, col, months
    better = sum(1 for _, v in vals if v > me)
    return (better + 1) / len(vals), col, months


def ceiling(c, months):
    """장세 나이(개월)에 가장 가까운 상위 % 한계 — config 키 m1·m3·m6·m12"""
    m = {int(str(k).lstrip("m")): float(v) for k, v in c["rank_ceiling"].items()}
    return m[min(m, key=lambda x: abs(x - months))]


def price_signals(w, since, c):
    """장세 시작(since) 이후 주봉 → 고점 대비 하락·최대 조정·돌파 거래량·10/40주선·상승/하락 속도"""
    seg = [b for b in w if since is None or b["date"] >= since] or w
    peak, worst, run_peak = 0.0, 0.0, 0.0
    for b in seg:
        run_peak = max(run_peak, b["c"])
        worst = min(worst, b["c"] / run_peak - 1)
    peak = max(b["c"] for b in seg)
    dd_now = seg[-1]["c"] / peak - 1
    # 돌파: 그 주 종가가 장세 안 직전 최고 종가를 넘은 주 — 거래량 ÷ 직전 10주 평균
    brk = []
    for i in range(1, len(seg)):
        prior = max(b["c"] for b in seg[:i])
        if seg[i]["c"] > prior:
            j = w.index(seg[i])
            base = [b["v"] for b in w[max(0, j - 10):j] if b["v"]]
            if base and seg[i]["v"]:
                brk.append(seg[i]["v"] / (sum(base) / len(base)))
    cl = [b["c"] for b in w]
    f, s = sma(cl, c["sell_fast_weeks"]), sma(cl, c["sell_slow_weeks"])
    dead = None
    for i in range(1, len(w)):
        if None not in (f[i], s[i], f[i - 1], s[i - 1]) and f[i - 1] >= s[i - 1] and f[i] < s[i]:
            dead = w[i]["date"]
    below = f[-1] is not None and s[-1] is not None and f[-1] < s[-1]
    # 속도: 장세 저점 → 고점 주당 상승률 vs 고점 → 지금 주당 하락률(리포트: 주도주는 상승이 하락보다 평균 14.5배 빠르다)
    ip = max(range(len(seg)), key=lambda i: seg[i]["c"])
    it = min(range(ip + 1), key=lambda i: seg[i]["c"])
    up_w, dn_w = max(ip - it, 1), max(len(seg) - 1 - ip, 0)
    up_speed = (seg[ip]["c"] / seg[it]["c"]) ** (1 / up_w) - 1 if seg[it]["c"] > 0 else None
    dn_speed = (1 - (seg[-1]["c"] / seg[ip]["c"]) ** (1 / dn_w)) if dn_w else None
    return {"peak": peak, "dd_now": dd_now, "worst_dd": worst, "breakouts": len(brk), "breakout_vol_ok": (sum(1 for x in brk if x > c["breakout_vol_ratio"]) / len(brk)) if brk else None,
            "ma_fast": f[-1], "ma_slow": s[-1], "below": below, "dead_cross": dead if below else None, "peak_date": seg[ip]["date"],
            "up_speed": up_speed, "dn_speed": dn_speed, "speed_ratio": (up_speed / dn_speed) if up_speed and dn_speed and dn_speed > 0 else None,
            "weeks": len(seg)}


def prev_leader(w, index_w, prev):
    """직전 상승 구간 수익률 vs KOSPI(그때 KOSPI 200 스냅숏이 있으면 순위로)"""
    if not prev:
        return None
    a, b = prev
    sw = [x for x in w if a <= x["date"] <= b]
    iw = [x for x in index_w if a <= x["date"] <= b]
    if len(sw) < 4 or len(iw) < 4:
        return {"period": prev, "ret": None, "kospi": None, "rank": None}
    d, univ = universe(b)
    return {"period": prev, "ret": sw[-1]["c"] / sw[0]["c"] - 1, "kospi": iw[-1]["c"] / iw[0]["c"] - 1, "snapshot": d if d and d >= a else None}


def judge(code, entity=None, name=None):
    c = cfg()
    index_w = read_series(STATE / "index.csv")
    w, src = stock_weekly(code, entity)
    out = {"code": code, "name": name or code, "source": src, "lines": [], "stage": "판정 불가", "flags": []}
    if not index_w:
        out["lines"].append("KOSPI 주봉 없음 — --spec의 ① 호출 뒤 --put-index")
        return out
    if len(w) < c["sell_slow_weeks"] + 2:
        out["lines"].append(f"주봉 {len(w)}주 — 40주선에 {c['sell_slow_weeks'] + 2}주 필요(--spec의 ③ 호출 뒤 --put-weekly)")
        return out
    rg = regime(index_w, c["regime"])
    out["regime"] = rg
    since = rg["start"] if rg["up"] else (rg["last_seg"] or (None, None))[0]
    ps = price_signals(w, since, c)
    out["price"] = ps
    ud, univ = universe()
    age_m = (rg["age_weeks"] or 0) / 4.345 if rg["up"] else None
    rk = rank_pct(univ, code, age_m) if (univ and age_m is not None) else (None, None, None)
    if age_m is not None and rk[0] is None:   # 스냅숏에 없으면 한 종목 순위 파일
        col, months = window(age_m)
        rf = rank_file(code, col)
        if rf:
            rk, ud = (rf["pct"], col, months), rf["date"]
    out["rank"] = {"pct": rk[0], "window": rk[1], "months": rk[2], "snapshot": ud}
    pl = prev_leader(w, index_w, rg["prev"])
    out["prev"] = pl
    u = univ.get(code) or {}
    rev_g, op_g = _f(u.get("rev_g")), _f(u.get("op_g"))
    out["earn"] = {"rev_g": rev_g, "op_g": op_g}

    # 단계
    lost = ps["worst_dd"] <= c["max_drawdown"]
    if lost:
        stage = "사(지위 상실 가정)"
    elif ps["below"]:
        stage = "병(10/40주선 하향 교차)"
    elif not rg["up"]:
        stage = "장세 밖(상승 장세 아님)"
    elif rk[0] is None:
        stage = "순위 미확인"
    elif age_m <= c["early_months"] and rk[0] <= c["top_pct"]:
        stage = "생(초기 주도 후보)"
    elif rk[0] <= ceiling(c, rk[2]):
        stage = "로(주도 진행)"
    else:
        stage = "해당 없음(순위 밖)"
    out["stage"] = stage
    if pl and pl.get("ret") is not None and pl.get("kospi") is not None and pl["ret"] > max(2 * pl["kospi"], pl["kospi"] + 0.5) and stage.startswith(("생", "로")):
        out["flags"].append("직전 장세 강세주 — 리포트상 직전 주도주가 다음 장세 주도주가 되는 일은 드물다(SK텔레콤·현대미포조선 같은 빅 사이클 예외)")

    # 문장
    pct = lambda x: "미확인" if x is None else f"{x:+.0%}"
    L = out["lines"]
    age_d = (date.today() - date.fromisoformat(w[-1]["date"])).days
    if age_d > 10:
        out["flags"].append(f"주봉 마지막 {w[-1]['date']}({age_d}일 전, {src}) — --spec ③으로 새로 받는다")
    if rg["up"]:
        L.append(f"장세: KOSPI 상승 장세(10주선 > 40주선) {rg['start']} 시작 · {rg['age_weeks']}주째")
    else:
        L.append(f"장세: KOSPI 상승 장세 아님(10주선 < 40주선, 직전 상승 구간 {rg['last_seg'][0]}~{rg['last_seg'][1]}) — 새 주도주는 재반등 시작부터 모멘텀이 가장 강한 종목에서 찾는다" if rg["last_seg"] else "장세: 상승 구간 없음")
    if rk[0] is not None:
        L.append(f"순위: KOSPI 200 {rk[2]}개월 수익률 상위 {rk[0]:.0%}(스냅숏 {ud}) — 주도주 한계 상위 {ceiling(c, rk[2]):.0%}" + (f", 초기 기준 상위 {c['top_pct']:.0%}" if age_m is not None and age_m <= c["early_months"] else ""))
    elif not rg["up"]:
        L.append("순위: 상승 장세가 아니라 보류 — 재반등이 시작되면 첫 3개월 KOSPI 200 상위 5%를 본다")
    else:
        L.append("순위: KOSPI 200 스냅숏·순위 파일 없음(KOSPI 200 밖이거나 미수집) — 순위 조건 미확인")
    L.append(f"조정: {'장세' if rg['up'] else '직전 장세 시작 이후'} 최대 {ps['worst_dd']:.0%}, 지금 고점({ps['peak_date']}) 대비 {ps['dd_now']:.0%} — 한계 {c['max_drawdown']:.0%}" + (" ✗ 넘었다" if lost else " ✓ 안"))
    if ps["breakouts"]:
        L.append(f"돌파: 직전 고점 돌파 {ps['breakouts']}주 중 거래량이 10주 평균보다 많았던 비율 {ps['breakout_vol_ok']:.0%}" if ps["breakout_vol_ok"] is not None else f"돌파 {ps['breakouts']}주(거래량 자료 없음)")
    L.append(f"이동평균: 10주선 {ps['ma_fast']:,.0f} {'<' if ps['below'] else '>'} 40주선 {ps['ma_slow']:,.0f}" + (f" — {ps['dead_cross']} 하향 교차(지위 상실 가능성)" if ps["dead_cross"] else ""))
    if ps["speed_ratio"]:
        L.append(f"속도: 상승 주당 {ps['up_speed']:.1%} vs 고점 뒤 하락 주당 {ps['dn_speed']:.1%} → {ps['speed_ratio']:.1f}배(주도주 평균 14.5배 — 크면 교차가 고점 가까이에서 난다)")
    L.append(f"실적: 매출 성장 {pct(rev_g / 100 if rev_g is not None else None)}, 영업이익 성장 {pct(op_g / 100 if op_g is not None else None)}(TTM) — 늘기만 하면 된다, 선별 조건은 아니다")
    if pl and pl.get("ret") is not None:
        L.append(f"직전 장세({pl['period'][0]}~{pl['period'][1]}): 종목 {pl['ret']:+.0%} vs KOSPI {pl['kospi']:+.0%}" + ("" if pl.get("snapshot") else " — 그때 KOSPI 200 순위 스냅숏 없음(상위 5% 판정 불가)"))
    return out


def text(j):
    head = f"■ 주도주 생애 단계: {j['stage']}"
    body = "\n".join("- " + x for x in j["lines"] + [f"⚠ {f}" for f in j["flags"]])
    tail = "\n(DB금융투자 「주도주의 생로병사」 2018 메커니즘, KOSPI 200 1992~2018 표본. 가격 판정이며 매수·매도 지시가 아니다. 방법·한계: knowledge/methods/kr_leader_lifecycle.md)"
    return f"{head}\n{body}{tail}"


def resolve(arg):
    """회사 id 또는 KRX 코드 → (코드, 회사 id, 이름)"""
    tv = ROOT / "config" / "tradingview_symbols.csv"
    rows = list(csv.DictReader(tv.open(encoding="utf-8", newline=""))) if tv.exists() else []
    a = arg.replace("KRX:", "")
    for r in rows:
        if r.get("exchange") == "KRX" and (r.get("entity_id") == arg or r.get("ticker") == a):
            return r["ticker"], r.get("entity_id") or None, r.get("name") or a
    p = COMPANIES / arg / "datapack.json"
    if p.exists():
        d = json.loads(p.read_text(encoding="utf-8"))
        return str(d.get("ticker") or ""), arg, d.get("name") or arg
    return a, None, a


def spec(codes):
    s = [{"note": "순위는 ②(KOSPI 200 스냅숏, 큰 응답) 또는 종목별 ④·⑤(작은 호출 2개) 중 하나"},
         {"tool": "mcp-tv-get-ohlcv", "args": {"symbol": cfg()["regime"]["index"], "interval": "1W", "count": 400, "format": "columns"}, "then": "--put-index"},
         {"tool": "mcp-tv-run-screener", "args": {"market": "korea", "symbolset": [cfg()["universe"]], "columns": UCOLS, "limit": 250, "sort_by": "Perf.3M"}, "then": "--put-universe"}]
    for c in codes:
        sym = c if ":" in c else f"KRX:{c}"
        s.append({"tool": "mcp-tv-get-ohlcv", "args": {"symbol": sym, "interval": "1W", "count": 260, "format": "columns"}, "then": f"--put-weekly <파일> {c}"})
        s.append({"tool": "mcp-tv-get-symbol-data", "args": {"symbol": sym, "columns": ["Perf.1M", "Perf.3M", "Perf.6M", "Perf.Y"]}, "then": "장세 나이에 맞는 창의 값 X"})
        s.append({"tool": "mcp-tv-run-screener", "args": {"market": "korea", "symbolset": [cfg()["universe"]], "filters": {"Perf.3M": ["X", None]}, "columns": ["name"], "limit": 1},
                  "then": f"totalCount(X 이상 수)로 --put-rank {c.replace('KRX:', '')} perf_3m <totalCount> 201 — 창이 다르면 Perf.1M/6M/Y·perf_1m/6m/y"})
    return s


def scan():
    ud, univ = universe()
    if not univ:
        raise SystemExit("KOSPI 200 스냅숏 없음 — --spec ② 뒤 --put-universe")
    c = cfg()
    rows = []
    for code, r in univ.items():
        if not (STATE / f"w_{code}.csv").exists():
            continue
        j = judge(code, None, r.get("name"))
        rows.append(j)
    day = datetime.now(KST).date().isoformat()
    OUTD.mkdir(parents=True, exist_ok=True)
    md = [f"# 국장 주도주 생애 단계 — {day} (KOSPI 200 스냅숏 {ud}, 주봉 있는 {len(rows)}종목)", ""]
    for j in sorted(rows, key=lambda x: (x.get("rank") or {}).get("pct") or 1):
        md += [f"## {j['name']} ({j['code']})", text(j), ""]
    (OUTD / f"kr_leader_{day}.md").write_text("\n".join(md), encoding="utf-8")
    return len(rows), day


def main(a):
    sys.stdout.reconfigure(encoding="utf-8")
    if a[:1] == ["--spec"]:
        print(json.dumps(spec(a[1:]), ensure_ascii=False, indent=1))
    elif a[:1] == ["--put-index"]:
        rows = bars_from(json.loads(Path(a[1]).read_text(encoding="utf-8")))
        write_series(STATE / "index.csv", rows)
        print(f"[주도주] KOSPI 주봉 {len(rows)}주 ({rows[0]['date']}~{rows[-1]['date']})")
    elif a[:1] == ["--put-universe"]:
        n, day = put_universe(a[1], a[2] if len(a) > 2 else None)
        print(f"[주도주] KOSPI 200 스냅숏 {n}종목 → universe_{day}.csv")
    elif a[:1] == ["--put-weekly"]:
        code = a[2].replace("KRX:", "")
        rows = bars_from(json.loads(Path(a[1]).read_text(encoding="utf-8")))
        write_series(STATE / f"w_{code}.csv", rows)
        print(f"[주도주] {code} 주봉 {len(rows)}주")
    elif a[:1] == ["--put-rank"]:
        print(put_rank(a[1].replace("KRX:", ""), a[2], a[3], a[4]))
    elif a[:1] == ["--about"]:
        code, ent, name = resolve(a[1])
        print(text(judge(code, ent, name)))
    elif a[:1] == ["--scan"]:
        n, day = scan()
        print(f"[주도주] {n}종목 판정 → outputs/discovery/kr_leader_{day}.md")
    else:
        print(__doc__)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
