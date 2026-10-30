"""EPS 리비전 시계열 — 텐배거 리포트 그림 5·8 (마스터 지시 2026-10-30 "그림 8의 주가 변화 분해 = EPS 리비전 × 멀티플 변화도 최근 4개 분기로 시계열을 그려라",
"그림 5는 … 지난 12개월(캘린더) 기준 EPS 리비전 추이로 대체하라. 실적 발표 또는 내러티브 변화 때마다 EPS 리비전이 어떻게 변했는지도 표기하라")

재료: datapack consensus.eps_history(본보기 scripts/fiscal/templates/eps_history.js → scripts/fiscal/adapter.py --eps-history) +
      datapack revision_events + knowledge/models/companies/<id>/ohlcv.csv(종가).
  consensus.eps_history = {"rows": [["A"|"Q", 기간 끝, asOf 또는 null, 평균, 애널리스트 수], …], "source": "…"}
  revision_events = [{"date": "2026-02-23", "kind": "실적"|"내러티브", "tag": "4Q25 실적", "q": "4Q25", "session": "after"|"before"|"intraday"}, …]
계산:
  ① 캘린더 연도 EPS — 회계연도가 12월이 아니면 두 회계연도를 달 수로 가중. 연간 추정이 갱신되지 않고 분기 추정만 바뀌면 그 차이를 연간 값에 더한다.
  ② 그림 5 — 지난 12개월 캘린더 EPS 계단선 + 사건 깃발, 사건마다 전(사건 전날까지) → 후(최대 14일, 다음 사건 전날까지) 변화.
     실적 창(발표 뒤 14일) 안의 내러티브 사건은 EPS 변화를 분리할 수 없어 '실적 창과 겹침'으로 표기한다.
  ③ 그림 8 — 실적 발표 사이 구간 4개. 구간 시작의 선행 12개월 기간을 고정해(같은 기간끼리) 리비전을 재고,
     (1 + 주가) = (1 + EPS 리비전) × (1 + 멀티플) 로 멀티플 변화를 계산한다. 시간이 지나 기간이 앞으로 굴러가는 효과는 멀티플 쪽에 남는다.
"""
import csv
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WINDOW_DAYS = 14


def _d(s):
    return date.fromisoformat(str(s)[:10])


def load_hist(rows):
    """{'A': {기간 끝: [(asOf, 평균, n)…]}, 'Q': …} — asOf가 없는 첫 값은 맨 앞(date.min)"""
    out = {"A": {}, "Q": {}}
    for r in rows or []:
        kind, end, asof, mean, n = (list(r) + [None])[:5]
        if mean is None or kind not in out:
            continue
        out[kind].setdefault(_d(end), []).append((_d(asof) if asof else date.min, float(mean), n))
    for k in out.values():
        for v in k.values():
            v.sort(key=lambda x: x[0])
    return out


def at(hist, day, strict=False):
    """day까지(strict면 day 전날까지) 알려진 최신 값"""
    last = None
    for row in hist:
        if row[0] < day or (not strict and row[0] == day):
            last = row
    return last


def fy_value(h, end, day, strict=False):
    """회계연도 EPS — 연간 추정 + 그 뒤에 바뀐 분기 추정의 차이"""
    a = at(h["A"].get(end) or [], day, strict)
    if not a:
        return None
    adj = 0.0
    for qe, qh in h["Q"].items():
        if not (end - timedelta(days=360) < qe <= end):
            continue
        now, then = at(qh, day, strict), at(qh, a[0])
        if now and then and now[0] > a[0]:
            adj += now[1] - then[1]
    return a[1] + adj


def _fy_tag(end):
    """회계연도 끝의 (연, 월) — 1월 초에 끝나는 해는 전년 12월로 본다"""
    d = end - timedelta(days=15)
    return (d.year, d.month) if end.day <= 15 or end.month == 1 else (end.year, end.month)


def cy_value(h, year, day, strict=False):
    """캘린더 연도 EPS. 12월 결산이면 그 회계연도, 아니면 두 회계연도를 달 수로 가중"""
    ends = {_fy_tag(e)[0]: e for e in h["A"]}
    e = ends.get(year)
    if e is None:
        return None
    m = _fy_tag(e)[1]
    v = fy_value(h, e, day, strict)
    if m == 12 or v is None:
        return v
    n = ends.get(year + 1)
    w = fy_value(h, n, day, strict) if n else None
    return None if w is None else m / 12 * v + (12 - m) / 12 * w


def ntm_weight(day):
    return (date(day.year, 12, 31) - day).days / 365


def ntm_fixed(h, base, day, strict=False):
    """base 시점의 선행 12개월 기간을 고정한 EPS(같은 기간끼리) — day 시점 추정으로"""
    w = ntm_weight(base)
    a, b = cy_value(h, base.year, day, strict), cy_value(h, base.year + 1, day, strict)
    if a is None or b is None:
        return None
    return w * a + (1 - w) * b


