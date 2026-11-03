"""텐배거 리포트 'P·Q 사이클' 절 (마스터 지시 2026-11-03 "이 기업이 구조적인 Q사이클과 구조적인 P사이클 중 어떤 사이클에 직면해 있고
앞으로 몇 분기가 지나면 다른 사이클로 전환하는지 그래프로 시각화하고 P와 Q사이클의 정도를 정량화하라")

매출 = P(가격) × Q(물량). 전년 대비 로그 증가율로 나눈다: g_매출 = g_P + g_Q. 숫자는 여기서 계산하고 모델은 가격·물량 근거만 고른다.
datapack "pq":
  {"why": "이 회사 가격·물량을 무엇으로 재는가 한 줄",
   "price": {"source": "asp", "series": {"2025-09-27": 12.4, …}, "unit": "$/개"}          # 회사 공시 ASP(분기 끝 날짜 → 값)
          | {"source": "ppi", "input": "pcb", "country": "us"}                             # 제품 PPI(config/trade_ppi.yaml)를 가격 대용
   "volume": {"series": {"2025-09-27": 1.2, …}, "unit": "백만 개"}}                         # 선택 — 출하량을 공시하면 P = 매출 ÷ 물량
  가격·물량을 잴 수 없으면 {"none": "이유"}.
매출은 datapack "quarters_hist"(scripts/tenbagger/quarters.py).

정량화(IB 사이클 분석 방식):
- 국면: 최근 4분기 평균 g_P·g_Q로 P 사이클(g_P > g_Q, g_P > 0) / Q 사이클(g_Q > g_P, g_Q > 0) / 동반 하강.
- 강도(0~10): 자기 이력 대비 z값 → 5 + 2z(0~10으로 자른다). 구조성: 최근 8분기 중 같은 요인이 우세했던 비율.
- 마진 확인: P 사이클인데 GPM이 오르지 않으면 원가 전가형(가짜 P)으로 표시한다.
- 전환 시점: g_P·g_Q 각각 AR(2)(y_t = c + a1·y_t-1 + a2·y_t-2)를 맞춰 8분기 앞까지 투영하고, 우세 요인이 처음 바뀌는 분기를 센다.
  AR(2) 특성근이 복소수면 고유 주기 2π ÷ arccos(a1 ÷ 2√−a2)도 낸다. 투영은 통계 외삽이며 가이던스가 아니다.
"""
import math

import sync_view as sv

UNKNOWN = "미확인"
MIN_POINTS = 8
HORIZON = 8


def _quarterly(series):
    out = {}
    for d, v in (series or {}).items():
        if v:
            out[sv.qlabel(str(d))[0]] = float(v)
    return out


def decompose(dp, history=None, db=sv.HS_DB):
    pq = dp["pq"]
    qs = [r for r in (dp.get("quarters_hist") or {}).get("q") or [] if r.get("rev")]
    rev, ends, gpm = {}, {}, {}
    for r in qs:
        lab, ym = sv.qlabel(r["period"])
        rev[lab], ends[lab] = float(r["rev"]), ym
        gp = r.get("gp") if r.get("gp") is not None else (r["rev"] - r["cogs"] if r.get("cogs") is not None else None)
        if gp is not None:
            gpm[lab] = gp / r["rev"]
    vol = _quarterly((pq.get("volume") or {}).get("series"))
    pr = pq.get("price") or {}
    if vol:
        price = {q: rev[q] / vol[q] for q in rev if vol.get(q)}
    elif pr.get("source") == "asp":
        price = _quarterly(pr.get("series"))
    elif pr.get("source") == "ppi":
        price = sv.quarterize(sv.monthly({"source": "ppi", "input": pr["input"], "country": pr["country"]}, history, db), ends, True)
    else:
        price = {}
    rows = []
    for q in sorted(rev):
        b = sv.shift_q(q, -4)
        if b in rev and q in price and b in price and price[b] and rev[b]:
            gr, gp_ = math.log(rev[q] / rev[b]), math.log(price[q] / price[b])
            rows.append({"q": q, "g_rev": gr, "g_p": gp_, "g_q": gr - gp_, "gpm": gpm.get(q), "gpm_prev": gpm.get(b)})
    return rows


