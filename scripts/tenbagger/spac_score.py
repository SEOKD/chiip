"""SPAC 비대칭 점수 3단계 (마스터 지시 2026-11-04 "3단계 진행", 설계 knowledge/methods/spac_discovery_design.md 3·4절)

입력은 spac_report.py와 같은 datapack "spac"(knowledge/models/companies/<id>/datapack.json, 금액 B$·주식 백만 주)과 장부(spac_watch 단계·spac_theme 테마).
요인 6개를 0~10으로 재고 단계별 가중으로 합친다. 연구 후보 지표이지 매수 권유가 아니다(목표주가·등급 없음).
  ① 바닥    환매 전(주총 전)만 — 환매율이 기록됐거나 주총 가결이면 바닥 없음: 신탁가 대비 프리미엄 p = 주가/주당 신탁가 − 1. p ≤ 0 → 10, p ≥ 0.30 → 0(선형). p ≤ floor_premium_max면 '바닥 인정'
  ② 희석    주당 순현금 = (남은 신탁 + PIPE + 기타 − 수수료 + 피인수 현금 − 차입) / 전체 주식(워런트는 행사가 아래면 제외 — 보수적이면 포함)
            → 순현금/$10 × 10 (Klausner, Ohlrogge & Ruan 2022 — 중앙값 약 $5.7)
  ③ 사업 엣지  datapack spac.edge(0~10, Chiip 렌즈 — 병목·해결 기술·양산성·고객 채택). 없으면 테마 일치 5, 불일치 3
  ④ 가치    EV = 주가 × 전체 주식 − 순현금, 선행 매출 = 경영진 전망 첫 해 × (1 − projection_haircut).
            배수 비율 r = (EV/선행 매출) / 동종 EV/매출 → 5 − 5·log2(r) (r 0.5 → 10, 1 → 5, 2 → 0). 전망·동종 배수가 없으면 공정성 의견 중간값 대비 주가로 대신
  ⑤ 오버행  overhang_days 안에 풀리는 보호예수 주식 / 유통 주식(환매 후 공개 주주 + PIPE) → 10·(1 − min(1, 비율/3))
  ⑥ 관심    환매율이 높아 유통이 작고 프리미엄이 크면 쏠림(양방향) — 5 ± 정보 없음이면 5
킬 조건: 계약 해지·환매 ≥ 95%에 PIPE 0·시한 연장 3회 이상인데 확정 계약 없음·재매각 대량 등록(datapack flags)
사용: py scripts/tenbagger/spac_score.py <회사 id> [--price <현재가>]     → 한 종목
      py scripts/tenbagger/spac_score.py --all                            → datapack에 spac이 있는 모든 종목 → knowledge/models/spac/scores.csv, candidates.json
      py scripts/tenbagger/spac_score.py --needs                          → 테마가 맞은 S2+ 스팩 중 datapack이 없는 것(모델이 서류로 채울 목록)
"""
import csv
import json
import math
import sys
from datetime import date, timedelta
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
COMP = ROOT / "knowledge" / "models" / "companies"
DIR = ROOT / "knowledge" / "models" / "spac"


def cfg():
    return yaml.safe_load((ROOT / "config" / "spac.yaml").read_text(encoding="utf-8"))["score"]


def lin(x, lo, hi):
    """x가 lo면 10, hi면 0(선형, 밖은 자름)"""
    return max(0.0, min(10.0, 10 * (hi - x) / (hi - lo)))


def net_cash(s):
    c = s.get("cash") or {}
    return (c.get("trust_left") or 0) + (c.get("pipe") or 0) + (c.get("other") or 0) - (c.get("fees") or 0) + (c.get("target_cash") or 0) - (c.get("debt") or 0)


def total_shares(s, price=None):
    n = sum((s.get("shares") or {}).values())
    for w in s.get("warrants") or []:   # 행사가 아래 주가면 행사될 것으로 본다(희석 보수적)
        if price is None or price >= (w.get("strike") or 1e9):
            n += w.get("count") or 0
    return n


