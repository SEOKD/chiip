"""알파 v2 — 정량 사전 Q + 판단 덧씌우기 J + 확률 해석 (ADR-016 §2, config/alpha_v2.yaml)

흐름(월스트리트 퀀터멘털 관행 — Grinold & Kahn 2000; Qian, Hua & Sorensen 2007):
 1. 종목마다 요인 원값을 데이터 묶음·일봉·FINRA·커뮤니티·v2 밸류 엔진에서 계산
 2. 단면 순위 → z(윈저화) — 단면은 치입 유니버스(데이터 묶음이 있는 종목)라 시장 전체 분위가 아니다 → 블록 z(부호 가중 평균을 다시 순위 z로)
 3. 블록 가중 = IC 사전값을 1/N 쪽으로 반 축소, 신호 나이에 따라 2^(−나이/반감기)로 감쇠 → Q = Σwz/√Σw²
 4. 판단 J(근거 URL 있는 모델 판단, (점수−5)/2.5) → z = Q + clip(λ·(J − Q), ±1), λ = 0.5. |J − Q| > 1.5면 '판단 충돌'
 5. 알파 v2 = 10·Φ(z) · 기대 초과수익 E[α] = σ·IC·z · P(1년 초과) = 보정 곡선(없으면 Φ(IC·z/√(1−IC²)))
전환 전 2주는 병행 기록만(shadow) — 게이트는 v1(scripts/alpha/score.py)이 그대로 쓴다.
사용: py scripts/alpha/v2.py --run | --show | --compare
"""
import argparse
import csv
import json
import math
import sys
from datetime import date, datetime
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "alpha"))
import score as v1  # noqa: E402

COS = ROOT / "knowledge" / "models" / "companies"
FUND = ROOT / "knowledge" / "models" / "fundamentals" / "us"
V2VAL = ROOT / "knowledge" / "models" / "valuation" / "v2"
SOCIAL = ROOT / "knowledge" / "models" / "social" / "latest.json"
OUT = ROOT / "knowledge" / "models" / "alpha" / "v2_latest.json"
SHADOW = ROOT / "knowledge" / "models" / "alpha" / "v2_shadow.csv"
CALIB = ROOT / "knowledge" / "models" / "alpha" / "calibration.json"
SCOLS = ["date", "id", "v1", "v2", "z", "Q", "J", "conflict", "blocks"]


def cfg():
    return yaml.safe_load((ROOT / "config" / "alpha_v2.yaml").read_text(encoding="utf-8"))


def norm_cdf(x):
    return 0.5 * (1 + math.erf(x / math.sqrt(2)))


def norm_ppf(p):
    """Acklam 근사(오차 1e-9 수준)"""
    a = [-3.969683028665376e+01, 2.209460984245205e+02, -2.759285104469687e+02, 1.383577518672690e+02, -3.066479806614716e+01, 2.506628277459239e+00]
    b = [-5.447609879822406e+01, 1.615858368580409e+02, -1.556989798598866e+02, 6.680131188771972e+01, -1.328068155288572e+01]
    c = [-7.784894002430293e-03, -3.223964580411365e-01, -2.400758277161838e+00, -2.549732539343734e+00, 4.374664141464968e+00, 2.938163982698783e+00]
    d = [7.784695709041462e-03, 3.224671290700398e-01, 2.445134137142996e+00, 3.754408661907416e+00]
    lo = 0.02425
    if p < lo:
        q = math.sqrt(-2 * math.log(p))
        return (((((c[0] * q + c[1]) * q + c[2]) * q + c[3]) * q + c[4]) * q + c[5]) / ((((d[0] * q + d[1]) * q + d[2]) * q + d[3]) * q + 1)
    if p > 1 - lo:
        return -norm_ppf(1 - p)
    q = p - 0.5
    r = q * q
    return (((((a[0] * r + a[1]) * r + a[2]) * r + a[3]) * r + a[4]) * r + a[5]) * q / (((((b[0] * r + b[1]) * r + b[2]) * r + b[3]) * r + b[4]) * r + 1)


def rank_z(values, clip=2.33):
    """{id: x} → {id: z} 평균 순위 → 정규 분위(동점은 평균 순위)"""
    items = sorted((v, k) for k, v in values.items() if v is not None and math.isfinite(v))
    n = len(items)
    out, i = {}, 0
    while i < n:
        j = i
        while j + 1 < n and items[j + 1][0] == items[i][0]:
            j += 1
        r = (i + j) / 2 + 1
        z = max(-clip, min(clip, norm_ppf((r - 0.5) / n)))
        for k in range(i, j + 1):
            out[items[k][1]] = z
        i = j + 1
    return out


def _age(day, today):
    try:
        return max(0, (today - date.fromisoformat(str(day)[:10])).days)
    except ValueError:
        return None


