"""Analysis 리포트 '커뮤니티 내러티브' 절 (마스터 지시 2026-11-07 "Analysis에서 다루는 종목이 X, 서브스택, 레딧, 유튜브에서 어떤 내러티브로
시장의 기대감을 소화하고 있는지 체계적으로 파악 … 관련 시각물은 한눈에 보기에")

숫자(언급 건수·급증 Z·감성)는 radar/social_surge.py 집계(knowledge/models/social/)에서 읽는다. 내러티브는 모델이 Quantral
get_company_signals·get_company_recaps를 읽고 자기 말로 datapack "social"에 쓴다 — 글 본문 인용·작성자 이름은 쓰지 않는다:
  "social": {"as_of": "2026-11-07", "summary": "기대를 어떻게 소화하고 있나 한 줄",
             "narratives": [{"channel": "X|레딧|유튜브|서브스택", "theme": "주된 이야기 한 줄", "expectation": "상향|하향|혼재|소진",
                             "vs_fact": "1차 자료와 맞나(확인·과장·미확인)", "share": 0.4}],   # share = 그 채널 언급 중 그 이야기 비중(어림)
             "turn": "기대가 바뀐 시점과 계기(있으면)"}
  반응 풀이(마스터 지시 2026-11-13 "통계만 찍지 말고 커뮤니티에서 실제로 어떤 반응이 나오는지 풀이"): "views" 3~5개
             [{"side": "강세|약세|새 쟁점|시장과 다른 점", "claim": "무엇을 말하나(자기 말 요약)", "basis": "무엇을 근거로",
               "source": "레딧 r/○○|Substack|X|Seeking Alpha|Stocktwits", "date": "YYYY-MM-DD",
               "quote": "선택 — 15단어 이하 1개까지(약관 준수 원천만)", "check": "확인|사실관계 미확인|사실과 다름"}]
  반응이 적으면 views를 비우고 "few": true — 리포트에 '언급 적음'으로 쓰고 지어내지 않는다. 통계는 맨 위 한 줄로만.
  Quantral에 없는 종목이면 {"none": "이유"}. 절 자체가 없으면(옛 리포트) 그리지 않는다.
커뮤니티 신호는 S1·S2 — 주장이 아니다. 관심 급증은 주가·펀더멘털 변화가 아니다(금지표).
"""
import csv
import json
import sys
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SOC = ROOT / "knowledge" / "models" / "social"
NAMES = {"x": "X", "reddit": "레딧", "youtube": "유튜브", "substack": "서브스택", "insider": "내부자 매수", "congress": "의회 매매"}
COLORS = {"x": "a", "reddit": "b", "youtube": "c", "substack": "d"}


