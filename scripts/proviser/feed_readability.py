"""텔레그램 피드 가독성 채점·개선 장부 (마스터 지시 2026-11-04 "텔레그램 피드를 적을 때 가독성 있게 쓰도록 보고 양식을 지속 개선하도록 해라")

발송된 글 전체(radar/state/sent/<YYYYMMDD>.jsonl, notify.send가 남긴다)를 기능(level)별로 모아 휴대폰에서 읽히는 정도를 0~10으로 잰다.
결정론 지표만 쓴다(감점식, 상수 config/feed_readability.yaml). 모델은 점수가 가장 낮은 지표 하나를 골라 양식 규칙을 고친다(Proviser 6-6).
  첫 줄: 결론이 첫 줄에 있는가(첫 줄 길이 ≤ first_line_max자, 숫자·고유명 포함)
  덩어리: 빈 줄 없는 연속 줄 수 ≤ block_max, 한 줄 ≤ line_max자, 한 문장 숫자 ≤ numbers_max
  잡음: 내부 코드(T0·P1·S3 등)·영문 약어 풀이 없음·'미확인' 남발·같은 링크 반복
  길이: 글 전체 ≤ chars_max자(넘으면 넘은 비율만큼)
사용: py scripts/proviser/feed_readability.py [YYYYMMDD] [--days 7]   → 기능별 점수·가장 약한 지표·최악 예시 3건, knowledge/models/proviser/feed_readability.csv에 하루 한 행씩
"""
import csv
import json
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
SENT = ROOT / "radar" / "state" / "sent"
CFG = ROOT / "config" / "feed_readability.yaml"
LEDGER = ROOT / "knowledge" / "models" / "proviser" / "feed_readability.csv"
KST = timezone(timedelta(hours=9))
URL = re.compile(r"https?://\S+|<a [^>]*>|</a>")
CODE = re.compile(r"(?<![\w/.=-])(?:T[0-3]|P[0-3]|S[1-5])(?![\w/.=-])")
NUM = re.compile(r"[-+]?\$?\d[\d,.]*%?")


def cfg():
    return yaml.safe_load(CFG.read_text(encoding="utf-8"))


def metrics(text, c):
    """감점 항목별 0~1(1이 나쁨)"""
    t = URL.sub("", str(text))
    t = re.sub(r"<[^>]+>", "", t)
    lines = [ln.rstrip() for ln in t.splitlines()]
    body = [ln for ln in lines if ln.strip()]
    if not body:
        return {}
    first = body[0].strip()
    blocks, run = [], 0
    for ln in lines:
        run = run + 1 if ln.strip() else 0
        blocks.append(run)
    sents = [s for s in re.split(r"(?<=[다요음임함됨.!?])\s+", " ".join(body)) if s.strip()]
    links = re.findall(r"https?://\S+", str(text))
    return {
        "첫 줄 결론": min(1.0, max(0, len(first) - c["first_line_max"]) / c["first_line_max"]) if len(first) > c["first_line_max"] else (0.5 if not NUM.search(first) and len(first) < 12 else 0.0),
        "덩어리": min(1.0, max(0, max(blocks) - c["block_max"]) / c["block_max"]),
        "긴 줄": sum(1 for ln in body if len(ln) > c["line_max"]) / len(body),
        "숫자 과밀": sum(1 for s in sents if len(NUM.findall(s)) > c["numbers_max"]) / max(len(sents), 1),
        "내부 코드": min(1.0, len(CODE.findall(t)) / 3),
        "미확인 남발": min(1.0, max(0, t.count("미확인") - c["unknown_max"]) / 4),
        "링크 반복": min(1.0, (len(links) - len(set(links))) / 3),
        "길이": min(1.0, max(0, len(t) - c["chars_max"]) / c["chars_max"]),
    }


def score(text, c=None):
    c = c or cfg()
    m = metrics(text, c)
    if not m:
        return None, {}
    pen = sum(c["weights"][k] * v for k, v in m.items())
    return round(max(0.0, 10 - pen), 1), m


def load(day, days):
    out = []
    end = datetime.strptime(day, "%Y%m%d")
    for i in range(days):
        f = SENT / f"{(end - timedelta(days=i)):%Y%m%d}.jsonl"
        if f.exists():
            out += [json.loads(l) for l in f.read_text(encoding="utf-8").splitlines() if l.strip()]
    return out


def run(day=None, days=1, c=None, rows=None):
    c = c or cfg()
    day = day or datetime.now(KST).strftime("%Y%m%d")
    rows = rows if rows is not None else load(day, days)
    by = {}
    for r in rows:
        s, m = score(r["text"], c)
        if s is None:
            continue
        by.setdefault(c["functions"].get(r["level"], r["level"]), []).append((s, m, r))
    out = {}
    for fn, xs in by.items():
        avg = sum(s for s, _, _ in xs) / len(xs)
        keys = xs[0][1].keys()
        weak = max(keys, key=lambda k: sum(c["weights"][k] * m[k] for _, m, _ in xs) / len(xs))
        worst = sorted(xs, key=lambda x: x[0])[:3]
        out[fn] = {"n": len(xs), "score": round(avg, 1), "weakest": weak,
                   "penalty": {k: round(sum(c["weights"][k] * m[k] for _, m, _ in xs) / len(xs), 2) for k in keys},
                   "worst": [{"at": r["at"], "score": s, "head": r["text"].splitlines()[0][:60]} for s, _, r in worst]}
    return day, out


def save(day, out):
    LEDGER.parent.mkdir(parents=True, exist_ok=True)
    new = not LEDGER.exists()
    old = [] if new else [r for r in csv.DictReader(LEDGER.open(encoding="utf-8")) if r["date"] != day]
    with LEDGER.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, ["date", "function", "n", "score", "weakest"])
        w.writeheader()
        for r in old:
            w.writerow(r)
        for fn, v in sorted(out.items()):
            w.writerow({"date": day, "function": fn, "n": v["n"], "score": v["score"], "weakest": v["weakest"]})


def main(argv):
    sys.stdout.reconfigure(encoding="utf-8")
    days = int(argv[argv.index("--days") + 1]) if "--days" in argv else 1
    day = next((a for a in argv if a.isdigit() and len(a) == 8), None)
    day, out = run(day, days)
    if days == 1:
        save(day, out)
    print(json.dumps({"date": day, "functions": out}, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
