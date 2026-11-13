"""섹터 순환 스크린 + 섹터 판단 틀 카드 (마스터 지시 2026-11-13 종목 범위 확대 2단계, ADR-027, 설정 config/sector_rotation.yaml)

왜: 발굴 지도는 AI 밸류체인 테마가 대부분이고, TradingView 섹션 바구니는 '왜 오르나' 근거가 없다(ADR-025 진단).
흐름(수집·점수는 결정론, TradingView 호출과 카드 판단만 모델):
  ① --plan     : 오늘 볼 섹터(하루 한 번, per_run개) — Portfolio 섹터 선정의 신규 편입·편입 후보 섹터를 먼저, 다음은 순번.
                 출력 = 섹터별 mcp-tv-run-screener 호출 사양(JSON). 같은 날 다시 부르면 due=false
  ② --put <TradingView 섹터> <응답 파일> : knowledge/models/discovery/rotation/<섹터>.json
  ③ --score    : 섹터 안 z점수(성장·모멘텀·이익률·규모·밸류, ±3 절단) 가중합 → 섹터별 상위 top_n
                 → knowledge/models/discovery/rotation_candidates.json (screen.py가 '섹터 순환: <섹터>' 테마로 합류)
  ④ 판단 틀 카드 : 상위 후보 중 볼 만한 종목은 모델이 knowledge/methods/sector_lenses/<틀>.md 질문지로
                 knowledge/models/discovery/lens_cards/<id>.yaml을 쓴다 → --card-check <파일> 통과분만 edge가 선별 점수에 들어간다.
                 카드가 없으면 edge 미판정(5) — 점수가 높아도 '① 아이디어'에 머문다(선별 통과는 edge 6 이상).
금지 연결: 스크린 점수 → 경쟁우위가 아니다. 섹터 성장 → 기업 이익이 아니다. 매출 급증 → 이익 증가가 아니다(가격·믹스·원가).
사용: py scripts/discovery/sector_rotation.py --plan | --put <섹터> <파일> | --score | --card-check <파일>
"""
import json
import math
import re
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
DISC = ROOT / "knowledge" / "models" / "discovery"
ROT = DISC / "rotation"
CANDS = DISC / "rotation_candidates.json"
CARDS = DISC / "lens_cards"
LENSES = ROOT / "knowledge" / "methods" / "sector_lenses"
STATE = ROOT / "radar" / "state" / "sector_rotation.json"
CARD_KEYS = ["id", "ticker", "lens", "as_of", "answers", "edge", "evidence", "kill", "why"]


def cfg():
    return yaml.safe_load((ROOT / "config" / "sector_rotation.yaml").read_text(encoding="utf-8"))