def _ohlcv(eid):
    p = COS / eid / "ohlcv.csv"
    if not p.exists():
        return []
    with p.open(encoding="utf-8") as fh:
        rows = [ln for ln in fh if not ln.startswith("#")]
    out = []
    for r in csv.DictReader(rows):
        try:
            out.append((r["date"], float(r["c"])))
        except (KeyError, TypeError, ValueError):
            continue
    return sorted(out)


def price_factors(eid):
    px = _ohlcv(eid)
    if len(px) < 130:
        return {}, None, None
    c = [x for _, x in px]
    out = {"mom_6m": c[-1] / c[-126] - 1}
    yr = c[-252:]
    hi, lo = max(yr), min(yr)
    out["price_range"] = (c[-1] - lo) / (hi - lo) if hi > lo else None
    if len(c) >= 252:
        out["mom_12_1"] = c[-21] / c[-252] - 1
    rets = [math.log(b / a) for a, b in zip(c[-253:-1], c[-252:]) if a > 0 and b > 0]
    vol = (sum((r - sum(rets) / len(rets)) ** 2 for r in rets) / (len(rets) - 1)) ** 0.5 * math.sqrt(252) if len(rets) > 20 else None
    return out, px[-1][0], vol


def investment_factors(ticker):
    """SEC 10-K: 자산 증가율, (자산 증가율 > EBITDA 증가율) 더미 — Yartseva(2025) Inv"""
    p = FUND / f"{ticker}.csv"
    if not ticker or not p.exists():
        return {}
    d = {}
    with p.open(encoding="utf-8", newline="") as fh:
        for r in csv.DictReader(fh):
            if r["fp"] != "FY" or not r["form"].startswith("10-K"):
                continue
            y = int(r["end"][:4])
            if r["metric"] == "total_assets":
                d.setdefault(y, {})["assets"] = float(r["value"])
            elif r["metric"] in ("operating_income", "da"):
                s, e = date.fromisoformat(r["start"]), date.fromisoformat(r["end"])
                if (e - s).days >= 340:
                    d.setdefault(y, {})[r["metric"]] = float(r["value"])
    ys = sorted(y for y, v in d.items() if {"assets", "operating_income", "da"} <= set(v))
    if len(ys) < 2:
        return {}
    a, b = d[ys[-2]], d[ys[-1]]
    ag = b["assets"] / a["assets"] - 1 if a["assets"] > 0 else None
    e0, e1 = a["operating_income"] + a["da"], b["operating_income"] + b["da"]
    eg = (e1 / e0 - 1) if e0 > 0 else None
    out = {"asset_growth": ag}
    if ag is not None and eg is not None:
        out["inv_dummy"] = 1.0 if ag > eg else 0.0
    return out


def _revision(c):
    r = (c or {}).get("revisions_90d")
    if isinstance(r, (int, float)):
        return float(r)
    if isinstance(r, dict):
        xs = [float(v) for v in r.values() if isinstance(v, (int, float))]
        return sum(xs) / len(xs) if xs else None
    return None


def _short(eid):
    p = COS / eid / "finra.json"
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None, None
    days = sorted((d.get("daily") or {}).items())[-20:]
    trf = sum(v.get("trf") or 0 for _, v in days)
    return (sum(v.get("short") or 0 for _, v in days) / trf if trf else None), d.get("retrieved")


