"""Analysis 리포트 '커뮤니티 내러티브' 절 (마스터 지시 2026-11-07 "Analysis에서 다루는 종목이 X, 서브스택, 레딧, 유튜브에서 어떤 내러티브로
시장의 기대감을 소화하고 있는지 체계적으로 파악 … 관련 시각물은 한눈에 보기에")

숫자(언급 건수·급증 Z·감성)는 radar/social_surge.py 집계(knowledge/models/social/)에서 읽는다. 내러티브는 모델이 Quantral
get_company_signals·get_company_recaps를 읽고 자기 말로 datapack "social"에 쓴다 — 글 본문 인용·작성자 이름은 쓰지 않는다:
  "social": {"as_of": "2026-11-07", "summary": "기대를 어떻게 소화하고 있나 한 줄",
             "narratives": [{"channel": "X|레딧|유튜브|서브스택", "theme": "주된 이야기 한 줄", "expectation": "상향|하향|혼재|소진",
                             "vs_fact": "1차 자료와 맞나(확인·과장·미확인)", "share": 0.4}],   # share = 그 채널 언급 중 그 이야기 비중(어림)
             "turn": "기대가 바뀐 시점과 계기(있으면)"}
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


def section(dp, eid):
    so = (dp or {}).get("social")
    if not so:
        return None
    if so.get("none"):
        return {"h2": "커뮤니티 내러티브", "blocks": [{"type": "p", "text": f"커뮤니티 집계 없음 — {so['none']}"}]}
    r = latest(eid) or {}
    head = f"**{so.get('summary', '')}**"
    if r.get("Z") is not None:
        head += f" 관심 급증 {r['score']}/10(결합 Z {r['Z']:+.1f})" + (f", 최근 7일 신뢰 가중 감성 {r['sent7']:+.2f}(관측 전체 {r['sent_all']:+.2f})" if r.get("sent7") is not None else "") + "."
    B = [{"type": "hl", "text": head}]
    nar = so.get("narratives") or []
    if nar:
        B.append({"type": "table", "title": "채널별 내러티브와 기대 소화", "headers": ["채널", "주된 이야기", "기대", "1차 자료 대조", "비중"],
                  "rows": [[x.get("channel"), x.get("theme"), x.get("expectation"), x.get("vs_fact", "미확인"), f"{x['share'] * 100:.0f}%" if x.get("share") is not None else "미확인"] for x in nar]})
    ch = r.get("channels") or {}
    if ch:
        rows = []
        for k, x in ch.items():
            if "p" in x:
                rows.append([NAMES.get(k, k), f"30일 {x['recent']}건", f"30일당 {x['base']}건", f"p {x['p']:.3f}", "-"])
            else:
                rows.append([NAMES.get(k, k), f"3일 {x['recent_n']}건", f"하루 {x['base']:.1f}건", f"Z {x['z']:+.1f}", "지속 상승" if x.get("alarm") else "-"])
        B.append({"type": "table", "title": "채널별 급증 측정(음이항 Z·CUSUM, 사건형은 포아송 꼬리확률)", "headers": ["채널", "최근", "평소", "급증", "지속"], "rows": rows})
    if so.get("turn"):
        B.append({"type": "p", "text": f"**기대가 바뀐 시점:** {so['turn']}"})
    for c in (daily_chart(eid), monthly_chart(eid)):
        if c:
            B.append({"type": "chart", "chart": c})   # report_layout이 한눈에 보기로 옮긴다
    B.append({"type": "p", "text": "원천: Quantral(X·레딧·유튜브·서브스택 언급 집계, 작성자 적중률로 신뢰 가중). 커뮤니티 의견은 시장 기대의 증거이지 사실이 아니며, 관심 급증은 주가·펀더멘털 변화가 아니다."})
    return {"h2": "커뮤니티 내러티브", "blocks": B}


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    eid = sys.argv[1]
    dp = json.loads((ROOT / "knowledge" / "models" / "companies" / eid / "datapack.json").read_text(encoding="utf-8"))
    print(json.dumps(section(dp, eid), ensure_ascii=False, indent=1))
