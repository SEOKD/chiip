"""모델 포트폴리오 가상 장부 3단계 (마스터 지시 2026-11-04 "3단계 진행", 설계 knowledge/methods/portfolio_management_design.md 2절 ⑥)

연구용 가상 포트폴리오다 — 마스터 계좌가 아니고, 마스터 포지션 파일을 읽지 않는다. 판단의 성적표 재료다.
장부(book) 4개를 같은 날 같은 시세로 굴린다:
  구성     construct.py 비중(오버레이 전)          — Chiip 판단 + 위험 제약
  오버레이 construct.py 오버레이 후 비중           — 변동성 목표·낙폭 제어·이벤트 할인까지
  HRP      risk.py HRP 기준선(판단 없음, 100% 투자) — 판단이 가치를 더하는지 가르는 비교 대상
  SPY      시장
매일: ① 직전 장부일 이후 거래일마다 시가평가(비중 표류, 현금은 rf/252) ② 오늘 목표와 비교해 무거래 구간(band) 밖인 종목만
      목표 쪽으로 a만큼 이동(Gârleanu & Pedersen 2013 부분 조정) ③ 거래 비용 = |Δw| × (스프레드 반 + 충격) 차감
      충격 = η·σ_일·√(주문 금액/일 거래대금) — 거래량을 모르면 스프레드만(표시)
기록: knowledge/models/pm/book.json(상태), book_log.csv(일별 NAV·수익·회전·비용)
사용: py scripts/pm/risk.py && py scripts/pm/construct.py && py scripts/pm/ledger.py
"""
import csv
import json
import math
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "pm"))
import risk  # noqa: E402

DIR = ROOT / "knowledge" / "models" / "pm"
BOOK = DIR / "book.json"
LOG = DIR / "book_log.csv"
KST = timezone(timedelta(hours=9))


def targets(c):
    rk = json.loads((DIR / "latest.json").read_text(encoding="utf-8"))
    cs = json.loads((DIR / "construct.json").read_text(encoding="utf-8"))
    return {"구성": {s: r["w"] for s, r in cs["rows"].items()},
            "오버레이": {s: r["w_overlay"] for s, r in cs["rows"].items()},
            "HRP": dict(rk["baselines"]["HRP"]["weights"]),
            "SPY": {c["universe"]["market"]: 1.0}}


def mark(book, series, days, rf):
    """days 동안 시가평가 — 비중 표류. 반환: 일별 (날짜, 수익)"""
    out = []
    for d in days:
        w = book["w"]
        book.setdefault("_snap", []).append([d, dict(w)])   # 그날 시작 비중 — 4단계 귀속이 읽는다
        cash = 1 - sum(w.values())
        r = sum(x * series.get(s, {}).get(d, 0.0) for s, x in w.items()) + cash * rf / 252
        grown = {s: x * (1 + series.get(s, {}).get(d, 0.0)) for s, x in w.items()}
        tot = sum(grown.values()) + cash * (1 + rf / 252)
        book["w"] = {s: x / tot for s, x in grown.items()} if tot > 0 else {}
        book["nav"] *= 1 + r
        out.append((d, r))
    return out


def rebalance(book, target, c, sig, adv):
    """무거래 구간 밖만 부분 조정. 반환 (회전, 비용)"""
    o = c["ledger"]
    w = dict(book["w"])
    turnover = cost = 0.0
    for s in set(w) | set(target):
        cur, tgt = w.get(s, 0.0), target.get(s, 0.0)
        gap = tgt - cur
        if abs(gap) <= max(o["band"] * tgt, o["band_abs"]):
            continue
        dw = gap if tgt == 0 or cur == 0 else o["speed"] * gap   # 신규 편입·전량 정리는 한 번에
        notional = abs(dw) * book["nav"] * o["nav_usd"]
        impact = o["eta"] * sig.get(s, 0.02) * math.sqrt(notional / adv[s]) if adv.get(s) else 0.0
        cost += abs(dw) * (o["half_spread_bps"] / 1e4 + impact)
        turnover += abs(dw)
        w[s] = cur + dw
    book["w"] = {s: x for s, x in w.items() if x > 1e-6}
    book["nav"] *= 1 - cost
    return turnover, cost


