"""산업 리포트 사고 논리 층 — 결론·핵심 논쟁·동인 분해·가격 내포 기대·시나리오·사이클 지표판·이익 풀·인과 사슬 (ADR-020)

마스터 지시 2026-11-08 "산업 리포트 양식이 사고 논리가 부실하다. IB 리포트 양식과 … 논리 구조를 참조해 고도화하라".
방법의 출처와 문턱은 config/industry_logic.yaml 맨 위. 주간(weekly_frame)·분기(quarter_frame)·사건(event_frame)이 같이 쓴다.
datapack["logic"]:
  bottom_line {call, changed, vs_prior: 첫 판단|유지|상향|하향}
  debates [{q, consensus{view, number, source}, chiip{view, number, evidence}, why_differ, signpost{date, metric, threshold}, p}]
  drivers [{pool, ref(풀:회사 id, 선택), name, volume{name, chg, source}, price{name, chg, source}, mix}]        # chg는 소수(+0.10 = +10%)
  expectations [{what, value, source, implied}]                                            # 시장이 이미 가정한 숫자
  scenarios [{case: 약세|기본|강세, p, assume, kpi, value}]                                 # p 합 1, value는 같은 단위 숫자(선택)
  cycle [{name, now, prior, kind: 선행|동행|후행, read}]
  profit_pool [{layer, before, after, why}]
  chain [{step, type: 확정사실|가이던스|추정|채널체크|자체추론|미확인, ref}]
  base_rate {text, source}  (선택)
숫자 검산은 코드가 한다: 물량 × 가격 브리지 vs 실제 세그먼트 성장(잔차), 시나리오 확률 합·확률 가중값, 인과 사슬의 가장 약한 고리.
"""
import json
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
CFG = ROOT / "config" / "industry_logic.yaml"
STRENGTH = {"확정사실": 5, "가이던스": 4, "채널체크": 3, "추정": 3, "자체추론": 2, "미확인": 0}


def cfg():
    return yaml.safe_load(CFG.read_text(encoding="utf-8"))


def applies(dp, c=None):
    c = c or cfg()
    return str(dp.get("date") or "") >= c["required_from"] or bool(dp.get("logic"))


def _num(x):
    return isinstance(x, (int, float)) and not isinstance(x, bool)


