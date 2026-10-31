"""Chiip Ten-bagger Discovery 피드 양식 (마스터 지시 2026-11-01 "글의 가독성이 매우 떨어진다. 문단 띄어쓰기, 표현 간결화, 하이픈 등 기호로 문장 분류")

모델은 내용만 JSON으로 쓰고 모양은 여기서 정한다. 읽는 순서: 결론 → 심층 검토 → 숫자 목록. 빈 절은 나오지 않는다.
{"date": "11/01",
 "summary": ["신규 편입 없음", "심층 검토 2곳 모두 보류"],                       # 결론 1~3줄, 줄당 40자
 "deep": [{"name": "National Presto(NPK)", "theme": "탄약", "stage": "보류", "biz": "사업 1줄", "view": "판단", "points": [["증거", "…"], ["다음", "…"]]}],   # 신규 후보·편입·보류
 "alpha": ["진입 Rambus(RMBS) 5.2"],
 "top": [{"name": "MilDef Group", "score": 6.8, "stage": "아이디어"}],             # 선별 상위 5
 "accel": [{"name": "…", "accel": 2.1}],
 "bands": [{"band": "$1–10B", "name": "Theon(THEON)", "score": 6.28, "note": "10배 산술 가능"}], "moves": ["Onto $10–20B → $20–30B"],
 "consumer": [{"name": "e.l.f. Beauty(ELF)", "score": 7.0, "phase": "상승 사이클 진입", "growth": "+36%", "demand": "미확인"}], "flips": ["…"],
 "quiet": [{"name": "National Presto(NPK)", "score": 7.5, "rise": 8.7, "inst": 9.7, "low": 9.8}],
 "watch": [{"name": "FormFactor(FORM)", "why": "200일선 아래, 고점의 62%"}],
 "zacks": true}
사용: py scripts/discovery/feed.py <json> [--send]
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FOOT = "연구 후보이지 매수 권유 아님 · 1차 판정, 미검증"
ZACKS = "Data provided by Zacks Investment Research, Inc., www.zacksdata.com"
MAX_LINE = 70


def _section(title, lines):
    return [f"**■ {title}**"] + lines if lines else []


def _deep(x):
    head = f"**▶ {x['name']}**" + "".join(f" · {v}" for v in (x.get("theme"), x.get("stage")) if v)
    body = [head] + ([f"기업: {x['biz']}"] if x.get("biz") else [])
    if x.get("view"):
        body.append(f"- 판단: {x['view']}")
    body += [f"- {a}: {b}" for a, b in x.get("points") or [] if b]
    return "\n".join(body)


def render(d):
    blocks = [f"[Chiip Ten-bagger Discovery {d['date']}]"]

    def add(title, lines):
        if lines:
            blocks.append("\n".join(_section(title, lines)))
    add("이번 회차 결론", [f"- {x}" for x in d.get("summary") or []])
    for i, x in enumerate(d.get("deep") or []):
        blocks.append(("**■ 심층 검토**\n" if i == 0 else "") + _deep(x))
    add("알파 진입·이탈", [f"- {x}" for x in d.get("alpha") or []])
    add("선별 상위", [f"- {x['name']} {x['score']} · {x['stage']}" for x in d.get("top") or []])
    add("관심 급가속", [f"- {x['name']} {x['accel']}배" for x in d.get("accel") or []])
    add("시가총액 구간 1위", [f"- {x['band']}: {x['name']} {x['score']}" + (f" · {x['note']}" if x.get("note") else "") for x in d.get("bands") or []] + [f"- 이동: {x}" for x in d.get("moves") or []])
    add("소비재·IP", [f"- {x['name']} {x['score']} · {x['phase']}\n  성장 {x['growth']} · 수요 가속 {x['demand']}" for x in d.get("consumer") or []] + [f"- 전환: {x}" for x in d.get("flips") or []])
    add("조용한 매집형 상승", [f"- {x['name']} {x['score']}\n  상승 {x['rise']} · 기관 {x['inst']} · 관심 부족 {x['low']}" for x in d.get("quiet") or []])
    add("관측 종목", [f"- {x['name']}: {x['why']}" for x in d.get("watch") or []])
    blocks.append("\n".join(([ZACKS] if d.get("zacks") else []) + [FOOT]))
    return "\n\n".join(blocks)


def check(d):
    """줄이 길면 양식이 무너진다 — 긴 문장은 나누라고 돌려준다"""
    bad = [str(x)[:40] for x in d.get("summary") or [] if len(str(x)) > 40]
    for x in d.get("deep") or []:
        bad += [str(v)[:40] for v in [x.get("view")] + [b for _, b in x.get("points") or []] if v and len(str(v)) > MAX_LINE]
    return bad


def main(argv):
    sys.stdout.reconfigure(encoding="utf-8")
    d = json.loads(Path(argv[0]).read_text(encoding="utf-8"))
    bad = check(d)
    if bad:
        print("문장이 길다 — 나눠 쓴다:", bad)
        return 1
    body = render(d)
    print(body)
    if "--send" in argv:
        sys.path.insert(0, str(ROOT / "radar"))
        import notify
        print(notify.send(body, "TENBAGGER", md=True))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
