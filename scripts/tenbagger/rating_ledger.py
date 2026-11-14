"""구매 등급 성과 원장 (마스터 지시 2026-11-04 "Buy와 Sell 등 평가 등급을 매길 때도 평가 체계가 고도화됐는지 점검")

점검 결과 등급 경계(prm-tb-rate-*)가 피팅된 적이 없었다 — 등급 뒤 주가 성과 자료가 없었다. 이 원장이 그 자료다.
  py scripts/tenbagger/rating_ledger.py log                  # outputs/tenbagger/reports/*.json의 등급을 올린다(같은 날·티커 중복 없음) + 그림자 등급
  py scripts/tenbagger/rating_ledger.py due                  # 성과를 아직 못 채운 티커 → 모델이 TradingView 일봉(+SPY)을 받는다
  py scripts/tenbagger/rating_ledger.py resolve <가격 json>  # {"SPY": [["2026-11-03", 680.1], …], "STRL": [...]} → 3·6·12개월(63·126·252거래일) 시장 대비 초과수익
  py scripts/tenbagger/rating_ledger.py fit [3|6|12]         # 등급별 평균 초과수익·순서 상관(스피어만), 운영·규칙·그림자 등급 비교 — 30건 전에는 판정 보류
그림자 등급(config/tenbagger_rating_lab.yaml): hyst = 경계 ±band 안이면 직전 등급 유지, volz = 업사이드 ÷ 연 변동성 경계. 운영 등급을 바꾸지 않는다.
"""
import csv
import json
import math
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
LEDGER = ROOT / "knowledge" / "models" / "tenbagger" / "rating_ledger.csv"
REPORTS = ROOT / "outputs" / "tenbagger" / "reports"
COMPANIES = ROOT / "knowledge" / "models" / "companies"
ORDER = ["Strong Sell", "Sell", "Neutral", "Buy", "Strong Buy"]
HORIZONS = {3: 63, 6: 126, 12: 252}
COLS = ["date", "ticker", "rating", "rule_rating", "price", "upside", "rr", "dcf_up", "vol", "hyst", "volz", "ex3", "ex6", "ex12"]
MIN_N = 30


def cfg():
    return (yaml.safe_load((ROOT / "config" / "tenbagger.yaml").read_text(encoding="utf-8"))["rating"],
            yaml.safe_load((ROOT / "config" / "tenbagger_rating_lab.yaml").read_text(encoding="utf-8")))


def rows():
    if not LEDGER.exists():
        return []
    with LEDGER.open(encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def save(rs):
    LEDGER.parent.mkdir(parents=True, exist_ok=True)
    with LEDGER.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, COLS)
        w.writeheader()
        w.writerows(rs)


def rule(up, rr, dcf_up, r):
    """report_layout.rating과 같은 규칙(여기서는 그림자 비교의 기준선). dcf_up None = DCF 산정 불가(ADR-039): Strong Buy 없음, Buy는 DCF 조건 없이"""
    if dcf_up is not None and up >= r["strong_buy"]["upside"] and rr >= r["strong_buy"]["rr"] and dcf_up >= r["strong_buy"]["dcf_min"]:
        return "Strong Buy"
    if up >= r["buy"]["upside"] and rr >= r["buy"]["rr"] and (dcf_up is None or dcf_up >= r["buy"]["dcf_min"]):
        return "Buy"
    if up >= r["neutral"]["upside"]:
        return "Neutral"
    return "Sell" if up >= r["sell"]["upside"] else "Strong Sell"


def hyst(up, rr, dcf_up, r, prev, band):
    """경계 ±band 안에서 바뀌면 직전 등급 유지 — 모델 오차보다 작은 차이로 등급이 뒤집히지 않게"""
    now = rule(up, rr, dcf_up, r)
    if not prev or prev == now:
        return now
    edges = [r["strong_buy"]["upside"], r["buy"]["upside"], r["neutral"]["upside"], r["sell"]["upside"]]
    return prev if any(abs(up - e) < band for e in edges) and abs(ORDER.index(prev) - ORDER.index(now)) == 1 else now


def volz(up, vol, v):
    if not vol:
        return ""
    z = up / vol
    return "Strong Buy" if z >= v["strong_buy"] else "Buy" if z >= v["buy"] else "Neutral" if z >= v["neutral"] else "Sell" if z >= v["sell"] else "Strong Sell"


def ann_vol(ticker, window):
    """회사 폴더 ohlcv.csv 종가의 연 변동성(일 로그수익률 표준편차 × √252)"""
    for dp in COMPANIES.glob("*/datapack.json"):
        try:
            if json.loads(dp.read_text(encoding="utf-8")).get("ticker") != ticker:
                continue
        except Exception:
            continue
        f = dp.with_name("ohlcv.csv")
        if not f.exists():
            return None
        c = [float(x["c"]) for x in csv.DictReader(l for l in f.read_text(encoding="utf-8").splitlines() if not l.startswith("#")) if x.get("c")][-window - 1:]
        r = [math.log(b / a) for a, b in zip(c, c[1:]) if a > 0 and b > 0]
        if len(r) < 20:
            return None
        m = sum(r) / len(r)
        return round((sum((x - m) ** 2 for x in r) / (len(r) - 1)) ** 0.5 * 252 ** 0.5, 4)
    return None


