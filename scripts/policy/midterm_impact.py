"""2026 미국 중간선거 이후 종목 영향 점수 (마스터 지시 2026-11-04 "Analysis·Pulse·Ten-bagger에 2026 미국 중간선거 이후 영향에 대해 주가가 어떤 영향을
받는지 풀이하고 주가가 오르는 영향을 받을수록 +, 반대면 −로 −10~+10 사이로 정량화")

정책은 아직 0단계(선거 결과)다 — 입법·예산 변화가 아니다(금지표: 법안 발의 → 시행). 점수는 가설이고, 실제 시장 반응으로 같이 검증한다.
  정책 점수  = Σ 채널 점수 × 회사 노출(config/midterm2026.yaml policy_channels × exposure_by_sub) × 미국 비중 계수
              — 노출: datapack midterm.exposure(모델이 근거와 함께 쓰면 우선) → 회사 하위 업종(sub·segment) 표
              — 미국 비중 계수: datapack region_mix의 미국 몫, 없으면 미국 상장 1.0 · 그 밖 0.5
  반응 점수  = 업종 ETF의 선거일 이후 비정상 누적 수익 t값 × reaction_per_t(±reaction_cap) — knowledge/models/midterm2026/latest.json
  최종       = w_policy × 정책 + (1 − w_policy) × 반응, −10~+10으로 자름. 채널별 기여와 이유를 함께 낸다
결과(시나리오)가 바뀌면(하원 확정 등) config outcome·채널 점수만 고친다. 매매 지시가 아니다.
사용: py scripts/policy/midterm_impact.py <회사 id 또는 티커> [...]   → JSON
      py scripts/policy/midterm_impact.py --all                       → knowledge/models/midterm2026/impact.json(보유·관심·리포트 종목)
"""
import json
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
MID = ROOT / "knowledge" / "models" / "midterm2026"


def cfg():
    return yaml.safe_load((ROOT / "config" / "midterm2026.yaml").read_text(encoding="utf-8"))


def _y(p):
    f = ROOT / p
    return (yaml.safe_load(f.read_text(encoding="utf-8")) or {}) if f.exists() else {}


def universe():
    """id·티커 → {sub, market}. 여러 지도를 모은다(먼저 나온 것 우선)"""
    out = {}

    def add(cid, tk, sub, market):
        for k in (cid, str(tk or "").upper()):
            if k and k not in out:
                out[k] = {"id": cid, "ticker": str(tk or "").upper(), "sub": sub, "market": market}
    for h in _y("config/portfolio.yaml").get("holdings") or []:
        add(h["id"], h.get("ticker"), h.get("sub"), "us" if str(h.get("exchange", "")).upper() in ("NYSE", "NASDAQ", "AMEX") else "other")
    for u in _y("config/valuation.yaml").get("universe") or []:
        code = str(u.get("code") or "")
        add(u["id"], code.split(".")[0], u.get("sub"), "us" if code.endswith(".US") else "other")
    for c in (_y("config/consumer.yaml").get("companies") or []) + (_y("config/consumer_auto.yaml").get("companies") or []):
        add(c["id"], c.get("code"), "consumer" if c.get("segment") not in ("household_durables", "apparel") else c["segment"], c.get("market"))
    return out


def datapack(cid):
    p = ROOT / "knowledge" / "models" / "companies" / str(cid) / "datapack.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}


def us_share(dp, market):
    rm = dp.get("region_mix") or {}
    items = rm.get("items") if isinstance(rm, dict) else rm
    for it in items or []:
        name = str(it.get("name") or it.get("region") or "")
        if any(w in name for w in ("미국", "United States", "US", "북미", "Americas")) and it.get("share") is not None:
            return max(0.2, min(1.0, float(it["share"]) + 0.2))   # 미국 몫 + 미국 증시 투자자 효과(최소 0.2)
    return 1.0 if market == "us" else 0.5


