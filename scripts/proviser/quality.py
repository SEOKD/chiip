"""Chiip proviser 품질 점수 — 기능별 산출물 품질을 10점 만점 소수 첫째 자리로 (마스터 지시 2026-10-29)

점수 = (1 − w) × 루브릭 + w × 성과 지표(KPI) 점수
  루브릭 = 축 A~E(각 0.0~2.0, 0.1 단위 — 프로바이저 판단) 합 − 운영 결함(최대 1.5)
  KPI = 로그에서 결정론으로 계산한 산출물 성과(놓친 사건·재발송·브라이어·채택률·데이터 검증 점수 …), floor~target 선형 0~10
  w = kpi_max_weight × N / (N + k) — 뷸만 신뢰도(Bühlmann 1967): 성과 관측 N이 적을수록 판단 쪽으로 당긴다
설정 config/proviser.yaml. 판단(루브릭)은 모델, 숫자는 이 스크립트.

사용:
  py scripts/proviser/quality.py --kpi [<taskId>]                   — 성과 지표만
  py scripts/proviser/quality.py --score <taskId> A B C D E ops [samples] [thinking reasoning system] [--write]
      → 최종 점수(소수 1자리)·전일 대비·7일 이동 평균. --write면 docs/proviser/scores.csv에 한 행 추가
"""
import csv
import json
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
SCORES = ROOT / "docs" / "proviser" / "scores.csv"
COLS = ["date", "task", "samples", "A", "B", "C", "D", "E", "ops", "score", "below9", "directives", "thinking", "reasoning", "system",
        "delta", "trend7", "rubric", "kpi", "kpi_w"]


def cfg():
    return yaml.safe_load((ROOT / "config" / "proviser.yaml").read_text(encoding="utf-8")) or {}


