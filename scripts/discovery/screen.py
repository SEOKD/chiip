"""Chiip Ten-bagger Discovery 선별 — IB 리서치 하우스식 단계 관문으로 후보를 줄인다 (마스터 지시 2026-10-29, 방법 knowledge/methods/discovery_ib_process.md).

입력: config/discovery.yaml(테마·후보·edge·가중치) · knowledge/models/discovery/attention_latest.json(radar/attention.py)
      · knowledge/models/discovery/fundamentals.json(주간 회차에 모델이 Fiscal.ai fundamentals.js → scripts/fiscal/adapter.py --fund로 채움:
        {id: {"as_of","mcap_usd","rev_growth","op_margin","ev_sales","n_analysts","source"}}) · config/coverage.yaml
단계: ① 아이디어(테마 지도 전부) → ② 선별(점수 ≥ 6.0, edge ≥ 6, 펀더멘털 확보) → ③ 심층 대기열(선별 통과·미커버 상위 DEEP_MAX) →
      ④ 위원회 메모(모델이 템플릿으로 작성) → ⑤ 커버리지 편입(--promote) — 편입되면 원문 팔로업·실적·텐배거 리포트 대기열에 자동 연결.
출력: outputs/discovery/<YYYYMMDD>.md(순위·구성 점수·단계·빠진 자료). 점수는 판단 보조 — 매수 권유 아님.
사용: py scripts/discovery/screen.py            · py scripts/discovery/screen.py --promote <id> [--stage focus|bench] [--memo <경로>]
"""
DEEP_MAX = 6   # 심층 대기열 — 2026-11-04 발굴 적극성 상향(3 → 6). 선별 관문은 그대로
import json
import sys
from datetime import date
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))
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


def components(c, fund, att, theme_val, caps, fx_ok=True, quiet=None):
    f, a = fund.get(c["id"]) or {}, att.get(c["id"]) or {}
    comp = {"edge": float(c.get("edge") or 5)}
    comp["quiet"] = (quiet or {}).get(c["id"])   # 조용한 매집형 상승 점수(scripts/discovery/quiet.py, 2026-10-29)
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


def asia_rows(fund, att, tv, caps, quiet, w, have):
    """대만·중국·홍콩 스크리너 상위(scripts/discovery/asia_screen.py → asia_candidates.json)를 '아시아 스크리너' 테마로 합류(2026-11-09).
    Fiscal.ai가 대부분 없는 시장이라 성장·시가총액은 TradingView 스크리너 값을 쓴다. edge는 미판정(5) — 병목 근거를 찾아 손으로 만든 테마로 옮길 때 적는다.
    그래서 점수가 높아도 '① 아이디어'에 머문다(선별 통과는 edge 6 이상)."""
    a = _j(DISC / "asia_candidates.json")
    out = []
    for m, rs in (a.get("markets") or {}).items():
        for r in rs:
            cid = f"asia-{r['market']}-{r['code']}"
            if cid in have:
                continue
            f = dict(fund.get(cid) or {})
            f.setdefault("rev_growth", None if r.get("outlier") or r.get("rev_growth") is None else r["rev_growth"] / 100)
            f.setdefault("mcap_usd", r.get("mcap_usd"))
            c = {"id": cid, "name": r["name"], "market": r["market"], "code": r["code"], "edge": 5}
            comp = components(c, {cid: f}, att, tv, caps, quiet=quiet)
            comp["growth"] = lin(r.get("score"), -1.5, 2.0, 2.5, 10.0)   # 절대 성장률은 이 시장 상위가 모두 상한(+60%)에 붙는다 → 시장 안 z합성(성장·가속·질·모멘텀·밸류·규모)으로 순위를 살린다
            s, missing = score(comp, w)
            why = f"아시아 스크리너 {m} z합성 {r['score']}" + (f" · 테마 {', '.join(r['themes'])}" if r.get("themes") else "") + (f" · 한국 연결 {', '.join(r['korea_link'])}" if r.get("korea_link") else "")
            out.append({"id": cid, "name": r["name"], "market": r["market"], "code": r["code"], "theme": "아시아 스크리너", "score": s,
                        "comp": comp, "missing": missing, "stage": "① 아이디어", "why": why})
    return out


def rotation_rows(fund, att, tv, caps, quiet, w, have):
    """섹터 순환 스크린 상위(scripts/discovery/sector_rotation.py → rotation_candidates.json)를 '섹터 순환: <섹터>' 테마로 합류(2026-11-13, ADR-027).
    edge는 섹터 판단 틀 카드(knowledge/models/discovery/lens_cards, --card-check 통과·90일 안)가 있을 때만 그 값, 없으면 미판정 5 → '① 아이디어'에 머문다"""
    try:
        import sector_rotation
        cands = sector_rotation.rows_for_screen(have)
    except Exception:  # noqa: BLE001 — 순환 스크린은 보조 입력이다
        return []
    out = []
    for r in cands:
        cid = r["id"]
        f = dict(fund.get(cid) or {})
        f.setdefault("rev_growth", r.get("rev_growth"))
        f.setdefault("mcap_usd", r.get("mcap_usd"))
        c = {"id": cid, "name": r["name"], "market": "us", "code": r["ticker"], "edge": r["edge"]}
        comp = components(c, {cid: f}, att, tv, caps, quiet=quiet)
        comp["growth"] = lin(r.get("z"), -1.5, 2.0, 2.5, 10.0)   # 섹터 안 z합성으로 순위를 살린다(아시아 스크리너와 같은 방식)
        s, missing = score(comp, w)
        stage = "② 선별 통과" if s and s >= 6.0 and comp["edge"] >= 6 and cid in fund else "① 아이디어"
        out.append({"id": cid, "name": r["name"], "market": "us", "code": r["ticker"], "theme": r["theme"], "score": s,
                    "comp": comp, "missing": missing, "stage": stage, "why": r["why"]})
    return out


