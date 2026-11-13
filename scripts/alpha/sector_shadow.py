"""알파 섹터 보정 그림자 계산 (마스터 지시 2026-11-13 종목 범위 확대 3단계, ADR-028, 설정 config/alpha_sector.yaml)

왜: 알파의 '병목' 요소(20%)가 반도체식 정의(해결 기술 독점도·샘플→인증→양산)라 AI 밖 종목이 구조적으로 낮다(ADR-025 진단 — 지도 밖 평균 2.8 vs AI 5.1).
무엇: 지금 알파(scripts/alpha/score.py, latest.json)는 바꾸지 않는다. 같은 판단으로 두 변형을 나란히 계산해 기록만 한다.
  S1 = 병목 → 구조적 우위(edge_struct). AI 밸류체인·미분류는 병목 그대로, AI 밖은 섹터 판단 틀 카드 edge → 판단 파일 edge_struct → 병목(대체)
  S2 = (1 − blend)·S1 + blend·10·섹터 안 백분위(같은 섹터 min_sector_n개 이상일 때, 아니면 전체 백분위)
기록: knowledge/models/alpha/sector_shadow.json(최신) · sector_shadow.csv(날짜마다 한 번)
채택: --gate — 4주 뒤 20거래일 앞 초과수익(SPY 대비)과의 순위 상관(IC)을 v1·S1·S2로 비교, 앞·뒤 절반 모두에서 S가 v1보다 ic_margin 이상이고
      AI 밖 부분집합에서도 나빠지지 않으면 '채택 제안 가능'. config/alpha.yaml 변경은 구조 변경이라 마스터 승인 뒤에만(Model Lab이 제안서를 쓴다).
시세: 공짜 원천만(유료 시세 금지 — 기억 no-paid-data-for-backtest). --price-request가 필요한 티커·시작일을 내면 모델이 Fiscal.ai company_stock_prices로 받아
      `[["YYYY-MM-DD", 종가], …]` {티커: …} JSON을 --put-prices <파일>로 넣는다(knowledge/models/alpha/shadow_prices.json).
사용: py scripts/alpha/sector_shadow.py [--dry] | --show | --price-request | --put-prices <파일> | --gate
"""
import csv
import json
import math
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
A = ROOT / "knowledge" / "models" / "alpha"
LATEST = A / "latest.json"
OUT = A / "sector_shadow.json"
LOG = A / "sector_shadow.csv"
PRICES = A / "shadow_prices.json"
GATE = A / "sector_shadow_gate.json"
COLS = ["date", "id", "sector", "ai", "v1", "s1", "s2", "sector_pct", "edge_src", "edge"]
sys.path.insert(0, str(ROOT / "scripts" / "alpha"))
sys.path.insert(0, str(ROOT / "scripts" / "sectors"))
sys.path.insert(0, str(ROOT / "scripts" / "discovery"))


def cfg():
    return yaml.safe_load((ROOT / "config" / "alpha_sector.yaml").read_text(encoding="utf-8"))


