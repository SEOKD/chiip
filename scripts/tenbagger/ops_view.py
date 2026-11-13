"""운영 지표 3종 — Rule of 40 · 수주/출하 × 재고 · 실적 발표 예상 변동폭 (마스터 지시 2026-11-14, ADR-033)

재료
  datapack "ops" = scripts/fiscal/templates/ops_metrics.js 출력(`--put <id> <파일>`):
     {"q": [{"period", "inventory", "ocf", "capex", "orders", "backlog"}], "orders_label", "backlog_label", "source"}
  datapack "quarters_hist" (매출·매출원가, 이미 있음) · "sbc_pct_rev" · "industry" · "revision_events"(실적 사건) · ohlcv.csv
  datapack "options_implied" = {"as_of", "spot", "expiry", "straddle", "iv", "source"} — 실적일 직후 만기 ATM 스트래들(옵션 원천은 ADR-033)

1. Rule of 40 (소프트웨어만 — industry 'software' 또는 sector_kpis.lens 'software')
   = 최근 4개 분기 매출 전년 대비 성장률(%) + 같은 기간 FCF 마진(%). FCF = 영업현금흐름 + CAPEX(음수).
   SBC 차감판 = 위 − 매출 대비 주식보상(%) — 독립 리서처들이 쓰는 엄격한 판(주식보상은 주주에게 실제 비용).
   40 이상이면 '통과'. 최근 4개 분기 말 기준 추이를 같이 낸다(한 분기 숫자로 판정하지 않는다).
2. 수주/출하(Book-to-Bill) × 재고
   B/B = 분기 수주 ÷ 분기 매출(4개 분기 합으로도). 재고 = 재고자산 ÷ (최근 4개 분기 매출원가 ÷ 365) = 재고 일수(DIO).
   읽기 — 사이클 사분면(4개 분기 B/B 기준 1.0, 재고 증가율 vs 매출 증가율):
     B/B ≥ 1 · 재고 ≤ 매출   → 수요가 공급을 앞섬, 재고 건전(상향 국면)
     B/B ≥ 1 · 재고 > 매출   → 수요 강함 + 재고 축적(증설·출하 대기 — 왜 쌓이는지 확인)
     B/B < 1 · 재고 > 매출   → 수요 둔화 + 재고 누적(하향 경고)
     B/B < 1 · 재고 ≤ 매출   → 수요 둔화, 재고 조정 중(바닥 확인 단계)
   수주를 공시하지 않으면 B/B 칸을 쓰지 않는다(지어내지 않는다). 재고가 없는 회사(소프트웨어·서비스)는 절을 넣지 않는다.
3. 실적 발표 예상 변동폭
   옵션 내재 변동폭 = 실적일 직후 만기 ATM 스트래들 ÷ 주가(관행). 과거 실적 발표 다음 거래일 실제 움직임(절댓값 평균·최대)과 비교:
   비율 > 1.2 = 시장이 평소보다 큰 움직임을 가격에 넣었다(불확실성·이벤트 프리미엄), < 0.8 = 작게(안도·무관심).
   옵션 자료가 없으면 과거 실제 움직임만 쓴다.
상수: config/ops_view.yaml(등록부 prm-ops-*).
사용: py scripts/tenbagger/ops_view.py --code <id>          # ops_metrics.js에 키를 넣은 코드
      py scripts/tenbagger/ops_view.py --put <id> <파일>    # datapack ops
      py scripts/tenbagger/ops_view.py --show <id>
"""
import json
import statistics
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
CFG = ROOT / "config" / "ops_view.yaml"
TPL = ROOT / "scripts" / "fiscal" / "templates" / "ops_metrics.js"
sys.path.insert(0, str(Path(__file__).resolve().parent))


def cfg():
    return yaml.safe_load(CFG.read_text(encoding="utf-8"))


def _q(dp):
    """분기 매출·매출원가 — quarters_hist가 먼저, 없으면 ops(ops_metrics.js 손익) — 각 행은 사본"""
    q = [dict(r) for r in ((dp.get("quarters_hist") or {}).get("q") or []) if r.get("rev")]
    return q or [dict(r) for r in ((dp.get("ops") or {}).get("q") or []) if r.get("rev")]


def _ttm(rows, key, end):
    """end(포함)까지 4개 분기 합 — 칸이 하나라도 없으면 None"""
    xs = [r.get(key) for r in rows[max(0, end - 3): end + 1]]
    return sum(xs) if len(xs) == 4 and all(x is not None for x in xs) else None


