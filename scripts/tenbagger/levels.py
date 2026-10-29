"""가격 구간 — 월봉·주봉·일봉 피보나치와 다수 투자자가 보는 기준선의 겹침 (마스터 지시 2026-10-29 "월봉·주봉·일봉으로 나눠 피보나치 기법을
적용해 어디 구간에 저항선과 지지선이 있는지 표기해 진입 시점도 직관적으로 파악할 수 있게. 유명한 기술 논문을 바탕으로 다수의 투자자들이
사용하는 기법으로 — 아무도 안 쓰는 특이한 기법은 유의미하지 않다")

기법(모두 널리 쓰이는 것만)
  ① 스윙 고점·저점 — 지그재그(ZigZag): 마지막 극값에서 임계 % 이상 반대로 움직이면 그 극값을 확정. 임계값 = max(하한, 2.5 × ATR(14) ÷ 가격)
     — 변동성에 맞춘 ATR 지그재그(실무 관행). 하한 월 20%·주 10%·일 5%(사전값, knowledge/models/params/registry.yaml levels.*).
  ② 피보나치 되돌림 23.6·38.2·50·61.8·78.6%, 확장 127.2·161.8% — 시간 단위별 '지배 스윙'에 그린다.
     월봉: 확보한 전체 구간 최저↔최고(장기 일봉이 없으면 datapack raw.anchors의 확인 범위 최저·최고) / 주봉: 최근 52주 최저↔최고 /
     일봉: 지그재그 마지막 완료 다리. 방향은 저점·고점의 날짜 순서로 정한다(상승 다리면 고점에서 아래로, 하락 다리면 저점에서 위로).
  ③ 이동평균 50·200일, 거래 범위 고·저(50·150·200일 최고·최저) — Brock, Lakonishok & LeBaron (1992, Journal of Finance)
     "Simple Technical Trading Rules and the Stochastic Properties of Stock Returns"가 검증한 이동평균·거래 범위 돌파 규칙의 기준선.
  ④ 라운드 넘버 — Osler (2003, Journal of Finance) "Currency Orders and Exchange Rate Dynamics": 지정가·손절 주문이 라운드 가격에 몰려
     지지·저항이 생긴다. Osler (2000, FRBNY Economic Policy Review) "Support for Resistance": 공개된 지지·저항 수준에서 추세가 멈추는 빈도가 높다.
  겹침(confluence): 서로 다른 기준선이 ±1.2% 폭 안에 모이면 한 구간으로 묶고 강도 = 겹친 기준선 수(라운드 넘버는 0.5).
  해석 주의: 피보나치 비율 자체의 학술 근거는 약하다. 효과가 있다면 다수가 같은 선을 보고 주문을 거기에 두기 때문(Osler)이다 —
  그래서 여러 기준선이 겹친 구간만 강하게 본다.
출력: 지지·저항 각 3구간(현재가 대비 %)과 시간 단위별 캔들 차트(수평선·구간 띠). 가격 구간 지표일 뿐 매수·매도 권유가 아니다.
사용: v2_to_report가 '가격 구간 — 월·주·일 피보나치' 절로 넣는다. 단독: py scripts/tenbagger/levels.py <entity_id>
"""
import json
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import flow  # noqa: E402

FIB_RET = (0.236, 0.382, 0.5, 0.618, 0.786)
FIB_EXT = (1.272, 1.618)
_L = ((__import__("yaml").safe_load((flow.ROOT / "config" / "report_tools.yaml").read_text(encoding="utf-8")) or {}).get("levels") or {})     if (flow.ROOT / "config" / "report_tools.yaml").exists() else {}   # 등록부 prm-lv-*
ZZ = {k: float(v) for k, v in (_L.get("zz_floor") or {"월봉": 0.20, "주봉": 0.10, "일봉": 0.05}).items()}
ATR_MULT, ATR_N = float(_L.get("atr_mult", 2.5)), int(_L.get("atr_n", 14))
BAND = float(_L.get("band", 0.012))