def factors(s, stage, theme_ok, c, today=None):
    today = today or date.today()
    price = s.get("price")
    tps = s.get("trust_per_share") or 10.0
    redeemed = (s.get("redemption") or {}).get("pct") is not None or "가결" in str(s.get("status") or "")
    pre = stage in ("S2", "S3", "S4") and not redeemed   # 환매가 끝나면(주총 가결) 신탁가 바닥이 사라진다
    out, notes = {}, []
    prem = price / tps - 1 if price and tps else None
    if pre and prem is not None:
        out["floor"] = lin(prem, 0.0, 0.30)
        if prem <= c["floor_premium_max"]:
            notes.append(f"바닥 인정(프리미엄 {prem:+.1%} — 주총 전 환매권)")
    n = total_shares(s, price)
    nc = net_cash(s)
    ncps = nc * 1000 / n if n else None
    if ncps is not None:
        out["dilution"] = max(0.0, min(10.0, ncps / 10 * 10))
    out["edge"] = float(s.get("edge")) if s.get("edge") is not None else (5.0 if theme_ok else 3.0)
    ev = price * n / 1000 - nc if price and n else None
    proj = s.get("projections") or []
    rev = proj[0]["rev"] * (1 - c["projection_haircut"]) if proj and proj[0].get("rev") else None
    if ev is not None and rev and s.get("peer_ev_rev"):
        r = (ev / rev) / s["peer_ev_rev"]
        out["value"] = max(0.0, min(10.0, 5 - 5 * math.log2(max(r, 1e-6))))
        notes.append(f"EV/할인 전망 매출 {ev / rev:.1f}배 vs 동종 {s['peer_ev_rev']:.1f}배")
    elif price and (s.get("fairness") or {}).get("base") and n:
        fv = s["fairness"]["base"] * 1000 / n   # 공정성 의견 중간값(지분가치 B$)을 주당으로
        r = price / fv
        out["value"] = max(0.0, min(10.0, 5 - 5 * math.log2(max(r, 1e-6))))
        notes.append(f"공정성 의견 중간값 주당 ${fv:.2f} 대비 주가 {r:.2f}배(경영진 측 평가 — 보수적으로 읽는다)")
    flt = ((s.get("shares") or {}).get("공개 주주(환매 후)") or 0) + ((s.get("shares") or {}).get("PIPE") or 0)
    cut = (today + timedelta(days=c["overhang_days"])).isoformat()
    lock = sum(x.get("shares") or 0 for x in s.get("lockups") or [] if str(x.get("date", "9999")) <= cut)
    if flt:
        out["overhang"] = 10 * (1 - min(1.0, (lock / flt) / 3))
        if lock:
            notes.append(f"{c['overhang_days']}일 안 보호예수 해제 {lock:.0f}백만 주 = 유통의 {lock / flt:.1f}배")
    red = (s.get("redemption") or {}).get("pct")
    out["attention"] = 5.0 if red is None or prem is None else max(0.0, min(10.0, 5 + 10 * prem * (1 if red < 0.9 else -1)))
    kills = []
    if red is not None and red >= 0.95 and not (s.get("cash") or {}).get("pipe"):
        kills.append("환매 95% 이상·PIPE 없음")
    for k in s.get("flags") or []:
        if k in ("계약 해지", "재매각 대량 등록", "최소 현금 미달"):
            kills.append(k)
    return out, {"premium": None if prem is None else round(prem, 4), "net_cash_ps": None if ncps is None else round(ncps, 2),
                 "ev_b": None if ev is None else round(ev, 3), "total_shares_m": round(n, 1)}, notes, kills


def score(s, stage, theme_ok, c=None, today=None):
    c = c or cfg()
    f, nums, notes, kills = factors(s, stage, theme_ok, c, today)
    redeemed = (s.get("redemption") or {}).get("pct") is not None or "가결" in str(s.get("status") or "")
    w = dict(c["weights"]["pre_vote" if stage in ("S2", "S3", "S4") and not redeemed else "post_close"])
    w = {k: v for k, v in w.items() if k in f}
    tot = sum(w.values())
    val = round(sum(f[k] * v for k, v in w.items()) / tot, 1) if tot else None
    if kills:
        val = min(val or 0.0, c["kill_cap"])
    return {"score": val, "factors": {k: round(v, 1) for k, v in f.items()}, "missing": [k for k in c["weights"]["pre_vote"] if k not in f],
            "numbers": nums, "notes": notes, "kills": kills, "stage": stage, "base_rate": base_rate_line(c), "candidate": bool(val is not None and val >= c["candidate_min"] and not kills and theme_ok)}


def base_rate_line(c):
    """스팩 종결 뒤 기저율 한 줄(4단계 표본, config/spac.yaml score.base_rate) — 점수와 함께 읽게"""
    b = c.get("base_rate") or {}
    if not b:
        return None
    return (f"스팩 종결 뒤 기저율(2021~2025 표본 {b['n']}건, 생존 편향으로 낙관 쪽): 24개월 수익 중앙값 {b['r24m_median']:+.0%}, "
            f"−50% 이하 {b['lt_minus50_24m']:.0%}, 2배 도달 {b['ge2x_24m']:.0%}, 3배 {b['ge3x_24m']:.0%}, 10배 {b['ge10x_24m']:.0%}")


