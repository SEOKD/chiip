"""Model Lab 그림자 운영 — 제안 값을 실전에 넣기 전에 매일 나란히 돌려 '앞으로의 성과'로 판정 (2026-11-08 마스터 지시 "Model Laboratory를 더욱 고도화")

문제: 11일 동안 숫자를 바꾼 채택이 0건이다. 표본 외 검증이 필요한데 유료 가격 데이터는 쓰지 않기로 했다(마스터 결정) —
그래서 증거가 '쌓이기 시작'하는 날부터 기다려야 하는데, 그 쌓임 자체가 없었다. 제안을 내는 날부터 그림자로 돌려 증거를 쌓는다.
구조:
  knowledge/models/lab/shadow/challengers.yaml — 도전자 [{id, param(등록부 id), binding(config/valuation_v2.yaml#경로), value, proposal, since, why}]
  run   — 매일 v2가 있는 전 종목에 대해 현행(baseline)과 도전자마다 v0·연 기대수익·매수 매력 신호를 ledger.csv에 남긴다(실전 산출은 그대로).
  score — h 거래일(기본 20·60) 뒤 가격(knowledge/models/valuation/history/*.csv의 price)과 맞춰
          ① 순위 정보계수 IC = Spearman(연 기대수익, 이후 수익률) ② '강함' 신호 종목의 이후 초과수익(표본 평균 대비)을 모델별로 낸다.
          도전자가 현행보다 IC가 높고 관측 수가 30 이상(등록부 adoption.min_oos_n), 날짜 수 8 이상이면 '채택 후보'로 올린다 — 채택은 여전히 stepwise 관문과 마스터 보고.
사용: py scripts/lab/shadow.py run · score [--h 20,60] · add <param> <value> <proposal> "<why>"
"""
import argparse
import copy
import csv
import random
import sys
from datetime import date, datetime
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "valuation" / "v2"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
BASE = ROOT / "knowledge" / "models" / "lab" / "shadow"
CHAL = BASE / "challengers.yaml"
LEDGER = BASE / "ledger.csv"
SCORE = BASE / "score.csv"
HIST = ROOT / "knowledge" / "models" / "valuation" / "history"
FIELDS = ["date", "entity", "model", "v0", "exp_return", "signal"]
MIN_OBS, MIN_DAYS = 30, 8


def challengers():
    return (yaml.safe_load(CHAL.read_text(encoding="utf-8")) or {}).get("challengers") or [] if CHAL.exists() else []


def add(param, value, proposal, why):
    import sensitivity as S
    reg = {p["id"]: p for p in S.registry()}
    b = str((reg.get(param) or {}).get("binding") or "")
    if not b.startswith(S.CFG + "#"):
        raise SystemExit(f"{param}: binding이 {S.CFG}#… 가 아니다 — 평가기를 붙인 모델부터 그림자 운영")
    d = yaml.safe_load(CHAL.read_text(encoding="utf-8")) if CHAL.exists() else {"challengers": []}
    cid = f"{param}={value}"
    if any(c["id"] == cid for c in d["challengers"]):
        return cid
    d["challengers"].append({"id": cid, "param": param, "binding": b, "value": float(value), "proposal": proposal, "since": date.today().isoformat(), "why": why})
    BASE.mkdir(parents=True, exist_ok=True)
    CHAL.write_text(yaml.safe_dump(d, allow_unicode=True, sort_keys=False), encoding="utf-8")
    return cid


def run(day=None):
    import run as v2
    import sensitivity as S
    day = day or date.today().isoformat()
    cfg = yaml.safe_load((ROOT / S.CFG).read_text(encoding="utf-8"))
    models = [("baseline", cfg)]
    for c in challengers():
        c2 = copy.deepcopy(cfg)
        S.set_path(c2, c["binding"].split("#", 1)[1].split("."), c["value"])
        models.append((c["id"], c2))
    have = set()
    if LEDGER.exists():
        with LEDGER.open(encoding="utf-8", newline="") as f:
            have = {(r["date"], r["entity"], r["model"]) for r in csv.DictReader(f)}
    rows = []
    for p in sorted((ROOT / "knowledge" / "models" / "companies").glob("*/drivers.yaml")):
        eid = p.parent.name
        for name, c in models:
            if (day, eid, name) in have:
                continue
            random.seed(7)
            try:
                r = v2.evaluate(eid, 200, cfg=c)
            except Exception:
                continue
            a = (r.get("decision") or {}).get("attractiveness") or {}
            rows.append({"date": day, "entity": eid, "model": name, "v0": (r.get("base") or {}).get("v0"), "exp_return": a.get("exp_return"), "signal": a.get("signal")})
    BASE.mkdir(parents=True, exist_ok=True)
    new = not LEDGER.exists()
    with LEDGER.open("a", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, FIELDS)
        if new:
            w.writeheader()
        w.writerows(rows)
    return len(rows), len(models)


