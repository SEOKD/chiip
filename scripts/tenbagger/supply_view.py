"""텐배거 리포트 '공급망 병목' 절 (마스터 지시 2026-11-02 "기업을 중심으로 형성된 부품 공급망(밸류체인) 업체들을 분석하고 공급망 신뢰성이 얼마나 높은지 분석해
10점 만점에 정량화하라", "신뢰성은 공급병목 관점에서 파악하라")

숫자는 여기서 계산한다. 모델은 datapack "supply"에 원자료만 쓴다. 모르는 값은 "미확인"으로 두고 지어내지 않는다.
datapack "supply":
  {"as_of": "2026-09-30", "summary": "한 줄",
   "links": [{"item": "HBM",              # 공급 품목. margin BOM의 item과 같은 이름이면 마진 민감도가 붙는다
              "critical": true,           # 이 품목이 끊기면 출하가 멈추나
              "suppliers": [{"name": "SK하이닉스", "role": "HBM3E 12단", "share": 0.6, "status": "공시", "source": "10-K p.14"}],   # STATUS 중 하나. 이름을 공개하지 않으면 "미공개"
              "qualified": 2,             # 이 회사가 인증한 공급사 수
              "capacity": "부족", "capacity_basis": "2026년 물량 완판 발언, 콜 날짜",   # 품목 전체의 공급 여력(config supply.capacity 중 하나)
              "lead_weeks": 40, "lead_normal": 20,   # 지금과 평시 리드타임
              "requal_months": 12,        # 다른 공급사 재인증 기간
              "top_share": 0.6,           # 품목 세계 1위 공급사 점유율
              "region_share": 0.9, "region": "한국",   # 한 지역 생산 집중도
              "secured": "장기계약",      # 물량을 묶어 둔 방식(config supply.secured 중 하나)
              "why": "왜 병목이거나 아닌가",
              "relief": "병목이 풀리는 조건과 시점, 증설은 장비 반입·수율 확인까지. 모르면 미확인",
              "source": "대표 출처"}]}          # 요인 값을 모르면 칸을 "미확인"으로 쓴다
  공급 품목이 없는 회사: {"none": "이유"} → 절을 넣지 않는다. 서비스 회사는 GPU·전력·데이터센터 임대 같은 투입물을 품목으로 쓴다.

엔진 계산(config/supply_bottleneck.yaml supply, 점수가 높을수록 병목이 적다): 품목 점수 = 채운 요인의 가중 평균.
공급망 신뢰성 = 가장 약한 필수 품목 × weakest_weight + 원가 가중 평균 × 나머지. 요인을 min_factors보다 적게 채운 품목은 점수에서 빼고 건수를 밝힌다.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import margin_view  # noqa: E402

UNKNOWN = "미확인"
STATUS = ("공시", "회사 발표", "보도", "추정")
FACTORS = {"capacity": "캐파 여유", "sources": "복수 공급원", "lead": "리드타임", "requal": "재인증 기간", "concentration": "공급 집중", "secured": "물량 확보", "region": "지역 분산"}
MIN_LINKS = 2


def _num(x):
    return float(x) if isinstance(x, (int, float)) and not isinstance(x, bool) else None


def scale(v, best, worst):
    """best면 10점, worst면 1점, 사이는 직선"""
    return max(1.0, min(10.0, 10 - 9 * (v - best) / (worst - best)))


def factors(x, cfg):
    """채운 요인의 점수만 낸다 — 빈칸은 재지 않는다"""
    out = {}
    if x.get("capacity") in cfg["capacity"]:
        out["capacity"] = float(cfg["capacity"][x["capacity"]])
    n = _num(x.get("qualified"))
    if n is not None and n >= 1:
        out["sources"] = float(cfg["sources"][min(int(n), max(cfg["sources"]))])
    now, usual = _num(x.get("lead_weeks")), _num(x.get("lead_normal"))
    if now is not None and usual:
        out["lead"] = scale(now / usual, cfg["lead"]["best"], cfg["lead"]["worst"])
    for key, src, conf in (("requal", "requal_months", "requal"), ("concentration", "top_share", "concentration"), ("region", "region_share", "region")):
        v = _num(x.get(src))
        if v is not None:
            out[key] = scale(v, cfg[conf]["best"], cfg[conf]["worst"])
    if x.get("secured") in cfg["secured"]:
        out["secured"] = float(cfg["secured"][x["secured"]])
    return out


def grade(score, cfg):
    return next(name for floor, name in cfg["grades"] if score >= floor)


def compute(dp):
    cfg, sp = margin_view.config()["supply"], dp["supply"]
    bom = {}
    if (dp.get("margin") or {}).get("products"):
        for r in margin_view.compute(dp)["items"]:
            bom.setdefault(r["item"], []).append(r)
    rows, thin = [], []
    for x in sp["links"]:
        f = factors(x, cfg)
        same = bom.get(x["item"], [])
        moves = [r["opm_move"] for r in same if r["opm_move"] is not None]
        weights = [r["cost_weight"] for r in same if r["cost_weight"] is not None]
        row = {**x, "factors": f, "opm_move": sum(moves) if moves else None, "cost_weight": sum(weights) if weights else None}
        if len(f) < cfg["min_factors"]:
            thin.append(row)
            continue
        w = cfg["weights"]
        row["score"] = sum(w[k] * v for k, v in f.items()) / sum(w[k] for k in f)
        row["grade"] = grade(row["score"], cfg)
        rows.append(row)
    if not rows:
        raise ValueError(f"datapack supply: 요인을 {cfg['min_factors']}개 이상 채운 품목이 없다")
    rows.sort(key=lambda r: r["score"])
    must = [r for r in rows if r.get("critical")] or rows
    weakest = must[0]
    known = [r["cost_weight"] for r in rows if r["cost_weight"]]
    fill = sum(known) / len(known) if known else 1.0
    pairs = [(r["cost_weight"] or fill, r["score"]) for r in rows]
    mean = sum(w * s for w, s in pairs) / sum(w for w, _ in pairs)
    total = cfg["weakest_weight"] * weakest["score"] + (1 - cfg["weakest_weight"]) * mean
    return {"rows": rows, "thin": thin, "weakest": weakest, "mean": mean, "score": total, "grade": grade(total, cfg), "cfg": cfg}


def check(sp):
    """예약 회차가 빈칸을 그럴듯하게 채우지 않도록 원자료를 검사한다"""
    if sp.get("none"):
        return
    links = sp.get("links") or []
    if len(links) < MIN_LINKS or len(str(sp.get("as_of") or "")) < 7:
        raise ValueError(f"datapack supply에 as_of와 links {MIN_LINKS}개 이상이 필요하다 — 공급 품목이 없으면 {{'none': '이유'}}")
    for x in links:
        name = x.get("item") or "이름 없음"
        if not x.get("suppliers") or not x.get("why") or not x.get("relief") or not x.get("source") or "critical" not in x:
            raise ValueError(f"supply {name}: suppliers·critical·why·relief·source가 필요하다(풀리는 시점을 모르면 '미확인')")
        for s in x["suppliers"]:
            if not s.get("name") or s.get("status") not in STATUS or not s.get("source"):
                raise ValueError(f"supply {name}: 공급사마다 name·status({STATUS})·source가 필요하다")


def factor_text(r):
    """병목 요인 한 줄 — 모르는 요인은 미확인으로 남긴다"""
    f, pct = r["factors"], lambda k: f"{(_num(r.get(k)) or 0) * 100:.0f}%"
    parts = (("sources", f"인증 공급사 {r.get('qualified')}곳", "인증 공급사"), ("capacity", f"캐파 {r.get('capacity')}", "캐파"), ("lead", f"리드타임 {r.get('lead_weeks')}주(평시 {r.get('lead_normal')}주)", "리드타임"),
             ("requal", f"재인증 {r.get('requal_months')}개월", "재인증"), ("concentration", f"1위 점유율 {pct('top_share')}", "1위 점유율"),
             ("region", f"{r.get('region') or '한 지역'} 집중 {pct('region_share')}", "지역 집중"), ("secured", f"물량 확보 {r.get('secured')}", "물량 확보"))
    return " · ".join(text if key in f else f"{label} {UNKNOWN}" for key, text, label in parts)


def tier(r, cfg, big):
    """병목과 마진을 함께 본 구분"""
    weak, heavy = r.get("score", 10) < cfg["weak"], r["opm_move"] is not None and abs(r["opm_move"]) >= big
    return "핵심 통제 품목" if weak and heavy else "출하 차질 위험" if weak else "가격 위험" if heavy else "일반"


def section(dp):
    sp = (dp or {}).get("supply")
    if not sp:
        raise SystemExit("datapack에 supply가 없다(scripts/tenbagger/supply_view.py 맨 위) — 공급 품목이 없으면 {'none': '이유'}, 옛 리포트 정정은 --legacy")
    check(sp)
    if sp.get("none"):
        return None
    c, cfg = compute(dp), margin_view.config()
    w, big = c["weakest"], cfg["margin"]["big_move"]
    head = f"**공급망 신뢰성 {c['score']:.1f}/10, {c['grade']}.** 가장 약한 고리는 {w['item']} {w['score']:.1f}점이고, 품목 평균은 {c['mean']:.1f}점이다."
    if c["thin"]:
        head += f" 근거가 부족한 {len(c['thin'])}건({' · '.join(x['item'] for x in c['thin'])})은 점수에서 뺐다."
    if sp.get("summary"):
        head += " " + str(sp["summary"])
    B = [{"type": "hl", "text": head}]
    B.append({"type": "chart", "chart": {"kind": "hbars", "w": 480, "label_w": 150, "title": "품목별 공급 병목 점수(10점, 낮을수록 병목)", "unit": "점",
                                         "rows": [{"label": r["item"], "bars": [{"name": "병목 점수", "color": "b" if r["score"] < c["cfg"]["weak"] else "d", "value": round(r["score"], 1)}]} for r in c["rows"]]}})
    shock = f"{cfg['margin']['shock'] * 100:+.0f}%"
    B.append({"type": "table", "title": f"병목과 마진 — 품목 가격 {shock} 시 OPM", "headers": ["품목", "점수", "판정", "구분", "OPM"],
              "rows": [[r["item"] + ("(필수)" if r.get("critical") else ""), f"{r['score']:.1f}", r["grade"], tier(r, c["cfg"], big), UNKNOWN if r["opm_move"] is None else f"{r['opm_move'] * 100:+.2f}%p"] for r in c["rows"]]})
    B.append({"type": "boxes", "items": [{"title": r["item"], "tag": f"{r['score']:.1f}/10", "lines": [["왜", r["why"]], ["병목 요인", factor_text(r)], ["풀리는 조건", r["relief"]]]} for r in c["rows"]]})
    B.append({"type": "table", "title": "공급사", "headers": ["품목", "공급사", "몫", "근거"],
              "rows": [[x["item"], s["name"] + (f"({s['role']})" if s.get("role") else ""), f"{s['share'] * 100:.0f}%" if _num(s.get("share")) is not None else UNKNOWN, s["status"]] for x in sp["links"] for s in x["suppliers"]]})
    src = {str(x["source"]) for x in sp["links"]} | {str(s["source"]) for x in sp["links"] for s in x["suppliers"]}
    return {"h2": "공급망 병목", "blocks": B, "_sources": sorted(src)}


def summary_item(dp):
    """한 장 요약 — 마진을 가장 흔드는 항목과 공급망 신뢰성"""
    mg = margin_view.compute(dp)
    top = margin_view.top_item(dp)
    a = f"GPM {mg['now']['gpm'] * 100:.1f}%, OPM {mg['now']['opm'] * 100:.1f}%."
    if top:
        a += f" OPM을 가장 흔드는 BOM 항목은 {top[0]}이고 가격 {mg['shock'] * 100:+.0f}%에 {top[1] * 100:+.2f}%p다."
    sp = dp.get("supply") or {}
    if sp and not sp.get("none"):
        c = compute(dp)
        a += f" 공급망 신뢰성은 {c['score']:.1f}/10({c['grade']})이고 가장 약한 고리는 {c['weakest']['item']}다."
    return {"q": "마진과 공급망은 어디가 약한가?", "a": a, "auto": True}
