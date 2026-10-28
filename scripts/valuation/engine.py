"""밸류에이션 계산 엔진 (L1~L5) — docs/valuation/framework.md §3·§5·§6. 모델을 부르지 않는다.

입력: knowledge/models/valuation/snapshots/(최신) · prices/ · scenarios.csv(모델 작성)
      knowledge/narratives/registry.yaml · radar/inbox/(레이더 수집 항목) · config/valuation.yaml
출력: knowledge/models/valuation/latest.csv · latest.json · history/YYYYMMDD.csv

사용: py scripts/valuation/engine.py                    (계산)
      py scripts/valuation/engine.py --digest morning    (아침 브리프용 요약 — evening: 저녁, 한국 종목 먼저)
      py scripts/valuation/engine.py --card co-skhynix   (종목 카드용 전체 수치)
"""
import csv
import json
import math
import re
import statistics
import sys
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "radar"))
from pollers import common  # noqa: E402

VAL = ROOT / "knowledge" / "models" / "valuation"
SNAP_DIR, PRICE_DIR, HIST_DIR = VAL / "snapshots", VAL / "prices", VAL / "history"
SCEN = VAL / "scenarios.csv"
REGISTRY = "knowledge/narratives/registry.yaml"
INBOX = ROOT / "radar" / "inbox"
DISCLAIMER = "공개 자료 기반 분석이며 투자 권유가 아님"
OUT_COLS = ["id", "name", "code", "region", "sub", "price", "price_date", "currency",
            "eps_ntm", "pe_ntm", "pe_ttm", "pb", "ev_ebitda", "ev_sales", "peg", "ev_sales_growth_adj",
            "growth_fy1", "rev_growth_fy1", "rev_ntm_7", "rev_ntm_30", "rev_ntm_90", "rev_fy1_30", "rev_fy1_90",
            "breadth7", "breadth30", "dispersion", "surprise_avg4", "beat_rate4", "beat_drop4",
            "op_margin", "roe", "gross_margin",
            "ret30", "ret90", "ret365", "eps_chg30", "eps_chg90", "pe_chg90", "rerating_share90",
            "peer_premium", "pe_hist_pct", "justified_pe", "residual_premium", "residual_z",
            "price_vs_revision_z", "implied_growth", "implied_growth_gap", "target_gap",
            "scn_bear", "scn_base", "scn_bull", "scn_expected", "implied_bull_prob", "skew",
            "narrative_heat", "top_narratives", "revision_score", "priced_in", "priced_in_n", "priced_in_parts",
            "flags"]


def _f(x):
    try:
        v = float(x)
        return v if math.isfinite(v) else None
    except (TypeError, ValueError):
        return None


def _clip(x, lo, hi):
    return max(lo, min(hi, x))


def _r(x, nd=4):
    return round(x, nd) if isinstance(x, float) else x


# ---------- 입력 ----------
def latest_snapshot():
    files = sorted(SNAP_DIR.glob("*.csv")) if SNAP_DIR.exists() else []
    if not files:
        return None, []
    with files[-1].open(encoding="utf-8") as f:
        return files[-1].stem, list(csv.DictReader(f))


def load_prices(code):
    p = PRICE_DIR / f"{code}.csv"
    if not code or not p.exists():
        return []
    with p.open(encoding="utf-8") as f:
        return [(r["date"], float(r["close"])) for r in csv.DictReader(f) if _f(r.get("close"))]


def price_on_or_before(prices, day):
    c = [p for d, p in prices if d <= day]
    return c[-1] if c else None


def load_scenarios():
    if not SCEN.exists():
        return {}
    with SCEN.open(encoding="utf-8") as f:
        rows = [r for r in csv.DictReader(f) if r.get("id") and r.get("scenario")]
    out = {}
    for r in rows:
        cur = out.setdefault(r["id"], {})
        old = cur.get(r["scenario"])
        if not old or r.get("as_of", "") >= old.get("as_of", ""):
            cur[r["scenario"]] = r
    return out


def scenario_value(r):
    v, m = _f(r.get("value")), _f(r.get("multiple"))
    metric = (r.get("metric") or "").upper()
    if metric == "PRICE":
        return v
    return v * m if v is not None and m is not None else None


