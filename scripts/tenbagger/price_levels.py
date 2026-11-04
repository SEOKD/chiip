"""Analysis 신호 가격 → TradingView 알림 (마스터 지시 2026-11-04 "밸류에이션 관점 지지선·저항선과 차트 테크니컬 관점 지지선·저항선을 종합해
Buy Signal·Sell Signal이 나오는 Price Level을 파악하고 TradingView 종목별 Alarm 시스템에 넣어라. 최종 Buy·Sell 판단 책임은 에이전트에 없고 나의 결정에 달려 있다")

신호 가격은 연구 지표다. 매매 지시가 아니고, 최종 판단과 책임은 마스터에게 있다(알림 문구에도 쓴다). 마스터 포지션 파일을 읽지 않는다.
  밸류 경계(리포트 규칙 등급과 같은 식 — scripts/tenbagger/report_layout.py rating, config/tenbagger.yaml rating)
    Buy 경계  = min(목표가 ÷ (1 + buy.upside), (강세 + buy.rr·약세) ÷ (1 + buy.rr), DCF 가치 ÷ (1 + buy.dcf_min))   — 이 아래면 등급이 Buy 이상
    Strong Buy 경계 = 같은 식(strong_buy)
    Sell 경계 = 목표가 ÷ (1 + neutral.upside)  — 이 위면 업사이드 −10% 미만(Neutral 아래)
  기술 지지·저항(TradingView): 월 피벗 S1·S2·R1·R2, 50·200일 이동평균, 52주 고·저
  합류(confluence): Buy 신호 = Buy 경계 이하이면서 경계에 가장 가까운 지지선(경계의 band 안), 없으면 경계 자체
                   Sell 신호 = Sell 경계 이상이면서 가장 가까운 저항선(band 안), 없으면 경계 자체
                   지금 가격이 이미 Buy 구간(경계 아래)이면 Buy 신호는 현재가 아래 가장 가까운 지지선(추가 하락 구간)
알림: Buy = 가격이 신호 가격을 아래로 지나갈 때(cross_down), Sell = 위로 지나갈 때(cross_up). 신호 가격이 change_min 이상 바뀌면 옛 알림을 멈추고 새로 만든다.
사용: py scripts/tenbagger/price_levels.py --symbols                 # TradingView 배치에 넣을 심볼
      py scripts/tenbagger/price_levels.py --compute <배치 JSON>      # 신호 가격 + 알림 작업 계획(create·stop) → knowledge/models/tenbagger/price_levels.json
      py scripts/tenbagger/price_levels.py --record <결과 JSON>       # 만든 알림 id 기록 {"TICK": {"buy": id, "sell": id}, "stopped": [id…]}
"""
import csv
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "discovery"))
OUT = ROOT / "knowledge" / "models" / "tenbagger" / "price_levels.json"
STATE = ROOT / "knowledge" / "models" / "tenbagger" / "tv_alerts.json"
KST = timezone(timedelta(hours=9))
COLUMNS = ["close", "SMA50", "SMA200", "price_52_week_high", "price_52_week_low", "Pivot.M.Classic.S1", "Pivot.M.Classic.S2", "Pivot.M.Classic.R1", "Pivot.M.Classic.R2"]
TECH = {"Pivot.M.Classic.S1": "월 피벗 S1", "Pivot.M.Classic.S2": "월 피벗 S2", "Pivot.M.Classic.R1": "월 피벗 R1", "Pivot.M.Classic.R2": "월 피벗 R2",
        "SMA50": "50일선", "SMA200": "200일선", "price_52_week_high": "52주 고점", "price_52_week_low": "52주 저점"}
DISCLAIMER = "Chiip 연구 지표 — 매매 지시가 아니며 최종 판단과 책임은 마스터에게 있다"


def cfg():
    t = yaml.safe_load((ROOT / "config" / "tenbagger.yaml").read_text(encoding="utf-8"))
    return t["rating"], t.get("price_levels") or {"band": 0.12, "change_min": 0.02}


