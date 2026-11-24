"""예측 원장 채점 (BUILD_PROMPT §5.9) — 만기 도래·브라이어 점수
사용: py scripts/score_predictions.py            # 채점 + 만기 도래 미판정 목록 + 원장 형식 문제
      py scripts/score_predictions.py --check    # 원장 형식 문제만(있으면 종료 코드 1)
      py scripts/score_predictions.py --due 5    # 판정할 만기 도래 건(오래된 순 5건, JSON) — Model Laboratory 회차가 1차 출처로 판정한다

2026-11-24 점검 D4(docs/audit/20261124_pipeline_audit.md): 원장 255건 중 제대로 판정된 건이 0건이었다. '판정'으로 보이던 2건은
따옴표 없는 쉼표로 칸이 밀린 행이었고, 기한이 지난 미판정이 16건(최대 19일 경과)이었다. 판정이 없으면 브라이어 점수(성적표)를 낼 수 없다.
  → 형식 검사(칸 수·기한·확률·판정값), 판정 결과는 1/0만 점수에 쓴다, '치입'·'Chiip' 표기는 한 주체로 묶는다, 판정 대기 목록(--due)을 Model Laboratory가 처리한다.
"""
import json
import sys
from datetime import date

from score_common import parse_date, read_csv

PATH = "knowledge/predictions.csv"
OWNER = {"치입": "Chiip", "chiip": "Chiip", "Chiip": "Chiip"}   # 같은 에이전트의 두 표기(2026-10-29 보고 표기 Chiip 지시 전후)
OWNERS = {"Chiip", "마스터"}
BINARY = {"1": 1.0, "0": 0.0, "true": 1.0, "false": 0.0}


def owner(r):
    v = (r.get("owner") or "").strip()
    return OWNER.get(v, v or "미표시")


def problems(rows):
    """[(pred_id, 문제)] — 사후 수정 금지라 고치지 않고 알린다(정정은 새 행으로)"""
    out = []
    for r in rows:
        pid = r.get("pred_id") or "?"
        if None in r or any(v is None for v in r.values()):
            out.append((pid, "칸 수가 머리줄과 다름 — 따옴표 없는 쉼표로 칸이 밀린 행(정정은 새 행으로)"))
            continue
        if not parse_date(r["deadline"]):
            out.append((pid, f"기한 형식 '{r['deadline'][:20]}'"))
        try:
            if not 0.0 <= float(r["probability"]) <= 1.0:
                out.append((pid, f"확률 범위 밖 '{r['probability']}'"))
        except ValueError:
            out.append((pid, f"확률 형식 '{r['probability'][:20]}'"))
        if owner(r) not in OWNERS:
            out.append((pid, f"주체 '{r['owner'][:20]}'"))
        if r["resolved_on"] and r["outcome"].strip().lower() not in BINARY:
            out.append((pid, f"판정값은 1 또는 0 — '{r['outcome'][:30]}'"))
    return out


def due(rows, today=None):
    today = today or date.today()
    bad = {pid for pid, _ in problems(rows)}
    out = [r for r in rows if r.get("pred_id") not in bad and not r["resolved_on"] and (parse_date(r["deadline"]) or date.max) <= today]
    return sorted(out, key=lambda r: parse_date(r["deadline"]))


def brier(rows):
    """{주체: (점수, n)} + 전체 — 판정값이 1/0이고 확률이 숫자인 행만"""
    by, all_ = {}, []
    for r in rows:
        o = BINARY.get((r.get("outcome") or "").strip().lower())
        try:
            p = float(r.get("probability"))
        except (TypeError, ValueError):
            continue
        if o is None or not r.get("resolved_on") or not 0.0 <= p <= 1.0:
            continue
        e = (p - o) ** 2
        all_.append(e)
        by.setdefault(owner(r), []).append(e)
    return {k: (sum(v) / len(v), len(v)) for k, v in by.items()}, ((sum(all_) / len(all_), len(all_)) if all_ else None)


def main(argv):
    sys.stdout.reconfigure(encoding="utf-8")
    rows = read_csv(PATH)
    bad = problems(rows)
    if "--check" in argv:
        for pid, why in bad:
            print(f"- {pid}: {why}")
        print(f"[예측 원장 형식] 문제 {len(bad)}건")
        return 1 if bad else 0
    todo = due(rows)
    if "--due" in argv:
        i = argv.index("--due")
        n = int(argv[i + 1]) if len(argv) > i + 1 and argv[i + 1].isdigit() else 5
        today = date.today()
        print(json.dumps([{"pred_id": r["pred_id"], "statement": r["statement"], "metric": r["metric"], "target": r["target"], "deadline": r["deadline"],
                           "probability": r["probability"], "days_over": (today - parse_date(r["deadline"])).days, "basis": r["basis"][:120]} for r in todo[:n]],
                         ensure_ascii=False, indent=1))
        return 0
    by, total = brier(rows)
    print(f"[예측 원장] 전체 {len(rows)}, 판정 {total[1] if total else 0}, 만기 도래 미판정 {len(todo)}, 형식 문제 {len(bad)}")
    for r in todo:
        print(f"- 판정 필요: {r['pred_id']} {r['statement']} (기한 {r['deadline']})")
    if total:
        print(f"- 브라이어 점수(낮을수록 좋음): {total[0]:.3f} (n={total[1]})")
    # 마스터 예측과 치입 예측을 따로 채점(§21.14 성적표) — 어느 분야에서 누구의 판단이 더 맞는지
    for who, (s, n) in sorted(by.items()):
        print(f"  · {who}: {s:.3f} (n={n})")
    for pid, why in bad:
        print(f"- 형식 문제: {pid} {why}")
    print("※ 사후 수정 금지: 정정은 새 행으로 · 판정값은 1(맞음) 또는 0(틀림), 실제 값은 notes에")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