def _j(p, default=None):
    try:
        return json.loads(Path(p).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {} if default is None else default


def judged_edge():
    """{id: edge_struct 점수} — 알파 판단 파일에 모델이 적은 edge_struct 요소(가장 최근 날짜)"""
    import score as v1
    out = {}
    for cid, comps in v1.load_judgments().items():
        if "edge_struct" in comps:
            out[cid] = float(comps["edge_struct"]["score"])
    return out


def edge_for(cid, sector, comps, cards, judged, is_ai, order):
    """(구조적 우위 점수, 원천) — AI 밸류체인·미분류는 병목 그대로"""
    b = comps.get("bottleneck")
    if sector is None or is_ai(sector):
        return b, "bottleneck"
    for src in order:
        if src == "card" and cid in cards:
            return cards[cid], "card"
        if src == "judgment" and cid in judged:
            return judged[cid], "judgment"
        if src == "bottleneck" and b is not None:
            return b, "bottleneck(대체)"
    return None, "없음"


def pct_rank(vals):
    """{k: 0~1 백분위} — 같은 값은 평균 순위"""
    xs = sorted(v for v in vals.values() if v is not None)
    out = {}
    for k, v in vals.items():
        if v is None or len(xs) < 2:
            continue
        lo = sum(1 for x in xs if x < v)
        eq = sum(1 for x in xs if x == v)
        out[k] = (lo + (eq - 1) / 2) / (len(xs) - 1)
    return out


def compute(rows, weights, c, tag, is_ai, cards, judged):
    """rows = latest.json rows → {id: 그림자 행}"""
    out = {}
    for cid, r in rows.items():
        comps = dict(r.get("components") or {})
        if r.get("total") is None or not comps:
            continue
        sec = tag(cid)
        e, src = edge_for(cid, sec, comps, cards, judged, is_ai, c["edge_sources"])
        c2 = {k: v for k, v in comps.items() if k in weights}
        if "bottleneck" in c2 or e is not None:
            c2.pop("bottleneck", None)
            if e is not None:
                c2["bottleneck"] = e          # 같은 가중 칸에 넣는다(가중치는 그대로)
        ws = sum(weights[k] for k in c2)
        s1 = round(sum(weights[k] * v for k, v in c2.items()) / ws, 2) if ws else None
        out[cid] = {"id": cid, "name": r.get("name"), "sector": sec, "ai": bool(sec and is_ai(sec)), "v1": r["total"], "s1": s1,
                    "edge_src": src, "edge": e}
    by_sec = {}
    for cid, x in out.items():
        by_sec.setdefault(x["sector"], {})[cid] = x["s1"]
    glob = pct_rank({k: x["s1"] for k, x in out.items()})
    for sec, vals in by_sec.items():
        p = pct_rank(vals) if sec and len(vals) >= c["min_sector_n"] else {k: glob.get(k) for k in vals}
        for k in vals:
            x = out[k]
            x["sector_pct"] = None if p.get(k) is None else round(p[k], 3)
            x["s2"] = None if x["s1"] is None or x["sector_pct"] is None else round((1 - c["blend"]) * x["s1"] + c["blend"] * 10 * x["sector_pct"], 2)
            x["sector_top"] = bool(x["sector_pct"] is not None and x["sector_pct"] >= c["top_pct"] and sec and len(vals) >= c["min_sector_n"])
    return out


def run(dry=False, today=None):
    import score as v1
    import sector_map
    c = cfg()
    today = (today or date.today()).isoformat()
    try:
        import sector_rotation
        cards = sector_rotation.cards()
    except Exception:  # noqa: BLE001
        cards = {}
    rows = _j(LATEST).get("rows") or {}
    out = compute(rows, v1.cfg()["weights"], c, lambda cid: sector_map.tag(cid), sector_map.is_ai, cards, judged_edge())
    non_ai = [x for x in out.values() if not x["ai"] and x["sector"]]
    summary = {"as_of": today, "n": len(out), "non_ai": len(non_ai),
               "non_ai_ge5": {"v1": sum(1 for x in non_ai if x["v1"] >= 5), "s1": sum(1 for x in non_ai if (x["s1"] or 0) >= 5),
                              "s2": sum(1 for x in non_ai if (x["s2"] or 0) >= 5)},
               "edge_src": {s: sum(1 for x in non_ai if x["edge_src"] == s) for s in ("card", "judgment", "bottleneck(대체)", "없음")},
               "sector_top": sorted(k for k, x in out.items() if x.get("sector_top"))}
    if not dry:
        OUT.write_text(json.dumps({**summary, "rows": out, "note": "그림자 기록 — 알파 게이트는 v1 그대로"}, ensure_ascii=False, indent=1), encoding="utf-8")
        have = set()
        if LOG.exists():
            with LOG.open(encoding="utf-8", newline="") as f:
                have = {(r["date"], r["id"]) for r in csv.DictReader(f)}
        new = not LOG.exists()
        with LOG.open("a", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=COLS, extrasaction="ignore")
            if new:
                w.writeheader()
            for x in out.values():
                if (today, x["id"]) not in have:
                    w.writerow({**x, "date": today})
    return summary, out


# ---------- 시세 ----------
def us_ticker():
    """id → 미국 티커 함수 — 감시 목록 code(.US) 먼저, 없으면 us-<티커>"""
    tick = {}
    for p in ("config/valuation.yaml", "config/earnings_watch.yaml"):
        d = yaml.safe_load((ROOT / p).read_text(encoding="utf-8")) or {}
        for u in (d.get("universe") or []) + (d.get("extra") or []):
            code = str(u.get("code") or "")
            if code.endswith(".US"):
                tick[u["id"]] = code[:-3]
    return lambda i: tick.get(i) or (i[3:].upper() if i.startswith("us-") else None)


def price_request():
    """기록된 종목 중 미국 티커와 필요한 시작일 — Fiscal.ai company_stock_prices로 받는다"""
    if not LOG.exists():
        return {"tickers": [], "start": None}
    with LOG.open(encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))
    t = us_ticker()
    out = sorted({t(r["id"]) for r in rows} - {None}) + ["SPY"]
    have = _j(PRICES)
    return {"tickers": out, "start": min(r["date"] for r in rows), "have": len(have)}


def put_prices(path):
    new = json.loads(Path(path).read_text(encoding="utf-8"))
    cur = _j(PRICES)
    for t, rows in new.items():
        m = dict(map(tuple, cur.get(t) or []))
        m.update({d: c for d, c in rows})
        cur[t] = sorted([d, c] for d, c in m.items())
    PRICES.write_text(json.dumps(cur, ensure_ascii=False), encoding="utf-8")
    return len(new)