def atr_pct(bars, n=ATR_N):
    """평균 진폭(ATR, Wilder) ÷ 종가"""
    if len(bars) < n + 1:
        return None
    trs = [max(b["h"] - b["l"], abs(b["h"] - p["c"]), abs(b["l"] - p["c"])) for p, b in zip(bars[-n - 1:-1], bars[-n:])]
    return sum(trs) / n / bars[-1]["c"]


def zz_threshold(bars, kind):
    a = atr_pct(bars)
    return max(ZZ[kind], ATR_MULT * a) if a else ZZ[kind]


def resample(bars, kind):
    """일봉 → 주봉(월요일 시작)·월봉"""
    out = {}
    for b in bars:
        k = flow.week_start(b["date"]) if kind == "W" else b["date"][:7]
        o = out.get(k)
        if not o:
            out[k] = {"date": k, "o": b["o"], "h": b["h"], "l": b["l"], "c": b["c"], "v": b["v"], "hd": b["date"], "ld": b["date"]}
        else:
            if b["h"] > o["h"]:
                o["h"], o["hd"] = b["h"], b["date"]
            if b["l"] < o["l"]:
                o["l"], o["ld"] = b["l"], b["date"]
            o["c"], o["v"] = b["c"], o["v"] + b["v"]
    return [out[k] for k in sorted(out)]


def zigzag(bars, pct):
    """확정된 피벗 [(인덱스, 가격, 'H'|'L', 날짜)] — 고가·저가 기준. 마지막 진행 중 극값은 넣지 않는다"""
    if not bars:
        return []
    piv, trend = [], 0
    hi_i, lo_i = 0, 0
    for i, b in enumerate(bars):
        if b["h"] >= bars[hi_i]["h"]:
            hi_i = i
        if b["l"] <= bars[lo_i]["l"]:
            lo_i = i
        if trend >= 0 and b["l"] <= bars[hi_i]["h"] * (1 - pct) and hi_i < i:
            if trend == 0 or not piv or piv[-1][2] != "H":
                piv.append((hi_i, bars[hi_i]["h"], "H", bars[hi_i].get("hd", bars[hi_i]["date"])))
            trend, lo_i = -1, i
        elif trend <= 0 and b["h"] >= bars[lo_i]["l"] * (1 + pct) and lo_i < i:
            if trend == 0 or not piv or piv[-1][2] != "L":
                piv.append((lo_i, bars[lo_i]["l"], "L", bars[lo_i].get("ld", bars[lo_i]["date"])))
            trend, hi_i = 1, i
    return piv


def fib(low, high, up):
    """up=True: 저점→고점 상승 다리(되돌림은 고점에서 아래로) / False: 고점→저점 하락 다리(되돌림은 저점에서 위로)"""
    rng = high - low
    if up:
        ret = {f"{r * 100:.1f}%": high - r * rng for r in FIB_RET}
        ext = {f"{e * 100:.1f}%": low + e * rng for e in FIB_EXT}
    else:
        ret = {f"{r * 100:.1f}%": low + r * rng for r in FIB_RET}
        ext = {f"{e * 100:.1f}%": high - e * rng for e in FIB_EXT}
    return ret, ext


def dominant(bars, kind, anchors=None):
    """시간 단위별 지배 스윙 {low, high, low_date, high_date, up, basis}"""
    if kind == "일봉":
        th = zz_threshold(bars, "일봉")
        piv = zigzag(bars, th)
        if len(piv) >= 2:
            a, b = piv[-2], piv[-1]
            lo, hi = (a, b) if a[2] == "L" else (b, a)
            return {"low": lo[1], "high": hi[1], "low_date": lo[3], "high_date": hi[3], "up": a[2] == "L", "basis": f"ATR 지그재그 {th * 100:.1f}% 마지막 완료 다리"}
        bars = bars[-84:]
    win = bars[-52:] if kind == "주봉" else bars
    lo_b = min(win, key=lambda b: b["l"])
    hi_b = max(win, key=lambda b: b["h"])
    sw = {"low": lo_b["l"], "high": hi_b["h"], "low_date": lo_b.get("ld", lo_b["date"]), "high_date": hi_b.get("hd", hi_b["date"]),
          "basis": "최근 52주 최저↔최고" if kind == "주봉" else "확보 구간 최저↔최고"}
    if kind == "월봉" and anchors:
        a_lo, a_hi = anchors.get("low") or {}, anchors.get("high") or {}
        if a_lo.get("price") and a_lo["price"] < sw["low"]:
            sw.update(low=a_lo["price"], low_date=a_lo["date"], basis=f"장기 기준점(raw.anchors — {a_lo.get('note', '확인 범위')})")
        if a_hi.get("price") and a_hi["price"] > sw["high"]:
            sw.update(high=a_hi["price"], high_date=a_hi["date"])
    sw["up"] = sw["low_date"] < sw["high_date"]
    return sw