def gate(dp, kind, c=None):
    """사고 논리 관문 — 빠진 고리를 이름으로 돌려준다(비면 통과)"""
    c = c or cfg()
    if not applies(dp, c):
        return []
    L = dp.get("logic") or {}
    bad = []
    bl = L.get("bottom_line") or {}
    if not bl.get("call"):
        bad.append("logic.bottom_line.call(한 문장 결론) 없음")
    elif len(bl["call"]) > 220:
        bad.append("결론이 길다 — 220자 안 한 문장")
    if bl.get("vs_prior") not in ("첫 판단", "유지", "상향", "하향"):
        bad.append("bottom_line.vs_prior(첫 판단·유지·상향·하향) 없음")
    ds = L.get("debates") or []
    if len(ds) < c["debates"][kind]:
        bad.append(f"핵심 논쟁 {len(ds)}개 — {c['debates'][kind]}개 이상")
    for i, d in enumerate(ds, 1):
        cs, ch, sp = d.get("consensus") or {}, d.get("chiip") or {}, d.get("signpost") or {}
        miss = [k for k, ok in (("q", d.get("q")), ("시장 견해", cs.get("view")), ("시장 견해 출처", cs.get("source")), ("Chiip 견해", ch.get("view")),
                                ("왜 다른가", d.get("why_differ")), ("확인 신호 날짜", sp.get("date")), ("확인 지표", sp.get("metric")), ("문턱", sp.get("threshold"))) if not ok]
        if miss:
            bad.append(f"논쟁 {i}: " + "·".join(miss) + " 없음")
        if not (_num(d.get("p")) and 0 < d["p"] < 1):
            bad.append(f"논쟁 {i}: 확률 p(0~1) 없음")
    dr = L.get("drivers") or []
    if len(dr) < c["drivers_min"][kind]:
        bad.append("동인 분해(물량 × 가격) 없음")
    for x in dr:
        for k in ("volume", "price"):
            v = x.get(k) or {}
            if not v.get("name") or (v.get("chg") is not None and not _num(v.get("chg"))) or (v.get("chg") is None and not v.get("source")):
                bad.append(f"동인 {x.get('name')}: {k} 이름·변화율(또는 '미공시' 출처) 필요")
    if not L.get("expectations"):
        bad.append("가격 내포 기대(expectations — 시장이 이미 가정한 숫자) 없음")
    for e in L.get("expectations") or []:
        if not e.get("source"):
            bad.append(f"기대 '{e.get('what')}': 출처 없음")
    sc = L.get("scenarios") or []
    if sorted(s.get("case") for s in sc) != sorted(c["cases"]):
        bad.append("시나리오는 약세·기본·강세 세 개")
    elif abs(sum(float(s.get("p") or 0) for s in sc) - 1) > 0.011:
        bad.append(f"시나리오 확률 합 {sum(float(s.get('p') or 0) for s in sc):.2f} — 1이어야 한다")
    for s in sc:
        if not s.get("assume") or not s.get("kpi"):
            bad.append(f"시나리오 {s.get('case')}: 가정·결과 지표 없음")
    if len(L.get("cycle") or []) < c["cycle_min"][kind]:
        bad.append(f"사이클 지표 {len(L.get('cycle') or [])}개 — {c['cycle_min'][kind]}개 이상")
    for x in L.get("cycle") or []:
        if x.get("kind") not in ("선행", "동행", "후행") or not x.get("read"):
            bad.append(f"사이클 지표 {x.get('name')}: 선행·동행·후행 구분과 해석 필요")
    if kind != "event" and not L.get("profit_pool"):
        bad.append("이익 풀 이동(누가 마진을 가져가나) 없음")
    ch = L.get("chain") or []
    if len(ch) < c["chain_min"]:
        bad.append(f"인과 사슬 {len(ch)}고리 — {c['chain_min']}고리 이상")
    for x in ch:
        if x.get("type") not in c["link_types"]:
            bad.append(f"인과 고리 '{str(x.get('step'))[:20]}': 증거 유형 없음")
    if ch and not any(x.get("type") == "확정사실" for x in ch):
        bad.append("인과 사슬에 확정사실 고리가 하나도 없다")
    status = ((dp.get("narrative") or {}).get("status") or "")
    if any(x.get("type") == "미확인" for x in ch) and status.startswith("판단 가능"):
        bad.append("미확인 고리가 있는데 종료 상태가 '판단 가능'")
    text = json.dumps({k: v for k, v in dp.items() if k not in ("sources",)}, ensure_ascii=False)
    bad += [f"금지 표현 '{w}'" for w in c["banned"] if w in text]
    if any(w in text for w in c["needs_expectations"]) and not L.get("expectations"):
        bad.append("'간과·과소평가' 류 표현은 가격 내포 기대 근거가 있어야 쓴다")
    return bad


def pct(x, d=0):
    return "미확인" if x is None else f"{x * 100:+.{d}f}%"


def bridge(dr, actual=None):
    """물량 × 가격 → 매출 효과((1+v)(1+p)−1). actual(풀 → 실제 세그먼트 성장)이 있으면 잔차"""
    out = []
    for x in dr:
        v, p = (x.get("volume") or {}).get("chg"), (x.get("price") or {}).get("chg")
        implied = (1 + v) * (1 + p) - 1 if v is not None and p is not None else None
        act = (actual or {}).get(x.get("ref") or x.get("pool"))   # ref = "풀:회사 id"(회사 사업부와 비교) 또는 풀 전체
        out.append({**x, "implied": implied, "actual": act, "resid": (act - implied) if act is not None and implied is not None else None})
    return out


def weakest(chain):
    return min(chain, key=lambda x: STRENGTH.get(x.get("type"), 0)) if chain else None


