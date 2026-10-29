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
   "attention": [{"label","value","unit"}]}   # 선택 — 층별 관심 크기 막대
계산 연결: 멀티플 엔진(scripts/valuation/v2/multiples.py)의 회사 고유 프리미엄(decomp.firm)과 consensus.revisions의 EPS 리비전 합을 함께 싣는다.
"""
import math

DRIVES = {"multiple": "멀티플", "revision": "리비전", "both": "멀티플+리비전"}
LAYERS = (("sell_side", "셀사이드(IB 애널리스트)"), ("buy_side", "바이사이드(기관 투자자)"), ("retail", "리테일(레딧·텔레그램·X)"), ("media", "언론·업계"))


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
                                           + (f" [{f['source']}]" if f.get("source") else "") for f in n["factors"]]})
    for key, label in LAYERS:
        lay = (n.get("layers") or {}).get(key)
        if not lay:
            continue
        if lay.get("metrics"):
            blocks.append({"type": "table", "title": f"{label}", "headers": ["지표", "값", "추세·해석", "출처"], "rows": lay["metrics"]})
        if lay.get("read"):
            blocks.append({"type": "p", "text": f"**{label} 해석:** {lay['read']}"})
    att = [a for a in n.get("attention") or [] if a.get("value") is not None]
    if att:
        blocks.append({"type": "chart", "chart": {"kind": "hbars", "title": "층별 관심 크기", "unit": "",
                                                   "rows": [{"label": a["label"], "bars": [{"name": a.get("unit", "값"), "color": "c", "value": a["value"]}]} for a in att]}})
    blocks.append({"type": "p", "text": "**읽는 법:** '멀티플' 요인은 같은 이익에 더 높은 배수를 주게 하는 이야기(지속성·위험 감소·희소성), '리비전' 요인은 추정 이익 자체를 올리는 이야기(수주·가격·이익률). "
                                        "회사 고유 프리미엄이 큰데 리비전 근거가 약하면 이야기가 숫자보다 앞서 있다(과밀 위험). 커뮤니티·IB 의견은 사실이 아니라 시장 기대의 증거다. "
                                        "틀: Damodaran(2017) Narrative and Numbers, Shiller(2019) Narrative Economics."})
    return {"h2": "내러티브 — 멀티플 프리미엄과 리비전을 끌어올리는 이야기", "blocks": blocks}
