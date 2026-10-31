"""종합 9.5 연구 명단 (마스터 지시 2026-10-31, config/composite.yaml)

알파(30%) + 손익비(30%) + 기술적(20%) + 시의성(20%) = 10점. 9.5 이상만 Chiip Portfolio 데일리에 싣는다. 없으면 아무것도 싣지 않는다.
우주는 텐배거 레이더 밖까지 넓힌다 — Portfolio 데일리가 TradingView 스크리너로 받은 종목 + 알파 산정 종목. 알파가 없으면 통과할 수 없고,
기술적 점수가 높으면 v2 대기열(radar/state/v2_queue.json)에 올려 알파·손익비를 만든다.
지표·연구 후보일 뿐 매수 권유가 아니다 — 마스터 포지션을 읽지 않고, 비중·시점·금액을 내지 않는다.

입력 radar/state/composite_in.json:
  {"as_of": "2026-10-31", "rows": [{"id": "co-ultraclean"|null, "ticker", "name",
    "tv": {close, SMA50, SMA200, RSI, relative_volume_10d_calc, "Perf.1M", "Perf.3M", price_52_week_high, average_volume_30d_calc},
    "timing": {"catalyst_days": 12, "catalyst": "3Q 실적", "new_primary": true, "revision_30d": 0.03, "sector_label": "…"},   # 확인한 것만, 모르면 비운다
    "killed": false}]}
사용: py scripts/discovery/composite.py [--in 파일] [--no-queue]
"""
import argparse
import json
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
ALPHA = ROOT / "knowledge" / "models" / "alpha" / "latest.json"
LATEST = ROOT / "knowledge" / "models" / "portfolio" / "composite_latest.json"
TAILWIND = "이익 상향과 주가 동행"


def cfg():
    return yaml.safe_load((ROOT / "config" / "composite.yaml").read_text(encoding="utf-8"))


def alpha_rows():
    if not ALPHA.exists():
        return {}
    r = json.loads(ALPHA.read_text(encoding="utf-8")).get("rows") or {}
    return r if isinstance(r, dict) else {x.get("id"): x for x in r}


def technical(tv, c):
    t, pts = c["technical"], 0
    close, s50, s200 = tv.get("close"), tv.get("SMA50"), tv.get("SMA200")
    if close and s50 and close > s50:
        pts += t["above_sma50"]
    if s50 and s200 and s50 > s200:
        pts += t["sma50_above_sma200"]
    if close and tv.get("price_52_week_high") and close >= t["near_ratio"] * tv["price_52_week_high"]:
        pts += t["near_52w_high"]
    if (tv.get("Perf.1M") or 0) > 0 and (tv.get("Perf.3M") or 0) > 0:
        pts += t["momentum"]
    if tv.get("RSI") is not None and t["rsi_low"] <= tv["RSI"] <= t["rsi_high"]:
        pts += t["rsi_band"]
    if (tv.get("relative_volume_10d_calc") or 0) >= t["volume_min"]:
        pts += t["volume"]
    return float(pts)


def timing(x, c):
    t, pts = c["timing"], 0
    x = x or {}
    if x.get("catalyst_days") is not None and 0 <= x["catalyst_days"] <= t["catalyst_days"]:
        pts += t["catalyst"]
    if x.get("new_primary"):
        pts += t["new_primary"]
    if (x.get("revision_30d") or 0) > 0:
        pts += t["revision"]
    if x.get("sector_label") == TAILWIND:
        pts += t["sector"]
    return float(pts)


def score(row, alpha, c):
    """한 종목 점수와 탈락 이유. alpha = 알파 행 또는 None"""
    w, full = c["weights"], c["full_marks"]
    tv = row.get("tv") or {}
    tech, tim = technical(tv, c), timing(row.get("timing"), c)
    al = min(10.0, alpha["total"] / full["alpha"] * 10) if alpha else None
    rr = min(10.0, (alpha.get("components") or {}).get("asymmetry", 0) / full["reward_risk"] * 10) if alpha else None
    out = {"id": row.get("id"), "ticker": row.get("ticker"), "name": row.get("name"), "technical": tech, "timing": tim, "alpha": al, "reward_risk": rr, "composite": None, "pass": False, "why": []}
    if alpha is None:
        out["why"].append("알파 미산정")
        return out
    out["composite"] = round(w["alpha"] * al + w["reward_risk"] * rr + w["technical"] * tech + w["timing"] * tim, 2)
    adv = (tv.get("close") or 0) * (tv.get("average_volume_30d_calc") or 0)
    if adv < c["gates"]["min_adv_usd"]:
        out["why"].append("거래대금 미달")
    if row.get("killed"):
        out["why"].append("킬 조건 발동")
    if out["composite"] < c["threshold"]:
        out["why"].append(f"{c['threshold']} 미만")
    out["pass"] = not out["why"]
    return out


def line(x):
    """Portfolio 데일리 한 줄 — 지표만"""
    return (f"· {x['name']}({x['ticker']}) 종합 {x['composite']:.1f}/10 — 알파 {x['alpha']:.1f} · 손익비 {x['reward_risk']:.1f} · 기술적 {x['technical']:.1f} · 시의성 {x['timing']:.1f}")


def run(data, c=None, queue=True):
    c = c or cfg()
    alphas = alpha_rows()
    rows = [score(r, alphas.get(r.get("id")), c) for r in data.get("rows") or []]
    rows.sort(key=lambda x: -(x["composite"] or 0))
    wait = [x for x in rows if x["alpha"] is None and x["technical"] >= c["gates"]["min_technical_for_queue"] and x["id"]][: c["gates"]["queue_per_run"]]
    if queue and wait:
        sys.path.insert(0, str(ROOT / "scripts" / "valuation" / "v2"))
        import alpha_watch
        for x in wait:
            alpha_watch.enqueue(x["id"], x["name"], "종합 명단 — 기술적 점수 높음, 알파 미산정", "composite")
    return {"as_of": data.get("as_of"), "threshold": c["threshold"], "n": len(rows), "pass": [x for x in rows if x["pass"]], "top": rows[:10], "queued": [x["id"] for x in wait]}


def main(argv):
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="src", default=str(ROOT / "radar" / "state" / "composite_in.json"))
    ap.add_argument("--no-queue", action="store_true")
    a = ap.parse_args(argv)
    out = run(json.loads(Path(a.src).read_text(encoding="utf-8")), queue=not a.no_queue)
    LATEST.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"[종합 명단] {out['n']}종목 · 통과 {len(out['pass'])} · 대기열 {len(out['queued'])}")
    for x in out["top"][:5]:
        print(f"  {x['ticker']} 종합 {x['composite']} 알파 {x['alpha']} 손익비 {x['reward_risk']} 기술 {x['technical']} 시의성 {x['timing']} {x['why']}")
    for x in out["pass"]:
        print(line(x))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