def tv_map():
    """티커 → TradingView 심볼(config/tradingview_symbols.csv, 확인된 행 우선)"""
    out = {}
    p = ROOT / "config" / "tradingview_symbols.csv"
    with p.open(encoding="utf-8", newline="") as f:
        for r in csv.DictReader(f):
            t = (r.get("ticker") or "").upper()
            if t and (t not in out or r.get("confirmed") == "true"):
                out[t] = r["tv_symbol"]
    return out


def reports():
    import buy_call
    return {r["ticker"].upper(): r for r in buy_call.reports().values()}


def symbols():
    m, reps = tv_map(), reports()
    return {t: m[t] for t in reps if t in m}


def boundary(rep, r):
    """밸류 경계 가격: Buy 이하·Strong Buy 이하·Sell 이상"""
    tgt, bull, bear, dcf = rep["target"], rep["bull"], rep["bear"], rep.get("dcf")

    def buy_line(g):
        xs = [tgt / (1 + g["upside"])]
        if bull and bear:
            xs.append((bull + g["rr"] * bear) / (1 + g["rr"]))
        if dcf:
            xs.append(dcf / (1 + g["dcf_min"]))
        return min(xs)
    return {"buy": buy_line(r["buy"]), "strong_buy": buy_line(r["strong_buy"]), "sell": tgt / (1 + r["neutral"]["upside"])}


def levels(rep, q, r, band):
    b = boundary(rep, r)
    price = q.get("close")
    techs = [(TECH[k], q[k]) for k in TECH if q.get(k)]
    sup = sorted([t for t in techs if t[1] <= b["buy"] and t[1] >= b["buy"] * (1 - band)], key=lambda t: -t[1])
    if price and price <= b["buy"]:   # 이미 Buy 구간 — 현재가 아래 band 안 가장 가까운 지지선, 없으면 Strong Buy 경계(현재가 아래일 때)
        below = sorted([t for t in techs if price * (1 - band) <= t[1] < price], key=lambda t: -t[1])
        buy = below[0] if below else (("밸류 Strong Buy 경계", b["strong_buy"]) if b["strong_buy"] < price else None)
        buy_note = "현재가가 이미 밸류 Buy 구간 — 추가 하락 시 지지"
    else:
        buy = sup[0] if sup else ("밸류 Buy 경계", b["buy"])
        buy_note = "밸류 Buy 경계와 기술 지지 합류" if sup else "근처 기술 지지 없음 — 밸류 경계"
    res = sorted([t for t in techs if t[1] >= b["sell"] and t[1] <= b["sell"] * (1 + band)], key=lambda t: t[1])
    if price and price >= b["sell"]:   # 이미 Sell 구간 — 현재가 위 band 안 가장 가까운 저항, 없으면 알림 없음
        above = sorted([t for t in techs if price < t[1] <= price * (1 + band)], key=lambda t: t[1])
        sell = above[0] if above else None
        sell_note = "현재가가 이미 밸류 Sell 구간 — 추가 상승 시 저항"
    else:
        sell = res[0] if res else ("밸류 Sell 경계", b["sell"])
        sell_note = "밸류 Sell 경계와 기술 저항 합류" if res else "근처 기술 저항 없음 — 밸류 경계"
    rd = lambda x: round(x, 2) if x < 1000 else round(x)
    return {"price": price, "grade": rep.get("grade"), "report": rep.get("date"), "target": rep["target"],
            "val_buy": rd(b["buy"]), "val_strong_buy": rd(b["strong_buy"]), "val_sell": rd(b["sell"]),
            "buy": {"price": rd(buy[1]), "basis": buy[0], "note": buy_note} if buy else {"price": None, "basis": "없음", "note": buy_note},
            "sell": {"price": rd(sell[1]), "basis": sell[0], "note": sell_note} if sell else {"price": None, "basis": "없음", "note": sell_note},
            "tech": {k: rd(v) for k, v in techs}}


def cur(sym):
    """통화 기호 — 미국 거래소만 $, 그 밖은 현지 통화 숫자 그대로(원·엔·크로네)"""
    return "$" if str(sym).split(":")[0] in ("NYSE", "NASDAQ", "AMEX") else ""


