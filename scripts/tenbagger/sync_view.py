"""텐배거 리포트 '거시 지표 싱크로율' 절 (마스터 지시 2026-11-03 "해당 상장기업이 속하거나 수출입하는 무역, PPI, 수출 지표와
매출, 영업이익 추이 간 싱크로율이 어떠한지 시각물과 모델링을 통한 산정 수치를 제공해 이 추이가 앞으로 전망되는 가이던스 수치 및
컨센서스 수치와 비슷한지 비교 분석")

숫자는 여기서 계산한다. 모델은 datapack "sync"에 어떤 지표를 볼지만 쓴다.
datapack "sync":
  {"why": "이 회사 매출이 어느 거시 지표를 따라가야 하는가 한 줄",
   "indicators": [{"label": "대만 PCB 수출", "source": "hs", "reporter": "tw", "flow": "export", "hs": "8534", "why": "…"},   # radar/trade_hs.py 저장소(WORLD 합계)
                  {"label": "미국 PCB PPI", "source": "ppi", "input": "pcb", "country": "us", "why": "…"},                   # config/trade_ppi.yaml inputs 키
                  {"label": "EU PCB 수입", "source": "trade", "input": "pcb", "country": "eu", "why": "…"}]}               # eu는 상대국 합계
  지표가 의미 없으면 {"none": "이유"}.
분기 손익은 datapack "quarters_hist"(scripts/tenbagger/quarters.py --put). 지표 월 시계열은 radar/trade_ppi.py(history.json)와 radar/trade_hs.py.

계산: 회사 분기 끝 달 기준 3개월로 지표를 분기화(무역은 합, PPI는 평균) → 전년 대비 증가율(쌍이 MIN_PAIRS보다 적으면 전 분기 대비) →
지표가 0~2분기 앞서는 경우마다 매출·영업이익 증가율과 상관계수 → |상관|이 가장 큰 시차를 고른다. 싱크로율 = 상관계수 × 100.
다음 분기: 회귀(증가율 = a + b × 지표 증가율)로 지표가 내포하는 매출을 구하고, 잔차 표준편차로 ±1σ 범위를 낸다. 시차 0이면 그 분기의
지난 달까지로 당겨 쓴다(나우캐스트). 가이던스·컨센서스가 이 범위 안인지 비교한다. 상관은 인과가 아니다.
지표 자동 선택(마스터 지시 2026-11-08 "기업 제품 및 서비스와 연관성이 가장 높은 PPI 세부 지표, 수출입 세부 지표와 연동하도록 해라. 그리고 다음 분기 추이까지 모델링을 통해 합리적으로 추산"):
  sync.products [{name, segment, hs(6자리), share(매출 비중), inputs[config/trade_ppi.yaml inputs 키]}] — 제품·서비스 → 품목 코드는 모델 판단(없으면 indicators의 hs·input에서 거꾸로 만든다).
  후보 = 그 HS의 무역 세부 시계열(radar/trade_hs.py 저장소, 나라·수출입 전부) + 같은 HS를 가진 PPI 세부 지수(config inputs, 나라별) + 모델 지정 지표.
  연관성 = 품목 일치(6자리 1.0 · 4자리 0.7) × 대용 지수 감점(업종 대용 PPI 0.6) × 제품 매출 비중. 점수 = 연관성 × 싱크로율(+방향만, 반대 부호 0점 — 반대여야 하는 지표는 sign: -1) × (유의 1.0, 아니면 0.8).
  PPI 1개·수출입 1개를 점수로 고른다(후보 표에 모두 남긴다 — 후보가 많을수록 최대 상관은 부풀므로 연관성을 먼저 곱한다).
  다음 분기: 지표가 선행하면 확정 값, 0분기면 나온 달로 나우캐스트, 한 달도 없으면 지표 증가율을 자기회귀모델로 한 분기 예측하고
  σ = √(회귀 잔차² + (기울기 × 지표 예측 오차)²)로 넓힌다. 추정값은 그림에 '다음 분기 추정'으로 이어 그린다.
"""
import json
import math
import sqlite3
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
HISTORY = ROOT / "knowledge" / "models" / "trade_ppi" / "history.json"
HS_DB = ROOT / "radar" / "state" / "trade_hs.sqlite"
MIN_PAIRS = 5
LAGS = (0, 1, 2, 3, 4)   # 0~4분기(0~12개월) 선행까지 — 2026-11-04 마스터 지시 "통계 지표가 기업 실적을 얼마나 선행하는지"
UNIT = {"$M": 1e6, "M$": 1e6, "M": 1e6, "$B": 1e9, "B$": 1e9, "B": 1e9}
UNKNOWN = "미확인"
TRADE_CFG = ROOT / "config" / "trade_ppi.yaml"
COUNTRY = {"us": "미국", "eu": "EU", "uk": "영국", "jp": "일본", "kr": "한국", "tw": "대만", "hk": "홍콩"}
FLOW = {"export": "수출", "import": "수입"}
MAX_CANDIDATES = 24
BROAD4 = {"8542", "8541", "8471", "8517"}   # 4자리 안에 서로 다른 제품이 섞인 품목군(IC 전체·반도체 소자·컴퓨터·통신기기) — 6자리 일치만 쓴다
WINDOW = 16   # 그림은 최근 16개 분기 — 매출과 지표를 같은 분기 축에 놓는다(마스터 지시 2026-11-08)