# ---------- 채택 관문 ----------
def spearman(xs, ys):
    n = len(xs)
    if n < 5:
        return None
    def rk(v):
        o = sorted(range(n), key=lambda i: v[i])
        r = [0.0] * n
        i = 0
        while i < n:
            j = i
            while j + 1 < n and v[o[j + 1]] == v[o[i]]:
                j += 1
            for k in range(i, j + 1):
                r[o[k]] = (i + j) / 2
            i = j + 1
        return r
    a, b = rk(xs), rk(ys)
    ma, mb = sum(a) / n, sum(b) / n
    cov = sum((x - ma) * (y - mb) for x, y in zip(a, b))
    va, vb = sum((x - ma) ** 2 for x in a), sum((y - mb) ** 2 for y in b)
    return cov / math.sqrt(va * vb) if va and vb else None


def fwd_return(series, d, h):
    """d 이후 첫 거래일 종가 → h거래일 뒤 종가 수익"""
    ds = [x for x in series if x[0] >= d]
    if len(ds) <= h:
        return None
    return ds[h][1] / ds[0][1] - 1


def gate(today=None, c=None, rows=None, prices=None, tick=None, write=False):
    c = c or cfg()
    g = c["gate"]
    today = today or date.today()
    if rows is None:
        if not LOG.exists():
            return {"verdict": "판정 보류", "why": "기록 없음"}
        with LOG.open(encoding="utf-8", newline="") as f:
            rows = list(csv.DictReader(f))
    if not rows:
        return {"verdict": "판정 보류", "why": "기록 없음"}
    first = min(r["date"] for r in rows)
    if (today - date.fromisoformat(first)).days < g["min_days"]:
        return {"verdict": "판정 보류", "why": f"그림자 {first} 시작, {g['min_days']}일 전"}
    prices = _j(PRICES) if prices is None else prices
    tick = tick or us_ticker()
    spy = prices.get("SPY") or []
    obs = []
    for r in rows:
        t = tick(r["id"])
        s = prices.get(t) if t else None
        if not s or not spy:
            continue
        fr, fb = fwd_return(s, r["date"], g["horizon_td"]), fwd_return(spy, r["date"], g["horizon_td"])
        if fr is None or fb is None:
            continue
        try:
            obs.append({"date": r["date"], "ai": str(r["ai"]) in ("True", "true", "1"), "v1": float(r["v1"]), "s1": float(r["s1"]),
                        "s2": float(r["s2"]), "x": fr - fb})
        except (TypeError, ValueError):
            continue
    if len(obs) < g["min_obs"]:
        return {"verdict": "판정 보류", "why": f"관측 {len(obs)} < {g['min_obs']}", "n": len(obs)}
    def ics(sub):
        return {k: spearman([o[k] for o in sub], [o["x"] for o in sub]) for k in ("v1", "s1", "s2")}
    dates = sorted({o["date"] for o in obs})
    mid = dates[len(dates) // 2]
    parts = {"전체": obs, "AI 밖": [o for o in obs if not o["ai"]]}
    if g.get("halves"):
        parts["앞 절반"] = [o for o in obs if o["date"] < mid]
        parts["뒤 절반"] = [o for o in obs if o["date"] >= mid]
    res = {k: ics(v) for k, v in parts.items()}
    best = None
    for s in ("s2", "s1"):
        ok_halves = all((res[h][s] or -9) - (res[h]["v1"] or -9) >= g["ic_margin"] for h in ("앞 절반", "뒤 절반") if h in res)
        ok_non = (res["AI 밖"][s] is None) or (res["AI 밖"]["v1"] is None) or res["AI 밖"][s] >= res["AI 밖"]["v1"]
        if ok_halves and ok_non:
            best = s
            break
    out = {"verdict": f"채택 제안 가능({best})" if best else "기각 — v1 유지", "n": len(obs), "ic": res, "as_of": today.isoformat(),
           "note": "config/alpha.yaml 구조 변경은 마스터 승인 뒤에만"}
    if write:
        GATE.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    return out


def main(argv):
    sys.stdout.reconfigure(encoding="utf-8")
    if "--gate" in argv:
        g = gate(write=True)
        if g["verdict"] == "판정 보류":   # 보류도 기록해 둔다(시험이 남긴 값이 남지 않게)
            GATE.write_text(json.dumps({**g, "as_of": date.today().isoformat()}, ensure_ascii=False, indent=1), encoding="utf-8")
        print(json.dumps(g, ensure_ascii=False, indent=1))
    elif "--price-request" in argv:
        print(json.dumps(price_request(), ensure_ascii=False))
    elif "--put-prices" in argv:
        print(f"{put_prices(argv[argv.index('--put-prices') + 1])}종목 시세 저장")
    else:
        summary, out = run(dry="--dry" in argv or "--show" in argv)
        print(json.dumps(summary, ensure_ascii=False, indent=1))
        top = sorted((x for x in out.values() if not x["ai"] and x["sector"]), key=lambda x: -(x["s2"] or 0))[:10]
        for x in top:
            print(f"  {x['name']}({x['sector']}) v1 {x['v1']} → S1 {x['s1']} · S2 {x['s2']} · 섹터 안 {x['sector_pct']} · 우위 {x['edge']}({x['edge_src']})")


if __name__ == "__main__":
    main(sys.argv[1:])
