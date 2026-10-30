"""치입 인사이트 판단 계산기 (knowledge/methods/insight_framework.md 2~6단계의 숫자 부분) — 2026-10-29 마스터 지시

모델이 판단 전에 숫자를 같은 방식으로 계산하게 한다(손으로 어림하면 단위·분모가 흔들린다). 금액 단위는 호출자가 통일한다.
사용(펄스·포트폴리오가 부른다):
  py scripts/insight/insight_calc.py materiality --amount 75 --mcap 55932 [--revenue 5500] [--ev 52502]
  py scripts/insight/insight_calc.py bridge --delta-op 75 --tax 0.3 --multiple 31.9 --mcap 55932
  py scripts/insight/insight_calc.py bridge --delta-cf 300 --years 4 --rate 0.10 --mcap 20000      # 현금흐름 현재가치 방식
  py scripts/insight/insight_calc.py priced --stock -4.0 --market 0.5 --beta 1.6 --implied 3.0
  py scripts/insight/insight_calc.py breakeven --cost 1142 --annual 273 [--rate 0.10]
  py scripts/insight/insight_calc.py score --novelty 3 --materiality 1 --mispricing 2 --confidence 1
  py scripts/insight/insight_calc.py baserate seo
  py scripts/insight/insight_calc.py diffusion --link --afterhours --filing     # 반영 지연 조건 표시
"""
import argparse
import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def materiality(amount, mcap=None, revenue=None, ev=None):
    """사건 금액의 상대 크기와 등급(10%+ 매우 큼 · 3~10 큼 · 1~3 중간 · 1 미만 작음), 점수 0~3"""
    ratios = {k: round(amount / v * 100, 2) for k, v in (("mcap", mcap), ("revenue", revenue), ("ev", ev)) if v}
    top = max(ratios.values()) if ratios else None
    if top is None:
        grade, pts = "정성 — 분모 없음", 1
    elif top >= 10:
        grade, pts = "매우 큼", 3
    elif top >= 3:
        grade, pts = "큼", 2
    elif top >= 1:
        grade, pts = "중간", 1
    else:
        grade, pts = "작음", 0
    return {"ratios_pct": ratios, "grade": grade, "points": pts}


def bridge(mcap, delta_op=None, tax=0.25, multiple=None, delta_cf=None, years=None, rate=0.10):
    """Δ지분가치와 시총 대비 %. (가) Δ영업이익×(1−세율)×PER (나) Δ연간 현금흐름의 years년 현재가치"""
    if delta_op is not None and multiple:
        dv, how = delta_op * (1 - tax) * multiple, f"Δ영업이익 {delta_op} × (1−{tax}) × {multiple}배"
    elif delta_cf is not None and years:
        dv = delta_cf * (1 - (1 + rate) ** -years) / rate
        how = f"Δ현금흐름 {delta_cf} × {years}년 연금현가({rate:.0%})"
    else:
        raise ValueError("delta_op+multiple 또는 delta_cf+years 필요")
    return {"delta_value": round(dv, 2), "pct_of_mcap": round(dv / mcap * 100, 2), "how": how}


def priced(stock, market=0.0, beta=1.0, implied=None):
    """비정상 수익률(AR = 종목 − β×시장, %)과 반영 비율(AR ÷ 밸류 다리 %). MacKinlay (1997) 사건 연구"""
    ar = round(stock - beta * market, 2)
    out = {"abnormal_return_pct": ar}
    if implied:
        r = round(ar / implied, 2)
        if r < 0:
            label = "역방향 반응 — 기대가 더 높았거나 다른 해석"
        elif r < 0.3:
            label = "덜 반영(지연 가능)"
        elif r <= 1.3:
            label = "대체로 반영"
        elif r <= 1.5:
            label = "다소 과잉"
        else:
            label = "과잉 반영(되돌림 위험)"
        out.update({"priced_ratio": r, "label": label})
    return out


def breakeven(cost, annual, rate=None):
    """손익분기 기간(연): 할인 없음 = 원가÷연간 순수입, 할인 = 연금현가가 원가와 같아지는 기간"""
    out = {"years_undiscounted": round(cost / annual, 2)}
    if rate:
        x = 1 - cost / annual * rate
        out["years_discounted"] = round(-math.log(x) / math.log(1 + rate), 2) if x > 0 else None
    return out