def ar2(y):
    """(c, a1, a2) 최소제곱 — 정규방정식 3×3"""
    X = [(1.0, y[i - 1], y[i - 2]) for i in range(2, len(y))]
    Y = y[2:]
    A = [[sum(x[i] * x[j] for x in X) for j in range(3)] for i in range(3)]
    b = [sum(x[i] * t for x, t in zip(X, Y)) for i in range(3)]
    for i in range(3):   # 가우스 소거
        p = max(range(i, 3), key=lambda r: abs(A[r][i]))
        A[i], A[p], b[i], b[p] = A[p], A[i], b[p], b[i]
        if abs(A[i][i]) < 1e-12:
            return None
        for r in range(3):
            if r != i:
                f = A[r][i] / A[i][i]
                A[r] = [a - f * c for a, c in zip(A[r], A[i])]
                b[r] -= f * b[i]
    return tuple(b[i] / A[i][i] for i in range(3))


def period(a1, a2):
    if a2 >= 0 or a1 * a1 + 4 * a2 >= 0:
        return None
    x = a1 / (2 * math.sqrt(-a2))
    return 2 * math.pi / math.acos(max(-1.0, min(1.0, x)))


def project(y, coef, n=HORIZON):
    c, a1, a2 = coef
    out, h = [], list(y)
    for _ in range(n):
        v = c + a1 * h[-1] + a2 * h[-2]
        v = max(-1.5, min(1.5, v))   # 로그 증가율 폭주 방지
        out.append(v)
        h.append(v)
    return out


def regime(gp, gq):
    if gp < 0 and gq < 0:
        return "동반 하강"
    return "P 사이클" if gp >= gq else "Q 사이클"


def strength(xs):
    m = sum(xs) / len(xs)
    s = math.sqrt(sum((x - m) ** 2 for x in xs) / max(len(xs) - 1, 1)) or 1
    return max(0.0, min(10.0, 5 + 2 * (sum(xs[-4:]) / len(xs[-4:]) - m) / s))


def compute(dp, history=None, db=sv.HS_DB):
    rows = decompose(dp, history, db)
    if len(rows) < 4:
        return {"rows": rows, "enough": False}
    gp, gq = [r["g_p"] for r in rows], [r["g_q"] for r in rows]
    mp, mq = sum(gp[-4:]) / 4, sum(gq[-4:]) / 4
    now = regime(mp, mq)
    last8 = rows[-8:]
    dom = "P" if now == "P 사이클" else ("Q" if now == "Q 사이클" else None)
    persist = None if not dom else sum(1 for r in last8 if (r["g_p"] >= r["g_q"]) == (dom == "P")) / len(last8)
    gpm_up = None
    if rows[-1]["gpm"] is not None and rows[-1]["gpm_prev"] is not None:
        gpm_up = rows[-1]["gpm"] - rows[-1]["gpm_prev"]
    out = {"rows": rows, "enough": True, "now": now, "mp": mp, "mq": mq, "p_score": strength(gp), "q_score": strength(gq), "persist": persist, "gpm_chg": gpm_up,
           "fake_p": now == "P 사이클" and gpm_up is not None and gpm_up <= 0, "proj": None, "switch": None, "period": None}
    if len(rows) >= MIN_POINTS:
        cp, cq = ar2(gp), ar2(gq)
        if cp and cq:
            pp, pq_ = project(gp, cp), project(gq, cq)
            last = rows[-1]["q"]
            proj = [{"q": sv.shift_q(last, i + 1), "g_p": a, "g_q": b} for i, (a, b) in enumerate(zip(pp, pq_))]
            cur = mp >= mq
            sw = next((i + 1 for i, p in enumerate(proj) if (p["g_p"] >= p["g_q"]) != cur), None)
            out.update({"proj": proj, "switch": sw, "period": {"P": period(cp[1], cp[2]), "Q": period(cq[1], cq[2])}})
    return out


def _pct(x):
    return UNKNOWN if x is None else f"{x * 100:+.1f}%"