def history_pe(eid, before):
    vals = []
    for p in sorted(HIST_DIR.glob("*.csv")) if HIST_DIR.exists() else []:
        if p.stem >= before:
            continue
        with p.open(encoding="utf-8") as f:
            for r in csv.DictReader(f):
                if r["id"] == eid and _f(r.get("pe_ntm")):
                    vals.append(float(r["pe_ntm"]))
    return vals


# ---------- L1·L2 종목별 ----------
def ntm(row, asof, suffix=""):
    e0, e1 = _f(row.get(f"eps_fy0{suffix}")), _f(row.get(f"eps_fy1{suffix}"))
    if e1 is None:
        return e0
    if e0 is None:
        return e1
    try:
        left = (date.fromisoformat(row["fy0_end"][:10]) - date.fromisoformat(asof)).days
    except (KeyError, TypeError, ValueError):
        return e1
    w = _clip(left / 365, 0, 1)
    return w * e0 + (1 - w) * e1


def pct_change(new, old):
    if new is None or old is None or old == 0:
        return None
    return new / old - 1 if old > 0 and new > 0 else (new - old) / abs(old)


def log_ratio(new, old):
    return math.log(new / old) if new and old and new > 0 and old > 0 else None


def per_ticker(row, u, cfg, asof):
    sub = cfg["subsectors"].get(u.get("sub"), {})
    m = {"id": u["id"], "name": u.get("name"), "code": u.get("code") or "", "region": u.get("region"),
         "sub": u.get("sub"), "currency": row.get("currency"), "flags": []}
    prices = load_prices(u.get("code"))
    price = _f(row.get("price")) or (prices[-1][1] if prices else None)
    m["price"], m["price_date"] = price, row.get("price_date") or (prices[-1][0] if prices else None)
    e = ntm(row, asof)
    m["eps_ntm"] = e
    m["pe_ntm"] = price / e if price and e and e > 0 else None
    for k in ("pe_ttm", "pb", "ev_ebitda", "ev_sales", "op_margin", "roe", "gross_margin",
              "surprise_avg4", "beat_rate4", "beat_drop4"):
        m[k] = _f(row.get(k))
    e0, e1 = _f(row.get("eps_fy0")), _f(row.get("eps_fy1"))
    m["growth_fy1"] = e1 / e0 - 1 if e0 and e1 is not None and e0 > 0 else None
    r0, r1 = _f(row.get("rev_fy0")), _f(row.get("rev_fy1"))
    m["rev_growth_fy1"] = r1 / r0 - 1 if r0 and r1 is not None and r0 > 0 else None
    for d in (7, 30, 90):
        m[f"rev_ntm_{d}"] = pct_change(e, ntm(row, asof, f"_{d}d"))
    for d in (30, 90):
        m[f"rev_fy1_{d}"] = pct_change(e1, _f(row.get(f"eps_fy1_{d}d")))
    for d in (7, 30):
        up, dn = _f(row.get(f"up{d}")) or 0, _f(row.get(f"down{d}")) or 0
        m[f"breadth{d}"] = (up - dn) / (up + dn) if up + dn else None
    lo, hi = _f(row.get("eps_fy1_lo")), _f(row.get("eps_fy1_hi"))
    m["dispersion"] = (hi - lo) / abs(e1) if lo is not None and hi is not None and e1 else None
    g = m["growth_fy1"]
    m["peg"] = m["pe_ntm"] / (g * 100) if m["pe_ntm"] and g and g > 0 else None
    rg = m["rev_growth_fy1"]
    m["ev_sales_growth_adj"] = m["ev_sales"] / (rg * 100) if m["ev_sales"] and rg and rg > 0 else None
    # 수익률 분해 (주가 변화 = EPS 전망 변화 + P/E 변화)
    today = m["price_date"] or asof
    for d in (30, 90, 365):
        old = price_on_or_before(prices, (date.fromisoformat(today[:10]) - timedelta(days=d)).isoformat()) if prices else None
        m[f"ret{d}"] = log_ratio(price, old)
    m["eps_chg30"] = log_ratio(e, ntm(row, asof, "_30d"))
    m["eps_chg90"] = log_ratio(e, ntm(row, asof, "_90d"))
    m["pe_chg90"] = m["ret90"] - m["eps_chg90"] if m["ret90"] is not None and m["eps_chg90"] is not None else None
    m["rerating_share90"] = (m["pe_chg90"] / m["ret90"]
                             if m["pe_chg90"] is not None and m["ret90"] and abs(m["ret90"]) > 0.02 else None)
    # 역DCF: P = EPS_NTM·(1+g)^(N−1)·장기PE / (1+r)^N → g
    r = cfg["params"]["discount_rate"].get(u.get("region"), 0.09)
    n_y, tpe = cfg["params"]["horizon_years"], sub.get("terminal_pe", 18)
    if price and e and e > 0:
        m["implied_growth"] = (price * (1 + r) ** n_y / (e * tpe)) ** (1 / (n_y - 1)) - 1
        if sub.get("cyclical"):
            m["flags"].append("사이클 업종: NTM EPS가 고점·저점이면 내포 성장 왜곡")
    else:
        m["implied_growth"] = None
    m["implied_growth_gap"] = (m["implied_growth"] - g if m["implied_growth"] is not None and g is not None else None)
    tp = _f(row.get("target_price"))
    m["target_gap"] = tp / price - 1 if tp and price else None
    if u.get("region") != "US" and (u.get("code") or "").endswith(".US"):
        m["flags"].append("미국 상장 ADR: 가격·추정치 통화 불일치 가능")
    if "manual" in (row.get("source") or ""):
        m["flags"].append("추정치 수동 입력")
    return m