DIFFUSION = {
    "link": ("고객·공급사 경제적 연결", "Cohen & Frazzini (2008), JF 63(4)"),
    "complex": ("복합 기업(여러 사업부)", "Cohen & Lou (2012), JFE 104(2)"),
    "filing": ("서류 속 문장 변화·보도자료 없는 공시", "Cohen, Malloy & Nguyen (2020), JF 75(3)"),
    "afterhours": ("금요일·장 마감 후 발표", "DellaVigna & Pollet (2009), JF 64(2)"),
    "short": ("공개 숏 리포트", "Ljungqvist & Qian (2016), RFS 29(8)"),
    "smallcap": ("소형주·커버리지 적음", "Hong, Lim & Stein (2000), JF 55(1)"),
    "callqa": ("어닝콜 Q&A 속 변화·답변 회피(전문 지연 게재)", "Matsumoto, Pronk & Roelofsen (2011), TAR 86(4); Hollander, Pronk & Roelofsen (2010), JAR 48(3)"),
    "foreign": ("외국어 1차 자료(일본어·중국어 공시)", "치입 운영 가설 — 문헌 미확인"),
}


def diffusion(flags, priced_label=None):
    hits = [DIFFUSION[f] for f in flags if f in DIFFUSION]
    under = bool(priced_label and priced_label.startswith("덜"))
    over = bool(priced_label and ("과잉" in priced_label))
    pts = 2 if (under and len(hits) >= 2) or over else (1 if hits else 0)
    return {"conditions": [h[0] for h in hits], "sources": [h[1] for h in hits], "points": pts}


def score(novelty, materiality_pts, mispricing, confidence):
    """인사이트 점수 = 새로움(0~3) + 중요도(0~3) + 가격 오류 가능성(0~2) + 확신도(0~2). 7 이상이면 '치입 판단'을 맨 위에"""
    s = min(novelty, 3) + min(materiality_pts, 3) + min(mispricing, 2) + min(confidence, 2)
    return {"score": s, "lead_with_view": s >= 7, "fact_only": s < 4, "prediction_required": s >= 7}


def baserate(key):
    import yaml
    d = yaml.safe_load((ROOT / "config" / "insight" / "base_rates.yaml").read_text(encoding="utf-8"))
    ev = (d.get("events") or {}).get(key)
    if not ev:
        return {"error": f"모르는 유형: {key}", "known": sorted((d.get("events") or {}).keys())}
    return ev


def main(argv):
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    sp = ap.add_subparsers(dest="cmd", required=True)
    m = sp.add_parser("materiality")
    m.add_argument("--amount", type=float, required=True)
    m.add_argument("--mcap", type=float)
    m.add_argument("--revenue", type=float)
    m.add_argument("--ev", type=float)
    b = sp.add_parser("bridge")
    b.add_argument("--mcap", type=float, required=True)
    b.add_argument("--delta-op", type=float)
    b.add_argument("--tax", type=float, default=0.25)
    b.add_argument("--multiple", type=float)
    b.add_argument("--delta-cf", type=float)
    b.add_argument("--years", type=float)
    b.add_argument("--rate", type=float, default=0.10)
    p = sp.add_parser("priced")
    p.add_argument("--stock", type=float, required=True)
    p.add_argument("--market", type=float, default=0.0)
    p.add_argument("--beta", type=float, default=1.0)
    p.add_argument("--implied", type=float)
    e = sp.add_parser("breakeven")
    e.add_argument("--cost", type=float, required=True)
    e.add_argument("--annual", type=float, required=True)
    e.add_argument("--rate", type=float)
    s = sp.add_parser("score")
    for k in ("novelty", "materiality", "mispricing", "confidence"):
        s.add_argument(f"--{k}", type=float, required=True)
    r = sp.add_parser("baserate")
    r.add_argument("key")
    d = sp.add_parser("diffusion")
    for k in DIFFUSION:
        d.add_argument(f"--{k}", action="store_true")
    d.add_argument("--priced-label")
    a = ap.parse_args(argv)
    if a.cmd == "materiality":
        out = materiality(a.amount, a.mcap, a.revenue, a.ev)
    elif a.cmd == "bridge":
        out = bridge(a.mcap, a.delta_op, a.tax, a.multiple, a.delta_cf, a.years, a.rate)
    elif a.cmd == "priced":
        out = priced(a.stock, a.market, a.beta, a.implied)
    elif a.cmd == "breakeven":
        out = breakeven(a.cost, a.annual, a.rate)
    elif a.cmd == "score":
        out = score(a.novelty, a.materiality, a.mispricing, a.confidence)
    elif a.cmd == "baserate":
        out = baserate(a.key)
    else:
        out = diffusion([k for k in DIFFUSION if getattr(a, k)], a.priced_label)
    print(json.dumps(out, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
