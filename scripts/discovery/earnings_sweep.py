"""실적 발표 종목 알파 전수 점검 (마스터 지시 2026-11-07, config/earnings_sweep.yaml)

단계(태그 = 2026-10-01_2026-11-07 같은 일회성 이름 또는 2026-W46 같은 주차):
  --put <태그> <파일> <시장> [--total N]  모델이 TradingView 스크리너 응답(rows)을 파일로 넘긴다. 레인별로 여러 번 불러도 된다(같은 종목은 합친다).
                                         --total = 그 시장 기간 내 발표 종목 수(전수 기준, 필터 없이 받은 totalCount)
  --rank <태그>                          알파 v2 블록 정의로 정량 사전 점수 Q → 판단 후보(judge_top) 목록과 이름표를 쓴다
  --finalize <태그> --floor 7            v1 알파(knowledge/models/alpha/latest.json) ≥ floor인 후보 → 와치리스트·리포트 대기열·요약 JSON
  --show <태그>
저장: knowledge/models/discovery/earnings_sweep/<태그>.json (집계·후보·결과), names.json(새 id 이름표 — 알파 score.names가 읽는다)
지표·연구 후보이지 매수 권유가 아니다.
"""
import argparse
import json
import math
import sys
from datetime import date
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "alpha"))
sys.path.insert(0, str(ROOT / "scripts" / "portfolio"))
DIR = ROOT / "knowledge" / "models" / "discovery" / "earnings_sweep"
NAMES = DIR / "names.json"
QUEUE = ROOT / "knowledge" / "models" / "tenbagger" / "report_queue.txt"


SEC_COLS = ["sic", "cik", "filing", "rev_yoy", "roa_q", "sue_proxy", "asset_growth", "inv_dummy", "float_usd", "symbol", "name", "description", "earnings_release_date"]


def cfg():
    return yaml.safe_load((ROOT / "config" / "earnings_sweep.yaml").read_text(encoding="utf-8"))


