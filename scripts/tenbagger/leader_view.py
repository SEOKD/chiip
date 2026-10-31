"""텐배거 리포트 '경영진·네트워크' 절 (마스터 지시 2026-11-01 "창업자와 회장, CEO의 프로필이 어떻게 되며 이들이 어떤 비즈니스 네트워크, 정계 네트워크,
학교 동문 네트워크, 사모임 네트워크로 엮어 있는지 파악하고 이게 비즈니스에 어떤 도움이 되는지 정량화하라")

경계: 임원·공개 직책자의 공개 기록만 쓴다(위임장·회사 소개·공직 이력·공시된 이사회·로비 공시·선거자금 공개 기록·언론 보도). 가족·주소·건강·비공개 모임은 쓰지 않는다.
정치 성향은 추측하지 않는다 — 공개 기록에 있는 행동(직책, 기부, 증언)만 적고, 없으면 '미확인'이다. 사모임은 공개된 회원 명단·공식 소개에 나온 것만 쓴다.

datapack "leaders":
  {"as_of": "2026-11-01", "summary": "한 줄",
   "people": [{"name": "이름", "role": "CEO", "since": "2013", "profile": "경력 요약",
               "business": "이사회·업계 연결", "political": "공개 기록의 정부·의회 연결", "alumni": "학교·군 동기 연결", "social": "공개된 모임, 없으면 미확인", "source": "2026 위임장"}…],   # 창업자·회장·CEO
   "value": [{"network": "비즈니스|정계|동문|사모임", "link": "무슨 연결인가", "strength": 0~5, "exposure": 1.2, "basis": "노출 금액을 어떻게 잡았나", "evidence": "1차 자료"}…]}
strength: 5 현직 직책·계약으로 문서 확인 · 4 직전 직책이나 공시로 확인 · 3 복수 공개 자료의 정황 · 2 단일 공개 자료 · 1 약한 정황 · 0 미확인.
엔진 계산: 가중 노출 = exposure × strength ÷ 5, 매출 대비 %. 이것은 연결이 닿는 매출의 크기이지 연결이 만든 매출이 아니다 — 인과는 입증하지 못하므로 그렇게 쓴다.
"""

NETWORKS = ("비즈니스", "정계", "동문", "사모임")
LINES = (("프로필", "profile"), ("비즈니스", "business"), ("정계", "political"), ("동문", "alumni"), ("사모임", "social"))


def compute(lv, rev):
    out = []
    for x in lv.get("value") or []:
        s, e = x.get("strength"), x.get("exposure")
        if s not in (0, 1, 2, 3, 4, 5):
            raise ValueError(f"leaders.value strength는 0~5: {x}")
        w = e * s / 5 if isinstance(e, (int, float)) else None
        out.append({**x, "weighted": w, "share": w / rev if w is not None and rev else None})
    return out


def check(lv):
    people = lv.get("people") or []
    if not people:
        raise ValueError("datapack leaders.people가 없다 — 창업자·회장·CEO")
    for p in people:
        miss = [k for _, k in LINES if not p.get(k)] + ([] if p.get("source") else ["source"])
        if miss:
            raise ValueError(f"leaders {p.get('name')}: {miss} 없음 — 공개 자료에 없으면 '미확인'")
    have = {x.get("network") for x in lv.get("value") or []}
    if not have & set(NETWORKS[:2]):
        raise ValueError("leaders.value에 비즈니스 또는 정계 연결의 정량화가 필요하다")


def report_section(dp, r, money):
    lv = (dp or {}).get("leaders")
    if not lv:
        raise SystemExit("datapack에 leaders가 없다(scripts/tenbagger/leader_view.py 맨 위) — 옛 리포트 정정은 --legacy")
    check(lv)
    rev = ((dp.get("financials") or {}).get("rev_ttm"))
    rows = compute(lv, rev)
    B = [{"type": "hl", "text": lv.get("summary", "")}] if lv.get("summary") else []
    B.append({"type": "boxes", "items": [{"title": p["name"], "tag": f"{p.get('role', '')} · {p.get('since', '')}".strip(" ·"), "lines": [[a, p.get(k)] for a, k in LINES]} for p in lv["people"]]})
    if rows:
        B.append({"type": "table", "title": "네트워크 정량화", "headers": ["연결", "강도", "닿는 매출", "가중 노출", "매출 대비", "근거"],
                  "rows": [[f"{x.get('network')}: {x.get('link')}", f"{x['strength']}/5", money(x["exposure"]) if isinstance(x.get("exposure"), (int, float)) else "미확인",
                            money(x["weighted"]) if x["weighted"] is not None else "미확인", f"{x['share'] * 100:.0f}%" if x["share"] is not None else "미확인", f"{x.get('basis', '')} {x.get('evidence', '')}".strip()] for x in rows]})
        B.append({"type": "p", "text": "가중 노출은 연결이 닿는 매출의 크기다. 연결이 그 매출을 만들었다는 뜻이 아니며, 인과는 공개 자료로 입증하지 못한다."})
    return {"h2": "경영진·네트워크", "blocks": B}