def is_software(dp):
    return str(dp.get("industry") or "").lower() == "software" or ((dp.get("sector_kpis") or {}).get("lens") == "software")


def rule40(dp, n=4):
    """[{period, growth, fcf_margin, r40, r40_sbc}] 최근 n개 분기 말. 재료가 모자라면 []"""
    q = _q(dp)
    ops = {r["period"]: r for r in ((dp.get("ops") or {}).get("q") or [])}
    for r in q:
        o = ops.get(r["period"]) or {}
        r["_fcf"] = (o["ocf"] + (o.get("capex") or 0)) if o.get("ocf") is not None else None
    sbc = dp.get("sbc_pct_rev")
    out = []
    for i in range(len(q) - 1, 6, -1):
        rev, prev = _ttm(q, "rev", i), _ttm(q, "rev", i - 4)
        fcf = _ttm(q, "_fcf", i)
        if not rev or not prev or fcf is None:
            continue
        g, m = rev / prev - 1, fcf / rev
        out.append({"period": q[i]["period"], "growth": g, "fcf_margin": m, "r40": (g + m) * 100,
                    "r40_sbc": (g + m - sbc) * 100 if sbc is not None else None})
        if len(out) == n:
            break
    return out[::-1]


def rule40_blocks(dp):
    if not is_software(dp):
        return []
    rows = rule40(dp)
    if not rows:
        return []
    c = cfg()["rule40"]
    last = rows[-1]
    ok = last["r40"] >= c["pass"]
    trend = rows[-1]["r40"] - rows[0]["r40"] if len(rows) > 1 else None
    text = (f"**Rule of 40 {last['r40']:.0f}({'통과' if ok else '미달'}).** 최근 4개 분기 매출 성장 {last['growth'] * 100:+.0f}% + FCF 마진 {last['fcf_margin'] * 100:.0f}%")
    if last["r40_sbc"] is not None:
        text += f", 주식보상을 비용으로 빼면 {last['r40_sbc']:.0f}" + ("(이 기준으로도 통과)" if last["r40_sbc"] >= c["pass"] else "(이 기준으로는 미달)")
    text += "."
    if trend is not None:
        text += f" {len(rows)}개 분기 동안 {trend:+.0f}점 움직였다 — " + ("성장과 수익성의 합이 좋아지는 중이다." if trend > c["flat"] else "나빠지는 중이다." if trend < -c["flat"] else "거의 그대로다.")
    hd = ["분기 말", "매출 성장(4분기)", "FCF 마진", "Rule of 40", "주식보상 차감"]
    tb = [[r["period"][:7], f"{r['growth'] * 100:+.0f}%", f"{r['fcf_margin'] * 100:.0f}%", f"{r['r40']:.0f}", "-" if r["r40_sbc"] is None else f"{r['r40_sbc']:.0f}"] for r in rows]
    chart = {"kind": "bars", "w": 440, "title": "Rule of 40 추이 — 매출 성장 + FCF 마진(최근 4개 분기 합 기준, 40 = 기준선)", "unit": "",
             "categories": [r["period"][2:7] for r in rows],
             "series": [{"name": "Rule of 40", "color": "c", "values": [round(r["r40"]) for r in rows]}]
             + ([{"name": "주식보상 차감", "color": "d", "values": [round(r["r40_sbc"]) for r in rows]}] if all(r["r40_sbc"] is not None for r in rows) else [])}
    return [{"type": "hl", "text": text}, {"type": "table", "title": "Rule of 40 — 성장과 수익성의 합", "headers": hd, "rows": tb}, {"type": "chart", "chart": chart}]


def cycle(dp):
    """[{period, bb, bb4, dio, inv_yoy, rev_yoy}] — 재고가 없으면 []"""
    q = _q(dp)
    ops = {r["period"]: r for r in ((dp.get("ops") or {}).get("q") or [])}
    for r in q:
        o = ops.get(r["period"]) or {}
        r["_orders"], r["_inv"] = o.get("orders"), o.get("inventory")
    out = []
    for i in range(4, len(q)):
        r = q[i]
        if r["_inv"] is None:
            continue
        cogs4 = _ttm(q, "cogs", i)
        rev4, rev4p = _ttm(q, "rev", i), _ttm(q, "rev", i - 4) if i >= 7 else None
        prev_inv = q[i - 4]["_inv"]
        o4 = _ttm(q, "_orders", i)
        out.append({"period": r["period"], "bb": r["_orders"] / r["rev"] if r["_orders"] is not None else None, "bb4": o4 / rev4 if o4 and rev4 else None,
                    "dio": r["_inv"] / (cogs4 / 365) if cogs4 else None, "inv_yoy": r["_inv"] / prev_inv - 1 if prev_inv else None,
                    "rev_yoy": rev4 / rev4p - 1 if rev4 and rev4p else None})
    return out[-8:]