def sections(dp, kind, actual=None, c=None):
    """{이름: blocks} — 프레임이 자기 순서로 끼운다. actual = {풀: 실제 세그먼트 성장(전분기)}"""
    c = c or cfg()
    L = dp.get("logic") or {}
    if not L:
        return {}
    out = {}
    bl = L.get("bottom_line") or {}
    ch = L.get("chain") or []
    wk = weakest(ch)
    out["bottom"] = [{"type": "hl", "text": bl.get("call", "")}] + ([{"type": "p", "text": f"지난 판단 대비 {bl.get('vs_prior')}. {bl.get('changed', '')}"}] if bl.get("changed") else []) \
        + ([{"type": "table", "title": "인과 사슬 — 고리마다 증거 유형(가장 약한 고리가 결론의 강도를 정한다)", "headers": ["#", "고리", "증거 유형", "근거"],
             "rows": [[str(i), x.get("step", ""), x.get("type", ""), x.get("ref", "")] for i, x in enumerate(ch, 1)]},
            {"type": "p", "text": f"가장 약한 고리: {wk['step']}({wk['type']}). 이 고리가 확인되면 결론의 확신도가 오른다."}] if ch else [])
    ds = L.get("debates") or []
    if ds:
        out["debates"] = [{"type": "table", "title": "핵심 논쟁 — 시장 견해 vs Chiip, 무엇이 판가름하나", "headers": ["논쟁", "시장 견해(출처)", "Chiip 견해", "왜 다른가", "판가름 신호(날짜·지표·문턱)", "Chiip 확률"],
                           "rows": [[d["q"], f"{d['consensus']['view']}" + (f" [{d['consensus']['number']}]" if d["consensus"].get("number") else "") + f" ({d['consensus']['source']})",
                                     d["chiip"]["view"] + (f" [{d['chiip']['number']}]" if d["chiip"].get("number") else ""), d["why_differ"],
                                     f"{d['signpost']['date']} · {d['signpost']['metric']} · {d['signpost']['threshold']}", f"{float(d['p']):.0%}"] for d in ds]}]
    dr = bridge(L.get("drivers") or [], actual)
    if dr:
        rows = [[x.get("name", x.get("pool", "")), f"{(x.get('volume') or {}).get('name', '')} {pct((x.get('volume') or {}).get('chg'))}",
                 f"{(x.get('price') or {}).get('name', '')} {pct((x.get('price') or {}).get('chg'))}", x.get("mix", ""), pct(x["implied"]),
                 pct(x["actual"]) if x["actual"] is not None else "—", (pct(x["resid"]) + (" ⚠ 설명 안 된 잔차" if abs(x["resid"]) > c["bridge_tolerance"] else "")) if x["resid"] is not None else "—",
                 "; ".join(s for s in ((x.get("volume") or {}).get("source"), (x.get("price") or {}).get("source")) if s)] for x in dr]
        out["drivers"] = [{"type": "table", "title": "동인 분해 — 매출 = 물량 × 가격 × 믹스(전분기 대비). 잔차가 크면 믹스·환율·분류 차이를 찾아야 한다",
                           "headers": ["사업", "물량", "가격", "믹스", "브리지 매출 효과", "실제 세그먼트", "잔차", "출처"], "rows": rows}]
    ex = L.get("expectations") or []
    if ex:
        out["expectations"] = [{"type": "table", "title": "가격 내포 기대 — 시장이 이미 가정한 숫자(이것을 넘어야 '차이'다)", "headers": ["무엇", "값", "함의", "출처"],
                                "rows": [[e["what"], str(e.get("value", "")), e.get("implied", ""), e["source"]] for e in ex]}]
    sc = L.get("scenarios") or []
    if sc:
        order = {k: i for i, k in enumerate(c["cases"])}
        sc = sorted(sc, key=lambda s: order.get(s["case"], 9))
        vals = [s for s in sc if _num(s.get("value"))]
        ev = sum(float(s["p"]) * s["value"] for s in vals) if len(vals) == len(sc) else None
        out["scenarios"] = [{"type": "table", "title": "시나리오 — 확률 합 1, 가정과 결과 지표", "headers": ["시나리오", "확률", "가정", "결과 지표", "값"],
                             "rows": [[s["case"], f"{float(s['p']):.0%}", s["assume"], s["kpi"], str(s.get("value", ""))] for s in sc]}] \
            + ([{"type": "p", "text": f"확률 가중값 {ev:,.1f}({sc[0]['kpi']}). 기본 시나리오 값과의 차이가 비대칭(위아래 어느 쪽 꼬리가 두꺼운가)을 보여 준다."}] if ev is not None else []) \
            + ([{"type": "p", "text": f"외부 관점(기저율): {L['base_rate']['text']} ({L['base_rate'].get('source', '')})"}] if L.get("base_rate") else [])
    cy = L.get("cycle") or []
    if cy:
        out["cycle"] = [{"type": "table", "title": "사이클 지표판 — 선행 지표가 먼저 꺾인다", "headers": ["지표", "구분", "지금", "직전", "읽기"],
                         "rows": [[x["name"], x["kind"], str(x.get("now", "")), str(x.get("prior", "")), x["read"]] for x in sorted(cy, key=lambda x: ("선행", "동행", "후행").index(x["kind"]))]}]
    pp = L.get("profit_pool") or []
    if pp:
        out["profit_pool"] = [{"type": "table", "title": "이익 풀 이동 — 가치사슬 층별로 마진을 누가 가져가나", "headers": ["층", "전", "후", "왜"],
                               "rows": [[x["layer"], str(x.get("before", "")), str(x.get("after", "")), x.get("why", "")] for x in pp]}]
    return out