def _rows(name):
    p = SOC / name
    if not p.exists():
        return []
    with p.open(encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def latest(eid):
    try:
        return (json.loads((SOC / "latest.json").read_text(encoding="utf-8")).get("rows") or {}).get(eid)
    except (OSError, ValueError):
        return None


def daily_chart(eid, days=30, today=None):
    today = today or date.today()
    rows = [r for r in _rows("daily.csv") if r["id"] == eid and r["channel"] in COLORS]
    if not rows:
        return None
    cats = [(today - timedelta(days=days - 1 - i)).isoformat() for i in range(days)]
    have = {(r["date"], r["channel"]): int(float(r["count"])) for r in rows}
    series = [{"name": NAMES[ch], "color": COLORS[ch], "values": [have.get((d, ch), 0) for d in cats]} for ch in COLORS if any((d, ch) in have for d in cats)]
    if not series:
        return None
    return {"kind": "bars", "stack": True, "title": f"커뮤니티 언급 수(최근 {days}일, 채널별)", "unit": "건", "categories": [d[5:] for d in cats], "series": series}


def monthly_chart(eid, months=12):
    rows = sorted((r for r in _rows("recaps.csv") if r["id"] == eid and r.get("posts") not in (None, "", "None")), key=lambda r: r["month"])[-months:]
    if len(rows) < 3:
        return None
    return {"kind": "bars", "trend": True, "title": f"커뮤니티 게시 수(월, 최근 {len(rows)}개월{' — 이번 달은 진행 중' if rows[-1].get('partial') == '1' else ''})", "unit": "건", "categories": [r["month"][2:] for r in rows],
            "series": [{"name": "게시 수", "color": "a", "values": [int(float(r["posts"])) for r in rows]}]}


SIDES = ("강세", "약세", "새 쟁점", "시장과 다른 점")
CHECKS = ("확인", "사실관계 미확인", "사실과 다름")


def check(so):
    """views가 양식을 지키는지 — 출처·날짜 없는 논지, 15단어 넘는 인용, 인용 2개 이상을 막는다"""
    views = so.get("views") or []
    if len(views) > 5:
        raise ValueError("social.views는 3~5개")
    if sum(1 for v in views if v.get("quote")) > 1:
        raise ValueError("social.views 인용은 1개까지")
    for v in views:
        if v.get("side") not in SIDES or not v.get("claim") or not v.get("source") or len(str(v.get("date") or "")) < 10 or v.get("check") not in CHECKS:
            raise ValueError(f"social.views {v.get('claim', '?')[:20]}: side·claim·source·date(YYYY-MM-DD)·check가 필요하다")
        if v.get("quote") and len(str(v["quote"]).split()) > 15:
            raise ValueError("social.views 인용은 15단어 이하")


def stat_line(so, r):
    """통계는 한 줄(마스터 지시 2026-11-13)"""
    parts = []
    if r.get("Z") is not None:
        parts.append(f"관심 급증 {r['score']}/10(결합 Z {r['Z']:+.1f})")
    if r.get("sent7") is not None:
        parts.append(f"최근 7일 신뢰 가중 감성 {r['sent7']:+.2f}")
    ch = r.get("channels") or {}
    n = sum(int(x.get("recent_n") or x.get("recent") or 0) for x in ch.values())
    if n:
        parts.append(f"최근 언급 {n}건")
    w = _weekly(r.get("ticker"))
    if w:   # Quantral 주간 리테일 순위(2026-11-14, ADR-032)
        parts.append(f"리테일 관심 {w['week']} {w['rank']}위(이야기 게시 {w['posts']}건" + (f", 묶음 테마 {'·'.join(w['themes'])}" if w["themes"] else "") + ")")
    return "통계: " + (", ".join(parts) if parts else "집계 없음") + "."


def _weekly(ticker):
    if not ticker:
        return None
    try:
        sys.path.insert(0, str(ROOT / "scripts" / "valuation" / "v2"))
        import queue_context
        return queue_context.weekly(str(ticker).upper())
    except Exception:
        return None


def section(dp, eid):
    so = (dp or {}).get("social")
    if not so:
        return None
    if so.get("none"):
        return {"h2": "커뮤니티 반응", "blocks": [{"type": "p", "text": f"언급 적음 — {so['none']}"}]}
    check(so)
    r = latest(eid) or {}
    r.setdefault("ticker", (dp or {}).get("ticker"))
    B = [{"type": "p", "text": stat_line(so, r)}]
    if so.get("summary"):
        B.append({"type": "hl", "text": f"**{so['summary']}**"})
    views = so.get("views") or []
    old = so.get("narratives") or []
    if not views and old:   # 옛 datapack(2026-11-13 전) — 채널별 표 그대로
        B.append({"type": "table", "title": "채널별 내러티브와 기대 소화", "headers": ["채널", "주된 이야기", "기대", "1차 자료 대조", "비중"],
                  "rows": [[x.get("channel"), x.get("theme"), x.get("expectation"), x.get("vs_fact", "미확인"), f"{x['share'] * 100:.0f}%" if x.get("share") is not None else "미확인"] for x in old]})
    elif not views or so.get("few"):
        B.append({"type": "p", "text": "언급 적음 — 풀이할 만한 논지가 모이지 않았다."})
    for v in views:
        tag = "" if v["check"] == "확인" else f" [{v['check']}]"
        q = f" 인용: \"{v['quote']}\"." if v.get("quote") else ""
        B.append({"type": "p", "text": f"**{v['side']}** — {v['claim']}" + (f" 근거로 드는 것: {v['basis']}." if v.get("basis") else "") + f"{q} ({v['source']}, {v['date']}){tag}"})
    if so.get("turn"):
        B.append({"type": "p", "text": f"**기대가 바뀐 시점:** {so['turn']}"})
    for c in (daily_chart(eid), monthly_chart(eid)):
        if c:
            B.append({"type": "chart", "chart": c})   # report_layout이 한눈에 보기로 옮긴다
    B.append({"type": "p", "text": "커뮤니티 의견은 시장 기대의 증거이지 사실이 아니며, 관심 급증은 주가·펀더멘털 변화가 아니다."})
    return {"h2": "커뮤니티 반응", "blocks": B}