def quadrant(x, c):
    if x.get("bb4") is None or x.get("inv_yoy") is None or x.get("rev_yoy") is None:
        return None
    hi = x["bb4"] >= c["bb_line"]
    heavy = x["inv_yoy"] - x["rev_yoy"] > c["inv_gap"]
    return {(True, False): "수요가 공급을 앞서고 재고는 건전하다(상향 국면)", (True, True): "수요는 강한데 재고도 쌓인다(증설·출하 대기 — 왜 쌓이는지 확인)",
            (False, True): "수요가 둔화되고 재고가 쌓인다(하향 경고)", (False, False): "수요는 둔화됐지만 재고를 줄이는 중이다(바닥 확인 단계)"}[(hi, heavy)]


def cycle_section(dp):
    rows = cycle(dp)
    if not rows:
        return None
    c = cfg()["cycle"]
    lab = (dp.get("ops") or {}).get("orders_label")
    last = rows[-1]
    pc = lambda v: "-" if v is None else f"{v * 100:+.0f}%"
    parts = []
    if last.get("bb4") is not None:
        parts.append(f"최근 4개 분기 수주/출하 비율(Book-to-Bill, {lab}) {last['bb4']:.2f}" + (f", 이번 분기 {last['bb']:.2f}" if last.get("bb") is not None else ""))
    if last.get("dio") is not None:
        d0 = rows[0].get("dio")
        parts.append(f"재고 일수 {last['dio']:.0f}일" + (f"({rows[0]['period'][:7]} {d0:.0f}일에서)" if d0 else ""))
    if last.get("inv_yoy") is not None and last.get("rev_yoy") is not None:
        parts.append(f"재고 전년 대비 {pc(last['inv_yoy'])} vs 매출(4개 분기) {pc(last['rev_yoy'])}")
    qd = quadrant(last, c)
    head = "**" + (qd + ".** " if qd else "수주 미공시 — 재고만 본다.** ") + " · ".join(parts) + "."
    tb = [[r["period"][:7], "-" if r["bb"] is None else f"{r['bb']:.2f}", "-" if r["bb4"] is None else f"{r['bb4']:.2f}",
           "-" if r["dio"] is None else f"{r['dio']:.0f}", pc(r["inv_yoy"]), pc(r["rev_yoy"])] for r in rows]
    B = [{"type": "hl", "text": head},
         {"type": "table", "title": "수주/출하 비율 × 재고 — 분기별", "headers": ["분기 말", "B/B(분기)", "B/B(4분기)", "재고 일수", "재고 전년 대비", "매출 전년 대비(4분기)"], "rows": tb}]
    series = [{"name": "재고 일수", "color": "b", "values": [None if r["dio"] is None else round(r["dio"]) for r in rows]}]
    if any(r.get("bb4") is not None for r in rows):
        series.insert(0, {"name": "B/B(4분기)×100", "color": "c", "values": [None if r["bb4"] is None else round(r["bb4"] * 100) for r in rows]})
    B.append({"type": "chart", "chart": {"kind": "bars", "w": 440, "title": "수주/출하 비율 × 재고 일수 — 분기별(B/B 100 = 수주와 출하가 같다)", "unit": "",
                                         "categories": [r["period"][2:7] for r in rows], "series": series}})
    B.append({"type": "p", "text": "B/B가 1을 넘으면 받은 주문이 내보낸 물건보다 많아 잔고가 쌓이고, 재고가 매출보다 빨리 늘면 수요보다 생산이 앞선다는 뜻이다. 둘을 함께 봐야 '주문이 많아 쌓이는 재고'와 '안 팔려 쌓이는 재고'를 가른다."})
    return {"h2": "수주·출하·재고 사이클", "blocks": B}


def earnings_moves(dp):
    """과거 실적 발표 다음 거래일(장전·장중이면 그날) 주가 변화 목록"""
    import revision_view as rv
    px = rv.load_prices(dp.get("id"))
    if not px:
        return []
    out = []
    for ev in dp.get("revision_events") or []:
        if ev.get("kind") != "실적":
            continue
        r = rv.reaction(px, ev)
        if r is not None:
            out.append({"date": ev["date"], "q": ev.get("q") or ev.get("tag"), "move": r})
    return sorted(out, key=lambda x: x["date"])[-8:]