def raw_factors(eid, dp, social, today):
    """{factor: 값}, {block: 나이(일)}, 연 변동성"""
    f, rw = dp.get("financials") or {}, dp.get("raw") or {}
    fp = rw.get("fiscal_profile") or {}
    bal = next((v for k, v in sorted(rw.items()) if k.startswith("balance") and isinstance(v, dict)), {})
    tax = dp.get("tax") or 0.21
    mcap, ebit = fp.get("market_cap"), f.get("ebit_ttm")
    x, ages = {}, {}
    if mcap and mcap > 0:
        ev = mcap + (fp.get("total_debt") or 0) - (fp.get("total_cash") or 0)
        if ebit is not None:
            nopat = ebit * (1 - tax)
            if f.get("capex_ttm") is not None and f.get("da_ttm") is not None:
                x["fcf_yield"] = (nopat + f["da_ttm"] - f["capex_ttm"]) / mcap
            if ev > 0:
                x["ebit_ev"] = ebit / ev
            if f.get("invested_capital"):
                x["roic"] = nopat / f["invested_capital"] if f["invested_capital"] > 0 else None
        if bal.get("equity") is not None:
            x["book_to_market"] = bal["equity"] / mcap
        x["log_mcap"] = math.log(mcap * float(dp.get("unit_usd") or 1e9))
    if (dp.get("consensus") or {}).get("n_analysts") is not None:
        x["n_analysts"] = float(dp["consensus"]["n_analysts"])
    rv = _revision(dp.get("consensus"))
    if rv is not None:
        x["rev_revision"] = rv
    a = _age(dp.get("as_of", ""), today)
    for b in ("value", "quality", "investment", "revision", "discovery"):
        ages[b] = a
    x.update(investment_factors(str(dp.get("ticker") or "")))
    pf, last, vol = price_factors(eid)
    x.update(pf)
    ages["price"] = _age(last, today) if last else None
    sr, sday = _short(eid)
    if sr is not None:
        x["short_ratio"], ages["risk"] = sr, _age(sday, today)
    srow = (social.get("rows") or {}).get(eid) or {}
    if srow.get("Z") is not None:
        x["social_z"], ages["attention"] = srow["Z"], _age(social.get("as_of", ""), today)
    try:
        v = json.loads((V2VAL / f"{eid}.json").read_text(encoding="utf-8"))
        up = v.get("upside") or {}
        p2 = (up.get("p_h") or {}).get("2") if isinstance(up.get("p_h"), dict) else None
        p2 = p2 if p2 is not None else (up.get("p_h") or {}).get(2)
        if p2 is not None:
            x["p_double"] = float(p2)
        bp, ip = (up.get("base_pct") or [None])[0], (up.get("implied_pct") or [None])[0]
        if bp is not None and ip is not None:
            x["base_vs_implied"] = float(bp) - float(ip)
        ages["engine"] = _age(v.get("as_of", ""), today)
    except (OSError, ValueError):
        pass
    return {k: v for k, v in x.items() if v is not None}, ages, vol


def judgment_z(comps, c, today):
    """근거 URL이 있는 판단 요소의 (점수 − 5)/scale 가중 평균(반감기 감쇠). 없으면 None"""
    j = c["judgment"]
    num = den = 0.0
    for k in j["components"]:
        v = (comps or {}).get(k)
        if not v or (j.get("require_url") and "http" not in (v.get("evidence") or "")):
            continue
        try:
            age = (today - datetime.strptime(v["day"][:8], "%Y%m%d").date()).days
        except ValueError:
            continue
        w = 2 ** (-max(0, age) / j["half_life"])
        num += w * (v["score"] - 5) / j["scale"]
        den += w
    return num / den if den else None


def compute(today=None, c=None, data=None):
    """data(시험용): {id: (factors, ages, vol)} 를 주면 파일을 읽지 않는다"""
    c = c or cfg()
    today = today or date.today()
    if data is None:
        try:
            social = json.loads(SOCIAL.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            social = {}
        data = {}
        for p in sorted(COS.glob("*/datapack.json")):
            try:
                dp = json.loads(p.read_text(encoding="utf-8"))
            except ValueError:
                continue
            data[p.parent.name] = raw_factors(p.parent.name, dp, social, today)
        judg = v1.load_judgments()
    else:
        judg = {}
    blocks = c["blocks"]
    fz = {}
    for b in blocks.values():
        for fac in b["factors"]:
            fz[fac] = rank_z({k: v[0].get(fac) for k, v in data.items()}, c["winsor_z"])
    braw = {}
    for name, b in blocks.items():
        vals = {}
        for k in data:
            num = den = 0.0
            for fac, s in b["factors"].items():
                if k in fz[fac]:
                    num += s * fz[fac][k]
                    den += abs(s)
            if den:
                vals[k] = num / den
        braw[name] = rank_z(vals, c["winsor_z"]) if len(vals) >= 3 else {}
    ics = {n: b["ic"] for n, b in blocks.items()}
    tot, N, sh = sum(ics.values()), len(ics), c["shrink_to_equal"]
    w0 = {n: (1 - sh) * ics[n] / tot + sh / N for n in ics}
    rows = {}
    for k, (fac, ages, vol) in data.items():
        have = {n: braw[n][k] for n in blocks if k in braw[n]}
        if len(have) < c["min_blocks"]:
            rows[k] = {"v2": None, "blocks": have, "why": f"정량 블록 {len(have)}개 < {c['min_blocks']}"}
            continue
        w = {n: w0[n] * 2 ** (-(ages.get(n) or 0) / blocks[n]["half_life"]) for n in have}
        Q = sum(w[n] * have[n] for n in have) / math.sqrt(sum(x * x for x in w.values()))
        J = judgment_z(judg.get(k), c, today)
        z, conflict = Q, False
        if J is not None:
            z = Q + max(-c["judgment"]["clip"], min(c["judgment"]["clip"], c["judgment"].get("weight", 0.5) * (J - Q)))
            conflict = abs(J - Q) > c["judgment"]["conflict"]
        ic = c["grinold"]["ic"]
        rows[k] = {"v2": round(10 * norm_cdf(z), 2), "z": round(z, 3), "Q": round(Q, 3), "J": None if J is None else round(J, 3), "conflict": conflict,
                   "blocks": {n: round(v, 2) for n, v in have.items()}, "factors": {f_: round(v, 4) for f_, v in fac.items()},
                   "e_alpha": None if vol is None else round(vol * ic * z, 4), "vol": None if vol is None else round(vol, 3),
                   "p_beat_1y": round(p_beat(z, ic), 3), "p_double_5y": fac.get("p_double")}
    return rows


def p_beat(z, ic):
    """보정 곡선(calibration.json, Platt a·b)이 있으면 그것, 없으면 이변량 정규 사전 Φ(IC·z/√(1−IC²))"""
    try:
        cal = json.loads(CALIB.read_text(encoding="utf-8"))
        if cal.get("method") == "platt":
            return 1 / (1 + math.exp(-(cal["a"] + cal["b"] * z)))
    except (OSError, ValueError, KeyError):
        pass
    return norm_cdf(ic * z / math.sqrt(1 - ic * ic))


def run(today=None):
    today = today or date.today()
    c = cfg()
    rows = compute(today, c)
    _, v1rows = v1.load_latest(today)
    nm = v1.names()
    for k, r in rows.items():
        r["v1"] = (v1rows.get(k) or {}).get("total")
        r["name"] = nm.get(k, k)
    out = {"as_of": today.isoformat(), "shadow": c.get("shadow", True), "rows": rows}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    old = []
    if SHADOW.exists():
        with SHADOW.open(encoding="utf-8", newline="") as fh:
            old = [r for r in csv.DictReader(fh) if r["date"] != today.isoformat()]
    with SHADOW.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=SCOLS)
        w.writeheader()
        w.writerows(old)
        for k, r in sorted(rows.items()):
            if r.get("v2") is None:
                continue
            w.writerow({"date": today.isoformat(), "id": k, "v1": r.get("v1"), "v2": r["v2"], "z": r["z"], "Q": r["Q"], "J": r["J"], "conflict": int(r["conflict"]),
                        "blocks": json.dumps(r["blocks"], ensure_ascii=False)})
    return out


