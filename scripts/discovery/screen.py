"""Chiip Ten-bagger Discovery 선별 — IB 리서치 하우스식 단계 관문으로 후보를 줄인다 (마스터 지시 2026-10-29, 방법 knowledge/methods/discovery_ib_process.md).

입력: config/discovery.yaml(테마·후보·edge·가중치) · knowledge/models/discovery/attention_latest.json(radar/attention.py)
      · knowledge/models/discovery/fundamentals.json(주간 회차에 모델이 easyconomics company_profile로 채움:
        {id: {"as_of","mcap_usd","rev_growth","op_margin","ev_sales","n_analysts","source"}}) · config/coverage.yaml
단계: ① 아이디어(테마 지도 전부) → ② 선별(점수 ≥ 6.0, edge ≥ 6, 펀더멘털 확보) → ③ 심층 대기열(선별 통과·미커버 상위 3) →
      ④ 위원회 메모(모델이 템플릿으로 작성) → ⑤ 커버리지 편입(--promote) — 편입되면 원문 팔로업·실적·텐배거 리포트 대기열에 자동 연결.
출력: outputs/discovery/<YYYYMMDD>.md(순위·구성 점수·단계·빠진 자료). 점수는 판단 보조 — 매수 권유 아님.
사용: py scripts/discovery/screen.py            · py scripts/discovery/screen.py --promote <id> [--stage focus|bench] [--memo <경로>]
"""
import json
import sys
from datetime import date
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
DISC = ROOT / "knowledge" / "models" / "discovery"
OUTD = ROOT / "outputs" / "discovery"
QUEUE = ROOT / "knowledge" / "models" / "tenbagger" / "report_queue.txt"


def _y(p):
    f = ROOT / p
    return (yaml.safe_load(f.read_text(encoding="utf-8")) or {}) if f.exists() else {}


def _j(p):
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}


def lin(x, x0, y0, x1, y1):
    if x is None:
        return None
    t = max(0.0, min(1.0, (x - x0) / (x1 - x0)))
    return y0 + (y1 - y0) * t


def components(c, fund, att, theme_val, caps, fx_ok=True):
    f, a = fund.get(c["id"]) or {}, att.get(c["id"]) or {}
    comp = {"edge": float(c.get("edge") or 5)}
    comp["growth"] = lin(f.get("rev_growth"), 0.0, 2.0, 0.6, 10.0)
    n = f.get("n_analysts")
    comp["coverage_gap"] = None if n is None else (10.0 if n <= 3 else lin(n, 3, 10.0, 20, 1.0))
    comp["attention_accel"] = lin(a.get("accel"), 0.5, 2.0, 3.0, 10.0)
    comp["crowding"] = None if a.get("crowding_pct") is None else a["crowding_pct"] / 10.0
    comp["valuation"] = theme_val.get(c["id"])
    m, lo, hi = f.get("mcap_usd"), caps.get("min_usd", 1e8), caps.get("max_usd", 3e9)
    comp["size_fit"] = None if m is None else (10.0 if lo <= m <= hi else 5.0 if hi < m <= 3 * hi else 3.0 if m < lo else 2.0)
    return comp


def theme_valuation(themes, fund):
    """같은 테마 안 EV/매출 ÷ 성장(성장 5% 하한) 순위 → 싼 쪽 10점"""
    out = {}
    for t in themes:
        pts = []
        for c in t.get("candidates") or []:
            f = fund.get(c["id"]) or {}
            if f.get("ev_sales") and f.get("rev_growth") is not None:
                pts.append((c["id"], f["ev_sales"] / max(f["rev_growth"], 0.05)))
        pts.sort(key=lambda x: x[1])
        for i, (cid, _) in enumerate(pts):
            out[cid] = 10.0 - 8.0 * i / max(1, len(pts) - 1)
    return out


def score(comp, w):
    tot, wsum, missing = 0.0, 0.0, []
    for k, wt in w.items():
        v = comp.get(k)
        if v is None:
            missing.append(k)
            v = 5.0   # 자료 없음 → 중립(빠진 자료로 표시)
        tot += wt * v
        wsum += abs(wt) if wt > 0 else 0
    return round(tot / wsum, 2) if wsum else None, missing