def prices():
    """{id: [(date, price)]} — 일별 밸류에이션 기록의 가격(유료 데이터 아님)"""
    out = {}
    for f in sorted(HIST.glob("*.csv")):
        with f.open(encoding="utf-8", newline="") as fh:
            for r in csv.DictReader(fh):
                try:
                    out.setdefault(r["id"], []).append((r.get("price_date") or f.stem, float(r["price"])))
                except (KeyError, TypeError, ValueError):
                    continue
    for k in out:
        out[k] = sorted(set(out[k]))
    return out


def fwd(series, d, h):
    """d 이후 첫 가격과 그로부터 h번째 가격의 수익률(없으면 None)"""
    idx = next((i for i, (dd, _) in enumerate(series) if dd >= d), None)
    if idx is None or idx + h >= len(series):
        return None
    return series[idx + h][1] / series[idx][1] - 1


def spearman(xs, ys):
    def rank(v):
        o = sorted(range(len(v)), key=lambda i: v[i])
        r = [0.0] * len(v)
        for k, i in enumerate(o):
            r[i] = k
        return r
    if len(xs) < 3:
        return None
    rx, ry = rank(xs), rank(ys)
    n = len(xs)
    mx, my = sum(rx) / n, sum(ry) / n
    cov = sum((a - mx) * (b - my) for a, b in zip(rx, ry))
    vx, vy = sum((a - mx) ** 2 for a in rx), sum((b - my) ** 2 for b in ry)
    return cov / (vx * vy) ** 0.5 if vx and vy else None


def score(hs=(20, 60)):
    if not LEDGER.exists():
        return []
    with LEDGER.open(encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))
    px = prices()
    out = []
    for h in hs:
        by = {}
        for r in rows:
            s = px.get(r["entity"])
            if not s or r["exp_return"] in ("", None):
                continue
            fr = fwd(s, r["date"], h)
            if fr is None:
                continue
            by.setdefault(r["model"], []).append((r["date"], float(r["exp_return"]), fr, r["signal"]))
        base_ic = None
        for m in sorted(by, key=lambda k: k != "baseline"):
            xs = by[m]
            ic = spearman([x[1] for x in xs], [x[2] for x in xs])
            mean = sum(x[2] for x in xs) / len(xs)
            strong = [x[2] - mean for x in xs if x[3] == "강함"]
            days = len({x[0] for x in xs})
            if m == "baseline":
                base_ic = ic
            cand = m != "baseline" and ic is not None and base_ic is not None and ic > base_ic and len(xs) >= MIN_OBS and days >= MIN_DAYS
            out.append({"h": h, "model": m, "n": len(xs), "days": days, "ic": None if ic is None else round(ic, 3),
                        "strong_excess": round(sum(strong) / len(strong), 4) if strong else None, "candidate": cand})
    BASE.mkdir(parents=True, exist_ok=True)
    with SCORE.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, ["as_of", "h", "model", "n", "days", "ic", "strong_excess", "candidate"])
        w.writeheader()
        for r in out:
            w.writerow({"as_of": date.today().isoformat(), **r})
    return out


def main(argv):
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["run", "score", "add"])
    ap.add_argument("rest", nargs="*")
    ap.add_argument("--h", default="20,60")
    a = ap.parse_args(argv)
    if a.cmd == "add":
        print(add(a.rest[0], a.rest[1], a.rest[2], a.rest[3] if len(a.rest) > 3 else ""))
    elif a.cmd == "run":
        n, m = run()
        print(f"[그림자 운영] {n}행 기록 · 모델 {m}개(현행 포함)")
    else:
        res = score(tuple(int(x) for x in a.h.split(",")))
        if not res:
            print("[그림자 판정] 아직 판정할 수 있는 관측이 없다(가격이 h거래일 쌓여야 한다)")
        for r in res:
            print(f"h={r['h']:>3} {r['model']:<40} n={r['n']:>4} 날짜 {r['days']:>3} IC {r['ic']} 강함 초과수익 {r['strong_excess']}" + (" ← 채택 후보" if r["candidate"] else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
