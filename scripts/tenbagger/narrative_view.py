"""텐배거 리포트 '내러티브 — 멀티플 프리미엄과 리비전을 끌어올리는 이야기' 절 (마스터 지시 2026-10-29 "이 종목의 멀티플 프리미엄을 부여하고
펀더멘털 리비전을 위로 이끄는 내러티브 요인이 무엇인지 정확히 파악하라. IB와 월스트리트 등 바이사이드와 셀사이드부터 레딧과 X 등 리테일에
이르기까지 다각도로")

틀: Damodaran '이야기 → 숫자'(Narrative and Numbers, 2017) — 내러티브마다 바꾸는 가치 입력(성장·이익률·재투자·위험)을 적고, 그것이
  ① 멀티플(같은 이익에 더 높은 배수 = 회사 고유 프리미엄)로 작동하는지 ② 리비전(추정 이익 자체를 올림)으로 작동하는지 가른다.
  층별로 누가 그 이야기를 믿는지 본다 — 셀사이드(등급·목표가 분산·리비전·콜 질문 초점), 바이사이드(기관 보유·콜 질문자 소속·행동주의),
  리테일(레딧 ApeWisdom·텔레그램 공개 채널 언급 수·X 언급 수·위키 조회), 언론. 커뮤니티·IB 의견은 사실이 아니라 '시장 기대의 증거'다.
  스킬 .claude/skills/narrative-premium(knowledge/narratives/companies/<id>.md)과 같은 단계 이름(태동·확산·컨센서스·과밀·소멸·붕괴)을 쓴다.

datapack "narrative":
  {"as_of", "stage", "crowding", "summary",
   "layers": {"sell_side"|"buy_side"|"retail"|"media": {"metrics": [[지표, 값, 추세/해석, 출처]...], "read": "한 줄 해석"}},
   "factors": [{"name","thesis","inputs":"바뀌는 가치 입력","who":{"sell":"강|중|약|-","buy":…,"retail":…},
                "drives":"multiple|revision|both","quant":"숫자로 바꾼 것","status":"강화|유지|약화","falsifier","source"}],
   "attention": [{"label","value","unit"}],   # 선택 — 층별 관심 크기 막대
   "lead": {"summary": "한 장 요약 첫 문단", "value_story": "기업가치 결정 논리", "premium": {"multiple","eps"}, "why_excited": "왜 열광했나",
            "lenses": [{"lens": LENSES 중 하나, "change", "evidence", "drives", "status", "falsifier"}…],   # 모두. 실행 속도는 "lead_time"(회사 납품 리드타임)·"peer_lead_time"(경쟁 대안) 추가
            "products": [{"kind": "제품|서비스|기술", "name", "what", "use", "money"}…],   # 맨 앞 절(lead_section) — 마스터 지시 2026-10-30
            "policy": {"fiscal": {"change", "evidence", "drives", "status", "falsifier", "house": {"level": 0~5, "why"}, "senate": {"level": 0~5, "why"}},   # 재정정책(행정부)
                       "orders": {같은 구조},                                                                                                      # 행정명령(행정부)
                       "laws": {"change", "evidence", "drives", "status", "falsifier"}}}}                                                          # 연관입법(의회) — 마스터 지시 2026-10-31
            해당이 없으면 change에 '해당 없음(이유)'을 쓰고 house·senate를 뺀다. policy가 있으면 lenses의 '재정정책'은 쓰지 않는다.
의회 동의 10점(마스터 지시 2026-10-31) = 하원 0~5 + 상원 0~5. 단계로 잰다 — CONGRESS_LEVELS 참조.
계산 연결: 멀티플 엔진(scripts/valuation/v2/multiples.py)의 회사 고유 프리미엄(decomp.firm)과 consensus.revisions의 EPS 리비전 합을 함께 싣는다.
"""
import math

DRIVES = {"multiple": "멀티플", "revision": "리비전", "both": "멀티플+리비전"}
LAYERS = (("sell_side", "셀사이드(IB 애널리스트)"), ("buy_side", "바이사이드(기관 투자자)"), ("retail", "리테일(레딧·텔레그램·X)"), ("media", "언론·업계"))
LENSES = ("구조적 체질 변화", "고부가 믹스 확장", "기술 혁신", "실행 속도", "M&A", "재정정책", "CAPEX 낙수효과")   # 마스터 지시 2026-10-30 — 맨 앞 내러티브 절의 필수 렌즈. 실행 속도 = 납품 리드타임(2026-10-31)


POLICY = (("fiscal", "재정정책(행정부)"), ("orders", "행정명령(행정부)"), ("laws", "연관입법(의회)"))
CONGRESS_LEVELS = {5: "본회의 통과·세출 반영", 4: "소관 위원회 통과", 3: "초당적 법안 발의·공개 지지", 2: "한쪽 당 지지만", 1: "논의 없음", 0: "반대 결의·삭감 통과"}


