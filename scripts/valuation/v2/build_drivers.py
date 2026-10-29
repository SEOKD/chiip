"""데이터 묶음(datapack) → v2 동인(drivers.yaml) 자동 생성 (마스터 지시 2026-10-29 "텐배거 리포트 밸류에이션 모델링에서 easyconomics의
컨센서스·어닝콜 스크립트 등 기업 정보를 모두 취합해 변수로 활용하도록")

흐름: 모델이 easyconomics(+SEC·IR)에서 모은 숫자를 knowledge/models/companies/<id>/datapack.json에 쓴다 →
이 스크립트가 정해진 규칙으로 동인을 만든다(어느 동인이 어느 자료에서 왔는지 provenance에 남김) → scripts/valuation/v2/run.py.
손으로 만든 drivers.yaml(auto 표시 없음)이 이미 있으면 덮어쓰지 않고 drivers.auto.yaml로 쓴다(비교용).

datapack.json (금액은 unit 하나로 통일 — 보통 B$, 비율은 소수):
{ "id","name","ticker","as_of","unit":"B$",
  "industry": "semiconductor|semicap|software|software_internet|computers|electronics|electrical_equipment|telecom_equipment|power_utility",
  "region_mix": {"US":1.0}, "tax": 0.21,
  "profile":   {"price", "shares_basic", "cash", "debt", "source"},
  "dilution":  {"options", "rsu", "warrants", "converts_shares"}           # 백만 주가 아니라 shares_basic과 같은 단위(10억 주 등)
  "financials":{"rev_ttm", "ebit_ttm", "invested_capital", "capex_ttm", "da_ttm", "sbc_ttm", "s2c"},
  "consensus": {"rev": {"FY2026": x, "FY2027": y, ...}, "ebit_margin": {"FY2026": m, ...},
                "rev_low": {"FY2027": ...}, "rev_high": {"FY2027": ...}, "n_analysts", "revisions_90d": {"rev": +0.05}},
  "guidance":  {"rev_fy0": [lo, hi], "ebit_margin_fy0": m, "source"},
  "call":      {"date", "tone": "up|flat|down", "kpis": {...}, "guidance_changes": [...], "risks": [...], "source"},
  "peers":     [{"ticker","ev_sales_ntm","growth_ntm","ebit_margin"}],
  "scenario_probs": {"bear": 0.25, "base": 0.5, "bull": 0.25},             # 선택 — 없으면 규칙
  "overrides": {"growth_base": {...}, "margin_base": {...}, "s2c": x, "why": "…"}   # 선택 — 모델이 이유와 함께
}
사용: py scripts/valuation/v2/build_drivers.py <entity_id> [--force]
"""
import json
import sys
from datetime import date
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[3]
TERMINAL = {"US": 0.035, "JP": 0.02, "KR": 0.03, "TW": 0.03, "EU": 0.03}
TONE_PROB = {"up": (0.20, 0.50, 0.30), "flat": (0.25, 0.50, 0.25), "down": (0.30, 0.50, 0.20)}   # (bear, base, bull)


def _fy_sorted(d):
    return [d[k] for k in sorted(d or {})]


def clamp(x, lo, hi):
    return max(lo, min(hi, x))


