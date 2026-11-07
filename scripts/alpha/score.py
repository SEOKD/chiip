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
    disc = yaml.safe_load((ROOT / "config" / "discovery.yaml").read_text(encoding="utf-8")) or {}
    for t in disc.get("themes") or []:   # 발굴 후보·TradingView 와치리스트 종목도 알파 점수 대상(2026-10-31 마스터 지시)
        for c in t.get("candidates") or []:
            out.setdefault(c["id"], c.get("name"))
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


def social_rows():
    """커뮤니티 관심 급증 모델의 attention 요소(radar/social_surge.py, 마스터 지시 2026-11-07 "이 변수는 알파 점수를 매기는 데도 활용")"""
    p = ROOT / "knowledge" / "models" / "social" / "latest.json"
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    sc = yaml.safe_load((ROOT / "config" / "social_surge.yaml").read_text(encoding="utf-8"))["alpha"]
    try:
        age = (date.today() - datetime.fromisoformat(d["as_of"]).date()).days
    except (KeyError, ValueError):
        return {}
    if age > sc["stale_days"]:
        return {}
    day = datetime.fromisoformat(d["as_of"]).strftime("%Y%m%d")
    return {k: {"score": v["attention"], "day": day} for k, v in (d.get("rows") or {}).items() if v.get("attention") is not None}


def combine(judg, c, social=None):
    w = c["weights"]
    rows = {}
    social = social_rows() if social is None else social
    for cid, comps in judg.items():
        have = {k: v for k, v in comps.items() if k in w and k != "attention"}
        total = None
        if len(have) >= int(c.get("min_components", 2)):   # 판단 요소가 충분할 때만 — 관심 요소만으로는 산정하지 않는다
            if cid in social and "attention" in w:
                have["attention"] = social[cid]
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
    if a.finalize:   # 알파 v2 병행 기록(ADR-016 — 전환 전 2주, 게이트는 이 v1 그대로)
        try:
            import v2
            v2.run()
        except Exception as e:   # v2 실패가 v1 산정을 막지 않는다
            print(f"[알파 v2 병행 기록 실패] {e}")
    rows = sorted(data["rows"].items(), key=lambda kv: -(kv[1]["total"] or -1))
    print(f"[알파 잠재력] {data['as_of']} 기준 {data['threshold']:.1f} 이상 {len(data['pass'])}/{len(rows)}종목")
    for cid, r in rows:
        t = "미산정" if r["total"] is None else f"{r['total']:.1f}"
        d = "" if r.get("delta") is None else f" ({r['delta']:+.1f})"
        print(f"- {r['name']} {t}{d}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
