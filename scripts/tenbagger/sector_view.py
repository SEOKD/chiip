"""Analysis 리포트 '섹터 핵심 지표' 절 (마스터 지시 2026-11-13 종목 범위 확대 4단계, ADR-029)

AI 밸류체인 밖 종목은 '공급망 병목'·'BOM' 절보다 그 섹터의 실적 동인이 판단을 가른다. 섹터 판단 틀(knowledge/methods/sector_lenses/)
질문 7개 중 숫자로 답할 수 있는 칸을 표로 싣는다. 숫자는 모델이 1차 출처에서 옮기고, 이 모듈은 형식·검사만 한다(모르면 '미확인').
datapack "sector_kpis":
  {"lens": "health",                     # 판단 틀 이름(sector_lenses/<lens>.md)
   "as_of": "3Q26",
   "kpis": [{"q": 1, "name": "Gvoke 매출 비중", "value": 62, "unit": "%", "peer": null, "period": "3Q26", "source": "https://…10-Q"}],
            # q = 틀의 질문 번호. value를 모르면 null → 표에 '미확인'. peer = 동종 비교값(없으면 null)
   "edge_struct": {"score": 6.5, "why": "동종보다 나은 숫자와 지속 이유 한 줄"},   # 틀 7번 질문 — 알파 그림자(ADR-028)와 같은 기준
   "kill": "무엇이 나오면 틀렸나 — 지표·문턱·날짜"}
  섹터 지표가 맞지 않는 회사: {"none": "이유"} → 절을 넣지 않는다. 키가 없어도 절을 넣지 않는다(옛 리포트 출력 그대로).
scripts/tenbagger/sector_data.py(gather 원천 sector_data)가 질문과 섹터 공개 데이터(openFDA·FDIC)를 먼저 보여 준다.
"""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
LENSES = ROOT / "knowledge" / "methods" / "sector_lenses"
NAMES = {"health": "헬스케어", "financials": "금융", "industrials": "산업재", "consumer": "소비재", "energy": "에너지·소재", "software": "소프트웨어"}


def questions(lens):
    f = LENSES / f"{lens}.md"
    if not f.exists():
        return {}
    return {int(m[1]): m[2].split(" — ")[0].strip() for m in re.finditer(r"(?m)^(\d+)\. (.+)$", f.read_text(encoding="utf-8"))}


def _fmt(v, unit):
    if v is None:
        return "미확인"
    if isinstance(v, (int, float)):
        s = f"{v:,.1f}" if isinstance(v, float) and abs(v) < 1000 else f"{v:,.0f}"
        return f"{s}{unit or ''}"
    return str(v)


def check(sk):
    """[문제] — 비면 통과"""
    errs = []
    if not sk.get("lens") or not (LENSES / f"{sk['lens']}.md").exists():
        errs.append(f"없는 판단 틀: {sk.get('lens')}")
    if not sk.get("kpis"):
        errs.append("kpis가 비었다")
    for k in sk.get("kpis") or []:
        if not k.get("name"):
            errs.append("이름 없는 지표")
        if k.get("value") is not None and not str(k.get("source") or "").strip():
            errs.append(f"{k.get('name')}: 숫자가 있는데 출처가 없다")
    e = (sk.get("edge_struct") or {}).get("score")
    if e is not None and not 0 <= float(e) <= 10:
        errs.append("edge_struct.score는 0~10")
    if not sk.get("kill"):
        errs.append("kill(반증)이 없다")
    return errs


def section(dp, entity=None):
    sk = (dp or {}).get("sector_kpis")
    if not sk or sk.get("none"):
        return None
    errs = check(sk)
    if errs:
        raise SystemExit("datapack sector_kpis 오류(scripts/tenbagger/sector_view.py 맨 위): " + "; ".join(errs))
    lens, qs = sk["lens"], questions(sk["lens"])
    B, src = [], []
    es = sk.get("edge_struct") or {}
    head = f"**{NAMES.get(lens, lens)} 틀로 본 구조적 우위"
    head += f" {float(es['score']):.1f}/10" if es.get("score") is not None else " 미판정"
    head += f".** {es.get('why', '')}".rstrip()
    B.append({"type": "hl", "text": head})
    rows = []
    for k in sorted(sk["kpis"], key=lambda x: (x.get("q") or 99)):
        rows.append([qs.get(k.get("q"), "기타") if k.get("q") else "기타", k["name"], _fmt(k.get("value"), k.get("unit")),
                     _fmt(k.get("peer"), k.get("unit")) if k.get("peer") is not None else "—", k.get("period") or "", k.get("source") or ""])
        if str(k.get("source") or "").startswith("http"):
            src.append(k["source"])
    B.append({"type": "table", "title": f"섹터 핵심 지표({sk.get('as_of', '')}, 판단 틀 질문 번호 순)".replace("(, ", "("),
              "headers": ["판단 틀 질문", "지표", "이 회사", "동종", "기간", "출처"], "rows": rows})
    unknown = sum(1 for k in sk["kpis"] if k.get("value") is None)
    tail = f"반증: {sk['kill']}"
    if unknown:
        tail += f" 미확인 {unknown}칸은 빈칸을 채우지 않고 그대로 뒀다."
    B.append({"type": "p", "text": tail})
    return {"h2": "섹터 핵심 지표", "blocks": B, "_sources": list(dict.fromkeys(src))}
