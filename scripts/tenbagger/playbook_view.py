"""투자 포인트 · 모멘텀 타임라인 · 언제 사서 언제 팔아야 할까 (마스터 지시 2026-11-16)

"Chiip Analysis 리포트에도 투자 포인트, 모멘텀 생성/소멸 타임라인, 언제 사서 언제 팔아야 할까?를 넣어라 … 세 항목의 사고 논리는
(마스터가 준 CRDO 분석보고서) 방식과 IB 리서치 하우스와 동일한 접근 방식 등 전문 기법을 종합해 넣도록 하라."

배치: 한 장 요약 — '기업가치를 결정하는 내러티브' 아래 투자 포인트, '밸류에이션 모델로 본 주가 상방' 아래 모멘텀 타임라인,
'무엇이 바뀌면 판단이 달라지나' 아래 언제 사서 언제 팔아야 할까. 본문 내러티브 절 끝에 세 항목의 세부.

사고 논리(모델이 datapack "playbook"에 쓰는 기준):
① 투자 포인트 = IB 'investment thesis' 3개. 각 포인트는 [한 줄 명제] → 숫자 근거(가이던스·실적·잔고) → 시장과 다른 점(variant perception —
   컨센서스·가격 내포 기대와 무엇이 다른가, `consensus-gap` 스킬 기준) → 무엇이 증명하나(다음 확인 숫자)·출처. 실적 숫자와 '본인 시각'을 섞지 않는다.
② 모멘텀 타임라인 = 카탈리스트 달력. 지난 사건(완료)은 날짜·사건·주가 반응·모멘텀 생성/소멸, 앞으로 사건(예정)은 날짜(미확정이면 '예상')·
   무엇을 확인하나(숫자 문턱)·결과에 따라 어느 시나리오로 가나. 회사 사건과 매크로·섹터 사건을 구분한다.
③ 언제 사서 언제 팔아야 할까 = 가격·조건 틀(밸류에이션 앵커 + 기술적 지지 + 이벤트 게이트). 가격은 엔진이 정한다:
   관찰 구간 = 지금 가격 아래 차트 지지 구간 중 기본 시나리오 대비 할인이 큰 곳 · 확인 = 모델이 쓴 숫자 조건(이벤트) ·
   무효화 = 모델이 쓴 조건 + 약세 시나리오 가격 · 차익 고민 1차 = 목표주가(기본~강세) · 2차 = 강세 시나리오.
   구간마다 목표주가까지 업사이드와 약세까지 다운사이드(손익비)를 붙인다. 비중·금액·매매 지시는 쓰지 않는다(CLAUDE.md 출력 모드) —
   '가격·조건 틀이며 매매 지시가 아니다'를 붙인다.

datapack "playbook":
  {"points": [{"title": "구리의 수명 연장 = 랙 안 표준", "claim": "한 줄 명제", "evidence": "숫자 근거", "variant": "시장과 다른 점", "proof": "무엇이 증명하나", "source": "출처"}] × 3,
   "momentum": [{"date": "2026-04-13" | "2026-12 초(예상)", "status": "완료|예정", "kind": "생성|소멸|확인|매크로", "event": "사건",
                 "reaction": "+12%"(완료만), "check": "확인할 숫자·문턱"(예정만), "then": "결과별 시나리오"(예정만)}] (완료 2개 이상 + 예정 2개 이상),
   "trade": {"watch": "관찰 구간을 보는 이유", "confirm": "확인 조건(숫자·이벤트)", "invalid": "무효화 조건", "trim": "차익 고민 근거",
             "style": "이벤트 전후 변동성·추격 경계 한 줄"}}
"""

UNKNOWN = "미확인"


def check(dp):
    """빠진 재료 목록 — 있으면 merge가 멈춘다"""
    p = (dp or {}).get("playbook") or {}
    err = []
    pts = p.get("points") or []
    if len(pts) < 3 or any(not (x.get("title") and x.get("claim") and x.get("evidence") and x.get("variant")) for x in pts[:3]):
        err.append("playbook.points 3개(title·claim·evidence·variant)")
    mo = p.get("momentum") or []
    if sum(1 for x in mo if x.get("status") == "완료") < 2 or sum(1 for x in mo if x.get("status") == "예정") < 2:
        err.append("playbook.momentum 완료 2개 이상 + 예정 2개 이상")
    if any(x.get("status") == "예정" and not x.get("check") for x in mo):
        err.append("playbook.momentum 예정 사건마다 check(확인할 숫자)")
    tr = p.get("trade") or {}
    if not (tr.get("confirm") and tr.get("invalid")):
        err.append("playbook.trade confirm·invalid")
    return err


def _pc(x):
    return UNKNOWN if x is None else f"{x * 100:+.0f}%"