def congress_score(item):
    """상·하원 동의 10점 — (합계, '하원 4(이유)·상원 3(이유)'). 해당 없음이면 (None, '')"""
    h, s = item.get("house"), item.get("senate")
    if not h or not s:
        return None, ""
    for x in (h, s):
        if x.get("level") not in CONGRESS_LEVELS:
            raise ValueError(f"의회 동의 단계는 0~5: {x}")
    side = lambda name, x: f"{name} {x['level']}/5({x.get('why') or CONGRESS_LEVELS[x['level']]})"
    return h["level"] + s["level"], f"{side('하원', h)} · {side('상원', s)}"


def policy_items(policy):
    """재정정책(행정부)·행정명령(행정부)·연관입법(의회) 세 줄. 재정정책과 행정명령에는 의회 동의 10점을 붙인다"""
    out = []
    for key, name in POLICY:
        x = policy.get(key) or {}
        na = str(x.get("change", "")).startswith("해당 없음")
        if not x.get("change"):
            raise ValueError(f"datapack narrative.lead.policy.{key} 없음")
        total, detail = congress_score(x)
        if key != "laws" and total is None and not na:
            raise ValueError(f"datapack narrative.lead.policy.{key}에 house·senate 단계가 없다")
        tag = " · ".join(t for t in (DRIVES.get(x.get("drives"), x.get("drives")), x.get("status")) if t)
        line = f"**{name}**" + (f" ({tag})" if tag else "") + f" — {x['change']}"
        if total is not None:
            line += f" **의회 동의 {total}/10** — {detail}."
        line += (f" 증거: {x['evidence']}" if x.get("evidence") else "") + (f" 반증: {x['falsifier']}" if x.get("falsifier") else "")
        out.append(line)
    return out


def revision_pct(cons):
    """consensus.revisions 중 EPS 행의 합계 리비전(같은 분기끼리) — 없으면 None"""
    rows = [r for r in ((cons or {}).get("revisions") or {}).get("rows") or [] if r.get("metric") == "EPS" and r.get("from") and r.get("to") is not None]
    if not rows:
        return None, None
    f, t = sum(r["from"] for r in rows), sum(r["to"] for r in rows)
    return (t / f - 1) if f else None, ", ".join(r["period"] for r in rows)


def report_section(dp, mm=None):
    n = (dp or {}).get("narrative") or {}
    if not n.get("factors"):
        return None
    blocks = []
    firm = ((mm or {}).get("decomp") or {}).get("firm")
    total = ((mm or {}).get("decomp") or {}).get("total")
    rev, periods = revision_pct(dp.get("consensus"))
    head = f"**한 줄:** {n.get('summary', '')}"
    link = []
    if total is not None and firm is not None:
        link.append(f"동종 대비 멀티플 차이 {math.exp(total) * 100 - 100:+.0f}% 중 회사 고유 몫 {math.exp(firm) * 100 - 100:+.0f}%(멀티플 엔진) — 내러티브가 설명해야 하는 크기")
    if rev is not None:
        link.append(f"직전 콜 이후 EPS 추정 {rev * 100:+.1f}%({periods}) — 리비전 경로로 이미 숫자가 된 몫")
    if link:
        head += " · " + " · ".join(link)
    if n.get("stage"):
        head += f" · 단계 {n['stage']}" + (f", 쏠림 {n['crowding']}" if n.get("crowding") else "")
    blocks.append({"type": "hl", "text": head})
    rows = []
    for f in n["factors"]:
        w = f.get("who") or {}
        rows.append([f.get("name", ""), w.get("sell", "-"), w.get("buy", "-"), w.get("retail", "-"), DRIVES.get(f.get("drives"), f.get("drives", "")),
                     f.get("quant", ""), f.get("status", ""), f.get("falsifier", "")])
    blocks.append({"type": "table", "title": "내러티브 요인 — 누가 믿고, 멀티플·리비전 중 어디로 작동하나",
                   "headers": ["요인", "셀사이드", "바이사이드", "리테일", "작동 경로", "숫자로 바꾸면", "상태", "반증 조건"], "rows": rows})
    blocks.append({"type": "ul", "items": [f"**{f.get('name')}** — {f.get('thesis', '')}" + (f" (바뀌는 입력: {f['inputs']})" if f.get("inputs") else "")
                                           for f in n["factors"]]})
    for key, label in LAYERS:
        lay = (n.get("layers") or {}).get(key)
        if not lay:
            continue
        if lay.get("metrics"):
            blocks.append({"type": "table", "title": f"{label}", "headers": ["지표", "값", "추세·해석"], "rows": [m[:3] for m in lay["metrics"]]})   # 데이터 출처 열은 싣지 않는다(2026-10-30)
        if lay.get("read"):
            blocks.append({"type": "p", "text": f"**{label} 해석:** {lay['read']}"})
    att = [a for a in n.get("attention") or [] if a.get("value") is not None]
    if att:
        blocks.append({"type": "chart", "chart": {"kind": "hbars", "title": "층별 관심 크기", "unit": "",
                                                   "rows": [{"label": a["label"], "bars": [{"name": a.get("unit", "값"), "color": "c", "value": a["value"]}]} for a in att]}})
    blocks.append({"type": "p", "text": "**읽는 법:** '멀티플' 요인은 같은 이익에 더 높은 배수를 주게 하는 이야기(지속성·위험 감소·희소성), '리비전' 요인은 추정 이익 자체를 올리는 이야기(수주·가격·이익률). "
                                        "회사 고유 프리미엄이 큰데 리비전 근거가 약하면 이야기가 숫자보다 앞서 있다(과밀 위험). 커뮤니티·IB 의견은 사실이 아니라 시장 기대의 증거다."})
    return {"h2": "내러티브 근거 — 누가 믿고 있나(셀사이드·바이사이드·리테일·언론)", "blocks": blocks}


