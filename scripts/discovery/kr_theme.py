"""국장 테마 엔진 — 테마의 점화·확산·과열·소멸·구조적 확인을 하루 단위로 판정한다 (마스터 지시 2026-11-15 "국장 테마주" 발굴 채널,
사전 config/kr_themes.yaml, 렌즈 knowledge/methods/sector_lenses/kr_theme.md, 설계 knowledge/methods/discovery_engine.md)

흐름(수집·판정은 결정론, TradingView 호출만 모델 — 평일 장 마감(15:30) 뒤 하루 한 번):
  ① --spec              : mcp-tv-run-screener 호출 사양(한국 하루 +7% 이상, 거래대금 순 80행 — 응답은 모델이 옮겨 적으므로 작게)
  ② --put <응답 파일> [날짜] : radar/state/kr_theme_daily/<날짜>.json — 급등 종목 스냅숏(거래대금 하한 적용, git 제외)
  ③ --score [날짜]       : 테마별 급등 수·상한가·활발한 날·텔레그램 언급 가속·KRX 투자경고 지정·구성 종목 성장·이익률 → 생애 단계 → 단서 장부(채널 kr_theme)
                          → outputs/discovery/kr_theme_<날짜>.md · knowledge/models/discovery/kr_theme_latest.json
  ④ --verify <파일>      : 사전 종목 코드 대조(get-symbol-data-batch 응답의 설명 ↔ 사전 이름 없음 — 못 찾은 코드만 보고)
  언급: radar/kr_theme_news.py(run_hourly 하루 1회) — 공개 텔레그램 채널 저장분의 테마 어휘 글 수 → kr_theme/news.csv(Google News는 robots 금지라 쓰지 않는다)
  적신호: radar/discovery_filings.py 장부(kr_flags.json) — 최근 180일 CB·BW·EB·유상증자 결정은 감점 1.5, 시장조치(관리·상장폐지 우려·불성실·실질심사)는 감점 3,
          KRX 투자경고 지정(내부 표지 — 거래소 법적고지상 목록 재배포 금지)은 과열 판정에만 쓴다
  사전 밖 급등 종목도 같은 TradingView 업종 cluster_min개 이상이면 '업종 묶음'(이름은 모델이 붙여 사전에 넣는다)
판정 문턱 = config/kr_themes.yaml lifecycle(사전값, 등록부 prm-krth-*).
금지 연결: 테마 급등 → 펀더멘털 변화가 아니다. 텔레그램 언급 수 → 수요가 아니다. 구조적 판정도 후보다 — 이익 상향·수출·수주를 1차 자료로 확인한다.
사용: py scripts/discovery/kr_theme.py --spec | --put <파일> [YYYY-MM-DD] | --score [YYYY-MM-DD] | --verify <파일>
"""
import csv
import json
import statistics
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))
DIR = ROOT / "knowledge" / "models" / "discovery" / "kr_theme"
DAILY = ROOT / "radar" / "state" / "kr_theme_daily"   # TradingView 급등 스냅숏 원자료 — git 제외
NEWS = DIR / "news.csv"
LATEST = ROOT / "knowledge" / "models" / "discovery" / "kr_theme_latest.json"
FLAGS = ROOT / "knowledge" / "models" / "discovery" / "kr_flags.json"
OUTD = ROOT / "outputs" / "discovery"
KST = timezone(timedelta(hours=9))
COLUMNS = ["name", "description", "industry", "sector", "change", "Perf.W", "Perf.1M", "Value.Traded", "market_cap_basic", "relative_volume_10d_calc",
           "total_revenue_yoy_growth_ttm", "operating_margin_ttm", "float_shares_percent_current", "price_52_week_high", "close"]
FLAGS_CACHE = {}
STAGE_KO = {"ignite": "점화", "spread": "확산", "overheat": "과열", "structural": "구조적 확인", "fade": "소멸"}


def cfg():
    return yaml.safe_load((ROOT / "config" / "kr_themes.yaml").read_text(encoding="utf-8"))


def today_kst():
    return datetime.now(KST).date()


