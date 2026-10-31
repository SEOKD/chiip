"""규칙 준수 측정기 (마스터 지시 2026-10-31 Chiip Laboratory) — 결정론, 실제 산출물을 evals/rules.yaml로 채점

지시문은 맥락일 뿐 강제가 아니고, 규칙 수가 늘수록 준수율은 떨어진다. 그래서 규칙별 위반율을 재서
실제로 어기는 규칙만 발송·렌더 관문으로 옮긴다. 채점표와 이 파일은 고도화 대상 바깥이다(자기 채점 금지).
사용: py scripts/lab/rule_evals.py [--since YYYY-MM-DD] [--write]   # 규칙별 위반율
      py scripts/lab/rule_evals.py --self-test                     # 규칙의 pass·fail 예시 시험
      py scripts/lab/rule_evals.py --gate                          # 기준선 대비 악화 여부(악화면 종료 코드 1)
      py scripts/lab/rule_evals.py --load                          # 매 회차 읽는 지시문 분량
"""
import argparse
import csv
import hashlib
import html
import json
import re
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "radar"))
RULES = ROOT / "evals" / "rules.yaml"
OUT = ROOT / "knowledge" / "models" / "lab" / "agent"
BASELINE = OUT / "rule_baseline.json"
DATE = re.compile(r"(20\d{2})(\d{2})(\d{2})")
TAG = re.compile(r"<(style|script)\b.*?</\1>|<[^>]+>", re.S)
HELD_OUT = 3   # 파일 3개 중 1개를 경로 해시로 떼어 둔다(개선을 본 표본과 평가 표본을 나눈다)
MIN_SAMPLE, NOISE_Z = 12, 1.64   # 표본이 적으면 판정하지 않고, 잡음 범위 안의 변화는 악화로 치지 않는다(단측 95%)
LOAD_FILES = {"chiip-pulse": ["CLAUDE.md", "docs/channels/pulse.md", "docs/tasks/chiip-pulse.md", "docs/proviser/chiip-pulse.md"],
              "chiip-portfolio": ["CLAUDE.md", "docs/channels/portfolio.md", "docs/tasks/chiip-portfolio.md", "docs/proviser/chiip-portfolio.md"],
              "chiip-tenbagger-report": ["CLAUDE.md", "docs/channels/tenbagger.md", "docs/tasks/chiip-tenbagger-report.md", "docs/proviser/chiip-tenbagger.md"]}
IMPERATIVE = re.compile(r"금지|하지 않는다|쓰지 않는다|않는다|해야|반드시|필수|만 쓴다|넣지|빼고|뺀다")


def load_rules(path=RULES):
    return yaml.safe_load(path.read_text(encoding="utf-8"))["rules"]


def violations(rule, text):
    """위반 조각 목록. require는 패턴이 없으면 한 건"""
    if rule.get("check"):
        import pulse_check
        return [detail for name, _, detail in pulse_check.check(text) if name == rule["check"]]
    if rule.get("require"):
        return [] if re.search(rule["require"], text) else ["(표시 없음)"]
    return [m.group(0) for m in re.finditer(rule["forbid"], text)]


def self_test(rules):
    bad = []
    for r in rules:
        bad += [(r["id"], "pass", s) for s in r.get("pass") or [] if violations(r, s)]
        bad += [(r["id"], "fail", s) for s in r.get("fail") or [] if not violations(r, s)]
        if not r.get("pass") or not r.get("fail"):
            bad.append((r["id"], "예시 없음", ""))
    return bad


def file_date(p):
    m = DATE.search(p.name)
    return date(int(m[1]), int(m[2]), int(m[3])) if m else None


def prepare(rule, text):
    if rule.get("brand"):
        import notify
        text = notify.brand(text)
    if rule.get("html"):
        text = html.unescape(TAG.sub(" ", text))
    return text


def held_out(path):
    return int(hashlib.sha1(path.encode()).hexdigest(), 16) % HELD_OUT == 0