def sma(bars, n):
    return sum(b["c"] for b in bars[-n:]) / n if len(bars) >= n else None


def round_levels(price):
    step = 50 if price >= 200 else 10 if price >= 50 else 5 if price >= 10 else 1
    base = int(price * 0.75 // step) * step
    return [x for x in range(base, int(price * 1.25) + step, step) if x > 0]


def collect_levels(daily, anchors=None):
    price = daily[-1]["c"]
    frames = {"주봉": resample(daily, "W"), "일봉": daily, "월봉": resample(daily, "M")}
    swings, lv = {}, []
    for k, bars in frames.items():
        sw = dominant(bars, k, anchors)
        ret, ext = fib(sw["low"], sw["high"], sw["up"])
        sw["ret"], sw["ext"] = ret, ext
        swings[k] = sw
        if k == "월봉" and (sw["low"], sw["high"]) == (swings["주봉"]["low"], swings["주봉"]["high"]):
            sw["same_as_weekly"] = True   # 장기 일봉·기준점이 없어 월봉 스윙 = 주봉 스윙 — 같은 선을 두 번 세지 않는다
            continue
        for name, v in ret.items():
            lv.append({"price": v, "src": f"{k} 피보 {name}", "kind": f"fib-{k}", "w": 1.0})
        for name, v in ext.items():
            lv.append({"price": v, "src": f"{k} 확장 {name}", "kind": f"fibx-{k}", "w": 1.0})
        lv.append({"price": sw["low"], "src": f"{k} 스윙 저점", "kind": f"swing-{k}", "w": 1.0})
        lv.append({"price": sw["high"], "src": f"{k} 스윙 고점", "kind": f"swing-{k}", "w": 1.0})
    prior = daily[:-1]
    for n in (50, 200):
        v = sma(daily, n)
        if v:
            lv.append({"price": v, "src": f"{n}일 이동평균", "kind": f"ma{n}", "w": 1.0})
    for n in (50, 150, 200):
        if len(prior) >= n:
            lv.append({"price": max(b["h"] for b in prior[-n:]), "src": f"{n}일 최고(거래 범위)", "kind": f"rng{n}h", "w": 1.0})
            lv.append({"price": min(b["l"] for b in prior[-n:]), "src": f"{n}일 최저(거래 범위)", "kind": f"rng{n}l", "w": 1.0})
    for x in round_levels(price):
        lv.append({"price": float(x), "src": f"라운드 ${x}", "kind": "round", "w": 0.5})
    return price, swings, lv


def cluster(levels, band=BAND):
    """가까운 기준선 묶기 — 묶음 첫 값 대비 band 안이면 같은 구간. 강도 = 서로 다른 종류의 가중 합"""
    out = []
    for x in sorted(levels, key=lambda l: l["price"]):
        if out and x["price"] <= out[-1]["lo"] * (1 + band):
            g = out[-1]
            g["items"].append(x)
            g["hi"] = x["price"]
        else:
            out.append({"lo": x["price"], "hi": x["price"], "items": [x]})
    for g in out:
        kinds = {}
        for x in g["items"]:
            kinds[x["kind"]] = max(kinds.get(x["kind"], 0), x["w"])
        g["strength"] = sum(kinds.values())
        g["mid"] = sum(x["price"] for x in g["items"]) / len(g["items"])
    return out


def zones(daily, anchors=None, n=3, min_strength=2.0):
    price, swings, lv = collect_levels(daily, anchors)
    cl = [g for g in cluster(lv) if g["strength"] >= min_strength]
    sup = sorted([g for g in cl if g["hi"] < price * 0.998], key=lambda g: -g["mid"])[:n]
    res = sorted([g for g in cl if g["lo"] > price * 1.002], key=lambda g: g["mid"])[:n]
    at = [g for g in cl if g["lo"] <= price * 1.002 and g["hi"] >= price * 0.998]
    return {"price": price, "swings": swings, "support": sup, "resistance": res, "at": at, "levels": lv}


# ---------- 리포트 절 ----------
def _z(g, price):
    lo, hi = g["lo"], g["hi"]
    rng = f"${lo:,.0f}" if abs(hi - lo) < 0.5 else f"${lo:,.0f}~{hi:,.0f}"
    srcs = sorted({x["src"] for x in g["items"]})
    return [rng, f"{(g['mid'] / price - 1) * 100:+.1f}%", f"{g['strength']:.1f}", " · ".join(srcs)]


def candle_chart(bars, title, sw, zs, price, tail):
    b = bars[-tail:]
    lo_v = min(x["l"] for x in b)
    hi_v = max(x["h"] for x in b)
    hl = [{"y": v, "label": f"{k} {v:,.0f}", "color": "e"} for k, v in sw["ret"].items() if lo_v * 0.9 <= v <= hi_v * 1.1]
    zn = [{"y0": g["lo"] * 0.999, "y1": g["hi"] * 1.001, "label": "지지" if g["mid"] < price else "저항", "tone": "grn" if g["mid"] < price else "red"}
          for g in zs if lo_v * 0.9 <= g["mid"] <= hi_v * 1.1]
    return {"type": "chart", "chart": {"kind": "candle", "title": title, "unit": "$", "bars": [[x["date"], x["o"], x["h"], x["l"], x["c"]] for x in b],
                                       "hlines": hl, "zones": zn,
                                       "note": f"지배 스윙: {sw['basis']} — 저점 ${sw['low']:,.2f}({sw['low_date']}) · 고점 ${sw['high']:,.2f}({sw['high_date']}), "
                                               f"{'상승' if sw['up'] else '하락'} 다리. 점선 = 피보나치 되돌림, 띠 = 겹침 구간(초록 지지·빨강 저항). 캔들: 빨강 상승·파랑 하락."}}


def report_section(entity, dp=None):
    daily = flow.load_ohlcv(entity)
    if len(daily) < 60:   # 상장 3개월 미만은 스윙이 성립하지 않는다(2026-10-30: 상장 후 60~119거래일 종목은 '상장 이후 전체'로 그린다)
        return None
    anchors = ((dp or {}).get("raw") or {}).get("anchors")
    z = zones(daily, anchors)
    price = z["price"]
    sw = z["swings"]
    blocks = []
    s0 = z["support"][0] if z["support"] else None
    r0 = z["resistance"][0] if z["resistance"] else None
    line = f"현재가 ${price:,.2f} — "
    if z["at"]:
        line += f"지금 가격이 겹침 구간 {', '.join(_z(g, price)[0] for g in z['at'])} 안에 있다. "
    if r0:
        line += f"바로 위 저항 {_z(r0, price)[0]}({_z(r0, price)[1]}, 강도 {r0['strength']:.1f}), "
    if s0:
        line += f"바로 아래 지지 {_z(s0, price)[0]}({_z(s0, price)[1]}, 강도 {s0['strength']:.1f})."
    blocks.append({"type": "hl", "text": "**한 줄:** " + line + " 가격 구간 지표일 뿐 매수·매도 권유가 아니다."})
    rows = [["저항 " + str(i + 1)] + _z(g, price) for i, g in enumerate(z["resistance"])][::-1]
    rows += [["현재 구간"] + _z(g, price) for g in z["at"]]
    rows += [["지지 " + str(i + 1)] + _z(g, price) for i, g in enumerate(z["support"])]
    blocks.append({"type": "table", "title": "지지·저항 겹침 구간(서로 다른 기준선이 ±1.2% 안에 모인 곳, 강도 = 겹친 기준선 수)",
                   "headers": ["구간", "가격", "현재가 대비", "강도", "겹친 기준선"], "rows": rows})
    fr = []
    for k in ("월봉", "주봉", "일봉"):
        s = sw[k]
        fr.append([k, f"${s['low']:,.2f}({s['low_date']}) → ${s['high']:,.2f}({s['high_date']})", "상승" if s["up"] else "하락"]
                  + [f"{v:,.1f}" for v in s["ret"].values()])
    blocks.append({"type": "table", "title": "시간 단위별 피보나치 되돌림($)", "headers": ["단위", "지배 스윙", "다리", "23.6%", "38.2%", "50%", "61.8%", "78.6%"], "rows": fr})
    zs = z["support"] + z["resistance"] + z["at"]
    blocks.append(candle_chart(resample(daily, "M"), "월봉 — 장기 스윙 되돌림", sw["월봉"], zs, price, 24))
    blocks.append(candle_chart(resample(daily, "W"), "주봉 — 52주 스윙 되돌림", sw["주봉"], zs, price, 52))
    blocks.append(candle_chart(daily, "일봉 — 마지막 완료 스윙 되돌림(최근 90거래일)", sw["일봉"], zs, price, 90))
    note = "월봉은 확보한 일봉 기간만큼만 그린다"
    if len(daily) < 120:
        note = f"상장 후 {len(daily)}거래일뿐이라 월·주봉 스윙은 상장 이후 전체 구간이다(장기 지지·저항으로 읽지 말 것)"
    if anchors:
        note += f" — 장기 기준점: {anchors.get('low', {}).get('note', '')}"
    blocks.append({"type": "p", "text": "**기법과 근거:** 스윙은 ATR 지그재그(임계 = max(월 20%·주 10%·일 5%, 2.5×ATR14)), 되돌림 23.6~78.6%·확장 127.2·161.8%. 함께 본 기준선: 50·200일 이동평균과 50·150·200일 거래 범위 고저"
                                        "(Brock·Lakonishok·LeBaron 1992, JF), 라운드 넘버($50 단위, Osler 2003 JF·Osler 2000 FRBNY EPR). "
                                        "피보나치 비율 자체의 학술 근거는 약하다 — 다수가 같은 선에 주문을 두는 데서 오는 효과로 보고, 여러 기준선이 겹친 구간만 강하게 본다. "
                                        f"{note}."})
    return {"h2": "가격 구간 — 월·주·일 피보나치와 겹침 구간", "blocks": blocks, "_summary": {
        "price": price, "support": [_z(g, price) for g in z["support"]], "resistance": [_z(g, price) for g in z["resistance"]],
        "at": [_z(g, price) for g in z["at"]], "swings": {k: {kk: v[kk] for kk in ("low", "high", "low_date", "high_date", "up", "basis")} for k, v in sw.items()}}}


def main(argv):
    sys.stdout.reconfigure(encoding="utf-8")
    entity = argv[0]
    dpp = flow.company_dir(entity) / "datapack.json"
    dp = json.loads(dpp.read_text(encoding="utf-8")) if dpp.exists() else {}
    sec = report_section(entity, dp)
    if not sec:
        print("[가격 구간] 일봉 60일 이상 필요")
        return 1
    s = sec["_summary"]
    print(f"[가격 구간] {entity} 현재 ${s['price']:,.2f}")
    for k, v in s["swings"].items():
        print(f"  {k}: {v['low']:.2f}({v['low_date']}) → {v['high']:.2f}({v['high_date']}) {'상승' if v['up'] else '하락'} · {v['basis']}")
    for lab in ("resistance", "at", "support"):
        for r in s[lab]:
            print(f"  {lab}: {r[0]} {r[1]} 강도 {r[2]} — {r[3]}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
