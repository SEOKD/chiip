"""텐배거 리포트 '애널리스트 토론' 절 (마스터 지시 2026-11-03 "평가등급별로 컨빅션이 뚜렷한 가상의 글로벌 IB 리서치 하우스
시니어 애널리스트를 각 한 명씩 배치하고 이들이 10분간 토론을 진행해 최적의 의사결정을 조율해 정하도록 해라")

등급 자리 5개(Strong Buy·Buy·Neutral·Sell·Strong Sell)에 가상의 애널리스트를 한 명씩 앉힌다. 실존 IB·인물 이름은 쓰지 않는다.
10분 토론은 시간이 아니라 정해진 차례로 재현한다: 개회 발언 → 반박 2차례 → 최종 발언 → 투표. 차례가 빠지면 --merge가 멈춘다.
규칙 등급(report_layout.rating)이 출발점이고, 토론 결론은 규칙 등급에서 config/tenbagger.yaml debate.max_shift 단계까지만 옮길 수 있다.
datapack "debate":
  {"panel": [{"seat": "Strong Buy", "name": "가상 이름", "house": "가상 리서치 하우스", "thesis": "이 등급의 핵심 논리 한 줄",
              "evidence": ["1차 자료 숫자", "…"], "falsifier": "이 논리가 틀리는 조건"}…],   # 자리 5개 모두, 같은 순서 아니어도 된다
   "rounds": [{"round": "개회", "remarks": [{"seat": "Strong Buy", "text": "…"}…]},          # 자리마다 한 번
              {"round": "반박1", "remarks": [{"seat": "Sell", "to": "Buy", "text": "상대 숫자를 겨냥한 반박"}…]},
              {"round": "반박2", "remarks": […]},
              {"round": "최종", "remarks": [{"seat": "…", "text": "…", "moved": "Buy"}…]}],   # moved = 토론 뒤 이 애널리스트가 옮긴 등급(선택)
   "final": {"rating": "Buy", "votes": {"Strong Buy": "Buy", "Buy": "Buy", "Neutral": "Buy", "Sell": "Neutral", "Strong Sell": "Sell"},
             "reason": "조율 근거 — 어느 반박이 살아남았나", "dissent": "끝까지 남은 반대 의견 한 줄"}}
"""
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
SEATS = ("Strong Buy", "Buy", "Neutral", "Sell", "Strong Sell")
ROUNDS = ("개회", "반박1", "반박2", "최종")


def config():
    return (yaml.safe_load((ROOT / "config" / "tenbagger.yaml").read_text(encoding="utf-8")) or {}).get("debate") or {"max_shift": 1}


def check(db):
    seats = sorted(p.get("seat") for p in db.get("panel") or [])
    if seats != sorted(SEATS):
        raise SystemExit(f"debate.panel은 등급 자리 5개가 하나씩이어야 한다: {seats}")
    for p in db["panel"]:
        if not (p.get("name") and p.get("house") and p.get("thesis") and p.get("evidence") and p.get("falsifier")):
            raise SystemExit(f"debate.panel {p.get('seat')}에 name·house·thesis·evidence·falsifier가 다 있어야 한다")
    got = [r.get("round") for r in db.get("rounds") or []]
    if got != list(ROUNDS):
        raise SystemExit(f"debate.rounds 차례는 {'→'.join(ROUNDS)}여야 한다: {got}")
    for r in db["rounds"]:
        said = {m.get("seat") for m in r.get("remarks") or [] if m.get("text")}
        if r["round"] in ("개회", "최종") and said != set(SEATS):
            raise SystemExit(f"debate {r['round']}에서 자리 5개가 모두 말해야 한다(빠진 자리 {sorted(set(SEATS) - said)})")
        if r["round"].startswith("반박") and (len(said) < 3 or any(not m.get("to") for m in r["remarks"])):
            raise SystemExit(f"debate {r['round']}는 3자리 이상이 상대(to)를 정해 반박해야 한다")
    f = db.get("final") or {}
    if f.get("rating") not in SEATS or sorted((f.get("votes") or {}).keys()) != sorted(SEATS) or not f.get("reason"):
        raise SystemExit("debate.final에 rating(5등급 중 하나)·votes(자리 5개)·reason이 있어야 한다")
    if any(v not in SEATS for v in f["votes"].values()):
        raise SystemExit("debate.final.votes 값은 5등급 중 하나여야 한다")


def decide(dp, rule):
    """규칙 등급에서 출발해 토론 결론으로 조율한 등급. 이동 폭은 max_shift로 자른다"""
    db = (dp or {}).get("debate")
    if not db:
        raise SystemExit("datapack에 debate가 없다(scripts/tenbagger/debate_view.py 맨 위) — 옛 리포트 정정은 --legacy")
    check(db)
    cap = int(config().get("max_shift", 1))
    i, j = SEATS.index(rule), SEATS.index(db["final"]["rating"])
    k = i + max(-cap, min(cap, j - i))
    return SEATS[k], {"rule": rule, "asked": db["final"]["rating"], "final": SEATS[k], "capped": k != j}


def section(dp, res):
    db = dp["debate"]
    f = db["final"]
    tally = {s: sum(1 for v in f["votes"].values() if v == s) for s in SEATS}
    head = f"**토론 결론 {res['final']}(규칙 등급 {res['rule']}).** " + str(f["reason"])
    if res["capped"]:
        head += f" 토론은 {res['asked']}를 냈지만 규칙 등급에서 {config().get('max_shift', 1)}단계까지만 옮길 수 있어 {res['final']}로 정했다."
    B = [{"type": "hl", "text": head},
         {"type": "table", "title": "패널(가상 애널리스트)", "headers": ["자리", "애널리스트", "핵심 논리", "틀리는 조건", "최종 투표"],
          "rows": [[p["seat"], f"{p['name']}({p['house']})", p["thesis"], p["falsifier"], f["votes"][p["seat"]]]
                   for p in sorted(db["panel"], key=lambda p: SEATS.index(p["seat"]))]},
         {"type": "table", "title": "투표", "headers": list(SEATS), "rows": [[str(tally[s]) for s in SEATS]]}]
    for r in db["rounds"]:
        B.append({"type": "boxes", "items": [{"title": f"{r['round']} · {m['seat']}" + (f" → {m['to']}" if m.get("to") else ""),
                                              "tag": m.get("moved") or "", "lines": [["발언", m["text"]]]} for m in r["remarks"]]})
    if f.get("dissent"):
        B.append({"type": "p", "text": f"남은 반대 의견: {f['dissent']}"})
    B.append({"type": "p", "text": "패널은 가상 인물이고 실존 IB의 의견이 아니다."})
    return {"h2": "애널리스트 토론", "blocks": B}