def _cards():
    """{id: edge} — knowledge/models/discovery/lens_cards(sector_rotation.card_check 통과·90일 안)"""
    try:
        import sector_rotation
        return sector_rotation.cards()
    except Exception:  # noqa: BLE001
        return {}


def card_queue(rows, n=6):
    """판단 카드가 필요한 상위 아이디어 — edge 미판정(5)·카드 없음·성장 자료 있음·점수 5 이상, 점수순. 회차마다 1~2개씩 카드를 쓴다"""
    have = set(_cards())
    q = [r for r in rows if r["stage"] == "① 아이디어" and r["comp"].get("edge") == 5 and r["id"] not in have and (r["score"] or 0) >= 5.0
         and "growth" not in (r.get("missing") or [])]
    return q[:n]


def _diverse(rows, n):
    """점수순 n개 — AI 밖 최소 비율·같은 섹터 상한(config/sector_map.yaml quota). 섹터 지도를 못 읽으면 점수순 그대로"""
    try:
        sys.path.insert(0, str(ROOT / "scripts" / "sectors"))
        import sector_map
        return sector_map.diversify(rows, n)
    except Exception:  # noqa: BLE001 — 할당량은 보조 규칙이다. 실패해도 선별은 돈다
        return rows[:n]


def run(today=None):
    today = today or date.today()
    cfg = _y("config/discovery.yaml")
    cov = {c["id"]: c for c in (_y("config/coverage.yaml").get("companies") or [])}
    caps = ((_y("config/tenbagger.yaml").get("universe") or {}).get("market_cap") or {}).get("US") or {}
    fund = _j(DISC / "fundamentals.json")
    att = (_j(DISC / "attention_latest.json") or {}).get("rows") or {}
    tv = theme_valuation(cfg.get("themes") or [], fund)
    w = cfg.get("scoring") or {}
    quiet = {r["id"]: r.get("score") for r in (_j(DISC / "quiet_latest.json") or {}).get("rows") or []}
    rows = []
    cards = _cards()
    for t in cfg.get("themes") or []:
        for c in t.get("candidates") or []:
            if c["id"] in cards:   # 판단 카드(검사 통과·90일)가 있으면 그 edge가 지도 값보다 앞선다(2026-11-14 점검, ADR-037)
                c = {**c, "edge": cards[c["id"]], "why": f"{c.get('why', '')} → 판단 카드 edge {cards[c['id']]:.1f}".replace("— edge 미판정 →", "→")}
            comp = components(c, fund, att, tv, caps, quiet=quiet)
            s, missing = score(comp, w)
            stage = "⑤ 커버리지" if c["id"] in cov else ("② 선별 통과" if s and s >= 6.0 and comp["edge"] >= 6 and c["id"] in fund else "① 아이디어")
            rows.append({"id": c["id"], "name": c["name"], "market": c.get("market"), "code": c.get("code"), "theme": t["name"], "score": s,
                         "comp": comp, "missing": missing, "stage": stage, "why": c.get("why", "")})
    rows += asia_rows(fund, att, tv, caps, quiet, w, {r["id"] for r in rows})
    rows += rotation_rows(fund, att, tv, caps, quiet, w, {r["id"] for r in rows})
    rows.sort(key=lambda r: -(r["score"] or 0))
    deep = _diverse([r for r in rows if r["stage"] == "② 선별 통과"], DEEP_MAX)   # 섹터 할당량(2026-11-13 종목 범위 확대, ADR-025)
    for r in deep:
        r["stage"] = "③ 심층 대기열"
    OUTD.mkdir(parents=True, exist_ok=True)
    f = lambda v: "-" if v is None else f"{v:.1f}"
    L = [f"# Chiip Ten-bagger Discovery 선별 {today.isoformat()}", "",
         f"펀더멘털 확보 {sum(1 for r in rows if r['id'] in fund)}/{len(rows)} · 관심도 {len(att)}/{len(rows)} · 커버리지 {len(cov)}", "",
         "| 순위 | 종목 | 시장·코드 | 테마 | 점수 | edge | 성장 | 커버 공백 | 관심 가속 | 쏠림 | 밸류 | 규모 | 조용한 상승 | 단계 | 빠진 자료 |", "|" + "---|" * 15]
    for i, r in enumerate(rows, 1):
        c = r["comp"]
        L.append(f"| {i} | {r['name']} | {r['market']} {r['code']} | {r['theme']} | **{f(r['score'])}** | {f(c['edge'])} | {f(c['growth'])} | {f(c['coverage_gap'])} | "
                 f"{f(c['attention_accel'])} | {f(c['crowding'])} | {f(c['valuation'])} | {f(c['size_fit'])} | {f(c.get('quiet'))} | {r['stage']} | {', '.join(r['missing']) or '-'} |")
    L += ["", "## 판단 카드 대기열(edge 미판정 상위 — 판단 틀로 카드를 쓰면 선별 통과 후보가 된다)"] + \
         [f"- {r['id']} {r['name']}({r['market']} {r['code']}) · 점수 {f(r['score'])} · {r['theme']}" for r in card_queue(rows)]
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
