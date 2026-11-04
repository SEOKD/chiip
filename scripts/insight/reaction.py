"""실적 발표 주가 반응 합리성 엔진 (마스터 지시 2026-11-04 "장전·장후 주가 반응이 왜 그렇게 나왔는지 해석하고 합리적인지 불합리한지 판단하라.
시장 가격이 대부분 정답이지만 시장이 그릇된 판단을 낼 때 아비트라지가 생긴다. 합리성을 10점 만점에 정량화 … 여러 전문가 집단의 집단 지성 … 정성·정량 동반,
정량은 프로페셔널 모델링") — 절차 knowledge/methods/reaction_rationality.md

정량(이 스크립트, 결정론):
  1. 사건 크기 σ_e  = 이 종목 과거 실적일 비정상 수익(AR)의 RMS(관측 4건 미만이면 사전값 × β 보정)
  2. 서프라이즈 표준화 z_k = 이번 서프라이즈 / 과거 서프라이즈 표준편차(EPS·매출, 가이던스는 사전 척도)
  3. 이익 반응 계수(ERC) b = 과거 (z_EPS, z_매출) → AR/σ_e 능형 회귀, 사전값(가이던스가 가장 큼) 쪽으로 n0건 상당 축소
     (Ball & Brown 1968; Kothari 2001 ERC 개관; 가이던스 우위 — Anilowski, Feng & Skinner 2007)
  4. 기대 반응 ÂR = σ_e · 3·tanh((b·z)/3) − κ·선반영(발표 전 20일 초과 상승)  — 이미 오른 만큼 덜 오르는 것이 정상
  5. 실제 AR = 종목 − β·시장(장전 발표 = 당일 종가/전일 종가, 장후 = 다음 날 종가/발표일 종가, 시간외 값이 있으면 그것을 1차 반응으로)
  6. 잔차 z_r = (AR − ÂR)/σ_r → 정량 합리성 Q = 10·exp(−z_r²/8)   (z 1 → 8.8 · 2 → 6.1 · 3 → 3.2 · 4 → 1.4)
  7. 유형: |z_r| < 1 합리적 · 같은 방향인데 작음 → 과소반응(실적 후 표류 PEAD 후보, Bernard & Thomas 1989)
           · 같은 방향인데 큼 → 과잉반응(되돌림 후보, De Bondt & Thaler 1985) · 방향이 반대 → 방향 괴리(숫자 밖 정보 — 콜 톤·가이던스 질 확인)
  8. 차익 제약(Shleifer & Vishny 1997): 변동성·유동성·공매도 여건 — 괴리가 있어도 기회가 아닐 수 있다
집단 지성(--panel): 전문가 패널 라운드(델파이, Dalkey & Helmer 1963)별 점수 → 라운드 중앙값·사분위 범위·수렴 여부, 레드팀 조정
최종 = w_q·Q + (1 − w_q)·패널 최종 중앙값. 지표일 뿐 매매 지시가 아니다.
사용: py scripts/insight/reaction.py <입력 json> [--panel <패널 json>] [--log]
입력(scripts/insight/reaction_data.js가 Fiscal.ai로 만든다):
  {"ticker","date","session":"pre|post","beta", "surprise":{"eps":%,"rev":%,"guide":%|null},
   "reaction":{"stock":%,"market":%,"peers":%|null,"extended":%|null}, "pre_drift20":%(종목−시장),
   "history":[{"date","eps":%,"rev":%,"ar":%}], "adv_usd":…, "vol_ann":…}
"""
import json
import math
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]


def cfg():
    return yaml.safe_load((ROOT / "config" / "insight" / "reaction.yaml").read_text(encoding="utf-8"))


def sd(xs):
    xs = [x for x in xs if x is not None]
    if len(xs) < 2:
        return None
    m = sum(xs) / len(xs)
    return math.sqrt(sum((x - m) ** 2 for x in xs) / (len(xs) - 1))