def lead_section(dp, mm=None, strict=True):
    """맨 앞 절 — 기업가치를 결정하고 멀티플·EPS 프리미엄을 부여하는 이야기, 왜 열광하나, 이 회사의 제품·서비스·기술(마스터 지시 2026-10-30).
    여섯 렌즈는 해당이 없어도 '해당 없음(이유)'를 쓴다 — 빠지면 ValueError"""
    lead = ((dp or {}).get("narrative") or {}).get("lead")
    if not lead:
        return None
    have = {x.get("lens"): x for x in lead.get("lenses") or []}
    policy = lead.get("policy")
    if strict and not policy:
        raise ValueError("datapack narrative.lead.policy가 없다 — 재정정책·행정명령·연관입법(옛 리포트 정정은 --legacy)")
    miss = [k for k in LENSES if not (have.get(k) or {}).get("change") and not (k == "재정정책" and policy) and (strict or k != "실행 속도")]
    speed = have.get("실행 속도") or {}
    if strict and not (speed.get("lead_time") or str(speed.get("change", "")).startswith("해당 없음")):
        raise ValueError("datapack narrative.lead.lenses 실행 속도에 lead_time이 없다 — 납품 리드타임, 없으면 change에 '해당 없음(이유)'")
    if miss or not lead.get("products") or not lead.get("summary"):
        raise ValueError(f"datapack narrative.lead 미비 — 렌즈 {miss or '완비'}, products·summary 필요")
    B = [{"type": "hl", "text": f"**기업가치를 결정하는 이야기:** {lead.get('value_story') or lead['summary']}"}]
    prem = lead.get("premium") or {}
    if prem:
        B.append({"type": "ul", "items": [f"**멀티플 프리미엄:** {prem['multiple']}" if prem.get("multiple") else None, f"**EPS 프리미엄:** {prem['eps']}" if prem.get("eps") else None]})
        B[-1]["items"] = [x for x in B[-1]["items"] if x]
    if lead.get("why_excited"):
        B += [{"type": "h3", "text": "투자자들은 왜 열광했나"}, {"type": "p", "text": lead["why_excited"]}]
    B.append({"type": "h3", "text": "무엇이 기업가치를 바꾸나"})   # 앞의 '여섯 렌즈'는 뺀다(마스터 지시 2026-10-31)
    items = []
    for k in LENSES:
        if k == "재정정책" and policy:
            items += policy_items(policy)
            continue
        if k not in have:   # 옛 리포트 정정(--legacy)
            continue
        x = have[k]
        tag = " · ".join(t for t in (DRIVES.get(x.get("drives"), x.get("drives")), x.get("status")) if t)
        speed_txt = "".join(f" {name} {x[key]}." for key, name in (("lead_time", "**납품 리드타임**"), ("peer_lead_time", "경쟁 대안")) if x.get(key))
        items.append(f"**{k}**" + (f" ({tag})" if tag else "") + f" — {x['change']}" + speed_txt + (f" 증거: {x['evidence']}" if x.get("evidence") else "") + (f" 반증: {x['falsifier']}" if x.get("falsifier") else ""))
    B.append({"type": "ul", "items": items})
    B.append({"type": "h3", "text": "이 회사의 제품·서비스·기술"})
    B.append({"type": "ul", "items": [f"**{p.get('kind', '')} — {p.get('name', '')}:** {p.get('what', '')}" + (f" 쓰는 곳: {p['use']}." if p.get("use") else "") + (f" 돈 버는 방식: {p['money']}." if p.get("money") else "")
                                      for p in lead["products"]]})
    return {"h2": "내러티브 — 기업가치와 멀티플·EPS 프리미엄을 결정하는 이야기", "blocks": B}


def summary_item(dp):
    lead = ((dp or {}).get("narrative") or {}).get("lead") or {}
    return {"q": "기업가치를 결정하는 내러티브", "a": lead.get("summary", ""), "auto": True}