def run(today=None):
    today = today or date.today()
    cfg = _y("config/discovery.yaml")
    cov = {c["id"]: c for c in (_y("config/coverage.yaml").get("companies") or [])}
    caps = ((_y("config/tenbagger.yaml").get("universe") or {}).get("market_cap") or {}).get("US") or {}
    fund = _j(DISC / "fundamentals.json")
    att = (_j(DISC / "attention_latest.json") or {}).get("rows") or {}
    tv = theme_valuation(cfg.get("themes") or [], fund)
    w = cfg.get("scoring") or {}
    rows = []
    for t in cfg.get("themes") or []:
        for c in t.get("candidates") or []:
            comp = components(c, fund, att, tv, caps)
            s, missing = score(comp, w)
            stage = "⑤ 커버리지" if c["id"] in cov else ("② 선별 통과" if s and s >= 6.0 and comp["edge"] >= 6 and c["id"] in fund else "① 아이디어")
            rows.append({"id": c["id"], "name": c["name"], "market": c.get("market"), "code": c.get("code"), "theme": t["name"], "score": s,
                         "comp": comp, "missing": missing, "stage": stage, "why": c.get("why", "")})
    rows.sort(key=lambda r: -(r["score"] or 0))
    deep = [r for r in rows if r["stage"] == "② 선별 통과"][:3]
    for r in deep:
        r["stage"] = "③ 심층 대기열"
    OUTD.mkdir(parents=True, exist_ok=True)
    f = lambda v: "-" if v is None else f"{v:.1f}"
    L = [f"# Chiip Ten-bagger Discovery 선별 {today.isoformat()}", "",
         f"펀더멘털 확보 {sum(1 for r in rows if r['id'] in fund)}/{len(rows)} · 관심도 {len(att)}/{len(rows)} · 커버리지 {len(cov)}", "",
         "| 순위 | 종목 | 시장·코드 | 테마 | 점수 | edge | 성장 | 커버 공백 | 관심 가속 | 쏠림 | 밸류 | 규모 | 단계 | 빠진 자료 |", "|" + "---|" * 14]
    for i, r in enumerate(rows, 1):
        c = r["comp"]
        L.append(f"| {i} | {r['name']} | {r['market']} {r['code']} | {r['theme']} | **{f(r['score'])}** | {f(c['edge'])} | {f(c['growth'])} | {f(c['coverage_gap'])} | "
                 f"{f(c['attention_accel'])} | {f(c['crowding'])} | {f(c['valuation'])} | {f(c['size_fit'])} | {r['stage']} | {', '.join(r['missing']) or '-'} |")
    L += ["", "## 심층 대기열(위원회 메모 작성 대상)"] + [f"- {r['name']}({r['market']} {r['code']}) — {r['why']}" for r in deep] + \
         ["", "점수는 판단 보조(가중치 config/discovery.yaml scoring — 성과로 피팅). 연구 후보이지 매수 권유 아님."]
    path = OUTD / f"{today.strftime('%Y%m%d')}.md"
    path.write_text("\n".join(L), encoding="utf-8")
    return rows, path


def promote(cid, stage="focus", memo=None, today=None):
    """커버리지 편입 — config/coverage.yaml에 추가하고 텐배거 리포트 대기열 맨 뒤에 넣는다"""
    today = today or date.today()
    cfg = _y("config/discovery.yaml")
    c = next((x for t in cfg.get("themes") or [] for x in t.get("candidates") or [] if x["id"] == cid), None)
    if not c:
        raise SystemExit(f"후보 없음: {cid}")
    p = ROOT / "config" / "coverage.yaml"
    d = _y("config/coverage.yaml")
    comps = d.get("companies") or []
    if any(x["id"] == cid for x in comps):
        return False
    comps.append({"id": cid, "name": c["name"], "market": c.get("market"), "code": str(c.get("code")), "stage": stage, "since": today.isoformat(),
                  "memo": memo or ""})
    head = "".join(l + "\n" for l in p.read_text(encoding="utf-8").splitlines() if l.startswith("#")) if p.exists() else ""
    p.write_text(head + yaml.safe_dump({"companies": comps}, allow_unicode=True, sort_keys=False), encoding="utf-8")
    QUEUE.parent.mkdir(parents=True, exist_ok=True)
    q = QUEUE.read_text(encoding="utf-8").splitlines() if QUEUE.exists() else []
    if cid not in q:
        QUEUE.write_text("\n".join(q + [cid]) + "\n", encoding="utf-8")
    return True


def main(argv):
    sys.stdout.reconfigure(encoding="utf-8")
    if argv and argv[0] == "--promote":
        stage = argv[argv.index("--stage") + 1] if "--stage" in argv else "focus"
        memo = argv[argv.index("--memo") + 1] if "--memo" in argv else None
        print("편입" if promote(argv[1], stage, memo) else "이미 커버리지")
        return 0
    rows, path = run()
    print(f"[발굴] {path.relative_to(ROOT).as_posix()} · 상위: " + ", ".join(f"{r['name']} {r['score']}" for r in rows[:5]))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
