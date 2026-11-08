"""Proviser 점검 대상 — 예약 작업 목록에서 매 회차 정한다 (마스터 지시 2026-11-09 "모든 기능을 점검 대상으로, 앞으로 새로 나올 모든 기능도 포함")

규칙: 켜져 있는 반복 예약 작업(cron)은 모두 대상이다. 빼는 것은 Proviser 자신과 1회성 작업(fireAt)뿐이다.
처음 보는 작업은 대상 표(config/proviser_targets.yaml)에 넣고 docs/proviser/<taskId>.md 원장을 뼈대로 만든다. 성과 지표(KPI)는 config/proviser.yaml systems에
있을 때만 쓰고, 없으면 quality.py가 판단 점수(루브릭)만 매긴다 — 성과 지표는 표본이 쌓이면 붙인다. 표본 경로는 대상 표, 없으면 지시문 원본(docs/tasks/…)에서 찾는다.
사용: py scripts/proviser/targets.py <list_scheduled_tasks 응답 JSON 파일>   → 대상 표(이름·표본 경로·새로 들어옴)와 docs/proviser/targets.json
"""
import json
import re
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
REG = ROOT / "config" / "proviser_targets.yaml"   # 대상 표 — 이 스크립트가 관리한다(config/proviser.yaml 주석을 건드리지 않게)
SELF = "chiip-proviser"
LEDGER = """# {title} ({task}) — Proviser 원장

자동 편입(scripts/proviser/targets.py, {date}): 예약 작업 목록에 새로 나타난 기능이다. 지시문 원본: {doc}
표본: {outputs}

## 역량 원장
| 날짜 | 점수 | 사고 | 추론 | 체계 | 근거 |
|---|---|---|---|---|---|

## 현재 보강 지시

## 상시 원칙
"""


def targets(tasks):
    return [t for t in tasks if t.get("enabled") and t.get("cronExpression") and t["taskId"] != SELF]


def doc_of(t):
    m = re.search(r"docs/tasks/[\w.-]+\.md|\.claude/skills/[\w-]+/SKILL\.md", t.get("description") or "")
    return m.group(0) if m else None


def run(tasks, today):
    reg = (yaml.safe_load(REG.read_text(encoding="utf-8")) if REG.exists() else None) or {}
    out, new = [], []
    for t in targets(tasks):
        tid = t["taskId"]
        info = reg.get(tid)
        if info is None:
            info = {"name": t.get("title") or tid, "outputs": "지시문 원본의 산출물 경로", "doc": doc_of(t), "added": today}
            reg[tid] = info
            new.append(tid)
        led = ROOT / "docs" / "proviser" / f"{tid}.md"
        if not led.exists():
            led.write_text(LEDGER.format(title=info["name"], task=tid, date=today, doc=info.get("doc") or "미확인", outputs=info.get("outputs")), encoding="utf-8")
        out.append({"taskId": tid, "name": info["name"], "outputs": info.get("outputs"), "doc": info.get("doc"), "new": tid in new,
                    "schedule": t.get("schedule"), "twin_of": info.get("twin_of")})
    gone = [k for k in reg if k not in {x["taskId"] for x in out}]
    if new:
        REG.write_text("# Proviser 점검 대상 표 — scripts/proviser/targets.py가 예약 작업 목록에서 새 기능을 자동으로 더한다(마스터 지시 2026-11-09). 이름·표본 경로는 고쳐도 된다\n"
                       + yaml.safe_dump(reg, allow_unicode=True, sort_keys=False, width=200), encoding="utf-8")
    (ROOT / "docs" / "proviser" / "targets.json").write_text(json.dumps({"date": today, "targets": out, "paused_or_removed": gone}, ensure_ascii=False, indent=1), encoding="utf-8")
    return out, new, gone


def main(argv):
    sys.stdout.reconfigure(encoding="utf-8")
    from datetime import date
    raw = json.loads(Path(argv[0]).read_text(encoding="utf-8"))
    tasks = raw if isinstance(raw, list) else raw.get("tasks") or raw
    out, new, gone = run(tasks, date.today().isoformat())
    print(f"[Proviser 대상] {len(out)}개" + (f" · 새로 들어옴 {', '.join(new)}" if new else "") + (f" · 꺼짐·삭제 {', '.join(gone)}" if gone else ""))
    for x in out:
        print(f"{x['taskId']} | {x['name']} | 표본 {x['outputs']}" + (f" | 함께 보는 짝 {x['twin_of']}" if x.get("twin_of") else "") + (" | 새로 편입" if x["new"] else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