# ---------- 횡단면 ----------
def pct_rank(values):
    """{id: v} → {id: 0~100 백분위}"""
    items = sorted((v, k) for k, v in values.items() if v is not None)
    n = len(items)
    if n < 2:
        return {k: 50.0 for _, k in items}
    return {k: 100.0 * i / (n - 1) for i, (_, k) in enumerate(items)}


def zscores(values):
    vals = [v for v in values.values() if v is not None]
    if len(vals) < 3:
        return {}
    mu, sd = statistics.mean(vals), statistics.pstdev(vals)
    return {k: (v - mu) / sd for k, v in values.items() if v is not None and sd > 0}


def ols(X, y, ridge=1e-3):
    """정규방정식 + 아주 작은 릿지(절편 제외). 가우스 소거 — numpy 없이"""
    k = len(X[0])
    A = [[sum(X[i][a] * X[i][b] for i in range(len(X))) + (ridge if a == b and a > 0 else 0) for b in range(k)]
         for a in range(k)]
    v = [sum(X[i][a] * y[i] for i in range(len(X))) for a in range(k)]
    for c in range(k):
        p = max(range(c, k), key=lambda r: abs(A[r][c]))
        if abs(A[p][c]) < 1e-12:
            return None
        A[c], A[p], v[c], v[p] = A[p], A[c], v[p], v[c]
        for r in range(k):
            if r != c:
                f = A[r][c] / A[c][c]
                A[r] = [A[r][j] - f * A[c][j] for j in range(k)]
                v[r] -= f * v[c]
    return [v[i] / A[i][i] for i in range(k)]


FEATURES = ["const", "growth_fy1", "rev_ntm_90", "op_margin", "is_kr", "is_cyclical"]