def _j(p, default=None):
    try:
        return json.loads(Path(p).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {} if default is None else default


def slug(sector):
    return re.sub(r"[^a-z0-9]+", "_", sector.lower()).strip("_")


# ---------- ① 계획 ----------
def priority_sectors(c):
    """Portfolio 섹터 선정(knowledge/models/portfolio/sector_select_latest.json)의 신규 편입·편입 후보 섹터 → TradingView 섹터"""
    ss = _j(ROOT / "knowledge" / "models" / "portfolio" / "sector_select_latest.json")
    hot = [r["id"] for r in (ss.get("shown") or []) if r.get("tag") == "신규 편입"] + [r["id"] for r in ss.get("watch") or []]
    back = {v[2]: tv for tv, v in c["rotation"].items()}
    back.update(c.get("group_tv") or {})
    return list(dict.fromkeys(back[g] for g in hot if back.get(g)))


def plan(today=None, c=None, st=None, write=True):
    c = c or cfg()
    today = (today or date.today()).isoformat()
    st = _j(STATE) if st is None else st
    if st.get("last_date") == today:
        return {"due": False, "date": today, "sectors": st.get("last_sectors") or []}
    order = list(c["rotation"])
    cur = int(st.get("cursor", 0)) % len(order)
    pick = [s for s in priority_sectors(c) if s in order][:c["per_run"]]
    while len(pick) < c["per_run"]:
        s = order[cur % len(order)]
        cur += 1
        if s not in pick:
            pick.append(s)
    st = {**st, "cursor": cur % len(order), "last_date": today, "last_sectors": pick}
    if write:
        STATE.parent.mkdir(parents=True, exist_ok=True)
        STATE.write_text(json.dumps(st, ensure_ascii=False, indent=1), encoding="utf-8")
    specs = [{"sector": s, "name": c["rotation"][s][0], "market": "america", "filters": {"sector": s, **c["filters"]},
              "columns": c["columns"], "sort_by": c["sort_by"], "sort_order": "desc", "limit": c["limit"]} for s in pick]
    return {"due": True, "date": today, "sectors": pick, "specs": specs}


# ---------- ② 저장 ----------
def put(sector, path, today=None):
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    rows = ((raw.get("data") or raw).get("rows") if isinstance(raw, dict) else raw) or []
    keep = set(cfg()["columns"]) | {"symbol", "name"}
    rows = [{k: v for k, v in r.items() if k in keep} for r in rows]       # 스크리너가 덧붙이는 칸(EMA 등)은 버린다
    ROT.mkdir(parents=True, exist_ok=True)
    (ROT / f"{slug(sector)}.json").write_text(json.dumps({"sector": sector, "as_of": (today or date.today()).isoformat(), "rows": rows},
                                                         ensure_ascii=False), encoding="utf-8")
    return len(rows)


# ---------- ③ 점수 ----------
def _wins(vals, lo=0.1, hi=0.9):
    """10·90 백분위로 자른다 — 영업이익률 −3,000% 같은 극단값 하나가 평균·표준편차를 끌지 않게"""
    xs = sorted(v for v in vals if v is not None and math.isfinite(v))
    if len(xs) < 5:
        return vals
    a, b = xs[int(lo * (len(xs) - 1))], xs[int(hi * (len(xs) - 1))]
    return [None if v is None or not math.isfinite(v) else min(b, max(a, v)) for v in vals]


def _z(vals, sign=1):
    vals = _wins(vals)
    xs = [v for v in vals if v is not None and math.isfinite(v)]
    if len(xs) < 3:
        return [0.0 for _ in vals]
    m = sum(xs) / len(xs)
    sd = (sum((x - m) ** 2 for x in xs) / (len(xs) - 1)) ** 0.5 or 1.0
    return [0.0 if v is None or not math.isfinite(v) else max(-3.0, min(3.0, sign * (v - m) / sd)) for v in vals]


def group_of(industry, sector, c):
    for pat, g in c.get("industry_group") or []:
        if re.search(pat, industry or "", re.I):
            return g
    return c["rotation"].get(sector, [None, None, None])[2]


def score_sector(data, c, today=None):
    rows = []
    for r in data.get("rows") or []:
        vt = (r.get("average_volume_30d_calc") or 0) * (r.get("close") or 0)
        if vt < c["min_value_traded_usd"] or str(r.get("symbol", "")).split(":")[0] in (c.get("exclude_exchanges") or []):
            continue
        rows.append({**r, "value_traded_usd": vt})
    if not rows:
        return []
    w = c["weights"]
    zs = {"growth": _z([r.get("total_revenue_yoy_growth_ttm") for r in rows]),
          "momentum": _z([r.get("Perf.6M") for r in rows]),
          "quality": _z([r.get("operating_margin_ttm") for r in rows]),
          "size": _z([math.log(r["market_cap_basic"]) if r.get("market_cap_basic") else None for r in rows], -1),
          "value": _z([r.get("enterprise_value_to_revenue_ttm") for r in rows], -1)}
    lens = c["rotation"][data["sector"]][1]
    out = []
    for i, r in enumerate(rows):
        s = sum(w[k] * zs[k][i] for k in w)
        tk = str(r.get("name") or r.get("symbol", "").split(":")[-1])
        out.append({"ticker": tk, "symbol": r.get("symbol"), "name": r.get("description") or tk, "industry": r.get("industry"),
                    "group": group_of(r.get("industry"), data["sector"], c), "lens": lens, "score": round(s, 2),
                    "rev_growth": r.get("total_revenue_yoy_growth_ttm"), "op_margin": r.get("operating_margin_ttm"), "perf_6m": r.get("Perf.6M"),
                    "mcap_usd": r.get("market_cap_basic"), "ev_sales": r.get("enterprise_value_to_revenue_ttm"),
                    "near_high": bool(r.get("price_52_week_high") and r.get("close") and r["close"] >= 0.9 * r["price_52_week_high"])})
    out.sort(key=lambda x: -x["score"])
    return out[:c["top_n"]]


def score(today=None, c=None):
    c = c or cfg()
    today = today or date.today()
    res = {}
    for f in sorted(ROT.glob("*.json")) if ROT.exists() else []:
        d = _j(f)
        if not d.get("sector") or d["sector"] not in c["rotation"]:
            continue
        if (today - date.fromisoformat(d["as_of"])).days > c["stale_days"]:
            continue
        res[d["sector"]] = {"name": c["rotation"][d["sector"]][0], "as_of": d["as_of"], "rows": score_sector(d, c, today)}
    out = {"as_of": today.isoformat(), "sectors": res, "note": "스크린 점수는 후보를 줄이는 보조 — 경쟁우위 판단이 아니다"}
    CANDS.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    return out


# ---------- ④ 판단 틀 카드 ----------
def card_check(path):
    """[문제] — 비면 통과. 카드 = knowledge/models/discovery/lens_cards/<id>.yaml"""
    try:
        d = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError) as e:
        return [f"읽기 실패: {e}"]
    errs = [f"빠진 칸: {k}" for k in CARD_KEYS if d.get(k) in (None, "", [], {})]
    if d.get("lens") and not (LENSES / f"{d['lens']}.md").exists():
        errs.append(f"없는 판단 틀: {d['lens']}")
    try:
        e = float(d.get("edge"))
        if not 0 <= e <= 10:
            errs.append("edge는 0~10")
    except (TypeError, ValueError):
        errs.append("edge가 숫자가 아님")
    ev = d.get("evidence") or []
    if not any(str(x).startswith("http") for x in ev):
        errs.append("근거 URL이 하나도 없음(1차 출처)")
    qs = len(re.findall(r"(?m)^\d+\. ", (LENSES / f"{d.get('lens')}.md").read_text(encoding="utf-8"))) if d.get("lens") and (LENSES / f"{d['lens']}.md").exists() else 0
    ans = d.get("answers") or {}
    if qs and len(ans) < qs:
        errs.append(f"질문 {qs}개 중 {len(ans)}개만 답함('미확인'도 답이다)")
    return errs