def _f(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def spec():
    lc = cfg()["lifecycle"]
    return {"market": "korea", "filters": {"change": [lc["mover_change_pct"], None]}, "columns": COLUMNS, "sort_by": "Value.Traded", "sort_order": "desc", "limit": 80}


def put(path, day=None):
    d = json.loads(Path(path).read_text(encoding="utf-8"))
    rows = (d.get("data") or {}).get("rows") if isinstance(d.get("data"), dict) else d.get("rows")
    if not isinstance(rows, list):
        raise SystemExit("응답에 rows가 없다 — mcp-tv-run-screener 응답 JSON을 그대로 저장한다")
    lc = cfg()["lifecycle"]
    keep = []
    for r in rows:
        val = _f(r.get("Value.Traded"))
        if val is not None and val < lc["min_value_krw"]:
            continue
        code = str(r.get("name") or "").strip()
        keep.append({"code": code, "name": r.get("description") or code, "industry": r.get("industry") or "", "change": _f(r.get("change")),
                     "value_krw": val, "mcap_krw": _f(r.get("market_cap_basic")), "perf_w": _f(r.get("Perf.W")), "perf_1m": _f(r.get("Perf.1M")),
                     "growth": _f(r.get("total_revenue_yoy_growth_ttm")), "op_margin": _f(r.get("operating_margin_ttm")), "rvol": _f(r.get("relative_volume_10d_calc")),
                     "close": _f(r.get("close"))})
    day = str(day or today_kst())
    DAILY.mkdir(parents=True, exist_ok=True)
    (DAILY / f"{day}.json").write_text(json.dumps({"date": day, "rows": keep, "received": len(rows)}, ensure_ascii=False, indent=0), encoding="utf-8")
    return len(keep), len(rows)


def snapshots(until, n=60):
    out = []
    for p in sorted(DAILY.glob("*.json")):
        if p.stem <= str(until):
            out.append(json.loads(p.read_text(encoding="utf-8")))
    return out[-n:]


def news_counts():
    """{theme: {date: count}}"""
    out = {}
    if NEWS.exists():
        with NEWS.open(encoding="utf-8", newline="") as f:
            for r in csv.DictReader(f):
                try:
                    out.setdefault(r["theme"], {})[r["date"]] = int(r["count"])
                except (KeyError, ValueError):
                    continue
    return out


def flags():
    d = json.loads(FLAGS.read_text(encoding="utf-8")) if FLAGS.exists() else {}
    return d.get("rows") or {}


def assign(rows, themes):
    """{theme id: [행]} + 사전 밖 {업종: [행]}"""
    by_code = {s: t["id"] for t in themes for s in t.get("seeds") or []}
    by_ind = {i: t["id"] for t in themes for i in t.get("industries") or []}
    got, rest = {}, {}
    for r in rows:
        tid = by_code.get(r["code"]) or by_ind.get(r["industry"])
        if tid:
            got.setdefault(tid, []).append(r)
        else:
            rest.setdefault(r["industry"] or "미분류", []).append(r)
    return got, rest


def theme_state(tid, t, snaps, news, lc, day):
    """테마 하나의 오늘 상태와 단계"""
    days = [s["date"] for s in snaps]
    act, lim, members = [], [], {}
    for s in snaps:
        g, _ = assign(s["rows"], [t])
        rs = g.get(tid, [])
        act.append(len(rs))
        lim.append(sum(1 for r in rs if (r["change"] or 0) >= lc["limit_up_pct"]))
        for r in rs:
            members[r["code"]] = r
    today_rows = assign(snaps[-1]["rows"], [t])[0].get(tid, []) if snaps and snaps[-1]["date"] == str(day) else []
    a_today = len(today_rows)
    l_today = sum(1 for r in today_rows if (r["change"] or 0) >= lc["limit_up_pct"])
    n = news.get(tid) or {}
    n_today = n.get(str(day))
    hist = [v for d, v in n.items() if d < str(day)][-20:]
    n_avg = statistics.mean(hist) if hist else None
    n_x = (n_today / n_avg) if n_today is not None and n_avg else None
    prior = act[-(lc["ignite_quiet_days"] + 1):-1] if len(act) > 1 else []
    last5 = act[-5:]
    prev20 = act[-25:-5]
    gs = [m["growth"] for m in members.values() if m.get("growth") is not None]
    ms = [m["op_margin"] for m in members.values() if m.get("op_margin") is not None]
    g_med = statistics.median(gs) if gs else None
    m_med = statistics.median(ms) if ms else None
    active60 = sum(1 for x in act[-60:] if x >= 1)
    stages = []
    lo_alert = (date.fromisoformat(str(day)) - timedelta(days=lc.get("alert_days", 10))).isoformat()
    warned = sorted({c for c in members if any(f.get("alert") and f["date"] >= lo_alert for f in (FLAGS_CACHE.get(c) or []))})
    if l_today >= lc["overheat_limit_ups"] or (n_x is not None and n_x >= lc["overheat_news_x"] and a_today >= 2) or len(warned) >= lc.get("overheat_alerts", 2):
        stages.append("overheat")
    quiet_before = len(prior) >= min(5, lc["ignite_quiet_days"]) and max(prior) <= 1
    if (a_today >= lc["ignite_min"] or (a_today >= 2 and l_today >= 1)) and quiet_before:
        stages.append("ignite")
    if t.get("type") in ("structural_candidate", "mixed") and g_med is not None and m_med is not None and g_med >= lc["structural_growth"] \
            and m_med >= lc["structural_margin"] and active60 >= lc["structural_active"]:
        stages.append("structural")
    lo, hi = lc["spread_days"]
    if len(last5) >= hi and sum(1 for x in last5 if x >= 2) >= lo:
        stages.append("spread")
    if len(act) >= 25 and sum(last5) == 0 and sum(1 for x in prev20 if x >= 2) >= lc["fade_days"]:
        stages.append("fade")
    return {"id": tid, "name": t["name"], "type": t.get("type"), "today": a_today, "limit_ups": l_today, "warned": len(warned), "active5": sum(1 for x in last5 if x >= 1),
            "active60": active60, "news_today": n_today, "news_x": None if n_x is None else round(n_x, 1), "growth_med": g_med, "margin_med": m_med,
            "stages": stages, "rows": sorted(today_rows, key=lambda r: -(r["value_krw"] or 0)), "days": len(days)}


STRENGTH = {"ignite": 6.0, "structural": 6.5, "spread": 5.0, "overheat": 3.0, "fade": 2.0}
TYPE_ADJ = {"structural_candidate": 0.5, "mixed": 0.0, "speculative": -1.0}


def score(day=None, write=True):
    day = date.fromisoformat(str(day)) if day else today_kst()
    c = cfg()
    lc, themes = c["lifecycle"], c["themes"]
    snaps = snapshots(day)
    if not snaps:
        return {"themes": [], "clusters": [], "note": "스냅숏 없음"}
    news = news_counts()
    fl = flags()
    FLAGS_CACHE.clear()
    FLAGS_CACHE.update(fl)
    lo = (day - timedelta(days=180)).isoformat()
    states = [theme_state(t["id"], t, snaps, news, lc, day) for t in themes]
    _, rest = assign(snaps[-1]["rows"], themes) if snaps[-1]["date"] == str(day) else ({}, {})
    clusters = [{"industry": k, "rows": sorted(v, key=lambda r: -(r["value_krw"] or 0))} for k, v in rest.items() if len(v) >= lc["cluster_min"] and k != "미분류"]
    rows = []
    for s in states:
        if not s["stages"] or not s["rows"] and s["stages"] != ["fade"]:
            continue
        kind = next(k for k in ("overheat", "ignite", "structural", "spread", "fade") if k in s["stages"])
        base = STRENGTH[kind] + TYPE_ADJ.get(s["type"], 0.0)
        if kind == "ignite":
            base += min(1.5, 0.3 * max(0, s["today"] - lc["ignite_min"]))
        head = f"{s['name']} {STAGE_KO[kind]} — 급등 {s['today']}종목(상한가 {s['limit_ups']}) · 5일 중 {s['active5']}일 · 60일 중 {s['active60']}일" + \
               (f" · 텔레그램 언급 {s['news_today']}건(20일 평균의 {s['news_x']}배)" if s["news_today"] is not None and s["news_x"] is not None else "") + \
               (f" · 투자경고 지정 {s['warned']}종목" if s.get("warned") else "")
        for r in s["rows"][:3]:
            fs = [f for f in fl.get(r["code"], []) if f["date"] >= lo and not f.get("alert")]
            severe = any(f.get("severe") for f in fs)
            st = round(max(0.0, min(10.0, base - (3.0 if severe else 1.5 if fs else 0.0))), 1)
            rows.append({"channel": "kr_theme", "kind": kind, "market": "kr", "ticker": r["code"], "name": r["name"], "tv": f"KRX:{r['code']}", "date": str(day),
                         "strength": st, "signal": head + f" · {r['name']} {r['change']:+.1f}%" + (f" · 적신호 공시 {len(fs)}건" if fs else ""), "url": "",
                         "price": r.get("close"), "extra": {"theme": s["id"], "theme_name": s["name"], "stages": s["stages"], "type": s["type"], "red_flag": bool(fs)}})
    for cl in clusters:
        for r in cl["rows"][:3]:
            fs = [f for f in fl.get(r["code"], []) if f["date"] >= lo]
            rows.append({"channel": "kr_theme", "kind": "ignite", "market": "kr", "ticker": r["code"], "name": r["name"], "tv": f"KRX:{r['code']}", "date": str(day),
                         "strength": round(max(0.0, 5.0 - (1.5 if fs else 0.0)), 1), "url": "", "price": r.get("close"),
                         "signal": f"사전 밖 업종 묶음 '{cl['industry']}' 급등 {len(cl['rows'])}종목 — {r['name']} {r['change']:+.1f}%(테마 이름은 모델 확인)",
                         "extra": {"theme": f"industry:{cl['industry']}", "red_flag": bool(fs)}})
    res = {"date": str(day), "snapshots": len(snaps), "themes": [{k: v for k, v in s.items() if k != "rows"} | {"top": [r["name"] for r in s["rows"][:5]]} for s in states],
           "clusters": [{"industry": cl["industry"], "n": len(cl["rows"]), "top": [r["name"] for r in cl["rows"][:5]]} for cl in clusters]}
    if write:
        import leads
        new = leads.add(rows, today=day)
        res["new_leads"] = len(new)
        LATEST.write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
        OUTD.mkdir(parents=True, exist_ok=True)
        (OUTD / f"kr_theme_{day.strftime('%Y%m%d')}.md").write_text(render(res, fl, lo), encoding="utf-8")
    return res


def render(res, fl, lo):
    L = [f"# 국장 테마 {res['date']}", "", f"스냅숏 {res['snapshots']}거래일 기준. 단계: 점화(조용하던 테마에 급등 몰림) · 확산 · 과열(상한가 다수·언급 급증·투자경고 지정) · 소멸 · 구조적 확인(구성 종목 성장·이익률이 받침, 후보).", "",
         "| 테마 | 유형 | 오늘 급등 | 상한가 | 투자경고 | 5일 활발 | 60일 활발 | 텔레그램(배) | 성장 중앙 | 이익률 중앙 | 단계 | 오늘 상위 |", "|---|---|---|---|---|---|---|---|---|---|---|---|"]
    fm = lambda v, suf="": "—" if v is None else f"{v:.0f}{suf}"
    for s in sorted(res["themes"], key=lambda x: (-len(x["stages"]), -x["today"])):
        L.append(f"| {s['name']} | {s['type']} | {s['today']} | {s['limit_ups']} | {s.get('warned', 0)} | {s['active5']} | {s['active60']} | {fm(s['news_today'])}({s['news_x'] if s['news_x'] is not None else '—'}) | "
                 f"{fm(s['growth_med'], '%')} | {fm(s['margin_med'], '%')} | {', '.join(STAGE_KO[k] for k in s['stages']) or '-'} | {', '.join(s['top'][:3])} |")
    if res["clusters"]:
        L += ["", "## 사전 밖 업종 묶음(이름 확인 필요)", ""] + [f"- {c['industry']}: {c['n']}종목 — {', '.join(c['top'])}" for c in res["clusters"]]
    L += ["", "적신호(최근 180일 OpenDART 희석 공시 −1.5, 시장조치 −3)는 단서 강도를 낮춘다. 투자경고 지정 수는 거래소 목록을 옮기지 않고 테마별 개수만 적는다.",
          "금지 연결: 테마 급등 → 펀더멘털 변화가 아니다. 텔레그램 언급 수 → 수요가 아니다. 연구 후보이지 매수 권유 아님."]
    return "\n".join(L) + "\n"


def verify(path):
    """get-symbol-data-batch 응답(사전 종목 KRX:<코드>) — 못 찾은 코드 목록"""
    d = json.loads(Path(path).read_text(encoding="utf-8"))
    data = d.get("data", d)
    found = {k.split(":")[-1]: v.get("description") for k, v in (data or {}).items() if isinstance(v, dict)}
    out = []
    for t in cfg()["themes"]:
        for s in t.get("seeds") or []:
            out.append({"theme": t["name"], "code": s, "description": found.get(s), "ok": s in found})
    return out


def main(argv):
    sys.stdout.reconfigure(encoding="utf-8")
    if argv and argv[0] == "--spec":
        print(json.dumps(spec(), ensure_ascii=False))
    elif argv and argv[0] == "--put" and len(argv) >= 2:
        k, n = put(argv[1], argv[2] if len(argv) > 2 else None)
        print(f"급등 {k}종목 저장(받은 {n}행)")
    elif argv and argv[0] == "--score":
        r = score(argv[1] if len(argv) > 1 else None)
        act = [s for s in r.get("themes", []) if s["stages"]]
        print(f"[국장 테마] {r.get('date')} 단계 있는 테마 {len(act)} · 업종 묶음 {len(r.get('clusters', []))} · 새 단서 {r.get('new_leads', 0)} — "
              + ", ".join(f"{s['name']}({'·'.join(STAGE_KO[k] for k in s['stages'])})" for s in act))
    elif argv and argv[0] == "--verify" and len(argv) >= 2:
        for x in verify(argv[1]):
            if not x["ok"]:
                print(f"못 찾음: {x['theme']} {x['code']}")
            else:
                print(f"{x['theme']} {x['code']} {x['description']}")
    else:
        print(__doc__)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
