"""포커스 종목 점수 (BUILD_PROMPT §21.13, config/focus.yaml) — 10점 만점, 매일 갱신·변화 표기

흐름(예약 작업 chiip-focus-score, 매일 06:40 KST):
  1) --prepare   : 밸류에이션 엔진 재계산 + 관심도 집계로 요소별 계산 점수(0~10) → prepared/YYYYMMDD.json, 판단 대상 목록 출력
  2) 모델(스킬 focus-score): 비어 있거나 맥락이 필요한 요소에 판단 점수·이유 → judgments/YYYYMMDD.csv
  3) --finalize  : 계산+판단 합성 → scores/YYYYMMDD.csv, latest.json(포커스 목록, 수집 관문이 읽음), 전일 대비 변화
  4) --send      : 텔레그램으로 점수표 발송
숫자 계산은 이 스크립트, 판단 점수는 모델 — 판단 점수는 출력에서 '판'으로 구분한다.
사용: py scripts/focus/score.py --prepare | --finalize [--send] | --digest
"""
import argparse
import csv
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "radar"))
sys.path.insert(0, str(ROOT / "scripts" / "valuation"))
from pollers import common, gate  # noqa: E402

DIR = ROOT / "knowledge" / "models" / "focus"
COMPONENTS = ("attention", "narrative", "fundamental", "multiple")
LABEL = {"attention": "관심", "narrative": "내러티브", "fundamental": "펀더룸", "multiple": "멀티플"}
JUDG_COLS = ["id", "component", "score", "reason", "evidence"]


def cfg():
    return common.load_yaml("config/focus.yaml") or {}


def pct_rank(values):
    """None 제외 백분위(0~1). 값이 하나뿐이거나 모두 같으면 0.5"""
    xs = sorted(v for v in values.values() if v is not None)
    out = {}
    for k, v in values.items():
        if v is None or not xs:
            out[k] = None
            continue
        lo = sum(1 for x in xs if x < v)
        eq = sum(1 for x in xs if x == v)
        out[k] = 0.5 if len(xs) == 1 or eq == len(xs) else (lo + 0.5 * (eq - 1)) / (len(xs) - 1)
    return out


def _abs(x):
    return None if x is None else abs(x)


def _mean(xs):
    xs = [x for x in xs if x is not None]
    return sum(xs) / len(xs) if xs else None


def quant_components(rows, mentions):
    """rows: 밸류에이션 엔진 행(id별), mentions: 7일 언급 수 → {id: {component: 0~10 또는 None}}, 근거"""
    ids = [r["id"] for r in rows]
    by = {r["id"]: r for r in rows}

    def pr(fn):
        return pct_rank({i: fn(by[i]) for i in ids})
    p_mention = (pct_rank({i: float(mentions.get(i, 0)) for i in ids}) if any(mentions.get(i) for i in ids)
                 else {i: None for i in ids})  # 언급 집계가 비면 관심도는 계산하지 않음(모델 판단)
    p_move = pr(lambda r: _abs(r.get("ret30")))
    p_heat = pr(lambda r: r.get("narrative_heat"))
    p_rev30 = pr(lambda r: _abs(r.get("rev_ntm_30")))
    p_rev90 = pr(lambda r: _abs(r.get("rev_ntm_90")))
    p_gap = pr(lambda r: _abs(r.get("implied_growth_gap")))
    p_skew = pr(lambda r: None if r.get("skew") is None else abs(r["skew"] - 1))
    p_prem = pr(lambda r: _abs(r.get("peer_premium")))
    p_resid = pr(lambda r: _abs(r.get("residual_z")))
    p_hist = pr(lambda r: None if r.get("pe_hist_pct") is None else abs(r["pe_hist_pct"] - 0.5))
    out = {}
    for i in ids:
        att = _mean([p_mention[i], p_move[i]]) if p_mention[i] is None or p_move[i] is None             else 0.7 * p_mention[i] + 0.3 * p_move[i]
        heat = p_heat[i] if (by[i].get("narrative_heat") or 0) > 0 else (0.0 if p_heat[i] is not None else None)
        fund = _mean([p_rev30[i], p_rev90[i], p_gap[i], p_skew[i]])
        mult = _mean([p_prem[i], p_resid[i], p_hist[i]])
        out[i] = {c: (None if v is None else round(10 * v, 1))
                  for c, v in zip(COMPONENTS, (att, heat, fund, mult))}
        out[i]["_evidence"] = {"mentions7": mentions.get(i, 0), "ret30": by[i].get("ret30"),
                               "narrative_heat": by[i].get("narrative_heat"), "top_narratives": by[i].get("top_narratives"),
                               "rev_ntm_30": by[i].get("rev_ntm_30"), "implied_growth_gap": by[i].get("implied_growth_gap"),
                               "peer_premium": by[i].get("peer_premium"), "residual_z": by[i].get("residual_z")}
    return out