def ridge_fit(Z, y, prior, n0):
    """y ≈ Z·b, 사전 b0 쪽 능형 축소: b = (Z'Z + n0·I)⁻¹(Z'y + n0·b0)"""
    k = len(prior)
    A = [[sum(z[i] * z[j] for z in Z) + (n0 if i == j else 0.0) for j in range(k)] for i in range(k)]
    r = [sum(z[i] * t for z, t in zip(Z, y)) + n0 * prior[i] for i in range(k)]
    det = A[0][0] * A[1][1] - A[0][1] * A[1][0]
    return [(A[1][1] * r[0] - A[0][1] * r[1]) / det, (A[0][0] * r[1] - A[1][0] * r[0]) / det]


def quant(d, c=None):
    c = c or cfg()
    p = c["prior"]
    hist = [h for h in d.get("history") or [] if h.get("ar") is not None]
    beta = d.get("beta") or 1.0
    ars = [h["ar"] for h in hist]
    sig_e = math.sqrt(sum(a * a for a in ars) / len(ars)) if len(ars) >= c["min_hist"] else p["sigma_event"] * max(beta, 0.5)
    se = sd([h.get("eps") for h in hist]) if len(hist) >= c["min_hist"] else None
    sr = sd([h.get("rev") for h in hist]) if len(hist) >= c["min_hist"] else None
    se, sr = se or p["eps_scale"], sr or p["rev_scale"]
    b0 = [p["erc_eps"], p["erc_rev"]]
    rows = [h for h in hist if h.get("eps") is not None and h.get("rev") is not None]
    b = ridge_fit([[h["eps"] / se, h["rev"] / sr] for h in rows], [h["ar"] / sig_e for h in rows], b0, c["ridge_n0"]) if rows else b0
    s = d.get("surprise") or {}
    z = {"eps": (s.get("eps") or 0) / se, "rev": (s.get("rev") or 0) / sr, "guide": (s.get("guide") or 0) / p["guide_scale"] if s.get("guide") is not None else 0.0}
    lin = b[0] * z["eps"] + b[1] * z["rev"] + p["erc_guide"] * z["guide"]
    drift = d.get("pre_drift20") or 0.0
    ar_hat = sig_e * 3 * math.tanh(lin / 3) - c["kappa_drift"] * drift * (1 if lin * drift > 0 else 0)   # 같은 방향으로 미리 오른 만큼만 뺀다
    r = d["reaction"]
    first = r.get("extended") if r.get("extended") is not None else r["stock"]
    mkt = r.get("market") or 0.0
    bench = mkt * beta if r.get("peers") is None else c["w_market"] * mkt * beta + (1 - c["w_market"]) * r["peers"]
    ar = first - bench
    resid_sd = sd([h["ar"] - sig_e * 3 * math.tanh((b[0] * h["eps"] / se + b[1] * h["rev"] / sr) / 3) for h in rows]) if len(rows) >= c["min_hist"] else None
    sig_r = max(resid_sd or 0.0, c["resid_floor"] * sig_e)
    zr = (ar - ar_hat) / sig_r if sig_r else 0.0
    q = 10 * math.exp(-zr * zr / 8)
    if abs(zr) < 1:
        kind = "합리적"
    elif ar_hat * ar < 0 and abs(ar_hat) > 0.5 * sig_e:
        kind = "방향 괴리 — 숫자 밖 정보(콜 톤·가이던스 질·일회성) 확인"
    elif abs(ar) < abs(ar_hat):
        kind = "과소반응 — 실적 후 표류(PEAD) 후보"
    else:
        kind = "과잉반응 — 되돌림 후보"
    lim = []
    if (d.get("vol_ann") or 0) > c["limits"]["vol_ann"]:
        lim.append(f"연 변동성 {d['vol_ann']:.0%} — 차익 위험 큼")
    if d.get("adv_usd") is not None and d["adv_usd"] < c["limits"]["adv_usd"]:
        lim.append("거래대금 작음 — 괴리가 남아도 실행 어려움")
    return {"sigma_event": round(sig_e, 2), "hist_n": len(hist), "erc": [round(x, 3) for x in b], "erc_source": "종목 이력 축소 추정" if rows else "사전값",
            "z": {k: round(v, 2) for k, v in z.items()}, "expected_ar": round(ar_hat, 2), "actual_ar": round(ar, 2), "benchmark": round(bench, 2),
            "first_reaction": "시간외" if r.get("extended") is not None else "정규장", "resid_z": round(zr, 2), "quant_score": round(q, 1), "kind": kind,
            "resid_1sigma_pp": round(sig_r, 1), "low_power": sig_r > c["low_power_pp"],   # 잔차 1σ가 크면 '합리적' 판정이 관대하다 — 패널 비중을 믿는다
            "limits_to_arbitrage": lim}