def build(p):
    prov = {}
    region = max(p.get("region_mix") or {"US": 1.0}, key=(p.get("region_mix") or {"US": 1.0}).get)
    end = TERMINAL.get(region, 0.03)
    cons, fin, gd, call = p.get("consensus") or {}, p.get("financials") or {}, p.get("guidance") or {}, p.get("call") or {}
    revs = _fy_sorted(cons.get("rev"))

    # 매출 기준점: 가이던스 중간값(회사) > 컨센서스 당해 > TTM
    if gd.get("rev_fy0"):
        rev0 = sum(gd["rev_fy0"]) / 2
        prov["rev0"] = f"회사 가이던스 중간값 {gd['rev_fy0']} ({gd.get('source', '어닝콜·보도자료')})"
    elif revs:
        rev0 = revs[0]
        prov["rev0"] = f"컨센서스 {sorted(cons['rev'])[0]} {rev0}"
    else:
        rev0 = fin["rev_ttm"]
        prov["rev0"] = "TTM 매출(컨센서스 없음)"

    # 성장: 컨센서스 1·2년차 성장 → 지수 감속으로 영구성장에 수렴
    g1 = revs[1] / rev0 - 1 if len(revs) >= 2 else None
    g2 = revs[2] / revs[1] - 1 if len(revs) >= 3 else None
    if g1 is None:
        g1 = 0.10
        prov["growth"] = "컨센서스 없음 — 기본 10% 가정(약함)"
    else:
        prov["growth"] = f"컨센서스 1년차 {g1:.1%}" + (f", 2년차 {g2:.1%}" if g2 is not None else "")
    if g2 is not None and g1 - end > 0.005:
        decay = clamp((g2 - end) / (g1 - end), 0.3, 0.9)
    else:   # 2년차 추정이 없으면: 초고성장(50%+)은 빨리 식는다(매출 성장 기저율 — 고성장 지속 확률이 낮음)
        decay = 0.45 if g1 > 0.5 else 0.7
    growth_base = {"start": round(g1, 4), "end": end, "decay": round(decay, 3)}

    # 이익률: 가이던스 > 컨센서스 당해 > TTM, 목표는 컨센서스 가장 먼 해 > 동종 중앙값 > 현재
    margins = cons.get("ebit_margin") or {}
    if gd.get("ebit_margin_fy0") is not None:
        m0, src = gd["ebit_margin_fy0"], "회사 가이던스"
    elif margins:
        m0, src = margins[sorted(margins)[0]], f"컨센서스 {sorted(margins)[0]}"
    else:
        m0, src = (fin["ebit_ttm"] / fin["rev_ttm"]) if fin.get("rev_ttm") else 0.10, "TTM EBIT 이익률"
    peer_m = sorted(x["ebit_margin"] for x in p.get("peers") or [] if x.get("ebit_margin") is not None)
    if len(margins) >= 2:
        target, tsrc, yt = margins[sorted(margins)[-1]], f"컨센서스 {sorted(margins)[-1]}", clamp(len(margins) - 1, 1, 5)
    elif peer_m:
        target, tsrc, yt = peer_m[len(peer_m) // 2], f"동종 {len(peer_m)}사 중앙값", 4
    else:
        target, tsrc, yt = m0, "현재 유지", 3
    margin_base = {"m0": round(m0, 4), "target": round(target, 4), "year_target": int(yt), "lr": 0.15, "lam": 0.35}
    prov["margin"] = f"출발 {src} {m0:.1%} → 목표 {tsrc} {target:.1%}({int(yt)}년)"

    # 재투자 효율(매출/투하자본 증분)
    if fin.get("s2c"):
        s2c, ssrc = fin["s2c"], "재무 재구성 증분 매출/투하자본"
    elif fin.get("invested_capital") and fin.get("rev_ttm"):
        s2c, ssrc = fin["rev_ttm"] / fin["invested_capital"], "TTM 매출 ÷ 투하자본(평균 근사)"
    else:
        s2c, ssrc = 2.0, "기본값(자료 없음)"
    s2c = round(clamp(s2c, 0.5, 6.0), 3)
    prov["s2c"] = f"{ssrc} {s2c}"

    # 강세·약세: 컨센서스 고·저 추정의 2년차 성장 폭, 없으면 ±40%
    lo_, hi_ = _fy_sorted(cons.get("rev_low")), _fy_sorted(cons.get("rev_high"))
    if lo_ and hi_:
        g_bear, g_bull = lo_[0] / rev0 - 1, hi_[0] / rev0 - 1
        prov["range"] = f"컨센서스 최저·최고 추정 → 1년차 성장 {g_bear:.1%}~{g_bull:.1%}"
    else:
        if g1 > 1.0:   # 초고성장: 약세는 램프 지연(성장의 40%), 강세는 +25%
            g_bear, g_bull = g1 * 0.4, g1 * 1.25
            prov["range"] = "고·저 추정 없음 — 초고성장 규칙(약세 ×0.4·강세 ×1.25)"
        else:
            g_bear, g_bull = g1 * 0.6, g1 * 1.4
            prov["range"] = "고·저 추정 없음 — 1년차 성장 ±40%"
    tone = call.get("tone") or "flat"
    probs = p.get("scenario_probs") or dict(zip(("bear", "base", "bull"), TONE_PROB.get(tone, TONE_PROB["flat"])))
    prov["probs"] = ("데이터 묶음 지정" if p.get("scenario_probs") else f"어닝콜 톤 '{tone}' 규칙") + f" {probs}"
    spread = clamp(abs(target - m0) * 0.5, 0.02, 0.08)   # 강세·약세 목표 이익률 폭 — 최대 ±8%p

    ov = p.get("overrides") or {}
    if ov:
        prov["overrides"] = ov.get("why", "이유 미기재")
    growth_base = ov.get("growth_base", growth_base)
    margin_base = ov.get("margin_base", margin_base)
    s2c = ov.get("s2c", s2c)

    pf, dl = p["profile"], p.get("dilution") or {}
    shares = pf["shares_basic"] + sum(dl.get(k) or 0 for k in ("options", "rsu", "warrants", "converts_shares"))
    prov["shares"] = f"완전 희석 = 기본 {pf['shares_basic']} + 옵션·RSU·워런트·전환 {shares - pf['shares_basic']:.4f}"
    net_debt = (pf.get("debt") or 0) - (pf.get("cash") or 0)
    ic0 = fin.get("invested_capital") or max(0.1, rev0 / s2c)

    drivers = {
        "auto": True, "id": p["id"], "name": p["name"], "ticker": p.get("ticker"), "unit": p.get("unit", "B$"),
        "unit_usd": 1e9 if p.get("unit", "B$") == "B$" else None, "industry": p["industry"], "region_mix": p.get("region_mix") or {"US": 1.0},
        "tax": p.get("tax", 0.21), "horizon": 10, "as_of": p.get("as_of") or date.today().isoformat(),
        "market": {"date": p.get("as_of"), "price": pf["price"], "shares": round(shares, 6), "net_debt": round(net_debt, 6), "source": pf.get("source", "easyconomics")},
        "rev0": round(rev0, 6), "ic0": round(ic0, 6),
        "scenarios": {
            "base": {"prob": probs["base"], "growth": growth_base, "margin": margin_base, "s2c": s2c},
            "bull": {"prob": probs["bull"], "growth": {"start": round(g_bull, 4), "end": end + 0.005, "decay": min(0.9, growth_base["decay"] + 0.05)},
                     "margin": {**margin_base, "target": round(margin_base["target"] + spread, 4), "lam": 0.25}, "s2c": round(s2c * 1.15, 3)},
            "bear": {"prob": probs["bear"], "growth": {"start": round(g_bear, 4), "end": end - 0.005, "decay": max(0.3, growth_base["decay"] - 0.1)},
                     "margin": {**margin_base, "target": round(margin_base["target"] - spread, 4), "lam": 0.5}, "s2c": round(s2c * 0.85, 3)}},
        "mc": {"sigma_growth": round(clamp((g_bull - g_bear) / 4, 0.03, 0.12), 4), "sigma_margin": 0.02, "sigma_s2c": 0.2, "sigma_wacc": 0.005},
        "provenance": prov,
        "notes": [f"자동 생성(build_drivers) {date.today().isoformat()} — 데이터 묶음 {p.get('as_of')}"] + ([f"어닝콜 위험: {r}" for r in call.get("risks") or []][:3]),
        "evidence": p.get("sources") or [],
    }
    return drivers


def main(argv):
    sys.stdout.reconfigure(encoding="utf-8")
    eid = argv[0]
    folder = ROOT / "knowledge" / "models" / "companies" / eid
    p = json.loads((folder / "datapack.json").read_text(encoding="utf-8"))
    d = build(p)
    target = folder / "drivers.yaml"
    if target.exists() and "--force" not in argv:
        cur = yaml.safe_load(target.read_text(encoding="utf-8")) or {}
        if not cur.get("auto"):
            target = folder / "drivers.auto.yaml"   # 손으로 만든 동인은 보존
    target.write_text(yaml.safe_dump(d, allow_unicode=True, sort_keys=False), encoding="utf-8")
    print(f"[동인] {target.relative_to(ROOT).as_posix()}")
    for k, v in d["provenance"].items():
        print(f"  - {k}: {v}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