def score(rules, since=None, root=ROOT):
    """규칙별 {checked, failed, in/out 구간, examples}. 날짜를 읽을 수 없는 파일은 채점하지 않는다"""
    out = []
    for r in rules:
        start = max(date.fromisoformat(str(r["since"])), since or date.min)
        row = {"id": r["id"], "rule": r["rule"], "checked": 0, "failed": 0, "in": [0, 0], "out": [0, 0], "examples": []}
        files = sorted({p for g in r["scope"] for p in root.glob(g) if p.is_file()})
        for p in files:
            d = file_date(p)
            if d is None or d < start:
                continue
            rel = p.relative_to(root).as_posix()
            hits = violations(r, prepare(r, p.read_text(encoding="utf-8", errors="replace")))
            side = row["out" if held_out(rel) else "in"]
            row["checked"] += 1
            side[0] += 1
            if hits:
                row["failed"] += 1
                side[1] += 1
                row["examples"].append(f"{rel}: {hits[0][:40]}")
        row["rate"] = row["failed"] / row["checked"] if row["checked"] else None
        out.append(row)
    return out


def rate(side):
    return side[1] / side[0] if side[0] else None


def noise_band(a, b):
    """두 위반율 차이의 잡음 폭 — 합친 비율의 표준오차 × NOISE_Z"""
    p = (a[1] + b[1]) / (a[0] + b[0])
    return NOISE_Z * (p * (1 - p) * (1 / a[0] + 1 / b[0])) ** 0.5


def gate(rows, base):
    """바뀐 뒤 어느 규칙이든 양쪽 표본 중 하나라도 잡음 폭을 넘게 나빠지면 불합격 — 표본 MIN_SAMPLE건 미만은 판정하지 않는다"""
    worse = []
    for r in rows:
        b = base.get(r["id"])
        for side in ("in", "out"):
            if not b or r[side][0] < MIN_SAMPLE or b[side][0] < MIN_SAMPLE:
                continue
            now, old = rate(r[side]), rate(b[side])
            if now - old > noise_band(r[side], b[side]):
                worse.append((r["id"], side, old, now))
    return worse


def instruction_load(root=ROOT):
    """회차마다 읽는 지시문의 글자 수·줄 수·금지형 문장 수. 규칙 수는 어림값이다"""
    out = {}
    for task, files in LOAD_FILES.items():
        text = "\n".join((root / f).read_text(encoding="utf-8") for f in files if (root / f).exists())
        out[task] = {"chars": len(text), "lines": text.count("\n") + 1, "imperatives": sum(len(IMPERATIVE.findall(s)) for s in re.split(r"[.\n]", text))}
    return out


def main(argv):
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("--since")
    ap.add_argument("--self-test", action="store_true")
    ap.add_argument("--gate", action="store_true")
    ap.add_argument("--load", action="store_true")
    ap.add_argument("--write", action="store_true")
    ap.add_argument("--save-baseline", action="store_true")
    a = ap.parse_args(argv)
    rules = load_rules()
    if a.self_test:
        bad = self_test(rules)
        print(f"규칙 {len(rules)}개, 예시 실패 {len(bad)}건")
        for b in bad:
            print(" ", *b)
        return 1 if bad else 0
    if a.load:
        for task, v in instruction_load().items():
            print(f"{task}: {v['chars']:,}자 · {v['lines']}줄 · 금지형 표현 {v['imperatives']}개")
        return 0
    rows = score(rules, date.fromisoformat(a.since) if a.since else None)
    for r in rows:
        shown = "표본 없음" if r["rate"] is None else f"{r['failed']}/{r['checked']} ({r['rate'] * 100:.0f}%)"
        print(f"{r['id']}: {shown}")
        for e in r["examples"][:3]:
            print(f"  {e}")
    if a.save_baseline:
        OUT.mkdir(parents=True, exist_ok=True)
        BASELINE.write_text(json.dumps({r["id"]: {"in": r["in"], "out": r["out"]} for r in rows}, ensure_ascii=False, indent=1), encoding="utf-8")
    if a.write:
        OUT.mkdir(parents=True, exist_ok=True)
        f = OUT / "rule_evals.csv"
        new = not f.exists()
        today = datetime.now(timezone(timedelta(hours=9))).strftime("%Y-%m-%d")
        with f.open("a", encoding="utf-8", newline="") as fh:
            w = csv.writer(fh)
            if new:
                w.writerow(["date", "rule", "checked", "failed"])
            w.writerows([today, r["id"], r["checked"], r["failed"]] for r in rows)
    if a.gate:
        worse = gate(rows, json.loads(BASELINE.read_text(encoding="utf-8")))
        for w in worse:
            print(f"악화: {w[0]} {'떼어 둔 표본' if w[1] == 'out' else '본 표본'} {w[2]:.2f} → {w[3]:.2f}")
        return 1 if worse else 0
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
