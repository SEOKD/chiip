"""Pulse 텔레그램 양식 (마스터 지시 2026-11-02 "텔레그램 봇으로 피드 제공할 때 Report는 가독성 있게 글을 구성했는데 Pulse는 여전히 가독성이 낮다")

Report 피드처럼 엔진이 조립한다. 모델은 내용만 JSON으로 쓴다. 읽는 순서: 머리줄 → 기업 → ■ 결론 → ■ 근거 → ■ 반대 → ■ 다음 확인 → 출처 → ■ 정량(인사이트·컨빅션, 2026-11-03).
입력(outputs/article/sources/<YYYYMMDD_HHMM>_feed.json):
  {"time": "16:24", "items": [{"icon": "⚡", "name": "Alphabet", "code": "GOOGL", "event": "사건 한 줄", "biz": "사업 1줄",
     "view": "판단 한 문장", "insight": 7, "conviction": 8, "basis": "1차 서류", "why": ["근거 줄"], "against": "다른 해석 → 가를 자료",
     "next": "다음 확인", "links": [["8-K 원문", "https://..."]], "read": "https://… 모델이 실제로 열어 읽은 원문 주소"}],
   "brief": [{"name": "삼성전자", "code": "005930", "line": "결론 한 마디", "link": ["보도", "https://..."]}],
   "empty": ["미보도 원문"], "zacks": false}
  본문 확인 관문(2026-11-14 마스터 지시 "본문을 반드시 확인하는 구조"): items·brief마다 "read"에 실제로 열어 읽은 원문 주소를 쓴다
  (fulltext.url 또는 모델이 WebFetch로 연 사본). 없거나 news.google.com 중계 주소면 _tg.txt를 만들지 않고 멈춘다(종료 코드 2).
사용: py radar/pulse_feed.py <json>   → 같은 이름 _tg.txt(끝의 _feed를 뗀다)를 쓰고 양식 점검 결과를 출력
잠금 평가기 pulse_check.py가 그대로 재도록 판단은 **굵게**, 근거·반대·다음 확인은 · 줄로 쓴다.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import pulse_check  # noqa: E402

CIRCLED = "①②③④⑤⑥⑦⑧⑨⑩"
RULE = "─────────"
FOOT = "1차 판정, 미검증 · 공개 자료 기반 분석이며 투자 권유가 아님"
ZACKS = "Data provided by Zacks Investment Research, Inc., www.zacksdata.com"
MAX_WHY = 3
MAX_BASIS = 20


def links(rows):
    return " · ".join(f"[{a}]({b})" for a, b in rows or []) or "출처 미확인"


def block(n, x):
    head = f"**{x['icon']} {CIRCLED[n]} {x['name']} {x['code']}｜{x['event']}**" if x.get("code") else f"**{x['icon']} {CIRCLED[n]} {x['name']}｜{x['event']}**"
    score = f"인사이트 {x['insight']}/10" +(f" · {x['basis'][:MAX_BASIS]}" if x.get("basis") else "")
    parts = [f"{head}\n기업: {x['biz']}", f"**■ 결론**\n**{x['view']}**", "**■ 근거**\n" + "\n".join(f"· {w}" for w in (x.get("why") or [])[:MAX_WHY])]
    if x.get("against"):
        parts.append(f"**■ 반대**\n· {x['against']}")
    if x.get("next"):
        parts.append(f"**■ 다음 확인**\n· {x['next']}")
    parts.append(links(x.get("links")))
    parts.append(f"**■ 정량**\n{score}")   # 정량 지표는 건의 맨 아래(2026-11-03 마스터 지시)
    return "\n\n".join(parts)


def brief_line(b):
    who = f"{b['name']} {b['code']}" if b.get("code") else b["name"]   # 티커에 괄호를 쓰지 않는다(2026-11-03)
    tail = f" [{b['link'][0]}]({b['link'][1]})" if b.get("link") else ""
    return f"· {who} — {b['line']}{tail}"


def build(d):
    rows = sorted(d.get("items") or [], key=lambda x: -x["insight"])
    out = [f"[Chiip Pulse {d['time']}]"]
    for n, x in enumerate(rows):
        out.append(block(n, x))
        if n < len(rows) - 1:
            out.append(RULE)
    if d.get("brief"):
        out += ([RULE] if rows else []) + ["**■ 간단히**\n" + "\n".join(brief_line(b) for b in d["brief"])]
    # '그 외 새 건 없음' 줄과 FOOT(1차 판정·투자 권유 아님)는 Pulse에서 뺀다 — 가독성(마스터 지시 2026-11-13). 다른 채널의 면책은 그대로
    if d.get("zacks"):
        out.append(ZACKS)
    return "\n\n".join(out)


def unread(d):
    """본문을 읽었다는 주소(read)가 없는 건 — 이름 목록"""
    bad = []
    for x in (d.get("items") or []) + (d.get("brief") or []):
        r = str(x.get("read") or "")
        if not r.startswith("http") or "news.google.com" in r:
            bad.append(f"{x.get('name')} {x.get('code') or ''}".strip())
    return bad


def main(argv):
    sys.stdout.reconfigure(encoding="utf-8")
    src = Path(argv[0])
    d = json.loads(src.read_text(encoding="utf-8"))
    bad = unread(d)
    if bad:
        print("본문 미확인 — 보내지 않는다(마스터 지시 2026-11-14): " + " · ".join(bad)
              + " → 원문(fulltext.url 또는 WebSearch로 찾은 사본)을 열어 읽고 'read'에 그 주소를 쓴다. 못 읽으면 그 건을 빼고 py radar/fulltext.py --hold <item_id>")
        return 2
    text = build(d)
    out = src.with_name(src.stem.removesuffix("_feed") + "_tg.txt")
    out.write_text(text, encoding="utf-8")
    print(out)
    rows = pulse_check.check(text)
    for name, head, detail in rows:
        print(f"{name}: {head[:40]} — {detail[:50]}")
    return 1 if any(r[0] == "link" for r in rows) else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
