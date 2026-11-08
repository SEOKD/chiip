"""성장주 PEG (마스터 지시 2026-11-08 "Analysis가 성장주를 다룰 때는 멀티플 항목에서 PEG 지표도 쓰도록 해라")

PEG = Fwd 1Y P/E ÷ 다음 해 EPS 성장률(%) — 성장 속도를 감안한 P/E(Lynch 관행: 1 안팎이 성장에 맞는 값).
EPS 성장률은 회사·동종사 모두 같은 기준으로 Fwd 1Y·2Y P/E에서 역산한다: 같은 주가라면 P/E1 ÷ P/E2 − 1 = EPS2 ÷ EPS1 − 1(컨센서스 다음 해 성장).
성장주 판정: 그 성장률이 config/tenbagger.yaml peg.growth_min 이상(등록부 prm-tb-peg-growth-min). 성장이 0 이하이면 PEG를 계산하지 않는다(의미 없음).
"""
import yaml
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def cfg():
    c = yaml.safe_load((ROOT / "config" / "tenbagger.yaml").read_text(encoding="utf-8")) or {}
    return c.get("peg") or {"growth_min": 0.15}


def _g(pe1, pe2):
    """Fwd 1Y·2Y P/E → 다음 해 EPS 성장률(소수). 값이 없거나 음수 이익이면 None"""
    if not pe1 or not pe2 or pe1 <= 0 or pe2 <= 0:
        return None
    return pe1 / pe2 - 1


def _peg(pe1, g):
    return pe1 / (g * 100) if pe1 and g and g > 0 else None


def compute(dp, name="대상"):
    mn = (dp or {}).get("multiples_now") or {}
    g = _g(mn.get("pe_fwd"), mn.get("pe_fwd2"))
    c = cfg()
    if g is None or g < c["growth_min"]:
        return {"growth": g, "is_growth": False}
    rows = [{"name": name, "pe": mn["pe_fwd"], "g": g, "peg": _peg(mn["pe_fwd"], g), "self": True}]
    for p in (dp or {}).get("peers") or []:
        pg = _g(p.get("pe_fwd"), p.get("pe_fwd2"))
        rows.append({"name": p.get("ticker") or p.get("name"), "pe": p.get("pe_fwd"), "g": pg, "peg": _peg(p.get("pe_fwd"), pg), "self": False})
    pegs = sorted(r["peg"] for r in rows if not r["self"] and r["peg"] is not None)
    med = (pegs[len(pegs) // 2] if len(pegs) % 2 else (pegs[len(pegs) // 2 - 1] + pegs[len(pegs) // 2]) / 2) if pegs else None
    return {"growth": g, "is_growth": True, "rows": rows, "peer_median": med, "peg": rows[0]["peg"]}


def blocks(dp, name="대상"):
    """밸류에이션 절에 넣을 글·표·그림 — 성장주가 아니면 빈 목록"""
    c = compute(dp, name)
    if not c["is_growth"]:
        return []
    peg, med = c["peg"], c["peer_median"]
    head = f"**PEG {peg:.2f}** — Fwd 1Y P/E {c['rows'][0]['pe']:.1f}배를 다음 해 EPS 성장 {c['growth']:.0%}로 나눈 값"
    if med is not None:
        head += f", 동종 중앙 {med:.2f}({'성장 대비 싸다' if peg < med * 0.9 else ('성장 대비 비싸다' if peg > med * 1.1 else '동종과 비슷하다')})."
    else:
        head += "."
    head += " 성장률은 Fwd 1Y·2Y P/E에서 역산한 컨센서스라 다음 해 한 해 성장만 반영하고, 성장 지속 기간은 담지 않는다."
    rows = [[("**" + r["name"] + "**") if r["self"] else r["name"], "-" if r["pe"] is None else f"{r['pe']:.1f}", "-" if r["g"] is None else f"{r['g']:+.0%}",
             "-" if r["peg"] is None else f"{r['peg']:.2f}"] for r in c["rows"]]
    chart = {"kind": "hbars", "w": 480, "label_w": 130, "title": "PEG — 성장 대비 멀티플(낮을수록 성장 대비 쌈)", "unit": "",
             "rows": [{"label": r["name"], "bars": [{"name": "PEG", "color": "e" if r["self"] else "c", "value": round(r["peg"], 2)}]} for r in c["rows"] if r["peg"] is not None]}
    return [{"type": "hl", "text": head}, {"type": "table", "title": "PEG — Fwd 1Y P/E ÷ 다음 해 EPS 성장률", "headers": ["회사", "Fwd 1Y P/E", "다음 해 EPS 성장", "PEG"], "rows": rows},
            {"type": "chart", "chart": chart}]