def section(dp, history=None, db=sv.HS_DB):
    pq = (dp or {}).get("pq")
    if not pq:
        raise SystemExit("datapack에 pq가 없다(scripts/tenbagger/pq_view.py 맨 위) — 가격·물량을 잴 수 없으면 {'none': '이유'}, 옛 리포트 정정은 --legacy")
    if pq.get("none"):
        return None
    c = compute(dp, history, db)
    if not c["enough"]:
        return {"h2": "P·Q 사이클", "blocks": [{"type": "hl", "text": f"**가격·물량을 나눌 표본이 부족하다(전년 대비 {len(c['rows'])}분기).** 가격 근거({pq.get('price', {}).get('source', '물량')})의 이력이 쌓이면 다시 잰다."}]}
    head = f"**{c['now']} — 최근 4분기 평균 가격 기여 {_pct(c['mp'])}, 물량 기여 {_pct(c['mq'])}(전년 대비 로그 증가율).** P 강도 {c['p_score']:.1f}/10, Q 강도 {c['q_score']:.1f}/10"
    if c["persist"] is not None:
        head += f", 최근 8분기 중 {c['persist'] * 100:.0f}%가 같은 요인 우세({'구조적' if c['persist'] >= 0.75 else '순환적'})"
    head += "."
    if c["fake_p"]:
        head += f" 다만 GPM이 전년보다 {c['gpm_chg'] * 100:+.1f}%p로 오르지 않아 원가 전가형 가격 상승일 가능성이 있다."
    if c["proj"]:
        other = "Q 사이클" if c["mp"] >= c["mq"] else "P 사이클"
        head += f" AR(2) 투영으로는 {f'{c['switch']}분기 뒤({c['proj'][c['switch'] - 1]['q']}) {other}로 전환' if c['switch'] else f'{HORIZON}분기 안에 전환 신호가 없다'}."
    if pq.get("why"):
        head += " " + str(pq["why"])
    rows = c["rows"]
    B = [{"type": "hl", "text": head}]
    hist_p = [[r["q"], round(r["g_p"] * 100, 1)] for r in rows]
    hist_q = [[r["q"], round(r["g_q"] * 100, 1)] for r in rows]
    series = [{"name": "가격(P) 기여", "color": "b", "points": hist_p}, {"name": "물량(Q) 기여", "color": "c", "points": hist_q}]
    if c["proj"]:
        lastp, lastq = hist_p[-1], hist_q[-1]
        series += [{"name": "P 투영", "color": "e", "points": [lastp] + [[p["q"], round(p["g_p"] * 100, 1)] for p in c["proj"]]},
                   {"name": "Q 투영", "color": "d", "points": [lastq] + [[p["q"], round(p["g_q"] * 100, 1)] for p in c["proj"]]}]
    B.append({"type": "chart", "chart": {"kind": "line", "title": "매출 증가율의 가격·물량 분해와 AR(2) 투영(전년 대비)", "unit": "%", "series": series}})
    B.append({"type": "chart", "chart": {"kind": "bars", "title": "분기별 매출 증가율 분해", "unit": "%", "categories": [r["q"] for r in rows[-8:]],
                                         "series": [{"name": "가격(P)", "color": "b", "values": [round(r["g_p"] * 100, 1) for r in rows[-8:]]},
                                                    {"name": "물량(Q)", "color": "c", "values": [round(r["g_q"] * 100, 1) for r in rows[-8:]]}]}})
    per = c.get("period") or {}
    B.append({"type": "table", "title": "P·Q 사이클 정량", "headers": ["항목", "가격(P)", "물량(Q)"],
              "rows": [["최근 4분기 평균 기여", _pct(c["mp"]), _pct(c["mq"])], ["강도(0~10, 자기 이력 z)", f"{c['p_score']:.1f}", f"{c['q_score']:.1f}"],
                       ["AR(2) 고유 주기", UNKNOWN if not per.get("P") else f"{per['P']:.1f}분기", UNKNOWN if not per.get("Q") else f"{per['Q']:.1f}분기"],
                       ["다음 4분기 투영 평균", UNKNOWN if not c["proj"] else _pct(sum(p["g_p"] for p in c["proj"][:4]) / 4), UNKNOWN if not c["proj"] else _pct(sum(p["g_q"] for p in c["proj"][:4]) / 4)]]})
    src = pq.get("price", {}).get("source") if not pq.get("volume") else "출하량 공시"
    B.append({"type": "p", "text": f"가격 근거: {src}. PPI를 쓰면 회사 판매가가 아니라 업종 가격 대용이다. 로그 증가율이라 가격·물량 기여의 합이 매출 증가율이다. 투영은 통계 외삽이며 가이던스·컨센서스가 아니다."})
    return {"h2": "P·Q 사이클", "blocks": B}
