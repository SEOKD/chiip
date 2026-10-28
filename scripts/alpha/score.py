"""알파 잠재력 점수 (마스터 지시 2026-10-28, config/alpha.yaml) — '텐배거 가능성' 10점 만점

판단(모델, 스킬 tenbagger-card '알파 점수')은 knowledge/models/alpha/judgments/YYYYMMDD.csv
(열 id,component,score,reason,evidence)에 쓴다. 날짜 파일이 여러 개면 (종목, 요소)마다 가장 최근 판단을 쓴다 —
주 1회 전체, 실적 후엔 그 종목만 고쳐도 된다.
합성: 있는 요소의 가중 평균(가중치 재정규화), 요소 min_components개 미만이면 미산정.
결과: knowledge/models/alpha/latest.json — 어닝 캘린더(radar/markets/earnings_calendar.py)가 5.0 이상만 보낸다.
사용: py scripts/alpha/score.py --finalize | --show
"""
import argparse
import csv
import json
import sys
from datetime import date, datetime
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
DIR = ROOT / "knowledge" / "models" / "alpha"
LATEST = DIR / "latest.json"
COLS = ["id", "component", "score", "reason", "evidence"]


def cfg():
    return yaml.safe_load((ROOT / "config" / "alpha.yaml").read_text(encoding="utf-8"))


def names():
    out = {}
    val = yaml.safe_load((ROOT / "config" / "valuation.yaml").read_text(encoding="utf-8"))
    ew = yaml.safe_load((ROOT / "config" / "earnings_watch.yaml").read_text(encoding="utf-8"))
    for u in val.get("universe", []) + (ew.get("extra") or []):
        out[u["id"]] = u["name"]
    return out


def load_judgments():
    """{id: {component: {score, reason, evidence, day}}} — 날짜순으로 덮어써 최신만 남김"""
    out = {}
    for f in sorted((DIR / "judgments").glob("*.csv")):
        day = f.stem
        with f.open(encoding="utf-8", newline="") as fh:
            for r in csv.DictReader(fh):
                try:
                    s = float(r["score"])
                except (TypeError, ValueError):
                    continue
                out.setdefault(r["id"], {})[r["component"]] = {"score": max(0.0, min(10.0, s)), "reason": r.get("reason", ""),
                                                               "evidence": r.get("evidence", ""), "day": day}
    return out


def combine(judg, c):
    w = c["weights"]
    rows = {}
    for cid, comps in judg.items():
        have = {k: v for k, v in comps.items() if k in w}
        total = None
        if len(have) >= int(c.get("min_components", 2)):
            ws = sum(w[k] for k in have)
            total = round(sum(w[k] * v["score"] for k, v in have.items()) / ws, 2)
        rows[cid] = {"total": total, "scored_on": max(v["day"] for v in comps.values()),
                     "components": {k: v["score"] for k, v in have.items()}}
    return rows


def finalize():
    c = cfg()
    prev = json.loads(LATEST.read_text(encoding="utf-8")) if LATEST.exists() else {"rows": {}}
    rows = combine(load_judgments(), c)
    nm = names()
    for cid, r in rows.items():
        r["name"] = nm.get(cid, cid)
        p = (prev.get("rows") or {}).get(cid, {}).get("total")
        r["delta"] = None if p is None or r["total"] is None else round(r["total"] - p, 2)
    th = float(c["threshold"])
    out = {"as_of": date.today().isoformat(), "threshold": th, "rows": rows,
           "pass": sorted(k for k, r in rows.items() if r["total"] is not None and r["total"] >= th)}
    DIR.mkdir(parents=True, exist_ok=True)
    LATEST.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    return out


def load_latest(today=None):
    """{id: total} 중 기준 이상·신선한 것, 그리고 전체 rows. 파일 없으면 ({}, {})"""
    if not LATEST.exists():
        return {}, {}
    data = json.loads(LATEST.read_text(encoding="utf-8"))
    c = cfg()
    today = today or date.today()
    fresh = {}
    for cid, r in data.get("rows", {}).items():
        try:
            age = (today - datetime.strptime(r["scored_on"][:8], "%Y%m%d").date()).days   # 20261028_sa 같은 같은 날 보정 파일 허용
        except (KeyError, ValueError):
            continue
        if r.get("total") is not None and age <= int(c.get("stale_days", 14)):
            fresh[cid] = r["total"]
    return {k: v for k, v in fresh.items() if v >= float(c["threshold"])}, data.get("rows", {})


def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument("--finalize", action="store_true")
    ap.add_argument("--show", action="store_true")
    a = ap.parse_args(argv)
    data = finalize() if a.finalize else json.loads(LATEST.read_text(encoding="utf-8"))
    rows = sorted(data["rows"].items(), key=lambda kv: -(kv[1]["total"] or -1))
    print(f"[알파 잠재력] {data['as_of']} 기준 {data['threshold']:.1f} 이상 {len(data['pass'])}/{len(rows)}종목")
    for cid, r in rows:
        t = "미산정" if r["total"] is None else f"{r['total']:.1f}"
        d = "" if r.get("delta") is None else f" ({r['delta']:+.1f})"
        print(f"- {r['name']} {t}{d}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
