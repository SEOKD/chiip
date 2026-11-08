"""Model Lab 제안 생애 추적 — 제안이 어디까지 왔고 무엇이 막고 있나 (2026-11-08 마스터 지시 "Model Laboratory를 더욱 고도화")

문제: 제안서 8건(MLP 4·AAP 4)이 '제안' 상태로 쌓이고, 판정일·막힌 이유·다음 행동이 파일마다 흩어져 있었다.
상태 사다리: 제안 → 그림자 운영(shadow.py 도전자 등록) → 판정 대기(관측 30·날짜 8) → 채택 후보 → 채택(stepwise 관문·마스터 보고) / 기각(이유 기록)
막힘 분류: '코드 연결 없음(binding null)' · '평가기 없음(v2 밖 모델)' · '마스터 승인' · '관측 부족' · '판정일 지남'
출력: 표준 출력 + knowledge/models/lab/pipeline.md(일일 노트가 맨 위에 붙인다)
사용: py scripts/lab/pipeline.py
"""
import csv
import re
import sys
from datetime import date
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
LAB = ROOT / "knowledge" / "models" / "lab"
sys.path.insert(0, str(Path(__file__).resolve().parent))


def proposals():
    out = []
    for f in sorted(list((LAB / "proposals").glob("MLP-*.md")) + list((LAB / "agent" / "proposals").glob("AAP-*.md"))):
        t = f.read_text(encoding="utf-8")
        st = re.search(r"상태:\s*\**([^\n·(]+)", t)
        tgt = re.search(r"대상 파라미터[^\n]*(?:\n\s+- [^\n]*)*", t)   # 제안이 바꾸려는 상수만(근거에 스친 상수 말고)
        params = sorted(set(re.findall(r"`(prm-[a-z0-9-]+)`", tgt.group(0) if tgt else t)))
        judge = re.search(r"판정일[:\s]*(20\d\d-\d\d-\d\d)", t)
        made = re.search(r"(20\d\d)(\d\d)(\d\d)", f.stem)
        out.append({"id": f.stem, "title": t.splitlines()[0].lstrip("# ").split("—", 1)[-1].strip(), "status": (st.group(1).strip() if st else "미상"),
                    "params": params, "judge": judge.group(1) if judge else None,
                    "made": f"{made.group(1)}-{made.group(2)}-{made.group(3)}" if made else None, "approval": bool(re.search(r"\*\*마스터 승인 필요\*\*|승인 대기", t)) and "채택" not in (st.group(1) if st else "")})
    return out


def blockers(p, reg, chal, sens):
    if p["status"].startswith(("채택", "adopted")):
        return "채택됨 — 효과 판정" + (f"({p['judge']})" if p["judge"] else ""), "판정일에 측정"
    if p["approval"]:
        return "마스터 승인", "마스터 결정 요청"
    if p["id"].startswith("AAP"):
        return "에이전트 트랙 — 측정 판정", f"{p['judge'] or '판정일 미정'}에 rule_evals 측정"
    binds = [(reg.get(x) or {}).get("binding") for x in p["params"]]
    if not p["params"] or all(not b for b in binds):
        return "코드 연결 없음(binding null)", "표시(flag)형이면 그림자 대신 '시험 운영 표시'로 먼저 붙이고, 숫자형이면 binding 경로를 만든다"
    if not any(str(b or "").startswith("config/valuation_v2.yaml#") for b in binds):
        return "평가기 없음(v2 밖 모델)", "sensitivity·shadow에 그 모델 평가기를 붙인다"
    if not any(c["param"] in p["params"] for c in chal):
        return "그림자 미등록", "py scripts/lab/shadow.py add <param> <value> <제안> \"<이유>\""
    return "관측 부족", "그림자 판정(shadow.py score)이 관측 30·날짜 8을 넘길 때까지"


def board(today=None):
    import sensitivity as S
    import shadow as SH
    today = today or date.today()
    reg = {p["id"]: p for p in S.registry()}
    chal = SH.challengers()
    sens = {r["param"]: r for r in S.top(999)}
    rows = []
    for p in proposals():
        why, nxt = blockers(p, reg, chal, sens)
        dv = max((float(sens[x]["decision_value"]) for x in p["params"] if x in sens), default=None)
        wait = (today - date.fromisoformat(p["made"])).days if p["made"] else None
        late = bool(p["judge"] and p["judge"] < today.isoformat() and not p["status"].startswith("채택"))
        rows.append({**p, "blocker": why, "next": nxt, "decision_value": dv, "waiting_days": wait, "overdue": late})
    for c in chal:   # 제안서 없이 의사결정 가치로 올린 도전자
        if not any(c["param"] in r["params"] for r in rows):
            rows.append({"id": c["id"], "title": c.get("why", "")[:60], "status": "그림자 운영", "params": [c["param"]], "judge": None, "made": c["since"],
                         "approval": False, "blocker": "관측 부족", "next": "shadow.py score", "decision_value": (float(sens[c["param"]]["decision_value"]) if c["param"] in sens else None),
                         "waiting_days": (today - date.fromisoformat(c["since"])).days, "overdue": False})
    return rows


def write(rows, today=None):
    today = today or date.today()
    L = [f"# Model Lab 제안 보드 — {today.isoformat()}", "", "| 제안 | 상태 | 막힌 곳 | 다음 행동 | 의사결정 가치 | 대기 일수 | 판정일 |", "|---|---|---|---|---|---|---|"]
    for r in rows:
        dv = "" if r["decision_value"] is None else f"{r['decision_value']:.3f}"
        flag = " ⚠ 판정일 지남" if r["overdue"] else ""
        L.append(f"| {r['id']} {r['title'][:40]} | {r['status']} | {r['blocker']}{flag} | {r['next']} | {dv} | {r['waiting_days'] if r['waiting_days'] is not None else ''} | {r['judge'] or ''} |")
    (LAB / "pipeline.md").write_text("\n".join(L) + "\n", encoding="utf-8")


def main(argv):
    sys.stdout.reconfigure(encoding="utf-8")
    rows = board()
    write(rows)
    for r in rows:
        print(f"{r['id']:<34} {r['status'][:14]:<14} 막힘: {r['blocker']:<26} → {r['next'][:60]}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