def implied_blocks(dp):
    moves = earnings_moves(dp)
    oi = dp.get("options_implied") or {}
    implied = oi["straddle"] / oi["spot"] if oi.get("straddle") and oi.get("spot") else None
    if not moves and implied is None:
        return []
    c = cfg()["implied"]
    absm = [abs(m["move"]) for m in moves]
    text = "**실적 발표 예상 변동폭:** "
    if moves:
        text += f"지난 {len(moves)}번 실적 발표 때 주가는 하루에 평균 ±{statistics.mean(absm) * 100:.1f}%(최대 {max(absm) * 100:.1f}%, 오른 날 {sum(1 for m in moves if m['move'] > 0)}번) 움직였다."
    if implied is not None:
        text += f" 지금 옵션 시장은 {oi.get('expiry', '')} 만기 스트래들로 ±{implied * 100:.1f}%를 가격에 넣었다"
        if absm:
            ratio = implied / statistics.mean(absm)
            text += f" — 과거 평균의 {ratio:.1f}배로, " + ("평소보다 큰 움직임(불확실성 프리미엄)을 예상한다." if ratio > c["hi"] else "평소보다 작은 움직임을 예상한다." if ratio < c["lo"] else "평소 수준이다.")
        else:
            text += "."
        if oi.get("iv") is not None:
            text += f" ATM 내재 변동성 {oi['iv'] * 100:.0f}%."
        if oi.get("earnings") and oi.get("expiry"):
            from datetime import date as _date
            gap = (_date.fromisoformat(oi["expiry"]) - _date.fromisoformat(oi["earnings"])).days
            if gap > 7:   # 주간 옵션이 없어 월물을 쓴 경우 — 실적 밖 기간의 변동이 섞여 크게 나온다
                text += f" 다만 가장 가까운 만기가 실적일 {gap}일 뒤라 실적 밖 기간의 변동이 섞여 실제 실적 몫보다 크다."
    B = [{"type": "p", "text": text}]
    if moves:
        B.append({"type": "table", "title": "실적 발표 예상 변동폭 — 과거 실적 발표 다음 거래일 주가 변화", "headers": ["분기", "발표일", "주가 변화"],
                  "rows": [[m["q"] or "", m["date"], f"{m['move'] * 100:+.1f}%"] for m in moves]
                  + ([["옵션 내재(이번)", oi.get("as_of", ""), f"±{implied * 100:.1f}%"]] if implied is not None else [])})
    return B


def put(cid, out):
    p = ROOT / "knowledge" / "models" / "companies" / cid / "datapack.json"
    dp = json.loads(p.read_text(encoding="utf-8"))
    dp["ops"] = {k: out.get(k) for k in ("q", "orders_label", "backlog_label", "source")}
    p.write_text(json.dumps(dp, ensure_ascii=False, indent=1), encoding="utf-8")
    return len(out.get("q") or [])


def _key(cid):
    d = yaml.safe_load((ROOT / "config" / "fiscal_keys.yaml").read_text(encoding="utf-8")) or {}
    return ((d.get("keys") or {}).get(cid) or {}).get("key")


def main(argv):
    sys.stdout.reconfigure(encoding="utf-8")
    if len(argv) >= 2 and argv[0] == "--code":
        k = _key(argv[1]) or (argv[2] if len(argv) > 2 else None)
        if not k:
            print(f"Fiscal 키 없음: {argv[1]} — `py scripts/fiscal/adapter.py --key {argv[1]} <키>` 먼저")
            return 1
        print(TPL.read_text(encoding="utf-8").replace("__KEY__", k))
        return 0
    if len(argv) >= 3 and argv[0] == "--put":
        print(f"[운영 지표] {argv[1]} {put(argv[1], json.loads(Path(argv[2]).read_text(encoding='utf-8')))}개 분기 → datapack ops")
        return 0
    if len(argv) >= 2 and argv[0] == "--show":
        dp = json.loads((ROOT / "knowledge" / "models" / "companies" / argv[1] / "datapack.json").read_text(encoding="utf-8"))
        dp.setdefault("id", argv[1])
        print(json.dumps({"rule40": rule40_blocks(dp), "cycle": cycle_section(dp), "implied": implied_blocks(dp)}, ensure_ascii=False, indent=1))
        return 0
    print(__doc__)
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
