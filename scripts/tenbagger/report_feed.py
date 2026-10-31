"""Ten-bagger Report 발행 알림 양식 (마스터 지시 2026-11-01 "리포트 작성 소식을 전달하는 피드 가독성이 매우 떨어진다. 양식을 직관적으로 볼 수 있게")

양식 3 리포트 JSON에서 만든다. 숫자는 리포트에서 가져오므로 모델이 다시 쓰지 않는다. 읽는 순서: 결론 → 이유 → 밸류에이션 → 셀온 조건 → 다음 확인.
모델은 verdict.points에 [["좋은 점", "한 문장"], ["나쁜 점", "한 문장"], ["가를 것", "한 문장"]]만 쓴다. 없으면 Chiip View 앞 세 문장을 쓴다.
사용: py scripts/tenbagger/report_feed.py <리포트 json>   → 미리보기
"""
import json
import re
import sys
from pathlib import Path

ZACKS = "Data provided by Zacks Investment Research, Inc., www.zacksdata.com"
FOOT = "구매 등급·목표주가 모두 규칙이 계산한 모델 값 · 투자 권유 아님 · 1차 판정, 미검증"
PLAIN = re.compile(r"\*\*")


def _sec(d, name):
    return next((s for s in d.get("sections") or [] if str(s.get("h2", "")).startswith(name)), {})


def _tile(d, key):
    return next((t for t in d.get("tiles") or [] if str(t.get("k", "")).startswith(key)), {})


def _table(sec, title):
    return next((b for b in sec.get("blocks") or [] if b.get("type") == "table" and str(b.get("title", "")).startswith(title)), {})


def _pct(x):
    p = round(x * 100)
    return "0%" if p == 0 else f"{p:+d}%".replace("-", "−")


def reasons(d):
    v = d.get("verdict") or {}
    if v.get("points"):
        return [[a, b] for a, b in v["points"][:3]]
    text = PLAIN.sub("", str(v.get("view") or ""))
    return [[None, x.strip() + "다."] for x in re.split(r"다\.\s*", text) if x.strip()][:3]


def build(d):
    v, val = d.get("verdict") or {}, _sec(d, "밸류에이션")
    money = "NOK " if "NOK" in str(_tile(d, "주가").get("v")) else "$"
    cases = {k["name"]: k for c in d.get("gallery") or [] if c.get("kind") == "scenario" for k in c.get("cases") or []}
    date = str(d["date"])[5:].replace("-", "/")
    out = [f"[Chiip Ten-bagger Report {date}]", "", f"**{d['company']}({d['ticker']})**", d["title"], f"기업: {d['biz']}", ""]
    alpha = v.get("insight") if v.get("insight") is not None else v.get("alpha")
    out += ["**■ 결론**", f"- 구매 등급 **{v.get('rating')}** · 알파 {alpha}/10"]
    if v.get("target_text"):
        out.append(f"- 목표주가 {v['target_text']} · {v.get('target_place')}")
    out.append(f"- 업사이드 {_pct(v.get('upside') or 0)} · 다운사이드 {_pct(v.get('downside') or 0)} · 손익비 {(v.get('rr') or 0):.1f}")
    out += ["", "**■ 왜 이렇게 보나**"] + [f"- {a}: {b}" if a else f"- {b}" for a, b in reasons(d)]
    out += ["", "**■ 밸류에이션**", f"- 주가 {_tile(d, '주가').get('v')} ({_tile(d, '주가').get('sub', '').split(' · ')[0]})"]
    if cases:
        out.append("- 시나리오: " + " · ".join(f"{n} {money}{cases[n]['value']:,.0f}" for n in ("약세", "기본", "강세") if n in cases))
    rows = {r[0]: r for r in _table(val, "멀티플 선정").get("rows") or []}
    sel = rows.get("**선정**")
    now = _tile(d, "멀티플")
    if sel:
        out.append(f"- 멀티플: 지금 {str(now.get('v')).split()[-1]} · 선정 {PLAIN.sub('', sel[1])} · {now.get('sub')}")
    hl = next((str(b.get("text")) for b in val.get("blocks") or [] if b.get("type") == "hl"), "")
    m = re.search(r"DCF 기준 업사이드는 기본 ([+\-−]?\d+%)", hl)
    if m:
        out.append(f"- DCF 기준 업사이드 {m.group(1).replace('-', '−')}")
    sup = _table(_sec(d, "수급"), "지지선").get("rows") or []
    if sup and sup[0][1] != "-":
        out.append(f"- 일봉 지지선: {sup[0][1].split(' · ')[0]}")
    bear = _sec(d, "약세 논리")
    sell = next((x for b in bear.get("blocks") or [] if b.get("type") == "boxes" for x in b.get("items") or [] if x.get("title") == "셀온 조건"), {})
    if sell.get("lines"):
        out += ["", "**■ 셀온 조건**"] + [f"- {t.rstrip('.')}" for _, t in sell["lines"][:3]]
    check = next((b for b in _sec(d, "체크리스트").get("blocks") or [] if b.get("type") == "table"), {})
    if check.get("rows"):
        out += ["", "**■ 다음 확인**"] + [f"- {r[0]}: {r[1]}" for r in check["rows"][:2]]
    out.append("")
    if "미확인" not in str(_tile(d, "구매등급").get("sub")) and not _tile(d, "구매등급").get("second"):
        out.append(ZACKS)
    out.append(FOOT)
    return "\n".join(out)


def main(argv):
    sys.stdout.reconfigure(encoding="utf-8")
    print(build(json.loads(Path(argv[0]).read_text(encoding="utf-8"))))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