def run(today=None):
    c = yaml.safe_load((ROOT / "config" / "pm.yaml").read_text(encoding="utf-8"))
    px = risk.load_prices()
    series = {k: risk.returns(v) for k, v in px.items()}
    tg = targets(c)
    need = {s for t in tg.values() for s in t}
    last_px = max(v[-1][0] for k, v in px.items() if k in need and v)
    sig = {s: (sum(x * x for x in list(series[s].values())[-63:]) / max(1, len(list(series[s].values())[-63:]))) ** 0.5 for s in need if series.get(s)}
    adv = {s: sum(b[1] * b[2] for b in px[s][-30:]) / len(px[s][-30:]) for s in need if px.get(s) and all(len(b) > 2 and b[2] for b in px[s][-30:])}
    st = json.loads(BOOK.read_text(encoding="utf-8")) if BOOK.exists() else {"books": {}, "start": last_px}
    rows = []
    for name, target in tg.items():
        bk = st["books"].setdefault(name, {"nav": 1.0, "w": {}, "last": last_px})
        days = sorted({d for s in need for d in series.get(s, {}) if bk["last"] < d <= last_px})
        daily = mark(bk, series, days, c["expected"]["rf"])
        target = {s: x for s, x in target.items() if s in px}
        bk["last"] = last_px
        for d, r in daily:
            rows.append([d, name, None, round(r, 6), "", ""])
        if bk.get("rebal") == last_px:   # 같은 시세일에 다시 돌면 거래·기록하지 않는다(하루 한 번)
            continue
        to, co = rebalance(bk, target, c, sig, adv)
        bk["rebal"] = last_px
        rows.append([last_px, name, round(bk["nav"], 6), "", round(to, 4), round(co, 6)])
    with (DIR / "weights_log.jsonl").open("a", encoding="utf-8") as f:   # 일별 시작 비중(4단계 브린슨 귀속 재료)
        for name, bk in st["books"].items():
            for d, w in bk.pop("_snap", []):
                f.write(json.dumps({"date": d, "book": name, "w": w}, ensure_ascii=False) + "\n")
    st["as_of"] = datetime.now(KST).isoformat(timespec="seconds")
    st["note"] = "연구용 가상 포트폴리오 장부 — 매매·비중 지시가 아님"
    DIR.mkdir(parents=True, exist_ok=True)
    BOOK.write_text(json.dumps(st, ensure_ascii=False, indent=1), encoding="utf-8")
    new = not LOG.exists()
    with LOG.open("a", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        if new:
            w.writerow(["date", "book", "nav", "ret", "turnover", "cost"])
        w.writerows(rows)
    return st


def summary(st):
    b = st["books"]
    spy = b.get("SPY", {}).get("nav", 1.0)
    return {n: {"nav": round(x["nav"], 4), "vs_spy": round(x["nav"] / spy - 1, 4), "invested": round(sum(x["w"].values()), 3),
                "top": sorted(x["w"].items(), key=lambda kv: -kv[1])[:3]} for n, x in b.items()}


def main(argv):
    sys.stdout.reconfigure(encoding="utf-8")
    st = run()
    print(f"[PM 장부] 시작 {st['start']} · 기준 {max(x['last'] for x in st['books'].values())}")
    for n, s in summary(st).items():
        print(f"  {n}: NAV {s['nav']:.4f} · SPY 대비 {s['vs_spy']:+.2%} · 투자 {s['invested']:.0%} · 상위 {[(k, round(v, 3)) for k, v in s['top']]}")


if __name__ == "__main__":
    main(sys.argv[1:])