def trend(h, start, end):
    """지난 12개월 캘린더 연도별 계단선 [(날짜, 값)…] — 값이 바뀐 날만 점을 찍는다"""
    days = sorted({d for kind in h.values() for hist in kind.values() for d, _, _ in hist if start < d <= end})
    out = {}
    for y in (end.year, end.year + 1):
        pts = []
        for d in [start] + days:
            v = cy_value(h, y, d)
            if v is not None and (not pts or abs(pts[-1][1] - v) > 1e-9):
                pts.append((d, round(v, 2)))
        if pts:
            out[y] = pts
    return out


def load_prices(entity):
    p = ROOT / "knowledge" / "models" / "companies" / str(entity) / "ohlcv.csv"
    if not p.exists():
        return {}
    with p.open(encoding="utf-8") as f:
        rows = list(csv.DictReader(line for line in f if not line.startswith("#")))
    return {_d(r["date"]): float(r["c"]) for r in rows if r.get("c")}


def price_on(px, day):
    """그날(휴장이면 직전 거래일) 종가"""
    ds = [d for d in px if d <= day]
    return (px[max(ds)], max(ds)) if ds else (None, None)


def reaction(px, ev):
    """사건이 시장에 반영된 하루의 주가 변화. 장후 발표면 다음 거래일, 그 밖엔 그날"""
    days = sorted(px)
    day = _d(ev["date"])
    if ev.get("session") == "after":
        nxt = [d for d in days if d > day]
        prev = [d for d in days if d <= day]
    else:
        nxt = [d for d in days if d >= day]
        prev = [d for d in days if d < day]
    if not nxt or not prev:
        return None
    return px[nxt[0]] / px[prev[-1]] - 1


def event_rows(h, events, px, end):
    """사건별 EPS 전 → 후. 실적 창 안의 내러티브 사건은 겹침으로 표시"""
    evs = sorted(events or [], key=lambda e: e["date"])
    earn = [_d(e["date"]) for e in evs if e.get("kind") == "실적"]
    y0, y1 = end.year, end.year + 1
    out = []
    for i, e in enumerate(evs):
        d = _d(e["date"])
        nxt = [_d(x["date"]) for x in evs[i + 1:] if _d(x["date"]) > d]
        if e.get("kind") == "실적":
            nxt = [x for x in earn if x > d]
        stop = min([d + timedelta(days=WINDOW_DAYS), end] + [x - timedelta(days=1) for x in nxt[:1]])
        overlap = e.get("kind") != "실적" and any(x <= d <= x + timedelta(days=WINDOW_DAYS) for x in earn)
        row = {**e, "overlap": overlap, "reaction": reaction(px, e)}
        for key, y in (("a", y0), ("b", y1)):
            before, after = cy_value(h, y, d, strict=True), cy_value(h, y, stop)
            row[key] = (before, after)
        b0, b1 = row["b"]
        row["rev"] = None if overlap or not b0 or b1 is None else b1 / b0 - 1
        out.append(row)
    return out


def decompose(h, events, px, n=4):
    """실적 발표 사이 구간 n개 — 마지막 구간은 마지막 가격일까지. 마지막 실적이 30일 안이면 그 앞 구간에 포함"""
    last = max(px)
    earn = sorted((e for e in events or [] if e.get("kind") == "실적"), key=lambda e: e["date"])
    if earn and (last - _d(earn[-1]["date"])).days <= 30:
        earn = earn[:-1]
    earn = earn[-n:]
    bounds = [(_d(e["date"]) if e.get("session") == "after" else _d(e["date"]) - timedelta(days=1)) for e in earn] + [last]
    out = []
    for i in range(len(bounds) - 1):
        s, t = bounds[i], bounds[i + 1]
        p0, d0 = price_on(px, s)
        p1, d1 = price_on(px, t)
        e0, e1 = ntm_fixed(h, s, s), ntm_fixed(h, s, t)
        if not p0 or not p1 or not e0 or e1 is None:
            continue
        price, rev = p1 / p0 - 1, e1 / e0 - 1
        n0, n1 = ntm_fixed(h, s, s), ntm_fixed(h, t, t)
        out.append({"label": f"{earn[i].get('q') or earn[i]['tag']} 후", "from": d0, "to": d1, "p0": p0, "p1": p1, "price": price, "rev": rev,
                    "rerate": (1 + price) / (1 + rev) - 1, "pe0": p0 / n0 if n0 else None, "pe1": p1 / n1 if n1 else None})
    return out


def _sign(x, nd=0):
    return "-" if x is None else f"{x * 100:+.{nd}f}%"


def _usd(x):
    return "-" if x is None else f"${x:,.2f}"


CIRCLE = "①②③④⑤⑥⑦⑧⑨⑩⑪⑫⑬⑭⑮⑯⑰⑱⑲⑳"