def spearman(xs, ys):
    rx, ry = rank_z(dict(enumerate(xs)), 9), rank_z(dict(enumerate(ys)), 9)
    a, b = [rx[i] for i in range(len(xs))], [ry[i] for i in range(len(ys))]
    ma, mb = sum(a) / len(a), sum(b) / len(b)
    cov = sum((x - ma) * (y - mb) for x, y in zip(a, b))
    return cov / math.sqrt(sum((x - ma) ** 2 for x in a) * sum((y - mb) ** 2 for y in b))


def compare():
    d = json.loads(OUT.read_text(encoding="utf-8"))
    both = [(k, r) for k, r in d["rows"].items() if r.get("v2") is not None and r.get("v1") is not None]
    print(f"[알파 v1 vs v2] {d['as_of']} — 둘 다 있는 종목 {len(both)}개")
    if len(both) >= 5:
        print(f"- 순위 상관(스피어먼 근사) {spearman([r['v1'] for _, r in both], [r['v2'] for _, r in both]):+.2f}")
    for k, r in sorted(both, key=lambda kv: -abs(kv[1]["v2"] - kv[1]["v1"]))[:10]:
        print(f"- {r['name']}: v1 {r['v1']:.1f} → v2 {r['v2']:.1f} (Q {r['Q']:+.2f}, J {r['J'] if r['J'] is not None else '—'}){' ⚠ 판단 충돌' if r['conflict'] else ''}")


def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", action="store_true")
    ap.add_argument("--show", action="store_true")
    ap.add_argument("--compare", action="store_true")
    a = ap.parse_args(argv)
    if a.compare:
        compare()
        return 0
    d = run() if a.run else json.loads(OUT.read_text(encoding="utf-8"))
    rows = sorted(d["rows"].items(), key=lambda kv: -(kv[1].get("v2") or -1))
    print(f"[알파 v2{' 병행 기록' if d.get('shadow') else ''}] {d['as_of']} — 산정 {sum(1 for _, r in rows if r.get('v2') is not None)}/{len(rows)}종목")
    for k, r in rows:
        if r.get("v2") is None:
            continue
        ea = f" · E[α] {r['e_alpha']:+.1%}" if r.get("e_alpha") is not None else ""
        print(f"- {r.get('name', k)} {r['v2']:.1f} (z {r['z']:+.2f} = Q {r['Q']:+.2f}" + (f", J {r['J']:+.2f}" if r["J"] is not None else "") + f"){ea} · P(1년 초과) {r['p_beat_1y']:.0%}"
              + (" ⚠ 판단 충돌" if r["conflict"] else ""))
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(main(sys.argv[1:]))