def _wa(word):
    """받침 뒤 '과', 모음 뒤 '와'(Proviser 2026-11-03, '수입와')"""
    c = str(word).rstrip()[-1:]
    return "과" if "가" <= c <= "힣" and (ord(c) - 0xAC00) % 28 else "와"


def qlabel(period):
    """회사 분기 끝 날짜 → (분기 라벨, 끝 달). 52·53주 결산이 다음 달 초에 끝나면 앞 달로 본다"""
    y, m, d = int(period[:4]), int(period[5:7]), int(period[8:10] or 28)
    if d <= 10:
        y, m = (y, m - 1) if m > 1 else (y - 1, 12)
    return f"{y}Q{(m - 1) // 3 + 1}", (y, m)


def months_back(ym, n=3):
    y, m = ym
    out = []
    for _ in range(n):
        out.append(f"{y}-{m:02d}")
        y, m = (y, m - 1) if m > 1 else (y - 1, 12)
    return out


def shift_q(label, k):
    y, q = int(label[:4]), int(label[-1])
    i = y * 4 + q - 1 + k
    return f"{i // 4}Q{i % 4 + 1}"


def monthly(ind, history=None, db=HS_DB):
    """지표 월 시계열 {YYYY-MM: 값}"""
    if ind["source"] == "hs":
        if not db.exists():
            return {}
        c = sqlite3.connect(db)
        try:
            rows = c.execute("SELECT period, value FROM obs WHERE reporter=? AND flow=? AND hs=? AND partner='WORLD'", (ind["reporter"], ind["flow"], str(ind["hs"]))).fetchall()
        finally:
            c.close()
        return {p[:7]: v for p, v in rows if v is not None}
    h = (history if history is not None else (json.loads(HISTORY.read_text(encoding="utf-8")) if HISTORY.exists() else {})).get("inputs", {}).get(ind["input"], {})
    part = h.get(ind["source"], {})
    if ind["source"] == "trade" and ind["country"] == "eu":
        out = {}
        for k, s in part.items():
            if k.startswith("eu:"):
                for p, v in s.items():
                    out[p[:7]] = out.get(p[:7], 0) + v
        return out
    return {p[:7]: v for p, v in (part.get(ind["country"]) or {}).items() if v is not None}


def quarterize(series, ends, avg):
    """분기 라벨 → 값. 세 달이 다 있어야 쓴다"""
    out = {}
    for lab, ym in ends.items():
        ms = months_back(ym)
        if all(m in series for m in ms):
            vals = [series[m] for m in ms]
            out[lab] = sum(vals) / 3 if avg else sum(vals)
    return out


def growth(x, k):
    return {q: x[q] / x[shift_q(q, -k)] - 1 for q in x if shift_q(q, -k) in x and x[shift_q(q, -k)]}


def corr(a, b):
    n = len(a)
    if n < 3:
        return None
    ma, mb = sum(a) / n, sum(b) / n
    sa = math.sqrt(sum((x - ma) ** 2 for x in a))
    sb = math.sqrt(sum((y - mb) ** 2 for y in b))
    return None if not sa or not sb else sum((x - ma) * (y - mb) for x, y in zip(a, b)) / (sa * sb)