def inbox_mentions(days=7):
    """레이더 inbox(관문 도입 전 저장분 포함)를 현재 별칭으로 다시 매칭해 센 언급 수 — 관문 집계가 쌓이기 전 보강용"""
    import engine
    out = {}
    for _, it in engine.inbox_items(days, common.now_kst().date()):
        for e in set(common.match_entities(f"{it.get('title', '')} {it.get('snippet', '')}")) | set(it.get("entities_matched") or []):
            out[e] = out.get(e, 0) + 1
    return out


def merged_mentions(days=7):
    a, b = gate.mentions(days), inbox_mentions(days)
    return {k: max(a.get(k, 0), b.get(k, 0)) for k in set(a) | set(b)}


def _today():
    return common.now_kst().strftime("%Y%m%d")


def prepare(day=None):
    import engine
    engine.compute()
    val = engine.load_latest() or {"rows": []}
    rows = val["rows"]
    q = quant_components(rows, merged_mentions(7))
    day = day or _today()
    out = {"as_of": common.iso(common.now_kst()), "coverage": val.get("coverage"),
           "rows": [{"id": r["id"], "name": r["name"], "sub": r["sub"], "region": r["region"], **q[r["id"]]} for r in rows]}
    (DIR / "prepared").mkdir(parents=True, exist_ok=True)
    (DIR / "prepared" / f"{day}.json").write_text(json.dumps(out, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    jf = DIR / "judgments" / f"{day}.csv"
    if not jf.exists():
        jf.parent.mkdir(parents=True, exist_ok=True)
        jf.write_text(",".join(JUDG_COLS) + "\n", encoding="utf-8")
    return out


def load_judgments(day):
    jf = DIR / "judgments" / f"{day}.csv"
    if not jf.exists():
        return {}
    out = {}
    with jf.open(encoding="utf-8", newline="") as f:
        for r in csv.DictReader(f):
            try:
                s = max(0.0, min(10.0, float(r["score"])))
            except (TypeError, ValueError):
                continue
            if r.get("component") in COMPONENTS:
                out.setdefault(r["id"], {})[r["component"]] = {"score": s, "reason": r.get("reason", "")}
    return out


def previous_scores(day):
    files = sorted(p for p in (DIR / "scores").glob("*.csv") if p.stem < day) if (DIR / "scores").exists() else []
    if not files:
        return {}, None
    with files[-1].open(encoding="utf-8", newline="") as f:
        return {r["id"]: r for r in csv.DictReader(f)}, files[-1].stem


def combine(prepared, judg, prev, c):
    w = c.get("weights") or {k: 0.25 for k in COMPONENTS}
    th, need = float(c.get("threshold", 5.0)), int(c.get("min_components", 2))
    rows = []
    for r in prepared["rows"]:
        comp, src = {}, {}
        for k in COMPONENTS:
            j = judg.get(r["id"], {}).get(k)
            if j is not None:  # 모델이 계산값을 검토하고 매긴 판단 점수가 우선
                comp[k], src[k] = j["score"], "판단"
            elif r.get(k) is not None:
                comp[k], src[k] = r[k], "계산"
        have = [k for k in COMPONENTS if k in comp]
        total = round(sum(comp[k] * w[k] for k in have) / sum(w[k] for k in have), 2) if len(have) >= need else None
        p = prev.get(r["id"]) or {}
        try:
            ptot = float(p["total"]) if p.get("total") not in (None, "") else None
        except ValueError:
            ptot = None
        rows.append({"id": r["id"], "name": r["name"], "sub": r["sub"], "total": total,
                     "delta": None if total is None or ptot is None else round(total - ptot, 2),
                     "prev_total": ptot, **{k: comp.get(k) for k in COMPONENTS},
                     "sources": ";".join(f"{k}={src[k]}" for k in have),
                     "focus": total is not None and total >= th,
                     "reasons": " / ".join(f"{LABEL[k]}: {judg[r['id']][k]['reason']}" for k in COMPONENTS
                                          if judg.get(r["id"], {}).get(k) and judg[r["id"]][k]["reason"])})
    rows.sort(key=lambda x: (x["total"] is None, -(x["total"] or 0)))
    return rows


SCORE_COLS = ["id", "name", "sub", "total", "delta", "prev_total", *COMPONENTS, "sources", "focus", "reasons"]


def finalize(day=None):
    day = day or _today()
    pf = DIR / "prepared" / f"{day}.json"
    prepared = json.loads(pf.read_text(encoding="utf-8")) if pf.exists() else prepare(day)
    c = cfg()
    prev, prev_day = previous_scores(day)
    rows = combine(prepared, load_judgments(day), prev, c)
    (DIR / "scores").mkdir(parents=True, exist_ok=True)
    with (DIR / "scores" / f"{day}.csv").open("w", encoding="utf-8", newline="") as f:
        wr = csv.DictWriter(f, fieldnames=SCORE_COLS, lineterminator="\n")
        wr.writeheader()
        wr.writerows(rows)
    focus = [r["id"] for r in rows if r["focus"]]
    prev_focus = {i for i, r in prev.items() if str(r.get("focus")) == "True"}
    latest = {"as_of": common.iso(common.now_kst()), "day": day, "prev_day": prev_day,
              "threshold": c.get("threshold", 5.0), "focus": focus,
              "entered": sorted(set(focus) - prev_focus) if prev_day else [],
              "exited": sorted(prev_focus - set(focus)) if prev_day else [],
              "unscored": [r["id"] for r in rows if r["total"] is None], "rows": rows}
    (DIR / "latest.json").write_text(json.dumps(latest, ensure_ascii=False, indent=1), encoding="utf-8")
    return latest


def _fmt(x, nd=1):
    return "—" if x is None else f"{x:.{nd}f}"


def digest(latest=None, near=5):
    latest = latest or json.loads((DIR / "latest.json").read_text(encoding="utf-8"))
    th = float(latest.get("threshold", 5.0))
    names = {r["id"]: r["name"] for r in latest["rows"]}
    lines = [f"[포커스 점수 {latest['day'][4:6]}/{latest['day'][6:]}] 기준 {th:.1f} · 추적 {len(latest['focus'])}종목"
             + (f" (전일 {latest['prev_day'][4:6]}/{latest['prev_day'][6:]} 대비)" if latest.get("prev_day") else " (첫 산정)")]
    if latest.get("entered"):
        lines.append("신규 편입: " + ", ".join(names.get(i, i) for i in latest["entered"]))
    if latest.get("exited"):
        lines.append("제외: " + ", ".join(names.get(i, i) for i in latest["exited"]))
    lines.append("종목 총점(변화) | 관심·내러티브·펀더룸·멀티플 (판=모델 판단)")

    def row(r):
        d = "" if r["delta"] is None else f"({r['delta']:+.1f})"
        src = dict(s.split("=") for s in r["sources"].split(";") if "=" in s)
        parts = [_fmt(r[k]) + ("판" if src.get(k) == "판단" else "") for k in COMPONENTS]
        return f"{r['name']} {_fmt(r['total'])}{d} | {'·'.join(parts)}"
    for r in latest["rows"]:
        if r["focus"]:
            lines.append(row(r))
    below = [r for r in latest["rows"] if not r["focus"] and r["total"] is not None][:near]
    if below:
        lines.append(f"— 기준 아래 상위 {len(below)}")
        lines.extend(row(r) for r in below)
    if latest.get("unscored"):
        lines.append(f"미산정 {len(latest['unscored'])}종목(요소 부족)")
    lines.append("공개 자료 기반 분석이며 투자 권유가 아님")
    return "\n".join(lines)


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--prepare", action="store_true")
    ap.add_argument("--finalize", action="store_true")
    ap.add_argument("--send", action="store_true")
    ap.add_argument("--digest", action="store_true")
    a = ap.parse_args(argv)
    sys.stdout.reconfigure(encoding="utf-8")
    if a.prepare:
        out = prepare()
        print(f"계산 점수 준비: {len(out['rows'])}종목, 커버리지 {out['coverage']}")
        print("id | 이름 | 관심·내러티브·펀더룸·멀티플(계산, 없음=—) | 7일 언급")
        for r in out["rows"]:
            print(f"{r['id']} | {r['name']} | " + "·".join(_fmt(r[k]) for k in COMPONENTS)
                  + f" | {r['_evidence']['mentions7']}")
        print(f"판단 점수 파일: knowledge/models/focus/judgments/{_today()}.csv (열: {','.join(JUDG_COLS)})")
    if a.finalize:
        latest = finalize()
        print(f"포커스 {len(latest['focus'])}종목 / 미산정 {len(latest['unscored'])}")
    if a.digest or a.send:
        text = digest()
        print(text)
        if a.send:
            sys.path.insert(0, str(ROOT / "radar"))
            import notify
            notify.send(text, "SCORE")
    return 0


if __name__ == "__main__":
    sys.exit(main())