def ledger():
    reg, th = {}, {}
    for name, store in (("registry.csv", reg), ("themes.csv", th)):
        p = DIR / name
        if p.exists():
            with p.open(encoding="utf-8", newline="") as f:
                store.update({r["cik"]: r for r in csv.DictReader(f)})
    return reg, th


def spac_packs():
    for p in COMP.glob("*/datapack.json"):
        d = json.loads(p.read_text(encoding="utf-8"))
        if d.get("spac"):
            yield p.parent.name, d


def lookup(d, reg, th):
    """datapack → 장부 행(티커·이름으로 맞춘다)"""
    tk = {str(d.get("ticker") or "").upper(), str((d.get("spac") or {}).get("new_ticker") or "").upper()} - {""}
    for cik, r in reg.items():
        if tk & {x.upper() for x in (r.get("tickers") or "").split(",") if x} or (d.get("name") and d["name"].lower() in r["name"].lower()):
            return r, th.get(cik) or {}
    return {}, {}


def run_all(prices=None):
    c = cfg()
    reg, th = ledger()
    rows, cands = [], []
    for cid, d in spac_packs():
        s = dict(d["spac"])
        if prices and d.get("ticker") in prices:
            s["price"] = prices[d["ticker"]]
        r, t = lookup(d, reg, th)
        stage = r.get("stage") or s.get("stage") or "S4"
        res = score(s, stage, bool(t.get("theme")) or bool(s.get("theme")), c)
        row = {"id": cid, "ticker": d.get("ticker"), "target": s.get("target"), "stage": stage, "theme": t.get("theme") or s.get("theme") or "", **res}
        rows.append(row)
        if res["candidate"]:
            cands.append(row)
    DIR.mkdir(parents=True, exist_ok=True)
    with (DIR / "scores.csv").open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["id", "ticker", "target", "stage", "theme", "score", "floor", "dilution", "edge", "value", "overhang", "attention", "premium", "net_cash_ps", "kills"])
        for x in rows:
            fa, nu = x["factors"], x["numbers"]
            w.writerow([x["id"], x["ticker"], x["target"], x["stage"], x["theme"], x["score"], *[fa.get(k, "") for k in ("floor", "dilution", "edge", "value", "overhang", "attention")],
                        nu["premium"], nu["net_cash_ps"], "|".join(x["kills"])])
    (DIR / "candidates.json").write_text(json.dumps({"as_of": date.today().isoformat(), "min": c["candidate_min"], "candidates": cands,
                                                     "note": "연구 후보 지표 — 매수 권유가 아님"}, ensure_ascii=False, indent=1), encoding="utf-8")
    return rows


def needs():
    """테마가 맞은 확정 계약 이후 스팩 중 datapack spac이 없는 것"""
    reg, th = ledger()
    have = set()
    for _, d in spac_packs():
        r, _ = lookup(d, reg, th)
        if r:
            have.add(r["cik"])
    stages = set((yaml.safe_load((ROOT / "config" / "spac.yaml").read_text(encoding="utf-8")) or {}).get("alert_stages") or [])
    return [{"cik": k, "name": r["name"], "tickers": r["tickers"], "stage": r["stage"], "theme": th[k]["theme"], "url": r["url"]}
            for k, r in reg.items() if r["stage"] in stages and th.get(k, {}).get("theme") and k not in have]


def main(argv):
    sys.stdout.reconfigure(encoding="utf-8")
    if "--needs" in argv:
        print(json.dumps(needs(), ensure_ascii=False, indent=1))
    elif "--all" in argv:
        for x in run_all():
            print(f"{x['ticker']} {x['target']} [{x['stage']}·{x['theme'] or '테마 없음'}] 점수 {x['score']} {x['factors']} {'후보' if x['candidate'] else ''} {x['kills'] or ''}")
    else:
        cid = argv[0]
        d = json.loads((COMP / cid / "datapack.json").read_text(encoding="utf-8"))
        s = dict(d["spac"])
        if "--price" in argv:
            s["price"] = float(argv[argv.index("--price") + 1])
        reg, th = ledger()
        r, t = lookup(d, reg, th)
        print(json.dumps(score(s, r.get("stage") or "S4", bool(t.get("theme"))), ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main(sys.argv[1:])