def ols(x, y):
    n = len(x)
    mx, my = sum(x) / n, sum(y) / n
    sxx = sum((v - mx) ** 2 for v in x)
    b = sum((u - mx) * (v - my) for u, v in zip(x, y)) / sxx if sxx else 0.0
    a = my - b * mx
    res = [v - (a + b * u) for u, v in zip(x, y)]
    se = math.sqrt(sum(r * r for r in res) / max(n - 2, 1))
    return a, b, se


def reliability(n):
    return "보통" if n >= 12 else ("낮음" if n >= 8 else "참고용")


def fit(comp, ind_q, k):
    """comp·ind_q: 분기 라벨 → 수준. k = 4(전년 대비) 또는 1(전 분기 대비)"""
    cg, ig = growth(comp, k), growth(ind_q, k)
    best = None
    for lag in LAGS:
        pairs = [(ig[shift_q(q, -lag)], cg[q]) for q in sorted(cg) if shift_q(q, -lag) in ig]
        if len(pairs) < MIN_PAIRS:
            continue
        x, y = zip(*pairs)
        r = corr(x, y)
        if r is None:
            continue
        hit = sum(1 for u, v in pairs if (u >= 0) == (v >= 0)) / len(pairs)
        t = r * math.sqrt(len(pairs) - 2) / math.sqrt(max(1e-9, 1 - r * r)) if len(pairs) > 2 else 0.0
        if best is None or abs(r) > abs(best["r"]):
            a, b, se = ols(x, y)
            best = {"lag": lag, "r": r, "n": len(pairs), "hit": hit, "a": a, "b": b, "se": se, "t": t, "sig": abs(t) >= 2.0}
    return best


def path(comp, ind_q, fr, k, last):
    """선행 분기만큼 앞선 지표가 이미 나왔으므로 그만큼 앞의 분기 매출 증가율을 전망한다(2026-11-04).
    h = 1..lag: q = last + h, 지표 = q − lag 분기(≤ last라 확정), 기준 = q − k 분기 실적(k=4면 h ≤ 4까지 실적이 있다)"""
    out = []
    ig = growth(ind_q, k)
    for h in range(1, max(1, fr["lag"]) + 1):
        q = shift_q(last, h)
        xq = shift_q(q, -fr["lag"])
        base = comp.get(shift_q(q, -k))
        if xq not in ig or base is None or fr["lag"] < h:
            continue
        g = fr["a"] + fr["b"] * ig[xq]
        out.append({"q": q, "x": ig[xq], "g": g, "rev": base * (1 + g), "lo": base * (1 + g - fr["se"]), "hi": base * (1 + g + fr["se"])})
    return out


def nowcast(series, ym_next, lag, k, ends_next_label, ind_q):
    """다음 분기를 설명하는 지표 증가율 — 시차가 있으면 이미 나온 분기 값, 0이면 그 분기의 나온 달만으로"""
    if lag >= 1:
        q = shift_q(ends_next_label, -lag)
        g = growth(ind_q, k)
        return (g[q], "확정") if q in g else (None, None)
    have = [m for m in reversed(months_back(ym_next)) if m in series]
    if not have:
        return None, None
    base = []
    for m in have:
        y, mo = int(m[:4]), int(m[5:7])
        if k == 4:
            base.append(f"{y - 1}-{mo:02d}")
        else:
            yy, mm = (y, mo - 3) if mo > 3 else (y - 1, mo + 9)
            base.append(f"{yy}-{mm:02d}")
    if not all(b in series and series[b] for b in base):
        return None, None
    return sum(series[m] for m in have) / sum(series[b] for b in base) - 1, f"나우캐스트 {len(have)}개월"


def _inputs():
    return (yaml.safe_load(TRADE_CFG.read_text(encoding="utf-8")) or {}).get("inputs") or {}


def products(dp):
    """제품·서비스 → 품목(HS) 목록. sync.products가 없으면 모델 지정 지표에서 만든다"""
    sy = dp.get("sync") or {}
    if sy.get("products"):
        return sy["products"]
    inp, out = _inputs(), {}
    for ind in sy.get("indicators") or []:
        hs = str(ind.get("hs") or (inp.get(ind.get("input")) or {}).get("hs") or "")
        if hs:
            by_hs = next((v["name"] for v in inp.values() if str(v.get("hs") or "") == hs), None)
            nm = (inp.get(ind.get("input")) or {}).get("name") or by_hs or ind.get("segment") or f"HS {hs}"
            out.setdefault(hs, {"name": str(nm).split("(")[0].strip(), "segment": ind.get("segment"), "hs": hs,
                                "inputs": [ind["input"]] if ind.get("input") else []})
    return list(out.values())