def score(key, c=None, uni=None, study=None):
    c = c or cfg()
    uni = uni if uni is not None else universe()
    study = study if study is not None else (json.loads((MID / "latest.json").read_text(encoding="utf-8")).get("study") or {} if (MID / "latest.json").exists() else {})
    u = uni.get(key) or uni.get(str(key).upper()) or {"id": key, "ticker": str(key).upper(), "sub": None, "market": "us"}
    if not datapack(u["id"]) and datapack(key):
        u = {**u, "id": key}
    if u.get("market") == "us" and not uni.get(key):   # 지도 밖 리포트 종목 — 티커·시장은 datapack으로
        d0 = datapack(key)
        u = {**u, "ticker": str(d0.get("ticker") or u["ticker"]).upper(), "market": "us" if str(key).startswith(("us-", "co-")) and not str(d0.get("ticker") or "").isdigit() else "other"}
    dp = datapack(u["id"])
    mt = dp.get("midterm") or {}
    sub = mt.get("sub") or u.get("sub") or c.get("industry_to_sub", {}).get(dp.get("industry"))
    exp = mt.get("exposure") or (c["exposure_by_sub"].get(sub) or {})
    k = us_share(dp, u.get("market"))
    parts = []
    for ch, e in exp.items():
        p = c["policy_channels"].get(ch)
        if p:
            parts.append({"channel": ch, "exposure": e, "points": round(p["score"] * float(e) * k, 2), "why": p["why"]})
    policy = max(-10.0, min(10.0, sum(x["points"] for x in parts)))
    etf = mt.get("etf") or c["etf_by_sub"].get(sub)
    st = study.get(etf) or {}
    im = c["impact"]
    react = max(-im["reaction_cap"], min(im["reaction_cap"], (st.get("t") or 0) * im["reaction_per_t"])) if st else None
    final = im["w_policy"] * policy + (1 - im["w_policy"]) * react if react is not None else policy
    o = c["outcome"]
    return {"id": u["id"], "ticker": u["ticker"], "sub": sub, "score": round(max(-10.0, min(10.0, final)), 1), "policy": round(policy, 2),
            "reaction": None if react is None else round(react, 2), "etf": etf, "etf_car": None if not st else round(st.get("car") or 0, 4),
            "etf_t": None if not st else round(st.get("t") or 0, 2), "us_factor": k, "channels": parts,
            "scenario": f"{o['scenario']}(상원 {o['senate']['party']} {o['senate']['status']} · 하원 {o['house']['party']} {o['house']['status']})",
            "note": "정책 0단계(선거 결과) 가설 + 업종 실제 반응 — 매매 지시가 아님"}


def run_all():
    c, uni = cfg(), universe()
    study = json.loads((MID / "latest.json").read_text(encoding="utf-8")).get("study") or {} if (MID / "latest.json").exists() else {}
    ids = {h["id"] for h in _y("config/portfolio.yaml").get("holdings") or [] if h.get("status") in ("보유", "관심")}
    sys.path.insert(0, str(ROOT / "scripts" / "discovery"))
    try:
        import buy_call
        ids |= set(buy_call.reports())
    except Exception:
        pass
    rows = sorted((score(i, c, uni, study) for i in ids), key=lambda r: -r["score"])
    (MID / "impact.json").write_text(json.dumps({"scenario": rows[0]["scenario"] if rows else None, "rows": rows}, ensure_ascii=False, indent=1), encoding="utf-8")
    return rows


def main(argv):
    sys.stdout.reconfigure(encoding="utf-8")
    if "--all" in argv:
        for r in run_all():
            print(f"{r['ticker'] or r['id']}: {r['score']:+.1f} (정책 {r['policy']:+.1f} · 반응 {r['reaction'] if r['reaction'] is not None else '없음'} {r['etf'] or ''}) {r['sub']}")
    else:
        print(json.dumps([score(a) for a in argv], ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main(sys.argv[1:])
