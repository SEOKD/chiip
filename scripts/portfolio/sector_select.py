"""Portfolio Daily '■ 섹터' 동적 선정 (마스터 지시 2026-11-13 "섹터를 고정 목록만 쓰지 말고 Chiip이 판단해 추가·제외", ADR-023)

후보 = config/sector_select.yaml groups — Chiip 바스켓(config/market_watch.yaml sectors) + 미국 11개 업종 + 산업·테마(AI 밸류체인 밖 포함).
판단은 이 스크립트(결정론), 문장은 모델. 모델은 아래 숫자·표시를 바꾸지 않는다.

  1. 재료    TradingView get_symbol_data_batch(50종목당 1회) → radar/state/sector_select_in.json
             {"as_of": "YYYY-MM-DD"(시세 기준일), "q": {"NYSE:GEV": [close, Perf.W, Perf.1M, relvol10, avgvol10, avgvol30, high52, eps_fy], ...}}
             Chiip 바스켓의 30일 EPS 추정 변화는 knowledge/models/portfolio/sector_latest.json(Fiscal) rev30을 쓴다.
             나머지는 eps_fy 스냅숏(knowledge/models/portfolio/sector_eps_snap.json)이 eps_rev_days만큼 쌓인 뒤부터 쓴다(그 전엔 비움).
  2. 세 축   모멘텀 = 5·20일 상대강도(SPY 대비) · 52주 고점 근처 비율 · EPS 추정 변화 — 섹터 간 백분위 평균
             수급   = 10일/30일 평균 거래량 비 · 당일 상대 거래량 — 백분위 평균, 5일 주가가 마이너스면 반으로(내려가는 거래는 유입이 아니다)
             알파   = 구성 종목 Chiip 알파 상위 2개 평균 (4점 → 0, 8점 → 1)
             점수 = 10 × (0.40 모멘텀 + 0.35 수급 + 0.25 알파). 축 '켜짐' 조건은 config pillar_on.
  3. 판정    편입 = 점수 ≥ enter.score 이고 켜진 축 ≥ enter.pillars, 서로 다른 날 confirm_runs회 연속
             제외 = 점수 < exit.score 이고 켜진 축 ≤ exit.pillars(신호 꺾임), 같은 방식으로 연속 — 1회째는 '제외 예정'
             protect_status(기본 '보유') 종목의 섹터는 빼지 않고 '약세 지속'. 최대 max_sectors개(보호 섹터 먼저, 다음 점수순).
             같은 테마를 겹쳐 싣지 않는다: 구성 종목 2/3 이상이 겹치는 활성 섹터가 있으면 편입하지 않는다.
  4. 출력    knowledge/models/portfolio/sector_select_latest.json(섹터·표시·사유 문장) · sector_select_log.csv · radar/state/sector_select.json(연속 횟수)
사용: py scripts/portfolio/sector_select.py --symbols      # TradingView 요청할 기호 목록(50개씩)
      py scripts/portfolio/sector_select.py [--in 파일] [--dry]
연구용 시장 지표다 — 매매·비중 지시가 아니다.
"""
import csv
import json
import statistics
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
M = ROOT / "knowledge" / "models"
DIR = M / "portfolio"
IN = ROOT / "radar" / "state" / "sector_select_in.json"
STATE = ROOT / "radar" / "state" / "sector_select.json"
LATEST = DIR / "sector_select_latest.json"
LOG = DIR / "sector_select_log.csv"
SNAP = DIR / "sector_eps_snap.json"
KST = timezone(timedelta(hours=9))
COLS = ["close", "Perf.W", "Perf.1M", "relative_volume_10d_calc", "average_volume_10d_calc", "average_volume_30d_calc", "price_52_week_high", "earnings_per_share_forecast_next_fy"]


def _y(p):
    return yaml.safe_load(Path(p).read_text(encoding="utf-8")) or {}