def log():
    r, lab = cfg()
    rs = rows()
    have = {(x["date"], x["ticker"]) for x in rs}
    last = {}
    for x in sorted(rs, key=lambda x: x["date"]):
        last[x["ticker"]] = x["rating"]
    n = 0
    for p in sorted(REPORTS.glob("*.json")):
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            continue
        v = d.get("verdict") or {}
        if not v.get("rating") or v.get("upside") is None or d.get("kind") == "spac":
            continue
        key = (d.get("date") or p.stem[:8], d.get("ticker") or p.stem.split("_", 1)[-1])
        if key in have:
            continue
        up, rr, du = float(v["upside"]), float(v.get("rr") or 0), (float(v["dcf_up"]) if v.get("dcf_up") is not None else None)   # None = DCF 산정 불가(ADR-039)
        vol = ann_vol(key[1], lab["vol_scaled"]["window"])
        rs.append({"date": key[0], "ticker": key[1], "rating": v["rating"], "rule_rating": v.get("rule_rating") or rule(up, rr, du, r), "price": v.get("price"),
                   "upside": up, "rr": rr, "dcf_up": du, "vol": vol or "", "hyst": hyst(up, rr, du, r, last.get(key[1]), lab["hysteresis"]["band"]),
                   "volz": volz(up, vol, lab["vol_scaled"]), "ex3": "", "ex6": "", "ex12": ""})
        last[key[1]] = v["rating"]
        have.add(key)
        n += 1
    save(rs)
    return n


def excess(series, mkt, day, h):
    """등급일 전날 종가 기준 h거래일 뒤 시장 대비 초과수익 %"""
    s, m = sorted(series), dict(mkt)
    base = [i for i, (d, _) in enumerate(s) if d < day]
    if not base or base[-1] + h >= len(s):
        return None
    (d0, c0), (d1, c1) = s[base[-1]], s[base[-1] + h]
    if d0 not in m or d1 not in m:
        return None
    return round((c1 / c0 - m[d1] / m[d0]) * 100, 2)


def resolve(prices, market="SPY"):
    rs, n = rows(), 0
    for x in rs:
        ser = prices.get(x["ticker"])
        if not ser:
            continue
        for mo, h in HORIZONS.items():
            if x[f"ex{mo}"] == "":
                v = excess(ser, prices.get(market) or [], _iso(x["date"]), h)
                if v is not None:
                    x[f"ex{mo}"] = v
                    n += 1
    save(rs)
    return n


def _iso(d):
    d = d.replace("-", "")
    return f"{d[:4]}-{d[4:6]}-{d[6:8]}"


def _rank(xs):
    o = sorted(range(len(xs)), key=lambda i: xs[i])
    r, i = [0.0] * len(xs), 0
    while i < len(o):
        j = i
        while j + 1 < len(o) and xs[o[j + 1]] == xs[o[i]]:
            j += 1
        for k in range(i, j + 1):
            r[o[k]] = (i + j) / 2
        i = j + 1
    return r


def spearman(a, b):
    ra, rb = _rank(a), _rank(b)
    n = len(a)
    ma, mb = sum(ra) / n, sum(rb) / n
    va, vb = sum((x - ma) ** 2 for x in ra), sum((y - mb) ** 2 for y in rb)
    return sum((x - ma) * (y - mb) for x, y in zip(ra, rb)) / (va * vb) ** 0.5 if va and vb else None


def fit(mo=12):
    done = [x for x in rows() if x[f"ex{mo}"] != ""]
    out = {"horizon_months": mo, "n": len(done), "min_n": MIN_N, "variants": {}}
    for col in ("rating", "rule_rating", "hyst", "volz"):
        use = [x for x in done if x[col] in ORDER]
        if len(use) < 3:
            continue
        g = {}
        for x in use:
            g.setdefault(x[col], []).append(float(x[f"ex{mo}"]))
        out["variants"][col] = {"n": len(use), "spearman": round(spearman([ORDER.index(x[col]) for x in use], [float(x[f'ex{mo}']) for x in use]) or 0, 3),
                                "by_rating": {k: {"n": len(v), "mean_ex": round(sum(v) / len(v), 2)} for k, v in sorted(g.items(), key=lambda kv: ORDER.index(kv[0]))}}
    out["verdict"] = "표본 부족 — 판정 보류" if len(done) < MIN_N else "등록부 design 규칙으로 후보를 하나씩 검정한다(scripts/fit/stepwise.py)"
    return out


def due():
    return sorted({(x["ticker"], x["date"]) for x in rows() if x["ex12"] == ""})


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    a = sys.argv[1:]
    if a[:1] == ["log"]:
        print(f"원장에 {log()}건 추가")
    elif a[:1] == ["due"]:
        print(json.dumps(due(), ensure_ascii=False))
    elif a[:1] == ["resolve"] and len(a) == 2:
        print(f"초과수익 {resolve(json.loads(Path(a[1]).read_text(encoding='utf-8')))}칸 채움")
    elif a[:1] == ["fit"]:
        print(json.dumps(fit(int(a[1]) if len(a) > 1 else 12), ensure_ascii=False, indent=1))
    else:
        raise SystemExit(__doc__)