def _rows(rel):
    p = ROOT / rel
    if not p.exists():
        return []
    with p.open(encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def _d(s):
    try:
        return date.fromisoformat(str(s)[:10])
    except ValueError:
        return None


def lin(x, floor, target):
    """floor → 0점, target → 10점 선형(방향은 두 값의 순서로), 범위 밖은 자른다"""
    if x is None or floor == target:
        return None
    t = (x - floor) / (target - floor)
    return round(10 * max(0.0, min(1.0, t)), 2)


# ---------- 성과 지표 (값, 관측 수) ----------
def radar_misses_7d(today):
    rows = [r for r in _rows("evals/radar_misses.csv") if (_d(r.get("date_seen")) or date.min) >= today - timedelta(days=6)]
    return len(rows), 7   # 관측 단위 = 7일(놓친 사건 0도 정보다)


def dup_send_rate_7d(today):
    rows = [r for r in _rows("outputs/article/sources/log.csv") if (_d(r.get("date")) or date.min) >= today - timedelta(days=6)]
    urls = [r.get("url") for r in rows if r.get("url")]
    return ((len(urls) - len(set(urls))) / len(urls) if urls else None), len(urls)


def _preds(origins=None):
    out = []
    for r in _rows("knowledge/predictions.csv"):
        if r.get("outcome") not in ("1", "0", "true", "false") or not r.get("probability"):
            continue
        if origins and not any(o in (r.get("origin") or "") for o in origins):
            continue
        try:
            out.append((float(r["probability"]), 1.0 if r["outcome"] in ("1", "true") else 0.0))
        except ValueError:
            continue
    return out


def brier_of(origins):
    ps = _preds(origins)
    return (sum((p - o) ** 2 for p, o in ps) / len(ps) if ps else None), len(ps)


def brier_skill_all(_today=None):
    """BSS = 1 − B ÷ B_ref, B_ref = 늘 기저 적중률을 말하는 예측의 브라이어(기후값 기준선)"""
    ps = _preds()
    if len(ps) < 2:
        return None, len(ps)
    base = sum(o for _, o in ps) / len(ps)
    b = sum((p - o) ** 2 for p, o in ps) / len(ps)
    ref = sum((base - o) ** 2 for _, o in ps) / len(ps)
    return (1 - b / ref if ref > 0 else None), len(ps)


def pitch_adoption_30d(today):
    rows = [r for r in _rows("outputs/article/pitch/log.csv") if (_d(r.get("date")) or date.min) >= today - timedelta(days=29)]
    if not rows:
        return None, 0
    yes = sum(1 for r in rows if str(r.get("adopted", "")).strip().lower() in ("adopted", "y", "yes", "1", "true", "채택"))
    return yes / len(rows), len(rows)


def datapack_score_7d(today):
    sys.path.insert(0, str(ROOT / "scripts" / "valuation" / "v2"))
    import datapack_check
    vals = []
    for r in _rows("outputs/tenbagger/reports/log.csv"):
        if (_d(r.get("date")) or date.min) < today - timedelta(days=6):
            continue
        try:
            vals.append(datapack_check.check(datapack_check.load(r["id"]))["score"])
        except (OSError, KeyError, ValueError, json.JSONDecodeError):
            continue
    return (sum(vals) / len(vals) if vals else None), len(vals)


def lab_validation_rate(_today=None):
    reg = yaml.safe_load((ROOT / "knowledge" / "models" / "params" / "registry.yaml").read_text(encoding="utf-8")) or {}
    log = _rows("knowledge/models/params/changelog.csv")
    touched = {r["param_id"] for r in log}
    prop = [p for p in reg.get("params") or [] if p.get("status") == "proposed" or p["id"] in touched]
    if not prop:
        return None, 0
    done = [p for p in prop if p.get("status") in ("fitted", "adopted", "retired")]
    return len(done) / len(prop), len(prop)


def portfolio_freshness_days(today):
    ds = [_d(r.get("date")) for r in _rows("knowledge/models/portfolio/coverage.csv")]
    ds = [d for d in ds if d]
    return ((today - max(ds)).days if ds else None), (1 if ds else 0)


def kpi_value(kid, task, today):
    c = cfg()
    if kid.startswith("brier_") and kid != "brier_skill_all":
        return brier_of((c.get("prediction_origins") or {}).get(task))
    fn = globals().get(kid)
    return fn(today) if fn else (None, 0)


def kpis(task, today=None):
    """[(id, 값, 점수 0~10 또는 None, 관측 수)], 합성 점수(관측 수 가중), 총 관측 수"""
    today = today or date.today()
    spec = ((cfg().get("systems") or {}).get(task) or {}).get("kpis") or []
    out = []
    for k in spec:
        v, n = kpi_value(k["id"], task, today)
        out.append({"id": k["id"], "value": v, "score": lin(v, k["floor"], k["target"]), "n": n, "note": k.get("note", "")})
    used = [k for k in out if k["score"] is not None and k["n"]]
    N = sum(k["n"] for k in used)
    comp = round(sum(k["score"] * k["n"] for k in used) / N, 2) if N else None
    return out, comp, N


def final_score(axes, ops, kpi_comp, N, c=None):
    """(최종, 루브릭, KPI 가중) — 소수 첫째 자리"""
    c = (c or cfg()).get("scoring") or {}
    step = float(c.get("axis_step", 0.1))
    axes = [min(2.0, max(0.0, round(round(a / step) * step, 2))) for a in axes]
    rubric = max(0.0, sum(axes) - min(float(c.get("ops_max", 1.5)), abs(ops)))
    w = 0.0 if kpi_comp is None else float(c.get("kpi_max_weight", 0.4)) * N / (N + float(c.get("credibility_k", 20)))
    score = (1 - w) * rubric + w * (kpi_comp or 0.0)
    return round(score, int(c.get("decimals", 1))), round(rubric, 2), round(w, 3)


def history(task):
    return [r for r in _rows("docs/proviser/scores.csv") if r.get("task") == task and r.get("score") not in (None, "")]


def delta_trend(task, score, today):
    h = [r for r in history(task) if r["date"] < today.isoformat()]
    prev = float(h[-1]["score"]) if h else None
    last7 = [float(r["score"]) for r in h if _d(r["date"]) and _d(r["date"]) > today - timedelta(days=7)] + [score]
    return (round(score - prev, 1) if prev is not None else None), round(sum(last7) / len(last7), 1)


def write_row(row):
    new = not SCORES.exists()
    with SCORES.open(encoding="utf-8", newline="") as f:
        head = next(csv.reader(f), COLS) if not new else COLS
    if head != COLS:   # 예전 머리행(17열) → 새 열을 덧붙인 머리행으로 한 번 옮긴다
        rows = _rows("docs/proviser/scores.csv")
        with SCORES.open("w", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=COLS)
            w.writeheader()
            for r in rows:
                w.writerow({k: r.get(k, "") for k in COLS})
    with SCORES.open("a", encoding="utf-8", newline="") as f:
        csv.DictWriter(f, fieldnames=COLS).writerow({k: row.get(k, "") for k in COLS})


def main(argv):
    sys.stdout.reconfigure(encoding="utf-8")
    today = date.today()
    if argv and argv[0] == "--kpi":
        tasks = argv[1:] or list((cfg().get("systems") or {}).keys())
        for t in tasks:
            out, comp, N = kpis(t, today)
            print(f"[{t}] KPI 합성 {comp if comp is not None else '-'} (관측 {N})")
            for k in out:
                print(f"  · {k['id']}: 값 {k['value'] if k['value'] is not None else '없음'} → {k['score'] if k['score'] is not None else '-'}점 (n={k['n']}) — {k['note']}")
        return 0
    if argv and argv[0] == "--score":
        task, nums = argv[1], [a for a in argv[2:] if a != "--write" and not a.startswith("dir=")]
        ndir = next((a[4:] for a in argv if a.startswith("dir=")), "")   # 새 지시 수(dir=3)
        axes, ops = [float(x) for x in nums[:5]], float(nums[5])
        samples = nums[6] if len(nums) > 6 else ""
        layers = nums[7:10] if len(nums) >= 10 else ["", "", ""]
        out, comp, N = kpis(task, today)
        score, rubric, w = final_score(axes, ops, comp, N)
        delta, trend = delta_trend(task, score, today)
        print(f"[{task}] 점수 {score:.1f} = (1−{w}) × 루브릭 {rubric} + {w} × KPI {comp if comp is not None else '-'} · 전일 대비 "
              f"{'기준선' if delta is None else f'{delta:+.1f}'} · 7일 평균 {trend:.1f}")
        if "--write" in argv:
            write_row({"date": today.isoformat(), "task": task, "samples": samples, "A": axes[0], "B": axes[1], "C": axes[2], "D": axes[3],
                       "E": axes[4], "ops": -abs(ops), "score": f"{score:.1f}", "below9": int(score < float((cfg().get('scoring') or {}).get('target', 9.0))),
                       "directives": ndir,
                       "thinking": layers[0], "reasoning": layers[1], "system": layers[2],
                       "delta": "기준선" if delta is None else f"{delta:+.1f}", "trend7": f"{trend:.1f}",
                       "rubric": rubric, "kpi": "" if comp is None else comp, "kpi_w": w})
        return 0
    print(__doc__)
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