def candidates(dp, db=HS_DB):
    """[(지표, 연관성)] — 모델 지정 지표 + 제품 HS로 찾은 PPI·무역 세부 시계열"""
    inp = _inputs()
    prods = products(dp)
    tot = sum(float(x.get("share") or 0) for x in prods) or None
    out, seen = [], set()

    def key(ind):
        return (ind["source"], ind.get("reporter") or ind.get("country"), ind.get("flow"), str(ind.get("hs") or ind.get("input")))

    def add(ind, rel):
        k = key(ind)
        if k in seen:
            for i, (x, r) in enumerate(out):
                if key(x) == k and rel > r:
                    out[i] = (x, rel)
            return
        seen.add(k)
        out.append((ind, rel))
    for ind in (dp.get("sync") or {}).get("indicators") or []:
        add({**ind, "origin": "모델 지정"}, 1.0)
    have = []
    if db.exists():
        c = sqlite3.connect(db)
        try:
            have = c.execute("SELECT DISTINCT reporter, flow, hs FROM obs WHERE partner='WORLD'").fetchall()
        finally:
            c.close()
    for pr in prods:
        hs = str(pr.get("hs") or "")
        w = (float(pr.get("share") or 0) / tot) if tot else 1.0 / max(len(prods), 1)
        w = max(w, 0.25)   # 작은 제품도 후보에서 아주 빠지지는 않게
        for rep, flow, h in have:
            m = 1.0 if h == hs else 0.7 if hs and h[:4] == hs[:4] and hs[:4] not in BROAD4 else 0
            if m:
                add({"label": f"{COUNTRY.get(rep, rep)} {pr['name']} {FLOW.get(flow, flow)}(HS {h})" if m == 1 else f"{COUNTRY.get(rep, rep)} HS {h} {FLOW.get(flow, flow)}({pr['name']}과 같은 4자리 품목군)", "source": "hs", "reporter": rep, "flow": flow, "hs": h,
                     "segment": pr.get("segment"), "why": f"{pr['name']} 품목 {'일치' if m == 1 else '같은 4자리'}", "origin": "자동"}, m * w)
        keys = list(pr.get("inputs") or []) + [k for k, v in inp.items() if hs and (str(v.get("hs") or "") == hs or (str(v.get("hs") or "")[:4] == hs[:4] and hs[:4] not in BROAD4))]
        for k in dict.fromkeys(keys):
            v = inp.get(k) or {}
            m = 1.0 if str(v.get("hs") or "") == hs or k in (pr.get("inputs") or []) else 0.7
            for ctry in (v.get("ppi") or {}):
                pen = 0.6 if ctry in (v.get("proxy") or []) else 1.0
                add({"label": f"{COUNTRY.get(ctry, ctry)} {v.get('name', k)} PPI" + ("(업종 대용)" if pen < 1 else ""), "source": "ppi", "input": k, "country": ctry,
                     "segment": pr.get("segment"), "why": f"{pr['name']} ↔ {v.get('name', k)} 생산자물가" + (" — 품목보다 넓은 업종 지수" if pen < 1 else ""), "origin": "자동"}, m * pen * w)
    out.sort(key=lambda x: -x[1])
    keep = [x for x in out if x[0].get("origin") == "모델 지정"]
    return keep + [x for x in out if x[0].get("origin") != "모델 지정"][:MAX_CANDIDATES]


def kind(ind):
    return "ppi" if ind["source"] == "ppi" else "trade"


def score(row):
    """지표는 기본적으로 같은 방향(+)이어야 말이 된다 — 반대 부호 상관은 점수 0(우연이거나 다른 경로). 반대여야 하는 지표는 sign: -1"""
    f = row.get("rev")
    if not f:
        return 0.0
    sg = row["ind"].get("sign", 1)   # 기본 +방향(수요·가격 지표). 원가·대체재처럼 반대로 움직여야 하는 지표는 indicators에 sign: -1
    r = f["r"] * sg
    return row["rel"] * max(r, 0.0) * (1.0 if f["sig"] else 0.8)