def regression(rows, cfg):
    cap, need = cfg["params"]["pe_cap"], cfg["params"]["min_regression_n"]
    margins = [r["op_margin"] for r in rows if r.get("op_margin") is not None]
    med_m = statistics.median(margins) if margins else 0.2
    data = []
    for r in rows:
        pe = r.get("pe_ntm")
        if not pe or not 0 < pe < cap or r.get("growth_fy1") is None:
            continue
        cyc = cfg["subsectors"].get(r["sub"], {}).get("cyclical", False)
        x = [1.0, _clip(r["growth_fy1"], -0.5, 3), _clip(r.get("rev_ntm_90") or 0, -0.5, 1),
             _clip(r["op_margin"] if r.get("op_margin") is not None else med_m, -0.5, 0.8),
             1.0 if r["region"] == "KR" else 0.0, 1.0 if cyc else 0.0]
        data.append((r["id"], x, math.log(pe)))
    if len(data) < max(need, len(FEATURES) + 3):
        return {"n": len(data), "status": f"표본 부족({len(data)}<{need})"}, {}
    beta = ols([x for _, x, _ in data], [y for _, _, y in data])
    if not beta:
        return {"n": len(data), "status": "회귀 불가(공선성)"}, {}
    res = {i: y - sum(b * xi for b, xi in zip(beta, x)) for i, x, y in data}
    sd = statistics.pstdev(res.values()) or None
    fitted = {i: math.exp(y - res[i]) for i, _, y in data}
    out = {i: {"justified_pe": fitted[i], "residual_premium": math.exp(res[i]) - 1,
               "residual_z": res[i] / sd if sd else None} for i in res}
    return {"n": len(data), "status": "ok", "beta": dict(zip(FEATURES, [round(b, 4) for b in beta]))}, out