def jload(p, d):
    try:
        return json.loads(Path(p).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return d


def path(tag):
    return DIR / f"{tag}.json"


def chiip_id(sym, market, c, known):
    """TradingView 심볼 → Chiip id. 이미 아는 종목(티커 일치)이면 그 id"""
    tk = sym.split(":")[-1]
    hit = known.get(tk.upper())
    if hit:
        return hit
    return f"{c['markets'][market]}-{tk.lower()}"


def known_ids():
    """티커 → 기존 id(알파 latest·portfolio·earnings_watch·valuation)"""
    out = {}
    for f in ("valuation.yaml", "earnings_watch.yaml"):
        y = yaml.safe_load((ROOT / "config" / f).read_text(encoding="utf-8")) or {}
        for u in (y.get("universe") or []) + (y.get("extra") or []):
            code = str(u.get("code") or u.get("ticker") or "")
            tk = code.split(".")[0].split(":")[-1]
            if tk:
                out.setdefault(tk.upper(), u["id"])
    port = yaml.safe_load((ROOT / "config" / "portfolio.yaml").read_text(encoding="utf-8")) or {}
    for h in port.get("holdings") or []:
        if h.get("ticker"):
            out.setdefault(str(h["ticker"]).upper(), h["id"])
    return out


def put(tag, rows, market, total=None, c=None):
    c = c or cfg()
    d = jload(path(tag), {"tag": tag, "markets": {}, "rows": {}})
    m = d["markets"].setdefault(market, {"total": None, "received": 0})
    if total is not None:
        m["total"] = int(total)
    known = known_ids()
    for r in rows:
        sym = r.get("symbol") or r.get("name")
        if not sym:
            continue
        cid = chiip_id(sym, market, c, known)
        keep = {k: r.get(k) for k in list(c["columns"]) + SEC_COLS if k in r}
        keep.update({"market": market, "id": cid})
        if not str(sym).startswith("SEC:") or "symbol" not in d["rows"].get(cid, {}):
            keep["symbol"] = sym
        d["rows"][cid] = {**d["rows"].get(cid, {}), **keep}
    m["received"] = sum(1 for x in d["rows"].values() if x["market"] == market)
    DIR.mkdir(parents=True, exist_ok=True)
    path(tag).write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
    return d


def sec_universe(tag, start, end, log=print):
    """미국 전수: EDGAR 전문검색 8-K 중 Item 2.02(실적 발표)를 낸 모든 회사(날짜별로 나눠 1만 건 상한 회피) →
    SEC frames 재무(최근 분기 vs 1년 전 같은 분기, 시점값 자산, 유통주식 가치)로 가격 없이 되는 요인을 붙인다. 모델 토큰을 쓰지 않는 결정론 단계"""
    from datetime import date as _d, timedelta as _td
    sys.path.insert(0, str(ROOT / "radar"))
    sys.path.insert(0, str(ROOT / "scripts" / "backtest"))
    from pollers import sec_earnings_all as sea
    import frames
    c = cfg()
    d0, d1 = _d.fromisoformat(start), _d.fromisoformat(end)
    filers = {}
    day = d0
    while day <= d1:
        for adsh, src in sea.fetch_hits(day, day, max_pages=40):
            if "2.02" not in (src.get("items") or []):
                continue
            name, ticker, cik = sea.parse_name((src.get("display_names") or [""])[0])
            if not ticker or not cik:
                continue
            k = str(int(cik))
            if k not in filers or src.get("file_date", "") > filers[k]["release"]:
                filers[k] = {"cik": k, "ticker": ticker, "name": name, "release": src.get("file_date"), "sic": (src.get("sics") or [""])[0],
                             "url": f"https://www.sec.gov/Archives/edgar/data/{k}/{adsh.replace('-', '')}/"}
        log(f"- {day} 누적 {len(filers)}개사")
        day += _td(days=1)
    q = c["sec"]["quarter"]
    y, qn = int(q[:4]), int(q[-1])
    prev = f"{y - 1}Q{qn}"

    def frame(tags, per):
        for t in tags:
            rows = frames.fetch(t, per)
            if rows:
                return {str(int(r["cik"])): float(r["val"]) for r in rows}
        return {}
    con = frames.cfg()["sec_frames"]["concepts"]
    rev, rev0 = frame(con["revenue"], f"CY{q}"), frame(con["revenue"], f"CY{prev}")
    oi, oi0 = frame(con["operating_income"], f"CY{q}"), frame(con["operating_income"], f"CY{prev}")
    ta, ta0 = frame(con["total_assets"], f"CY{q}I"), frame(con["total_assets"], f"CY{prev}I")
    flt = {}
    for per in c["sec"]["float_periods"]:
        for k, v in frame(["dei:EntityPublicFloat"], per).items():
            flt.setdefault(k, v)
    rows = []
    for k, f in filers.items():
        r = {"symbol": f"SEC:{f['ticker']}", "name": f["ticker"], "description": f["name"], "earnings_release_date": f["release"], "sic": f["sic"], "cik": k, "filing": f["url"]}
        if k in rev and k in rev0 and rev0[k] > 0:
            r["rev_yoy"] = rev[k] / rev0[k] - 1
        if k in ta and ta[k] > 0:
            if k in oi:
                r["roa_q"] = oi[k] * 4 * 0.79 / ta[k] * 100
                if k in oi0:
                    r["sue_proxy"] = (oi[k] - oi0[k]) / ta[k]
            if k in ta0 and ta0[k] > 0:
                r["asset_growth"] = ta[k] / ta0[k] - 1
                if k in oi and k in oi0 and oi0[k] > 0:
                    r["inv_dummy"] = 1.0 if r["asset_growth"] > oi[k] / oi0[k] - 1 else 0.0
        if k in flt and flt[k] > 0:
            r["float_usd"] = flt[k]
        rows.append(r)
    known = known_ids()
    _, al = __import__("score").load_latest()
    # 유통주식 가치는 지난 10-K 기준이라 늦다 — 이미 Chiip이 아는 종목(감시·알파 산정)은 소형 제외를 적용하지 않는다(2026-11-07 AXTI 누락)
    small = [r for r in rows if r.get("float_usd") is not None and r["float_usd"] < c["sec"]["min_float_usd"]
             and r["name"].upper() not in known and f"us-{r['name'].lower()}" not in al]
    keep = [r for r in rows if r not in small]
    put(tag, keep, "america", total=len(rows))
    d = jload(path(tag), {})
    d.setdefault("notes", []).append(f"미국 전수: 8-K Item 2.02 {len(rows)}개사({start}~{end}) — 유통주식 가치 < ${c['sec']['min_float_usd'] / 1e6:.0f}M {len(small)}개사 제외")
    path(tag).write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
    return len(rows), len(small)


def price_targets(tag, n=None):
    """정량(가격 없이) 상위 n개 미국 종목 — 모델이 TradingView get_symbol_data_batch(50개씩)로 가격·밸류 열을 받아 --put으로 합친다"""
    c = cfg()
    n = n or c["sec"]["price_top"]
    d = jload(path(tag), {})
    us = [r for r in d.get("rows", {}).values() if r["market"] == "america" and r.get("Q") is not None]
    us.sort(key=lambda r: -r["Q"])
    return [r["symbol"].split(":")[-1] for r in us[:n]]


def _inv(x):
    return 1 / x if isinstance(x, (int, float)) and x > 0 else None


def factors(r):
    hi, lo, px = r.get("price_52_week_high"), r.get("price_52_week_low"), r.get("close")
    f = {"fcf_yield": _inv(r.get("price_free_cash_flow_ttm")), "ebit_ev": _inv(r.get("enterprise_value_to_ebit_ttm")), "book_to_market": _inv(r.get("price_book_fq")),
         "roa": r.get("return_on_assets"), "fscore": r.get("piotroski_f_score_ttm"), "rev_surprise": r.get("revenue_surprise_percent_fq"),
         "eps_surprise": r.get("eps_surprise_percent_fq"), "mom_12m": r.get("Perf.Y"), "mom_6m": r.get("Perf.6M"),
         "price_range": (px - lo) / (hi - lo) if all(isinstance(v, (int, float)) for v in (hi, lo, px)) and hi > lo else None,
         "log_mcap": math.log(r["market_cap_basic"]) if (r.get("market_cap_basic") or 0) > 0 else (math.log(r["float_usd"]) if (r.get("float_usd") or 0) > 0 else None),
         "n_analysts": r.get("recommendation_total"), "rev_yoy": r.get("rev_yoy"), "sue_proxy": r.get("sue_proxy"), "asset_growth": r.get("asset_growth"),
         "inv_dummy": r.get("inv_dummy")}
    if f["roa"] is None and r.get("roa_q") is not None:
        f["roa"] = r["roa_q"]
    return {k: v for k, v in f.items() if isinstance(v, (int, float)) and math.isfinite(v)}


def rank(tag, c=None):
    """알파 v2와 같은 방식(단면 순위 z → 블록 z → IC 가중·1/N 반 축소 → Q). 단면 = 이번 태그의 발표 종목 풀"""
    import v2
    c = c or cfg()
    a2 = v2.cfg()
    d = jload(path(tag), None)
    if not d:
        raise SystemExit(f"{tag} 자료 없음 — 먼저 --put")
    fac = {k: factors(r) for k, r in d["rows"].items()}
    names = sorted({f for b in c["factors"].values() for f in b})
    fz = {f: v2.rank_z({k: x.get(f) for k, x in fac.items()}, a2["winsor_z"]) for f in names}
    bz = {}
    for b, fs in c["factors"].items():
        raw = {}
        for k in fac:
            num = sum(s * fz[f][k] for f, s in fs.items() if k in fz[f])
            den = sum(abs(s) for f, s in fs.items() if k in fz[f])
            if den:
                raw[k] = num / den
        bz[b] = v2.rank_z(raw, a2["winsor_z"]) if len(raw) >= 3 else {}
    ics = {b: a2["blocks"][b]["ic"] for b in c["factors"]}
    tot, n, sh = sum(ics.values()), len(ics), a2["shrink_to_equal"]
    w = {b: (1 - sh) * ics[b] / tot + sh / n for b in ics}
    scored = {}
    for k in fac:
        have = {b: bz[b][k] for b in bz if k in bz[b]}
        if len(have) >= c["min_blocks"]:
            scored[k] = sum(w[b] * have[b] for b in have) / math.sqrt(sum(w[b] ** 2 for b in have))
    _, al = __import__("score").load_latest()
    pre = [k for k in d["rows"] if (al.get(k) or {}).get("total") is not None]   # 이미 알파 판단이 있는 종목은 판단 후보에 늘 포함
    top = sorted(scored, key=lambda k: -scored[k])[:c["judge_top"]]
    cands = list(dict.fromkeys(top + pre))
    for k, r in d["rows"].items():
        r["Q"] = round(scored[k], 3) if k in scored else None
        r["alpha_q"] = round(10 * v2.norm_cdf(scored[k]), 2) if k in scored else None
    d["candidates"] = cands
    d["ranked_n"] = len(scored)
    path(tag).write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
    nm = jload(NAMES, {})
    for k in cands:
        nm.setdefault(k, d["rows"][k].get("description") or d["rows"][k].get("name"))
    NAMES.write_text(json.dumps(nm, ensure_ascii=False, indent=1), encoding="utf-8")
    return d


def finalize(tag, floor, today=None, dry=False):
    import score
    import watchlist
    c = cfg()
    today = today or date.today().isoformat()
    d = jload(path(tag), None)
    _, al = score.load_latest()
    res = []
    for k in d.get("candidates") or []:
        a = (al.get(k) or {}).get("total")
        r = d["rows"][k]
        res.append({"id": k, "ticker": r["symbol"].split(":")[-1], "symbol": r["symbol"], "name": r.get("description") or r.get("name"),
                    "market": r["market"], "release": r.get("earnings_release_date"), "Q": r.get("Q"), "alpha_q": r.get("alpha_q"), "alpha": a,
                    "components": (al.get(k) or {}).get("components"), "pass": a is not None and a >= floor})
    res.sort(key=lambda x: -(x["alpha"] or -1))
    passed = [x for x in res if x["pass"]]
    added = [] if dry else watchlist.add_sweep(passed, floor, c["watchlist"]["added_by"], tag, today)
    queued = [] if dry or not c.get("report_queue") else queue(passed, tag)
    d["result"] = {"as_of": today, "floor": floor, "judged": sum(1 for x in res if x["alpha"] is not None), "rows": res,
                   "passed": [x["id"] for x in passed], "watchlist_added": added, "report_queued": queued}
    path(tag).write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
    return d


def queue(passed, tag):
    have = QUEUE.read_text(encoding="utf-8").splitlines() if QUEUE.exists() else []
    keys = {ln.split("|")[0].strip() for ln in have if ln.strip()}
    out = []
    for x in passed:
        key = x["ticker"] if x["market"] == "america" and x["id"] == f"us-{x['ticker'].lower()}" else x["id"]
        if key in keys or x["id"] in keys:
            continue
        have.append(f"{key} | sweep | 실적 발표 알파 점검 {tag} — 알파 {x['alpha']:.1f}(마스터 지시 2026-11-07: 기준 이상이면 Watchlist + Analysis 리포트)")
        out.append(key)
    if out:
        QUEUE.write_text("\n".join(have) + "\n", encoding="utf-8")
    return out


def summary(tag):
    """Weekly Review 절 재료 — 렌더러(scripts/weekly/render.py)가 읽는다"""
    d = jload(path(tag), None)
    if not d or not d.get("result"):
        return None
    r = d["result"]
    return {"tag": tag, "floor": r["floor"], "universe": {m: v.get("total") for m, v in d["markets"].items()}, "pool": len(d["rows"]),
            "ranked": d.get("ranked_n"), "judged": r["judged"], "passed": [x for x in r["rows"] if x["pass"]],
            "near": [x for x in r["rows"] if not x["pass"] and x["alpha"] is not None and x["alpha"] >= r["floor"] - 1.0][:5],
            "watchlist_added": r["watchlist_added"], "report_queued": r["report_queued"]}


def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument("--put", nargs=3, metavar=("TAG", "FILE", "MARKET"))
    ap.add_argument("--total", type=int)
    ap.add_argument("--rank")
    ap.add_argument("--finalize")
    ap.add_argument("--floor", type=float)
    ap.add_argument("--dry", action="store_true")
    ap.add_argument("--show")
    ap.add_argument("--sec", nargs=3, metavar=("TAG", "START", "END"))
    ap.add_argument("--targets")
    a = ap.parse_args(argv)
    if a.put:
        raw = jload(a.put[1], [])
        rows = raw.get("rows") if isinstance(raw, dict) else raw
        d = put(a.put[0], rows or [], a.put[2], a.total)
        print(f"[{a.put[0]}] {a.put[2]} 받음 {d['markets'][a.put[2]]['received']} / 발표 {d['markets'][a.put[2]]['total']}")
    if a.sec:
        n, small = sec_universe(*a.sec)
        print(f"[{a.sec[0]}] 미국 8-K Item 2.02 {n}개사, 소형 제외 {small}")
    if a.targets:
        print(json.dumps(price_targets(a.targets)))
    if a.rank:
        d = rank(a.rank)
        print(f"[{a.rank}] 정량 산정 {d['ranked_n']} / 풀 {len(d['rows'])} → 판단 후보 {len(d['candidates'])}")
        for k in d["candidates"]:
            r = d["rows"][k]
            print(f"- {k} {r.get('description') or r.get('name')} Q {r['Q']} ({r.get('earnings_release_date')})")
    if a.finalize:
        c = cfg()
        floor = a.floor if a.floor is not None else c["floors"]["weekly"]
        d = finalize(a.finalize, floor, dry=a.dry)
        r = d["result"]
        print(f"[{a.finalize}] 판단 {r['judged']} → 알파 ≥ {floor}: {len(r['passed'])} · 와치리스트 +{len(r['watchlist_added'])} · 리포트 대기열 +{len(r['report_queued'])}")
        for x in r["rows"]:
            if x["alpha"] is not None:
                print(f"- {x['name']}({x['ticker']}) 알파 {x['alpha']:.1f}{' ✓' if x['pass'] else ''} · 정량 {x['alpha_q']}")
    if a.show:
        print(json.dumps(summary(a.show), ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(main(sys.argv[1:]))