def zones(v, supports, fmt):
    """가격 구간 — v = {price, bear, base, bull, target}. supports = levels zones(mid·lo·hi). 엔진 값만 쓴다"""
    p, bear, base, bull, tgt = (v.get(k) for k in ("price", "bear", "base", "bull", "target"))
    below = sorted((z for z in supports or [] if z.get("mid") and z["mid"] < p), key=lambda z: -z["mid"])
    watch = below[0] if below else None
    rr = lambda at: (None if not at else ((tgt / at - 1) if tgt else None, (bear / at - 1) if bear is not None else None))
    out = []
    if watch:
        u, d = rr(watch["mid"])
        out.append({"k": "관찰 구간", "price": f"{fmt(watch['lo'])}~{fmt(watch['hi'])}", "up": u, "down": d, "at": watch["mid"]})
    out.append({"k": "확인 뒤", "price": f"지금 {fmt(p)} 이상에서 조건 확인", "up": (tgt / p - 1) if tgt else None, "down": (bear / p - 1) if bear is not None else None, "at": p})
    out.append({"k": "무효화", "price": f"약세 시나리오 {fmt(bear)}" if bear is not None else UNKNOWN, "up": None, "down": (bear / p - 1) if bear is not None else None, "at": bear})
    hi1 = max(x for x in (base, tgt) if x is not None) if (base or tgt) else None
    if hi1 and hi1 > p:
        out.append({"k": "차익 고민 1차", "price": f"{fmt(hi1)}(목표주가·기본 시나리오)", "up": hi1 / p - 1, "down": None, "at": hi1})
    if bull and bull > p and (not hi1 or bull > hi1 * 1.03):
        out.append({"k": "차익 고민 2차", "price": f"{fmt(bull)}(강세 시나리오)", "up": bull / p - 1, "down": None, "at": bull})
    return out


def summary_points(dp):
    pts = ((dp or {}).get("playbook") or {}).get("points") or []
    return {"q": "투자 포인트", "a": "\n".join(f"**[{x['title']}]** {x['claim']} {x['evidence']}".strip() for x in pts[:3]), "auto": True}


def summary_momentum(dp):
    mo = ((dp or {}).get("playbook") or {}).get("momentum") or []
    done = [x for x in mo if x.get("status") == "완료"][-2:]
    nxt = [x for x in mo if x.get("status") == "예정"][:3]
    lines = [f"{x['date']} {x['event']}" + (f" → {x['reaction']}" if x.get("reaction") else "") for x in done]
    lines += [f"**{x['date']}** {x['event']} — 확인: {x['check']}" for x in nxt]
    return {"q": "모멘텀은 어떻게 만들어지고 사라지나?", "a": "\n".join(lines), "auto": True}


def summary_trade(dp, v, supports, fmt):
    tr = ((dp or {}).get("playbook") or {}).get("trade") or {}
    zs = {z["k"]: z for z in zones(v, supports, fmt)}
    out = []
    if "관찰 구간" in zs:
        z = zs["관찰 구간"]
        out.append(f"**관찰 {z['price']}**: 목표주가까지 {_pc(z['up'])}, 약세까지 {_pc(z['down'])}" + (f" — {tr['watch']}" if tr.get("watch") else ""))
    out.append(f"**확인**: {tr.get('confirm', UNKNOWN)}")
    out.append(f"**무효화**: {tr.get('invalid', UNKNOWN)}" + (f"(약세 {zs['무효화']['price'].split(' ')[-1]})" if zs.get("무효화", {}).get("at") is not None else ""))
    for k in ("차익 고민 1차", "차익 고민 2차"):
        if k in zs:
            out.append(f"**{k} {zs[k]['price']}**: 지금보다 {_pc(zs[k]['up'])}")
    if tr.get("style"):
        out.append(tr["style"])
    out.append("가격·조건 틀이며 매매·비중 지시가 아니다.")
    return {"q": "언제 사서 언제 팔아야 할까?", "a": "\n".join(out), "auto": True}


def blocks(dp, v, supports, fmt):
    """내러티브 절 끝 — 세 항목 세부"""
    p = (dp or {}).get("playbook") or {}
    B = [{"type": "h3", "text": "투자 포인트"},
         {"type": "boxes", "items": [{"title": x["title"], "lines": [["명제", x.get("claim")], ["숫자", x.get("evidence")], ["시장과 다른 점", x.get("variant")],
                                                                     ["증명", x.get("proof")], ["출처", x.get("source")]]} for x in (p.get("points") or [])[:3]]}]
    mo = p.get("momentum") or []
    if mo:
        B += [{"type": "h3", "text": "모멘텀 생성·소멸 타임라인"},
              {"type": "table", "title": "카탈리스트 달력 — 지난 사건의 주가 반응과 앞으로 확인할 숫자", "headers": ["날짜", "상태", "구분", "사건", "반응·확인", "결과에 따라"],
               "rows": [[x.get("date"), x.get("status"), x.get("kind", ""), x.get("event"), x.get("reaction") if x.get("status") == "완료" else x.get("check"), x.get("then", "")] for x in mo]}]
    zs = zones(v, supports, fmt)
    tr = p.get("trade") or {}
    why = {"관찰 구간": tr.get("watch"), "확인 뒤": tr.get("confirm"), "무효화": tr.get("invalid"), "차익 고민 1차": tr.get("trim"), "차익 고민 2차": tr.get("trim")}
    B += [{"type": "h3", "text": "언제 사서 언제 팔아야 할까?"},
          {"type": "table", "title": "가격·조건 틀 — 가격은 밸류에이션(약세·기본·강세·목표주가)과 차트 지지 구간에서, 조건은 이벤트에서",
           "headers": ["구간", "가격", "목표주가까지", "약세까지", "조건·근거"],
           "rows": [[z["k"], z["price"], _pc(z["up"]) if z["up"] is not None else "-", _pc(z["down"]) if z["down"] is not None else "-", why.get(z["k"]) or ""] for z in zs]},
          {"type": "p", "text": (tr.get("style") + " " if tr.get("style") else "") + "가격·조건 틀이며 매매·비중 지시가 아니다(투자 권유 아님)."}]
    return B