def _j(p, default=None):
    try:
        return json.loads(Path(p).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {} if default is None else default


def cfg():
    return _y(ROOT / "config" / "sector_select.yaml")


def groups(c=None, mw=None):
    """{gid: {name, etf, members:[TV 기호], chiip}} — Chiip 바스켓 구성은 market_watch.yaml에서"""
    c = c or cfg()
    mw = mw if mw is not None else (_y(ROOT / "config" / "market_watch.yaml").get("sectors") or {})
    out = {}
    for gid, g in (c.get("groups") or {}).items():
        mem = list(g.get("members") or [])
        if g.get("chiip") and not mem:
            mem = [k.replace("_", ":", 1) for k in (mw.get(gid) or {}).get("keys", [])]
        out[gid] = {"name": g["name"], "etf": g.get("etf"), "members": mem, "chiip": bool(g.get("chiip"))}
    return out


def symbols(c=None):
    c = c or cfg()
    seen = [c.get("bench", "AMEX:SPY")]
    for g in groups(c).values():
        for s in ([g["etf"]] if g["etf"] else []) + g["members"]:
            if s not in seen:
                seen.append(s)
    return seen


def _row(v):
    """입력 한 줄 → dict. 리스트(COLS 순서) 또는 dict 모두 받는다. Perf는 % 단위(TradingView 그대로)"""
    if isinstance(v, dict):
        v = [v.get(k) for k in COLS]
    v = list(v) + [None] * (len(COLS) - len(v))
    return dict(zip(COLS, v))


def _med(xs):
    xs = [x for x in xs if x is not None]
    return statistics.median(xs) if xs else None


def alpha_map():
    """{TV 기호 또는 티커: 알파}"""
    sys.path.insert(0, str(ROOT / "scripts" / "discovery"))
    try:
        import alpha_gate
        t = alpha_gate.table()
    except Exception:  # noqa: BLE001 — 알파가 없으면 알파 축은 0(모르면 미확인, 없는 점수로 올리지 않는다)
        t = {}
    return {k.upper(): v for k, v in t.items() if v is not None}


def eps_revision(q, as_of, days, snap):
    """스냅숏을 갱신하고 {기호: days일 전 대비 eps_fy 변화}를 낸다. 그만큼 쌓이지 않았으면 비운다"""
    rev = {}
    cut = (datetime.fromisoformat(as_of) - timedelta(days=round(days * 7 / 5))).date().isoformat()   # 거래일 → 달력일
    for sym, r in q.items():
        e = r.get("earnings_per_share_forecast_next_fy")
        hist = [h for h in snap.get(sym, []) if h[0] != as_of]
        if e is not None:
            hist.append([as_of, e])
        hist = sorted(hist)[-60:]
        snap[sym] = hist
        old = [h for h in hist if h[0] <= cut]
        if e is not None and old and old[-1][1] and old[-1][1] > 0:
            rev[sym] = e / old[-1][1] - 1
    return rev


def metrics(gs, q, bench, rev30, rev_snap, amap, c):
    """섹터별 원재료 숫자"""
    b = q.get(bench) or {}
    b5, b20 = (b.get("Perf.W") or 0) / 100, (b.get("Perf.1M") or 0) / 100
    out = {}
    for gid, g in gs.items():
        mem = [q[s] | {"sym": s} for s in g["members"] if s in q and q[s].get("close") is not None]
        etf = q.get(g["etf"]) if g["etf"] else None
        if len(mem) < c.get("min_members", 3):
            out[gid] = {"name": g["name"], "n": len(mem), "status_data": "미확인"}
            continue
        r5 = _med([m.get("Perf.W") for m in mem]) / 100
        r20 = _med([m.get("Perf.1M") for m in mem]) / 100
        legs = mem + ([etf] if etf else [])
        turn = _med([m["average_volume_10d_calc"] / m["average_volume_30d_calc"] for m in legs
                     if m.get("average_volume_10d_calc") and m.get("average_volume_30d_calc")])
        relvol = _med([m.get("relative_volume_10d_calc") for m in legs])
        near = sum(1 for m in mem if m.get("price_52_week_high") and m["close"] >= c.get("near_high", 0.97) * m["price_52_week_high"])
        if g["chiip"] and rev30.get(gid) is not None:
            eps = rev30[gid]
        else:
            eps = _med([rev_snap.get(m["sym"]) for m in mem])
        al = sorted([a for a in (amap.get(m["sym"].upper(), amap.get(m["sym"].split(":")[-1].upper())) for m in mem) if a is not None], reverse=True)
        out[gid] = {"name": g["name"], "n": len(mem), "r5": round(r5, 4), "r20": round(r20, 4), "rs5": round(r5 - b5, 4), "rs20": round(r20 - b20, 4),
                    "near_high": near, "near_ratio": round(near / len(mem), 3), "turnover": round(turn, 3) if turn else None,
                    "relvol": round(relvol, 3) if relvol else None, "eps_rev": round(eps, 4) if eps is not None else None,
                    "alpha_n5": sum(1 for a in al if a >= 5), "alpha_max": al[0] if al else None,
                    "alpha_top2": round(sum(al[:2]) / len(al[:2]), 2) if al else None}
    return out, {"r5": round(b5, 4), "r20": round(b20, 4)}


def _pct(vals):
    """{k: 값} → {k: 백분위 0~1}(값 없는 칸은 빠진다). 같은 값은 평균 순위"""
    xs = sorted(v for v in vals.values() if v is not None)
    if len(xs) < 2:
        return {k: 0.5 for k, v in vals.items() if v is not None}
    out = {}
    for k, v in vals.items():
        if v is None:
            continue
        lo = sum(1 for x in xs if x < v)
        eq = sum(1 for x in xs if x == v)
        out[k] = (lo + (eq - 1) / 2) / (len(xs) - 1)
    return out


def score(mx, c):
    """세 축·점수·켜진 축"""
    ok = {k: v for k, v in mx.items() if "r5" in v}
    P = {f: _pct({k: v.get(f) for k, v in ok.items()}) for f in ["rs5", "rs20", "near_ratio", "eps_rev", "turnover", "relvol"]}
    w, on = c["weights"], c["pillar_on"]
    for k, v in ok.items():
        mom = [P[f][k] for f in ["rs5", "rs20", "near_ratio", "eps_rev"] if k in P[f]]
        flow = [P[f][k] for f in ["turnover", "relvol"] if k in P[f]]
        v["momentum"] = round(sum(mom) / len(mom), 3) if len(mom) >= 2 else None
        fl = sum(flow) / len(flow) if flow else None
        v["flow"] = round(fl * (1 if v["r5"] > 0 else 0.5), 3) if fl is not None else None
        # 알파 산정 종목이 하나도 없으면 0이 아니라 미확인 — 나머지 두 축으로 재정규화(AI 밖 섹터가 구조적으로 밀리지 않게)
        v["alpha"] = None if v.get("alpha_top2") is None else round(min(1.0, max(0.0, (v["alpha_top2"] - 4) / 4)), 3)
        pillars = []
        if v["momentum"] is not None and v["momentum"] >= on["momentum"]["pct"] and v["rs20"] > on["momentum"]["rs20_min"]:
            pillars.append("모멘텀")
        if v["flow"] is not None and fl >= on["flow"]["pct"] and (v.get("turnover") or 0) >= on["flow"]["turnover_min"] and v["r5"] > on["flow"]["r5_min"]:
            pillars.append("수급")
        if v["alpha_n5"] >= on["alpha"]["n_ge5"] or (v.get("alpha_max") or 0) >= on["alpha"]["max_ge"]:
            pillars.append("알파")
        v["pillars"] = pillars
        parts = [(w["momentum"], v["momentum"] or 0), (w["flow"], v["flow"] or 0)] + ([(w["alpha"], v["alpha"])] if v["alpha"] is not None else [])
        v["score"] = round(10 * sum(a * b for a, b in parts) / sum(a for a, _ in parts), 1)
    return mx


def protected(c, holdings=None, gs=None):
    """보호 섹터 {gid: [티커]} — protect_status 종목이 속한 섹터"""
    if holdings is None:
        holdings = _y(ROOT / "config" / "portfolio.yaml").get("holdings") or []
    hg = c.get("holding_group") or {}
    mw = _y(ROOT / "config" / "market_watch.yaml").get("sectors") or {}
    out = {}
    for h in holdings:
        if h.get("status") not in (c.get("protect_status") or ["보유"]):
            continue
        t = str(h.get("ticker"))
        gid = hg.get(t) or next((sid for sid, s in mw.items() if h.get("sub") and h.get("sub") in (s.get("sub") or [])), None)
        if gid:
            out.setdefault(gid, []).append(t)
    return out


def _overlap(a, b):
    a, b = set(a), set(b)
    return bool(a and b) and len(a & b) >= (2 / 3) * min(len(a), len(b))


def _josa(word, pair=("은", "는")):
    """받침이 있으면 은, 없으면 는"""
    ch = word.rstrip(")")[-1:]
    if "가" <= ch <= "힣":
        return pair[0] if (ord(ch) - 0xAC00) % 28 else pair[1]
    return pair[1]


def _f(x, nd=1):
    return f"{x * 100:+.{nd}f}".replace("-", "−")


def reason(v, tag):
    """사유 한 줄 — 숫자는 문장당 2개 이하(데일리 양식). 모델은 다듬을 수 있어도 숫자는 바꾸지 않는다"""
    if v.get("status_data") == "미확인":
        return "시세가 모자라 판단하지 못했습니다."
    parts = []
    if tag in ("신규 편입", "편입 후보"):
        if "모멘텀" in v["pillars"]:
            parts.append(f"한 달 주가가 S&P 500보다 {abs(v['rs20']) * 100:.1f}%p 앞섰습니다")
        if "수급" in v["pillars"]:
            parts.append(f"최근 10일 거래량이 한 달 평균의 {v['turnover']:.2f}배로 늘었습니다")
        if "알파" in v["pillars"]:
            parts.append(f"Chiip 알파 5점 이상 종목이 {v['alpha_n5']}곳 있습니다" if v["alpha_n5"] else f"Chiip 알파 {v['alpha_max']:.1f}점 종목이 있습니다")
        return ". ".join(parts[:2]) + "."
    if tag in ("제외 예정", "제외", "약세 지속"):
        lead = f"한 달 주가가 S&P 500보다 {abs(v['rs20']) * 100:.1f}%p {'뒤졌' if v['rs20'] < 0 else '앞섰'}고, 켜진 신호가 {len(v['pillars'])}개뿐입니다"
        tail = {"제외 예정": "다음 회차에도 같으면 뺍니다", "제외": "두 회차 연속 꺾여 뺍니다", "약세 지속": "보유 종목이 있어 계속 봅니다"}[tag]
        return f"{lead}. {tail}."
    # 유지 — 이익과 주가 방향
    if v.get("eps_rev") is not None:
        a = f"한 달 동안 주가는 {abs(v['r20']) * 100:.1f}% {'빠졌' if v['r20'] < 0 else '올랐'}"
        b = f"이익 추정은 {abs(v['eps_rev']) * 100:.1f}% {'올랐' if v['eps_rev'] >= 0 else '내렸'}습니다"
        joint = "지만" if (v["r20"] < 0) == (v["eps_rev"] >= 0) else "고"
        return f"{a}{joint} {b}."
    return f"한 달 주가가 S&P 500보다 {abs(v['rs20']) * 100:.1f}%p {'뒤처져' if v['rs20'] < 0 else '앞서'} 있습니다."


def decide(mx, st, as_of, c, prot, gs):
    """히스테리시스 판정 → (섹터 목록, 새 상태)"""
    st = {"active": dict(st.get("active") or {}), "streak": dict(st.get("streak") or {}), "dates": list(st.get("dates") or [])}
    if not st["active"] and not st["dates"]:
        st["active"] = {g: {"since": as_of, "by": "초기 고정 목록"} for g in c.get("bootstrap_active") or [] if g in gs}
    new_day = as_of not in st["dates"]
    en, ex, need = c["enter"], c["exit"], c.get("confirm_runs", 2)
    rows = []
    for gid, v in mx.items():
        if "score" not in v:
            continue
        ok_in = v["score"] >= en["score"] and len(v["pillars"]) >= en["pillars"]
        ok_out = v["score"] < ex["score"] and len(v["pillars"]) <= ex["pillars"]
        s = st["streak"].get(gid) or {"in": 0, "out": 0, "last": None}
        if new_day or s.get("last") != as_of:
            s = {"in": s["in"] + 1 if ok_in else 0, "out": s["out"] + 1 if ok_out else 0, "last": as_of}
        st["streak"][gid] = s
        rows.append((gid, v, s, ok_in, ok_out))
    out = []
    for gid, v, s, ok_in, ok_out in rows:
        act = gid in st["active"]
        if gid in prot:
            if not act:
                st["active"][gid] = {"since": as_of, "by": "보유 섹터"}
            tag = "약세 지속" if ok_out else ("신규 편입" if not act else "유지")
        elif act:
            if s["out"] >= need:
                tag = "제외"
            elif s["out"] == 1:
                tag = "제외 예정"
            else:
                tag = "유지"
        else:
            dup = next((a for a in st["active"] if a in gs and _overlap(gs[a]["members"], gs[gid]["members"])), None)
            if s["in"] >= need and not dup:
                tag = "신규 편입"
            elif s["in"] >= 1:
                tag = "편입 후보"
            else:
                continue
        out.append({"id": gid, "name": v["name"], "tag": tag, "protected": prot.get(gid, []), "score": v["score"], "pillars": v["pillars"],
                    "streak_in": s["in"], "streak_out": s["out"], **{k: v.get(k) for k in ["r5", "r20", "rs5", "rs20", "near_high", "n", "turnover", "relvol", "eps_rev", "alpha_n5", "alpha_max"]}})
    # 정원 — 보호 먼저, 다음 점수. 제외된 것은 뺀다
    keep = [r for r in out if r["tag"] not in ("제외", "편입 후보")]
    keep.sort(key=lambda r: (not r["protected"], -r["score"]))
    cap = c.get("max_sectors", 8)
    for r in keep[cap:]:
        r["tag"] = "제외" if r["id"] in st["active"] else "편입 후보"
        r["cap_cut"] = True
    for r in out:
        if r["tag"] == "제외":
            st["active"].pop(r["id"], None)
        elif r["tag"] == "신규 편입":
            st["active"].setdefault(r["id"], {"since": as_of, "by": "신호"})
        r["reason"] = ("정원(최대 %d개)이 차서 점수가 낮은 순으로 밀렸습니다." % cap) if r.get("cap_cut") else reason(r, r["tag"])
    if new_day:
        st["dates"] = (st["dates"] + [as_of])[-30:]
    order = {"신규 편입": 0, "약세 지속": 1, "유지": 1, "제외 예정": 2, "제외": 3, "편입 후보": 4}
    out.sort(key=lambda r: (order[r["tag"]], -r["score"]))
    return out, st


def run(path=IN, dry=False, c=None, holdings=None, state=None, today=None):
    c = c or cfg()
    data = _j(path)
    if not data.get("q"):
        raise SystemExit(f"입력 없음: {path} — --symbols 목록을 TradingView get_symbol_data_batch로 받아 저장")
    as_of = data.get("as_of") or (today or datetime.now(KST).date().isoformat())
    q = {k: _row(v) for k, v in data["q"].items()}
    gs = groups(c)
    sec = _j(DIR / "sector_latest.json")
    rev30 = {k: v.get("rev30") for k, v in (sec.get("sectors") or {}).items()}
    snap = _j(SNAP)
    rev_snap = eps_revision(q, as_of, c.get("eps_rev_days", 20), snap)
    mx, bench = metrics(gs, q, c.get("bench", "AMEX:SPY"), rev30, rev_snap, alpha_map(), c)
    score(mx, c)
    prot = protected(c, holdings)
    st = state if state is not None else _j(STATE)
    rows, st2 = decide(mx, st, as_of, c, prot, gs)
    shown = [r for r in rows if r["tag"] in ("신규 편입", "약세 지속", "유지", "제외 예정")]
    out = {"as_of": as_of, "made": datetime.now(KST).isoformat(timespec="seconds"), "bench": bench, "shown": shown,
           "watch": [r for r in rows if r["tag"] == "편입 후보"], "dropped": [r for r in rows if r["tag"] == "제외"],
           # 문턱 1점 안쪽인데 켜진 축이 하나뿐인 섹터 — '왜 아직 안 넣었나' 한 문장 재료
           "near": [{"id": k, "name": v["name"], "score": v["score"], "pillars": v["pillars"]} for k, v in sorted(mx.items(), key=lambda x: -(x[1].get("score") or 0))
                    if "score" in v and k not in st2["active"] and k not in {r["id"] for r in rows} and v["pillars"] and v["score"] >= c["enter"]["score"] - 1.0][:3],
           "all": {k: v for k, v in mx.items()}, "missing": sorted(set(symbols(c)) - set(q)),
           "note": "연구용 시장 지표 — 매매·비중 지시가 아님"}
    if not dry:
        DIR.mkdir(parents=True, exist_ok=True)
        LATEST.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
        SNAP.write_text(json.dumps(snap, ensure_ascii=False), encoding="utf-8")
        STATE.parent.mkdir(parents=True, exist_ok=True)
        STATE.write_text(json.dumps(st2, ensure_ascii=False, indent=1), encoding="utf-8")
        new = not LOG.exists()
        with LOG.open("a", encoding="utf-8", newline="") as f:
            w = csv.writer(f)
            if new:
                w.writerow(["as_of", "id", "tag", "score", "pillars", "rs20", "turnover", "eps_rev", "alpha_n5"])
            for r in rows:
                w.writerow([as_of, r["id"], r["tag"], r["score"], "+".join(r["pillars"]), r["rs20"], r["turnover"], r["eps_rev"], r["alpha_n5"]])
    return out


def lines(out):
    """데일리 '■ 섹터' 절 초안 — 줄마다 '이름 — 표시. 사유'"""
    ls = []
    for r in out["shown"]:
        tag = "" if r["tag"] == "유지" else f"{r['tag']}. "
        ls.append(f"{r['name']} — {tag}{r['reason']}")
    if out["watch"]:
        ls.append("다음 회차에도 신호가 이어지면 편입: " + ", ".join(r["name"] for r in out["watch"][:4]) + ".")
    for r in out["dropped"]:
        ls.append(f"{r['name']} — 제외. {r['reason']}")
    if out.get("near") and not out["watch"]:
        by = {}
        for r in out["near"]:
            by.setdefault(r["pillars"][0], []).append(r["name"])
        for p, names in by.items():
            miss = "거래가 늘지 않아" if p == "모멘텀" else "주가 흐름이 받쳐 주지 않아"
            ls.append(f"{', '.join(names)}{_josa(names[-1])} {p} 신호만 켜지고 {miss} 아직 넣지 않았습니다.")
    return ls


def main(argv):
    if "--symbols" in argv:
        s = symbols()
        print(json.dumps({"columns": COLS, "batches": [s[i:i + 50] for i in range(0, len(s), 50)]}, ensure_ascii=False))
        return
    p = Path(argv[argv.index("--in") + 1]) if "--in" in argv else IN
    out = run(p, dry="--dry" in argv)
    print(f"섹터 선정 {out['as_of']} — 표시 {len(out['shown'])} · 후보 {len(out['watch'])} · 제외 {len(out['dropped'])}" + (f" · 시세 없음 {len(out['missing'])}" if out["missing"] else ""))
    for ln in lines(out):
        print(ln)


if __name__ == "__main__":
    main(sys.argv[1:])