def panel(pj, c=None):
    """{"rounds": [{"round": 1, "scores": {"셀사이드": 6, …}, "notes": {…}}, …], "redteam": {"adjust": -0.5, "why": "…"}}"""
    c = c or cfg()
    out = []
    for r in pj.get("rounds") or []:
        v = sorted(float(x) for x in r["scores"].values())
        n = len(v)
        med = v[n // 2] if n % 2 else (v[n // 2 - 1] + v[n // 2]) / 2
        iqr = v[(3 * n) // 4] - v[n // 4] if n >= 4 else v[-1] - v[0]
        out.append({"round": r.get("round"), "median": round(med, 1), "iqr": round(iqr, 1), "n": n})
    if not out:
        return None
    adj = max(-c["panel"]["redteam_cap"], min(c["panel"]["redteam_cap"], float((pj.get("redteam") or {}).get("adjust") or 0)))
    final = max(0.0, min(10.0, out[-1]["median"] + adj))
    return {"rounds": out, "converged": len(out) > 1 and out[-1]["iqr"] <= out[0]["iqr"], "weak_consensus": out[-1]["iqr"] > c["panel"]["weak_iqr"],
            "redteam_adjust": adj, "final": round(final, 1)}


def combine(qr, pr, c=None):
    c = c or cfg()
    if not pr:
        return {"score": qr["quant_score"], "basis": "정량만(패널 없음)"}
    w = c["w_quant"]
    return {"score": round(w * qr["quant_score"] + (1 - w) * pr["final"], 1), "basis": f"정량 {w:.0%} + 패널 {1 - w:.0%}"}


def main(argv):
    sys.stdout.reconfigure(encoding="utf-8")
    d = json.loads(Path(argv[0]).read_text(encoding="utf-8"))
    qr = quant(d)
    pr = panel(json.loads(Path(argv[argv.index("--panel") + 1]).read_text(encoding="utf-8"))) if "--panel" in argv else None
    out = {"ticker": d.get("ticker"), "date": d.get("date"), "quant": qr, "panel": pr, "rationality": combine(qr, pr), "note": "합리성 지표 — 매매 지시가 아님"}
    if "--log" in argv:   # 성적표 재료: 5·20거래일 뒤 표류(drift5·drift20)는 나중에 채운다
        import csv
        log = ROOT / "knowledge" / "models" / "earnings" / "reaction_log.csv"
        new = not log.exists()
        log.parent.mkdir(parents=True, exist_ok=True)
        with log.open("a", encoding="utf-8", newline="") as f:
            w = csv.writer(f)
            if new:
                w.writerow(["date", "ticker", "session", "expected_ar", "actual_ar", "resid_z", "kind", "quant", "panel", "score", "low_power", "drift5", "drift20"])
            w.writerow([d.get("date"), d.get("ticker"), d.get("session"), qr["expected_ar"], qr["actual_ar"], qr["resid_z"], qr["kind"], qr["quant_score"],
                        (pr or {}).get("final", ""), out["rationality"]["score"], qr["low_power"], "", ""])
    print(json.dumps(out, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main(sys.argv[1:])