def message(t, side, lv):
    s, u = lv[side], cur(lv.get("symbol"))
    head = "Buy 신호 가격 도달" if side == "buy" else "Sell 신호 가격 도달"
    return (f"[Chiip] {t} {head} {u}{s['price']:,} — 근거: {s['basis']} · {s['note']} · 밸류 Buy 경계 {u}{lv['val_buy']:,} / Strong Buy {u}{lv['val_strong_buy']:,} / "
            f"Sell 경계 {u}{lv['val_sell']:,} · 리포트 {lv['report']} 목표가 {u}{lv['target']:,.2f}(등급 {lv['grade']}). {DISCLAIMER}")


def compute(batch_path):
    r, pl = cfg()
    reps, syms = reports(), symbols()
    data = json.loads(Path(batch_path).read_text(encoding="utf-8"))
    data = data.get("data", data)
    st = json.loads(STATE.read_text(encoding="utf-8")) if STATE.exists() else {}
    out, plan = {}, {"create": [], "stop": []}
    for t, sym in syms.items():
        q = data.get(sym)
        if not q or not q.get("close"):
            continue
        lv = levels(reps[t], q, r, pl["band"])
        lv["symbol"] = sym
        out[t] = lv
        for side, cond in (("buy", "cross_down"), ("sell", "cross_up")):
            old = (st.get(t) or {}).get(side) or {}
            newp = lv[side]["price"]
            if newp is None:   # 이 쪽은 알림을 걸 가격이 없다(이미 그 구간이고 근처 기술선 없음)
                if old.get("id"):
                    plan["stop"].append(old["id"])
                continue
            fresh = old.get("at") and old["at"] > (datetime.now(KST) - timedelta(days=pl.get("refresh_days", 25))).isoformat()
            if old.get("price") and abs(newp / old["price"] - 1) < pl["change_min"] and fresh:
                continue   # 거의 같은 가격이고 만료(기본 30일) 전 — 기존 알림 유지
            if old.get("id"):
                plan["stop"].append(old["id"])
            plan["create"].append({"ticker": t, "side": side, "symbol": sym, "price": newp, "condition": cond, "resolution": "1D",
                                   "name": f"Chiip {'Buy' if side == 'buy' else 'Sell'} 신호 {t} {cur(sym)}{newp:,}", "message": message(t, side, lv)})
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({"as_of": datetime.now(KST).isoformat(timespec="seconds"), "note": DISCLAIMER, "levels": out, "plan": plan},
                              ensure_ascii=False, indent=1), encoding="utf-8")
    return out, plan


def record(path):
    """{"TICK": {"buy": [id, price], "sell": [id, price]}, …} — 만든 알림을 기록"""
    st = json.loads(STATE.read_text(encoding="utf-8")) if STATE.exists() else {}
    for t, v in json.loads(Path(path).read_text(encoding="utf-8")).items():
        for side, (aid, price) in v.items():
            st.setdefault(t, {})[side] = {"id": aid, "price": price, "at": datetime.now(KST).isoformat(timespec="seconds")}
    STATE.write_text(json.dumps(st, ensure_ascii=False, indent=1), encoding="utf-8")
    return len(st)


def main(argv):
    sys.stdout.reconfigure(encoding="utf-8")
    if "--symbols" in argv:
        print(json.dumps({"symbols": list(symbols().values()), "columns": COLUMNS}, ensure_ascii=False))
    elif "--compute" in argv:
        out, plan = compute(argv[argv.index("--compute") + 1])
        for t, lv in out.items():
            print(f"{t} {lv['price']}: Buy {lv['buy']['price']}({lv['buy']['basis']}) · Sell {lv['sell']['price']}({lv['sell']['basis']}) · 밸류 Buy {lv['val_buy']}/Sell {lv['val_sell']}")
        print(f"알림 계획: 새로 {len(plan['create'])} · 멈춤 {len(plan['stop'])}")
    elif "--record" in argv:
        print(record(argv[argv.index("--record") + 1]), "종목 기록")


if __name__ == "__main__":
    main(sys.argv[1:])