def blocks(dp):
    """그림 5(pin 5)·그림 8(pin 8)과 표. 재료가 없으면 빈 목록 → earnings_view가 옛 단일 구간 분해를 쓴다"""
    cons = dp.get("consensus") or {}
    hist = cons.get("eps_history") or {}
    px = load_prices(dp.get("id"))
    if not hist.get("rows") or not px or not dp.get("revision_events"):
        return []
    h = load_hist(hist["rows"])
    end = max(px)
    start = end - timedelta(days=372)
    tr = trend(h, start, end)
    ev = [r for r in event_rows(h, dp["revision_events"], px, end) if _d(r["date"]) >= start]
    for i, r in enumerate(ev):
        r["mark"] = CIRCLE[i] if i < len(CIRCLE) else str(i + 1)
    colors = {end.year: "c", end.year + 1: "b"}
    ns = sorted({row[2] for k in h.values() for v in k.values() for row in v if row[2]})
    n_txt = f"EPS 추정 표본 {ns[0]}명" if ns and ns[0] == ns[-1] else (f"EPS 추정 표본 {ns[0]}~{ns[-1]}명" if ns else "")
    B = [{"type": "chart", "chart": {"kind": "revision", "pin": 5, "title": f"지난 12개월 EPS 리비전 추이 — 캘린더 {end.year}·{end.year + 1}년 EPS 추정($/주), 사건별 표기",
                                     "unit": "$", "start": start.isoformat(), "end": end.isoformat(),
                                     "series": [{"name": f"CY{y} EPS 추정", "color": colors[y], "points": [[d.isoformat(), v] for d, v in pts]} for y, pts in tr.items()],
                                     "events": [{"date": r["date"], "mark": r["mark"], "kind": r.get("kind"), "tag": r.get("tag"),
                                                 "pct": ("겹침" if r["overlap"] else _sign(r["rev"]))} for r in ev],
                                     "note": f"계단선 = 조정 EPS 추정이 바뀐 날. 숫자 = 사건 전 → 후 CY{end.year + 1} EPS 변화. 파란 점선 실적, 금색 점선 내러티브. {n_txt}."}}]
    rows = []
    for r in ev:
        a0, a1 = r["a"]
        b0, b1 = r["b"]
        rows.append([r["mark"], r["date"][2:], r.get("kind", ""), r.get("tag", ""), f"{_usd(a0)} → {_usd(a1)}", f"{_usd(b0)} → {_usd(b1)}",
                     "실적 창과 겹침" if r["overlap"] else _sign(r["rev"], 1), _sign(r["reaction"], 1)])
    B.append({"type": "table", "title": "사건별 EPS 리비전 — 실적 발표·내러티브 변화 때 추정이 어떻게 움직였나",
              "headers": ["#", "날짜", "구분", "사건", f"CY{end.year} EPS 전→후", f"CY{end.year + 1} EPS 전→후", "리비전", "주가 반응"], "rows": rows,
              "note": f"전 = 사건 전날까지, 후 = 최대 {WINDOW_DAYS}일(다음 사건 전날까지). 주가 반응 = 장후 발표는 다음 거래일, 그 밖은 그날. {n_txt}."})
    dec = decompose(h, dp["revision_events"], px)
    if dec:
        B.append({"type": "chart", "chart": {"kind": "bars", "pin": 8, "w": 440, "title": "최근 4개 분기 주가 변화 분해 = EPS 리비전 × 멀티플 변화 (%, 실적 발표 사이 구간)", "unit": "%",
                                             "categories": [x["label"] for x in dec],
                                             "series": [{"name": "주가", "color": "a", "values": [round(x["price"] * 100, 1) for x in dec]},
                                                        {"name": "EPS 리비전", "color": "d", "values": [round(x["rev"] * 100, 1) for x in dec]},
                                                        {"name": "멀티플 변화", "color": "b", "values": [round(x["rerate"] * 100, 1) for x in dec]}],
                                             "note": f"(1 + 주가) = (1 + EPS 리비전) × (1 + 멀티플 변화). EPS는 구간 시작의 선행 12개월 기간을 고정해 같은 기간끼리 비교."}})
        B.append({"type": "table", "title": "분기별 주가 분해 — 실적 발표 사이 구간",
                  "headers": ["구간", "기간", "주가", "EPS 리비전", "멀티플 변화", "선행 P/E 시작 → 끝"],
                  "rows": [[x["label"], f"{x['from'].isoformat()[2:]} ~ {x['to'].isoformat()[2:]}", f"${x['p0']:,.2f} → ${x['p1']:,.2f} ({_sign(x['price'])})", _sign(x["rev"]), _sign(x["rerate"]),
                            f"{x['pe0']:.1f}배 → {x['pe1']:.1f}배" if x["pe0"] and x["pe1"] else "-"] for x in dec]})
        cum = {k: 1.0 for k in ("price", "rev", "rerate")}
        for x in dec:
            for k in cum:
                cum[k] *= 1 + x[k]
        who = "멀티플" if abs(cum["rerate"] - 1) > abs(cum["rev"] - 1) else "EPS 리비전"
        B.append({"type": "p", "text": f"**해석:** {len(dec)}개 구간 누적 주가 {_sign(cum['price'] - 1)} = EPS 리비전 {_sign(cum['rev'] - 1)} × 멀티플 {_sign(cum['rerate'] - 1)}. 더 크게 움직인 쪽은 **{who}**이다."})
    return B