# ---------- L4 내러티브 ----------
def inbox_items(days, end):
    out = []
    for i in range(days):
        d = (end - timedelta(days=i)).strftime("%Y%m%d")
        folder = INBOX / d
        if not folder.exists():
            continue
        for p in folder.glob("*.json"):
            try:
                it = json.loads(p.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            for x in it if isinstance(it, list) else [it]:
                if isinstance(x, dict):
                    out.append((d, x))
    return out


def narratives(cfg, end=None):
    reg = (common.load_yaml(REGISTRY) or {}).get("narratives", [])
    win = cfg["params"].get("narrative_window_days", 7)
    end = end or common.now_kst().date()
    items = inbox_items(2 * win, end)
    cut = (end - timedelta(days=win - 1)).strftime("%Y%m%d")
    days_prev = {d for d, _ in items if d < cut}
    out = []
    for n in reg:
        try:
            pat = re.compile(n.get("keywords") or r"$^", re.I)
        except re.error:
            pat = re.compile(r"$^")
        cur = prev = 0
        langs, sample = set(), []
        for d, it in items:
            text = f"{it.get('title', '')} {it.get('snippet', '')}"
            if not pat.search(text):
                continue
            if d >= cut:
                cur += 1
                langs.add(it.get("language") or "?")
                if len(sample) < 3:
                    sample.append(it.get("title", "")[:80])
            else:
                prev += 1
        accel = (cur - prev) / max(prev, 1) if len(days_prev) >= win else None
        out.append({"id": n["id"], "story": n.get("story"), "count": cur, "prev": prev, "accel": accel,
                    "langs": sorted(langs), "stage": n.get("stage", "미판정"), "exposure": n.get("exposure") or {},
                    "sample": sample, "baseline_ok": len(days_prev) >= win})
    return out


# ---------- 종합 ----------
def compute(write=True):
    cfg = common.load_yaml("config/valuation.yaml") or {}
    asof = common.now_kst().strftime("%Y-%m-%d")
    snap_name, snap = latest_snapshot()
    by_id = {r["id"]: r for r in snap}
    rows = [per_ticker(by_id.get(u["id"], {}), u, cfg, asof) for u in cfg.get("universe", [])]
    # 피어 프리미엄
    for sub in {r["sub"] for r in rows}:
        pes = [r["pe_ntm"] for r in rows if r["sub"] == sub and r["pe_ntm"] and r["pe_ntm"] < cfg["params"]["pe_cap"]]
        med = statistics.median(pes) if len(pes) >= 2 else None
        for r in rows:
            if r["sub"] == sub:
                r["peer_premium"] = r["pe_ntm"] / med - 1 if med and r["pe_ntm"] else None
    # 자기 역사 백분위
    for r in rows:
        hist = history_pe(r["id"], asof.replace("-", ""))
        r["pe_hist_pct"] = (100.0 * sum(1 for v in hist if v <= r["pe_ntm"]) / len(hist)
                            if r["pe_ntm"] and len(hist) >= cfg["params"]["history_min_days"] else None)
    reg_info, reg = regression(rows, cfg)
    for r in rows:
        r.update(reg.get(r["id"], {"justified_pe": None, "residual_premium": None, "residual_z": None}))
    zp = zscores({r["id"]: r["ret90"] for r in rows if r["eps_chg90"] is not None})
    ze = zscores({r["id"]: r["eps_chg90"] for r in rows if r["ret90"] is not None})
    for r in rows:
        r["price_vs_revision_z"] = zp[r["id"]] - ze[r["id"]] if r["id"] in zp and r["id"] in ze else None
    # 시나리오
    scn = load_scenarios()
    for r in rows:
        s = scn.get(r["id"], {})
        vals = {k: scenario_value(s[k]) for k in ("bear", "base", "bull") if k in s}
        r["scn_bear"], r["scn_base"], r["scn_bull"] = vals.get("bear"), vals.get("base"), vals.get("bull")
        probs = {k: _f(s[k].get("prob")) for k in vals}
        r["scn_expected"] = (sum(vals[k] * probs[k] for k in vals)
                             if vals and all(probs[k] is not None for k in vals) and abs(sum(probs.values()) - 1) < 0.02 else None)
        p, lo, hi = r["price"], r["scn_bear"], r["scn_bull"]
        r["implied_bull_prob"] = _clip((p - lo) / (hi - lo), 0, 1) if p and lo is not None and hi and hi > lo else None
        r["skew"] = (hi - p) / (p - lo) if p and lo is not None and hi and p > lo else None
    # 내러티브 열기
    nars = narratives(cfg)
    for r in rows:
        contrib = [(n["id"], n["exposure"].get(r["id"], 0) * n["count"]) for n in nars if r["id"] in n["exposure"]]
        r["narrative_heat"] = sum(c for _, c in contrib) if contrib else None
        r["top_narratives"] = ";".join(i for i, c in sorted(contrib, key=lambda t: -abs(t[1]))[:3] if c)
    # 리비전 점수·반영도 지수
    pr30, prb = pct_rank({r["id"]: r["rev_ntm_30"] for r in rows}), pct_rank({r["id"]: r["breadth30"] for r in rows})
    for r in rows:
        parts = [v for v in (pr30.get(r["id"]), prb.get(r["id"])) if v is not None]
        r["revision_score"] = sum(parts) / len(parts) if parts else None
    comp = {"pe_vs_peer": pct_rank({r["id"]: r["peer_premium"] for r in rows}),
            "residual_premium": pct_rank({r["id"]: r["residual_premium"] for r in rows}),
            "price_ahead_of_revision": pct_rank({r["id"]: r["price_vs_revision_z"] for r in rows}),
            "implied_growth_gap": pct_rank({r["id"]: r["implied_growth_gap"] for r in rows})}
    w = cfg.get("priced_in_weights", {})
    for r in rows:
        parts = {k: comp[k].get(r["id"]) for k in comp}
        parts["pe_vs_history"] = r["pe_hist_pct"]
        parts["implied_bull_prob"] = r["implied_bull_prob"] * 100 if r["implied_bull_prob"] is not None else None
        parts["beat_and_drop"] = r["beat_drop4"] * 100 if r["beat_drop4"] is not None else None
        got = {k: v for k, v in parts.items() if v is not None and w.get(k, 0) > 0}
        r["priced_in_n"] = len(got)
        r["priced_in"] = (sum(v * w[k] for k, v in got.items()) / sum(w[k] for k in got)) if len(got) >= 3 else None
        r["priced_in_parts"] = ";".join(f"{k}={v:.0f}" for k, v in got.items())
    result = {"as_of": common.iso(common.now_kst()), "snapshot": snap_name, "regression": reg_info,
              "coverage": {"universe": len(rows), "price": sum(1 for r in rows if r["price"]),
                           "estimates": sum(1 for r in rows if r["eps_ntm"] is not None),
                           "priced_in": sum(1 for r in rows if r["priced_in"] is not None)},
              "narratives": nars, "rows": rows}
    if write:
        VAL.mkdir(parents=True, exist_ok=True)
        flat = [{k: (";".join(v) if isinstance(v, list) else _r(v)) for k, v in r.items()} for r in rows]
        for path in (VAL / "latest.csv", HIST_DIR / f"{asof.replace('-', '')}.csv"):
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("w", encoding="utf-8", newline="") as f:
                wr = csv.DictWriter(f, fieldnames=OUT_COLS, extrasaction="ignore", lineterminator="\n")
                wr.writeheader()
                wr.writerows(flat)
        (VAL / "latest.json").write_text(json.dumps(result, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    return len(rows)


# ---------- 출력 ----------
def _pct(x, nd=1):
    return "—" if x is None else f"{x * 100:+.{nd}f}%"


def _num(x, nd=1):
    return "—" if x is None else f"{x:.{nd}f}"


def load_latest():
    p = VAL / "latest.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None


def digest(kind="morning"):
    res = load_latest()
    if not res:
        compute()
        res = load_latest()
    rows, cov = res["rows"], res["coverage"]
    lines = [f"### 밸류에이션 레이더 (계산 {res['as_of'][:16]} · 스냅숏 {res['snapshot'] or '없음'})",
             f"- 데이터: 가격 {cov['price']}/{cov['universe']} · 추정치 {cov['estimates']}/{cov['universe']} · 반영도 산출 {cov['priced_in']}"]
    if not cov["price"]:
        lines.append("- **가격·추정치 미수집** — EODHD 키·펀더멘털 요금제 대기(TODO 21). 아래는 레이더 기반 내러티브 강도만.")
    est = [r for r in rows if r.get("rev_ntm_30") is not None]
    if est:
        up = sorted(est, key=lambda r: -r["rev_ntm_30"])[:5]
        dn = sorted(est, key=lambda r: r["rev_ntm_30"])[:5]
        lines.append("**EPS 리비전(NTM, 30일)** 상향: " + ", ".join(f"{r['name']} {_pct(r['rev_ntm_30'])}" for r in up))
        lines.append("　하향: " + ", ".join(f"{r['name']} {_pct(r['rev_ntm_30'])}" for r in dn))
    gap = [r for r in rows if r.get("price_vs_revision_z") is not None]
    if gap:
        hi = sorted(gap, key=lambda r: -r["price_vs_revision_z"])[:3]
        lo = sorted(gap, key=lambda r: r["price_vs_revision_z"])[:3]
        lines.append("**주가 vs 리비전(90일)** 리비전보다 앞서감: " + ", ".join(
            f"{r['name']}(주가 {_pct(r['ret90'], 0)}·EPS {_pct(r['eps_chg90'], 0)})" for r in hi))
        lines.append("　리비전보다 뒤처짐: " + ", ".join(
            f"{r['name']}(주가 {_pct(r['ret90'], 0)}·EPS {_pct(r['eps_chg90'], 0)})" for r in lo))
    pi = [r for r in rows if r.get("priced_in") is not None]
    if pi:
        hi = sorted(pi, key=lambda r: -r["priced_in"])[:5]
        lo = sorted(pi, key=lambda r: r["priced_in"])[:5]
        lines.append("**반영도 지수(0~100, 기대의 높이 — 방향 예측 아님)** 높음: " + ", ".join(
            f"{r['name']} {r['priced_in']:.0f}" for r in hi) + " / 낮음: " + ", ".join(f"{r['name']} {r['priced_in']:.0f}" for r in lo))
    t0 = [r for r in rows if r["region"] == "KR" and r["id"] in T0_IDS]
    lines.append("")
    lines.append("| T0 | NTM P/E | 피어 대비 | 리비전 30일 | 주가 90일 중 P/E 몫 | 반영도 | 내러티브 |")
    lines.append("|---|---|---|---|---|---|---|")
    for r in t0:
        share = "—" if r.get("rerating_share90") is None else f"{r['rerating_share90'] * 100:.0f}%"
        lines.append(f"| {r['name']} | {_num(r.get('pe_ntm'))} | {_pct(r.get('peer_premium'), 0)} | {_pct(r.get('rev_ntm_30'))} | "
                     f"{share} | {_num(r.get('priced_in'), 0)} | {(r.get('top_narratives') or '—').replace('nar-', '')} |")
    lines.append("")
    nars = sorted(res["narratives"], key=lambda n: -n["count"])
    lines.append("**내러티브 강도(레이더 7일 언급 — 관심의 크기이지 사실의 증거가 아님)**")
    for n in nars[:6]:
        acc = "기준선 부족" if n["accel"] is None else _pct(n["accel"], 0)
        lines.append(f"- {n['id'].replace('nar-', '')}: {n['count']}건 (직전 7일 대비 {acc}, 언어 {'/'.join(n['langs']) or '—'}) · 단계 {n['stage']}")
    lines.append(f"\n_{DISCLAIMER}_")
    return "\n".join(lines)


T0_IDS = {"co-samsung", "co-skhynix", "co-semco", "co-lginnotek", "co-doosan", "co-lotteem", "co-isupetasys"}

LABELS = [("price", "주가"), ("pe_ntm", "NTM P/E"), ("pe_ttm", "TTM P/E"), ("pb", "P/B"), ("ev_ebitda", "EV/EBITDA"),
          ("peg", "PEG"), ("ev_sales_growth_adj", "성장 조정 EV/S"), ("growth_fy1", "EPS 성장 FY1"),
          ("rev_growth_fy1", "매출 성장 FY1"), ("rev_ntm_7", "리비전 7일"), ("rev_ntm_30", "리비전 30일"),
          ("rev_ntm_90", "리비전 90일"), ("breadth30", "리비전 폭 30일"), ("dispersion", "추정치 분산"),
          ("surprise_avg4", "서프라이즈 평균(%)"), ("beat_drop4", "서프라이즈 후 하락 비율"),
          ("ret90", "주가 90일(log)"), ("eps_chg90", "EPS 전망 90일(log)"), ("pe_chg90", "P/E 90일(log)"),
          ("rerating_share90", "재평가 비중"), ("peer_premium", "피어 대비 프리미엄"), ("pe_hist_pct", "자기 역사 백분위"),
          ("justified_pe", "정당 P/E(회귀)"), ("residual_premium", "잔차 프리미엄"), ("price_vs_revision_z", "주가−리비전 z"),
          ("implied_growth", "역DCF 내포 성장"), ("implied_growth_gap", "내포−컨센서스 성장"), ("target_gap", "컨센서스 목표가 괴리"),
          ("scn_bear", "약세 가치"), ("scn_base", "기본 가치"), ("scn_bull", "강세 가치"), ("scn_expected", "기대값"),
          ("implied_bull_prob", "내포 강세 확률"), ("skew", "상방/하방 비대칭"), ("narrative_heat", "내러티브 열기"),
          ("revision_score", "리비전 점수"), ("priced_in", "반영도 지수"), ("priced_in_parts", "반영도 구성")]


def card(eid):
    res = load_latest() or {}
    rows = {r["id"]: r for r in res.get("rows", [])}
    r = rows.get(eid)
    if not r:
        return f"{eid}: 유니버스에 없음(config/valuation.yaml)"
    out = [f"## {r['name']} ({r['code'] or '코드 미확인'}, {r['sub']}) — 계산 {res['as_of'][:16]}", "| 항목 | 값 |", "|---|---|"]
    for k, lab in LABELS:
        v = r.get(k)
        out.append(f"| {lab} | {'미확인' if v is None or v == '' else (round(v, 4) if isinstance(v, float) else v)} |")
    out.append(f"| 주의 | {'; '.join(r.get('flags') or []) or '—'} |")
    peers = [p for p in rows.values() if p["sub"] == r["sub"] and p["id"] != eid]
    out.append("\n피어(같은 하위 섹터): " + ", ".join(
        f"{p['name']} P/E {_num(p.get('pe_ntm'))}·리비전30 {_pct(p.get('rev_ntm_30'))}" for p in peers))
    for n in res.get("narratives", []):
        if eid in n["exposure"]:
            out.append(f"- 내러티브 {n['id']} (노출 {n['exposure'][eid]}): 7일 {n['count']}건, 단계 {n['stage']}")
    out.append(f"\n회귀: {res.get('regression')}")
    return "\n".join(out)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    if "--digest" in sys.argv:
        compute()
        i = sys.argv.index("--digest")
        print(digest(sys.argv[i + 1] if len(sys.argv) > i + 1 else "morning"))
    elif "--card" in sys.argv:
        compute()
        print(card(sys.argv[sys.argv.index("--card") + 1]))
    else:
        print("계산", compute())