def cards(c=None, today=None):
    """{id: edge} — 검사 통과·유효 기간 안 카드만"""
    c = c or cfg()
    today = today or date.today()
    out = {}
    for f in CARDS.glob("*.yaml") if CARDS.exists() else []:
        if card_check(f):
            continue
        d = yaml.safe_load(f.read_text(encoding="utf-8"))
        try:
            age = (today - date.fromisoformat(str(d["as_of"])[:10])).days
        except ValueError:
            continue
        if age <= c["card_days"]:
            out[d["id"]] = float(d["edge"])
    return out


def rows_for_screen(have):
    """screen.py 합류용 — [(id, 이름, 티커, 테마 이름, z합성, 성장(소수), 시가총액, edge, why)]"""
    c = cfg()
    cand, edges, out = _j(CANDS), cards(c), []
    for sec, v in (cand.get("sectors") or {}).items():
        for r in v.get("rows") or []:
            cid = f"us-{re.sub(r'[^a-z0-9]', '', r['ticker'].lower())}"
            if cid in have:
                continue
            why = f"섹터 순환 {v['name']} z합성 {r['score']} · {r.get('industry')}" + (" · 판단 틀 카드" if cid in edges else " · 판단 틀 카드 없음(edge 미판정)")
            out.append({"id": cid, "name": r["name"], "ticker": r["ticker"], "theme": f"섹터 순환: {v['name']}", "z": r["score"],
                        "rev_growth": None if r.get("rev_growth") is None else r["rev_growth"] / 100, "mcap_usd": r.get("mcap_usd"),
                        "edge": edges.get(cid, 5), "why": why})
    return out


def main(argv):
    sys.stdout.reconfigure(encoding="utf-8")
    if "--plan" in argv:
        print(json.dumps(plan(), ensure_ascii=False, indent=1))
    elif "--put" in argv:
        i = argv.index("--put")
        print(f"{argv[i + 1]}: {put(argv[i + 1], argv[i + 2])}행 저장")
    elif "--score" in argv:
        out = score()
        for s, v in out["sectors"].items():
            print(f"■ {v['name']}({s}, {v['as_of']})")
            for r in v["rows"]:
                print(f"  {r['ticker']} {r['name']} — z {r['score']} · 매출 {r['rev_growth']:+.0f}% · 6개월 {r['perf_6m']:+.0f}% · {r['industry']} → 틀 {r['lens']}")
    elif "--card-check" in argv:
        errs = card_check(argv[argv.index("--card-check") + 1])
        print("통과" if not errs else "\n".join("오류 " + e for e in errs))
        sys.exit(1 if errs else 0)
    else:
        print(__doc__)


if __name__ == "__main__":
    main(sys.argv[1:])