def forecast_x(iq, k):
    """지표 증가율 한 분기 앞 — 자기회귀모델(절편, BIC 차수, 전년 대비면 겹친 표본 장기 분산). (값, 표준오차) 또는 (None, None)"""
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import pq_forecast as PF
    g = growth(iq, k)
    qs = sorted(g)
    y = [g[q] for q in qs]
    if len(y) < 10:
        return None, None
    fr = PF.ar_fit(y, pmax=2, intercept=True, overlap=k if k > 1 else 1)
    if not fr:
        return None, None
    m, se = PF.ar_path(y, fr, 1)
    return m[0], se[0]


def compute(dp, history=None, db=HS_DB):
    sy = dp.get("sync") or {}
    qs = [r for r in (dp.get("quarters_hist") or {}).get("q") or [] if r.get("rev")]
    ends = {}
    rev, op = {}, {}
    for r in qs:
        lab, ym = qlabel(r["period"])
        ends[lab] = ym
        rev[lab] = r["rev"]
        if r.get("op") is not None:
            op[lab] = r["op"]
    last = max(rev)
    nxt = shift_q(last, 1)
    y, m = ends[last]
    ym_next = (y + (m + 2) // 12, (m + 2) % 12 + 1)
    ends_all = dict(ends)
    ends_all[nxt] = ym_next
    for i in range(1, 9):   # 회사 분기보다 앞선 지표 분기(시차용)
        lab = shift_q(min(ends), -i)
        yy, mm = ends[min(ends)]
        mm -= 3 * i
        while mm <= 0:
            yy, mm = yy - 1, mm + 12
        ends_all[lab] = (yy, mm)
    segs = {}
    for name, rows_ in ((dp.get("segments_hist") or {}).get("segments") or {}).items():   # 세그먼트 분기 매출(2026-11-04) — 지표가 그 세그먼트를 따라가는지
        segs[name] = {qlabel(r["period"])[0]: r["rev"] for r in rows_ if r.get("rev")}
    out = []
    for ind, rel in candidates(dp, db):
        s = monthly(ind, history, db)
        if not s:
            continue
        iq = quarterize(s, ends_all, ind["source"] == "ppi")
        target = segs.get(ind.get("segment")) if ind.get("segment") else None
        comp = target if target and len(target) >= MIN_PAIRS + 4 else rev
        row = {"ind": ind, "rel": rel, "months": len(s), "iq": iq, "basis": None, "rev": None, "op": None, "next": None, "path": [],
               "target": ind.get("segment") if comp is not rev else "전사 매출", "comp": comp}
        for k, basis in ((4, "전년 대비"), (1, "전 분기 대비")):
            fr = fit(comp, iq, k)
            if fr:
                row.update({"basis": basis, "k": k, "rev": fr, "op": fit(op, iq, k) if op else None})
                break
        if row["rev"]:
            fr, k = row["rev"], row["k"]
            row["path"] = path(comp, iq, fr, k, last)
            x, how = nowcast(s, ym_next, fr["lag"], k, nxt, iq)
            base = comp.get(shift_q(nxt, -k))
            se = fr["se"]
            if x is None and base:   # 다음 분기 지표가 한 달도 없으면 지표를 자기회귀모델로 한 분기 예측한다
                x, sx = forecast_x(iq, k)
                if x is not None:
                    how, se = "지표 자기회귀 추정", math.sqrt(fr["se"] ** 2 + (fr["b"] * sx) ** 2)
            if x is not None and base:
                g = fr["a"] + fr["b"] * x
                row["next"] = {"x": x, "how": how, "g": g, "rev": base * (1 + g), "lo": base * (1 + g - se), "hi": base * (1 + g + se), "se": se}
        row["score"] = score(row)
        out.append(row)
    chosen = []
    for kd in ("ppi", "trade"):   # PPI 1개·수출입 1개 — 연관성 × 싱크로율 점수
        c = [r for r in out if r["rev"] and kind(r["ind"]) == kd and score(r) > 0]
        if c:
            chosen.append(max(c, key=lambda r: r["score"]))
    for r in out:
        r["chosen"] = r in chosen
    return {"last": last, "next": nxt, "rev": rev, "op": op, "rows": out, "chosen": chosen}


def _targets(dp, nxt):
    """다음 분기 가이던스·컨센서스 매출(원 단위)"""
    g = (dp.get("guidance") or {}).get("next") or {}
    guide = cons = None
    sc = UNIT.get(str(g.get("unit") or ""))
    if sc and g.get("rev"):
        guide = float(g["rev"]) * sc
        if g.get("rev_cons"):
            cons = float(g["rev_cons"]) * sc
    qe = (dp.get("consensus") or {}).get("quarters_est") or {}
    sc2 = UNIT.get(str(dp.get("unit") or ""))
    if cons is None and sc2 and qe.get(nxt) is not None:
        cons = float(qe[nxt]) * sc2
    return guide, cons


def _pct(x, d=0):
    return UNKNOWN if x is None else f"{x * 100:+.{d}f}%"


def _money(v):
    return UNKNOWN if v is None else (f"{v / 1e9:,.2f}B" if abs(v) >= 1e9 else f"{v / 1e6:,.0f}M")


def _compare(v, lo, hi, mid):
    if v is None or mid is None:
        return UNKNOWN
    pos = "범위 안" if lo <= v <= hi else ("범위 위" if v > hi else "범위 아래")
    return f"{v / mid - 1:+.1%}({pos})"


def window(last, n=WINDOW):
    """마지막 매출 분기까지 n개 분기 라벨(오래된 순)"""
    return [shift_q(last, -i) for i in range(n - 1, -1, -1)]


def level_chart(c, win, top=None):
    """매출과 지표 레벨을 같은 분기 축·같은 기준 분기 지수(= 100)로 — 단위가 달라도 한 그림에서 흐름을 대조한다(마스터 지시 2026-11-08 "매출 시계열과 PPI 및 수출입 데이터의 시계열은 동일해야 한다").
    축 = 최근 16개 분기 중 매출이 있는 분기, 기준 = 그 첫 분기. 지표는 회사 분기 끝 달 기준 3개월(무역 합·PPI 평균)이라 매출과 같은 기간이다.
    지표가 기준 분기에 값이 없으면(발표 지연) 그 지표의 첫 값으로 기준을 잡고 이름에 적는다"""
    axis = [q for q in win if c["rev"].get(q)]
    if not axis:
        return None
    base_q = axis[0]

    def idx(series):
        have = [q for q in axis if series.get(q)]
        if not have:
            return [], None
        b = have[0]
        return [[q, round(series[q] / series[b] * 100, 1)] for q in have], b
    cols = ["a", "b", "c", "d", "e"]
    series = [{"name": "매출", "color": "a", "points": idx(c["rev"])[0]}]
    for i, r in enumerate(c["rows"]):
        pts, b = idx(r["iq"])
        if pts:
            src = {"ppi": "PPI", "hs": "수출입", "trade": "수출입"}.get(r["ind"].get("source"), "")
            name = r["ind"]["label"] + (f"({src})" if src and src not in r["ind"]["label"] else "") + (f" — {b} = 100" if b != base_q else "")
            series.append({"name": name, "color": cols[(i + 1) % len(cols)], "points": pts})
    nx = (top or {}).get("next")
    if nx and c["rev"].get(c["last"]):
        b0 = c["rev"][axis[0]]
        series.append({"name": f"매출 다음 분기 추정({c['next']})", "color": "e", "points": [[c["last"], round(c["rev"][c["last"]] / b0 * 100, 1)], [c["next"], round(nx["rev"] / b0 * 100, 1)]]})
    return {"kind": "line", "title": f"매출·PPI·수출입 — 최근 {len(axis)}개 분기 같은 축({base_q} = 100) + 다음 분기 추정", "unit": "", "series": series}


def section(dp, history=None, db=HS_DB):
    sy = (dp or {}).get("sync")
    if not sy:
        raise SystemExit("datapack에 sync가 없다(scripts/tenbagger/sync_view.py 맨 위) — 지표가 무의미하면 {'none': '이유'}, 옛 리포트 정정은 --legacy")
    if sy.get("none"):
        return None
    if len((dp.get("quarters_hist") or {}).get("q") or []) < 8:
        raise SystemExit("datapack에 quarters_hist가 없거나 8분기 미만이다 — scripts/fiscal/templates/quarters.js → py scripts/tenbagger/quarters.py --put <id> <파일>")
    if not sy.get("indicators"):
        raise SystemExit("datapack sync.indicators가 비었다")
    c = compute(dp, history, db)
    guide, cons = _targets(dp, c["next"])
    ok = [r for r in c["rows"] if r["rev"]]
    if not ok:
        return {"h2": "거시 지표 싱크로율", "blocks": [{"type": "hl", "text": f"**지표와 실적을 맞출 표본이 부족하다(쌍 {MIN_PAIRS}개 미만).** 지표 월 시계열이 더 쌓이면 다시 잰다."},
                                                    {"type": "table", "title": "지표 표본", "headers": ["지표", "월 수"], "rows": [[r["ind"]["label"], str(r["months"])] for r in c["rows"]]}]}
    top = max(c["chosen"] or ok, key=lambda r: r["score"])
    fr = top["rev"]
    head = (f"**{top['ind']['label']}{_wa(top['ind']['label'])} {top['target']} 싱크로율 {fr['r'] * 100:.0f}%({fr['lag']}분기 = 약 {fr['lag'] * 3}개월 선행, {top['basis']}, "
            f"표본 {fr['n']}개·t {fr['t']:.1f}{'·유의' if fr['sig'] else '·유의 아님'}·신뢰 {reliability(fr['n'])}).** ")
    nx, cmp = top["next"], None
    if nx:
        head += f"이 지표가 내포하는 {c['next']} {top['target']}은 {_money(nx['rev'])}(±1σ {_money(nx['lo'])}~{_money(nx['hi'])}, {nx['how']})다. "
        cmp = nx
        if top["target"] != "전사 매출":   # 세그먼트 값을 전사 가이던스와 바로 비교하지 않는다 — 기준 분기의 세그먼트 비중으로 전사 환산
            bq = shift_q(c["next"], -top["k"])
            sh = (top["comp"].get(bq) / c["rev"][bq]) if c["rev"].get(bq) and top["comp"].get(bq) else None
            if sh:
                cmp = {k: nx[k] / sh for k in ("rev", "lo", "hi")}
                head += f"기준 분기({bq}) 세그먼트 비중 {sh:.0%}로 환산한 전사 매출은 {_money(cmp['rev'])}({_money(cmp['lo'])}~{_money(cmp['hi'])})다(다른 사업이 같은 속도로 움직인다는 가정). "
            else:
                cmp = None
                head += "세그먼트 비중을 몰라 전사 가이던스와 비교하지 않는다. "
        if cmp and guide:
            head += f"가이던스는 이보다 {_compare(guide, cmp['lo'], cmp['hi'], cmp['rev'])}, "
        if cmp and cons:
            head += f"컨센서스는 {_compare(cons, cmp['lo'], cmp['hi'], cmp['rev'])}다."
    if sy.get("why"):
        head += " " + str(sy["why"])
    rows = []
    shown = c["chosen"] + [r for r in c["rows"] if r["ind"].get("origin") == "모델 지정" and r not in c["chosen"]]
    for r in shown:
        f, o, n = r["rev"], r["op"], r["next"]
        rows.append([r["ind"]["label"], r["target"], r["basis"] or "표본 부족", UNKNOWN if not f else f"{f['lag']}분기({f['lag'] * 3}개월)", UNKNOWN if not f else f"{f['r'] * 100:.0f}%(t {f['t']:.1f})",
                     UNKNOWN if not o else f"{o['r'] * 100:.0f}%({o['lag']}분기)", UNKNOWN if not f else f"{f['hit'] * 100:.0f}%",
                     UNKNOWN if not f else f"{f['n']}·{reliability(f['n'])}", UNKNOWN if not n else f"{_pct(n['g'], 1)} → {_money(n['rev'])}" + (f"({n['how']})" if n.get("how") else "")])
    B = [{"type": "hl", "text": head},
         {"type": "table", "title": "지표별 싱크로율(상관계수 × 100) — 위 두 줄이 제품 연관성 × 싱크로율로 고른 PPI·수출입 세부 지표", "headers": ["지표", "비교 대상", "증가율 기준", "지표 선행", "매출(t값)", "영업이익", "방향 일치", "표본·신뢰", f"{c['next']} 내포 매출"], "rows": rows}]
    cand_rows = [[r["ind"]["label"] + (" ✔" if r["chosen"] else ""), {"ppi": "PPI", "trade": "수출입"}[kind(r["ind"])], f"{r['rel']:.2f}",
                  UNKNOWN if not r["rev"] else f"{r['rev']['r'] * 100:.0f}%({r['rev']['lag']}분기)", f"{r['score']:.2f}", r["ind"].get("origin", "")]
                 for r in sorted(c["rows"], key=lambda r: -r["score"])[:12]]
    B.append({"type": "table", "title": f"지표 후보 {len(c['rows'])}개 — 연관성(제품 품목 일치 × 대용 감점 × 매출 비중) × 싱크로율로 고른다. 후보가 많을수록 최대 상관은 우연히 부풀 수 있다",
              "headers": ["후보", "종류", "연관성", "싱크로율(선행)", "점수", "출처"], "rows": cand_rows})
    win = window(c["last"])
    lv = level_chart({**c, "rows": c["chosen"] or [top]}, win, top)
    if lv:
        B.append({"type": "chart", "chart": lv})
    k = top["k"]
    cg, full_ig = growth(c["rev"], k), growth(top["iq"], k)
    pts_c = [[q, round(cg[q] * 100, 1)] for q in win if q in cg]
    lag_label = f"{top['ind']['label']}({fr['lag']}분기 앞당김)" if fr["lag"] else top["ind"]["label"]
    pts_i = [[q, round(full_ig[shift_q(q, -fr["lag"])] * 100, 1)] for q in win if q in cg and shift_q(q, -fr["lag"]) in full_ig]
    gser = [{"name": "매출", "color": "a", "points": pts_c}, {"name": lag_label, "color": "b", "points": pts_i}]
    if nx and pts_c:   # 다음 분기 추정을 마지막 실적에서 이어 그린다
        gser.append({"name": f"다음 분기 추정({nx['how']}, ±1σ {_pct(nx['g'] - nx['se'], 0)}~{_pct(nx['g'] + nx['se'], 0)})", "color": "e",
                     "points": [pts_c[-1], [c["next"], round(nx["g"] * 100, 1)]]})
    B.append({"type": "chart", "chart": {"kind": "line", "title": f"매출과 {top['ind']['label']} 증가율({top['basis']}, 최근 {WINDOW}개 분기 + 다음 분기 추정)", "unit": "%", "series": gser}})
    if nx and cmp and (guide or cons):
        cats, vals = ["지표 내포" + ("(전사 환산)" if cmp is not nx else ""), "−1σ", "+1σ"], [cmp["rev"], cmp["lo"], cmp["hi"]]
        if guide:
            cats.append("가이던스")
            vals.append(guide)
        if cons:
            cats.append("컨센서스")
            vals.append(cons)
        sc = 1e9 if max(vals) >= 1e9 else 1e6
        B.append({"type": "chart", "chart": {"kind": "bars", "w": 480, "title": f"{c['next']} 매출 — 지표 추세 vs 가이던스·컨센서스", "unit": "B" if sc == 1e9 else "M",
                                             "categories": cats, "series": [{"name": "매출", "color": "a", "values": [round(v / sc, 2 if sc == 1e9 else 0) for v in vals]}]}})
    pth = [r for r in ok if r["path"]]
    if pth:   # 선행 지표로 본 향후 분기 세그먼트 매출 전망
        prow = [[r["ind"]["label"], r["target"], p["q"], _pct(p["x"], 1), _pct(p["g"], 1), f"{_money(p['rev'])}({_money(p['lo'])}~{_money(p['hi'])})"]
                for r in pth for p in r["path"]]
        B.append({"type": "table", "title": "선행 지표로 본 향후 분기 매출 전망(이미 나온 지표 값 기준, ±1σ)", "headers": ["지표", "대상", "분기", "지표 증가율", "내포 매출 증가율", "내포 매출"], "rows": prow})
        B.append({"type": "p", "text": "지표가 k분기 앞서면 이미 발표된 지표로 k분기 뒤까지의 매출 증가율을 회귀식으로 읽는다. 표본이 작거나 t값이 2 미만이면 전망은 참고용이다."})
    B.append({"type": "table", "title": "지표를 고른 이유", "headers": ["지표", "이유"], "rows": [[r["ind"]["label"], r["ind"].get("why", "")] for r in shown]})
    B.append({"type": "p", "text": "싱크로율은 증가율의 상관계수이며 인과가 아니다. 지표 단위·통화는 원자료 그대로이고 나라끼리 더하지 않는다(EU 수입만 상대국 합계). ±1σ는 회귀 잔차 표준편차이고, 지표를 예측한 분기는 지표 예측 오차까지 더해 넓혔다."})
    return {"h2": "거시 지표 싱크로율", "blocks": B}

