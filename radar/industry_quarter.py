"""Chiip Industry Quarterly — 시즌·산업별 80% 관문·수집 (ADR-018, 마스터 결정 2026-11-08)

산업마다 따로 쓴다. 산업 구성 종목(config/industry_weekly.yaml 산업 = 감시 목록·알파 유니버스) 중 직전 TTM 매출(대략 달러) 기준 80%가
그 분기 실적을 냈거나 분기 말 + 55일이 지나면 그 산업의 분기 결산 리포트 차례가 된다. Pulse(radar/pulse.py)가 status()를 부른다.
수집(모델 — MCP는 스크립트가 직접 못 부른다):
  `--plan <산업>` → Fiscal 키가 있는 종목은 scripts/fiscal/templates/quarter_batch.js 본문, 없는 종목(한국·일본·대만 상당수)은 TradingView 심볼 목록
  → 출력 파일을 `--put <산업> <파일>`(Fiscal 배치) 또는 `--put-tv <산업> <파일>`(TradingView 재무 이력 [{id, labels, series}]) → members.csv
  `--broker <산업>` → 가이던스·재고가 빈 아시아 종목마다 국내 증권사 리포트를 인용한 기사 제목(Google News 한국판) 목록 — 모델이 Chiip 말로 요지를 적어 `--put-broker`
상태 radar/state/industry_quarter.json(쓴 산업), 장부 knowledge/models/industries/quarterly/<YYYYQn>/members.csv.
사용: py radar/industry_quarter.py [--status] · --plan <산업> · --put … · --put-tv … · --broker <산업> · --put-broker <산업> <파일> · --done <산업>
"""
import csv
import json
import sys
import urllib.parse
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
from pollers import common  # noqa: E402

ROOT = common.ROOT
CFG = ROOT / "config" / "industry_quarterly.yaml"
BASE = ROOT / "knowledge" / "models" / "industries" / "quarterly"
TPL = ROOT / "scripts" / "fiscal" / "templates" / "quarter_batch.js"
STATE = "industry_quarter"
KST = timezone(timedelta(hours=9))
FIELDS = ["industry", "id", "name", "key", "source", "currency", "period", "rev", "rev_prev_y", "rev_prev_q", "gp", "gp_prev_y", "op", "inventory", "inventory_prev_q",
          "capex", "capex_prev_y", "ttm_rev", "next_q_cons", "next_fy_cons", "cons_pre_q", "cons_pre_fy", "guide_note", "inventory_note", "broker_note", "broker_src", "car", "tone", "layer", "at"]
sys.path.insert(0, str(ROOT / "scripts" / "industry"))
sys.path.insert(0, str(ROOT / "scripts" / "tenbagger"))


def cfg():
    return yaml.safe_load(CFG.read_text(encoding="utf-8"))


def season_quarter(today=None):
    """다룰 분기 = 오늘 직전에 끝난 달력 분기 — (라벨 '2026Q3', 분기 말 날짜)"""
    today = today or date.today()
    q = (today.month - 1) // 3   # 이번 분기 번호-1 = 직전 분기
    y = today.year
    if q == 0:
        y, q = y - 1, 4
    end = {1: date(y, 3, 31), 2: date(y, 6, 30), 3: date(y, 9, 30), 4: date(y, 12, 31)}[q]
    return f"{y}Q{q}", end


def qlabel(period):
    import sync_view
    return sync_view.qlabel(str(period))[0]


def members():
    """산업 → 구성 종목. 세그먼트 풀이 정의된 산업(config/industry_segments.yaml)은 풀 회원 — 겸업 회사는 그 사업부만 센다(ADR-020)"""
    import industry_segments as S
    import weekly_pick
    m = dict(weekly_pick.members())
    for ind in (S.cfg().get("industry_pools") or {}):
        seen = {}
        for x in S.members(ind):
            if x["id"] in seen:
                seen[x["id"]]["share_hint"] = min(1.0, seen[x["id"]]["share_hint"] + x["share_hint"])
            else:
                seen[x["id"]] = dict(x)
        m[ind] = list(seen.values())
    return m


def industries():
    """분기 결산 대상 산업 id — 세그먼트 풀 산업 + 시장 세부 산업 묶음(풀 산업과 겹치는 묶음도 그대로 둔다)"""
    import industry_segments as S
    import weekly_pick
    return list((S.cfg().get("industry_pools") or {})) + [k for k in weekly_pick.cfg()["industries"] if k not in (S.cfg().get("industry_pools") or {})]


def industry_name(industry):
    import industry_segments as S
    import weekly_pick
    ip = (S.cfg().get("industry_pools") or {}).get(industry)
    return ip["name"] if ip else weekly_pick.cfg()["industries"][industry]["name"]


def keys():
    k = (yaml.safe_load((ROOT / "config" / "fiscal_keys.yaml").read_text(encoding="utf-8")) or {}).get("keys") or {}
    out = {i: (v or {}).get("key") for i, v in k.items() if (v or {}).get("key")}
    for i, v in ((yaml.safe_load((ROOT / "config" / "fiscal_ir_docs.yaml").read_text(encoding="utf-8")) or {}).get("extra") or {}).items():
        out.setdefault(i, v["key"] if isinstance(v, dict) else v)
    return out


def ledger_path(quarter):
    return BASE / quarter / "members.csv"


def load(quarter):
    p = ledger_path(quarter)
    if not p.exists():
        return {}
    with p.open(encoding="utf-8", newline="") as f:
        return {(r["industry"], r["id"]): r for r in csv.DictReader(f)}


def save(quarter, rows):
    p = ledger_path(quarter)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, FIELDS, extrasaction="ignore")
        w.writeheader()
        for r in sorted(rows.values(), key=lambda x: (x["industry"], x["id"])):
            w.writerow(r)


def _f(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def progress(industry, quarter=None, c=None):
    """(발표 비중, 발표 종목, 전체 종목, 가중 근거) — 달러 환산 TTM 매출 가중, 매출을 모르는 종목은 중앙값 가중"""
    c = c or cfg()
    quarter = quarter or season_quarter()[0]
    rows = load(quarter)
    ms = members().get(industry) or []
    w, rep = {}, set()
    for m in ms:
        r = rows.get((industry, m["id"])) or {}
        fx = c["fx_usd"].get((r.get("currency") or "USD").upper(), None)
        ttm = _f(r.get("ttm_rev"))
        w[m["id"]] = ttm * fx * m.get("share_hint", 1.0) if ttm and fx else None   # 겸업 회사는 그 산업 사업부 비중만큼만 무게
        if r.get("period") == quarter and _f(r.get("rev")):
            rep.add(m["id"])
    known = [v for v in w.values() if v]
    med = sorted(known)[len(known) // 2] if known else 1.0
    tot = sum(v or med for v in w.values()) or 1.0
    share = sum((w[i] or med) for i in rep) / tot
    return round(share, 3), len(rep), len(ms), "매출 가중" if known else "동일 가중"


def status(now=None, c=None):
    """Pulse 관문 — 80% 넘은(또는 마감 지난) 산업 중 아직 안 쓴 것"""
    c = c or cfg()
    now = now or datetime.now(KST)
    quarter, end = season_quarter(now.date())
    if now.date() < end + timedelta(days=14) or now.date() > end + timedelta(days=c["deadline_days"] + 14):   # 시즌 창 밖
        return {"due": False}
    st = common.load_state(STATE, {})
    last = (st.get("collected") or {}).get(quarter)
    done = set((common.load_state(STATE, {}).get("done") or {}).get(quarter, []))
    ready, prog = [], {}
    for k in industries():
        s, n, tot, _ = progress(k, quarter, c)
        prog[k] = s
        if k not in done and tot and (s >= c["gate_share"] or now.date() >= end + timedelta(days=c["deadline_days"])):
            ready.append(k)
    if ready:
        return {"due": True, "phase": "write", "quarter": quarter, "ready": ready, "progress": prog}
    if not last or datetime.fromisoformat(last) < now - timedelta(hours=24):   # 하루 한 번 수집 회차 — 관문을 재려면 먼저 모아야 한다
        return {"due": True, "phase": "collect", "quarter": quarter, "industries": [k for k in prog if k not in done], "progress": prog}
    return {"due": False, "quarter": quarter, "progress": prog}


def collected(quarter=None):
    st = common.load_state(STATE, {})
    st.setdefault("collected", {})[quarter or season_quarter()[0]] = datetime.now(KST).isoformat(timespec="minutes")
    common.save_state(STATE, st)


def plan(industry, quarter=None):
    ms = members().get(industry) or []
    ks = keys()
    def us(t):   # 'MU'·'WDC.US' → 미국 거래소 후보 키
        t = str(t or "").replace(".US", "")
        return [f"NASDAQ_{t}", f"NYSE_{t}"] if t and t.isalpha() and t.isupper() else None
    fis = [ks[m["id"]] if ks.get(m["id"]) else us(m["ticker"]) for m in ms if ks.get(m["id"]) or us(m["ticker"])]
    tv = [m for m in ms if not ks.get(m["id"]) and not us(m["ticker"])]
    body = TPL.read_text(encoding="utf-8")
    bodies = [body.replace("__KEYS__", json.dumps(fis[i:i + 6])) for i in range(0, len(fis), 6)]
    return bodies, [{"id": m["id"], "name": m["name"], "ticker": m["ticker"]} for m in tv]


def _yoy(q, i):
    """q는 최신순 — i번째 분기와 4분기 전"""
    return q[i + 4] if len(q) > i + 4 else None


def put(industry, path, quarter=None):
    quarter = quarter or season_quarter()[0]
    text = Path(path).read_text(encoding="utf-8")
    data = json.loads(text[text.index("["):text.rindex("]") + 1])
    by_key = {v: k for k, v in keys().items()}
    for m in members().get(industry) or []:   # 후보 키로 찾은 미국 종목
        t = str(m["ticker"] or "").replace(".US", "")
        if "_" in t:   # 세그먼트 풀 회원은 Fiscal 키 그대로
            by_key.setdefault(t, m["id"])
        for ex in ("NASDAQ_", "NYSE_"):
            by_key.setdefault(ex + t, m["id"])
    names = {m["id"]: m["name"] for m in members().get(industry) or []}
    rows, n = load(quarter), 0
    for d in data:
        cid = by_key.get(d.get("key"))
        if not cid or d.get("error") or not d.get("q"):
            continue
        q = d["q"]   # 최신순
        lab = qlabel(q[0]["period"]) if q[0].get("period") else None
        inv = {qlabel(x["period"]): x.get("inventory") for x in d.get("inv") or [] if x.get("period")}
        cap = {qlabel(x["period"]): x.get("capex") for x in d.get("capex") or [] if x.get("period")}
        prev_q = q[1] if len(q) > 1 else {}
        py = q[4] if len(q) > 4 else {}
        lab_py = qlabel(py["period"]) if py.get("period") else None
        lab_pq = qlabel(prev_q["period"]) if prev_q.get("period") else None
        r = rows.get((industry, cid)) or {"industry": industry, "id": cid}
        r.update({"name": names.get(cid, cid), "key": d["key"], "source": "Fiscal.ai", "currency": d.get("currency") or "USD", "period": lab,
                  "rev": q[0].get("rev"), "rev_prev_y": py.get("rev"), "rev_prev_q": prev_q.get("rev"), "gp": q[0].get("gp"), "gp_prev_y": py.get("gp"), "op": q[0].get("op"),
                  "inventory": inv.get(lab), "inventory_prev_q": inv.get(lab_pq), "capex": cap.get(lab), "capex_prev_y": cap.get(lab_py),
                  "ttm_rev": sum(x.get("rev") or 0 for x in q[:4]) or None,
                  "next_q_cons": (d.get("next_q") or {}).get("rev"), "next_fy_cons": (d.get("next_fy") or {}).get("rev"),
                  "at": datetime.now(KST).isoformat(timespec="minutes")})
        rows[(industry, cid)] = r
        n += 1
    save(quarter, rows)
    return n


def put_tv(industry, path, quarter=None):
    """TradingView mcp-tv-get-financial-history(fq) 응답을 [{id, currency, labels, series}]로 묶은 파일"""
    quarter = quarter or season_quarter()[0]
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    names = {m["id"]: m["name"] for m in members().get(industry) or []}
    rows, n = load(quarter), 0
    for d in data:
        labs, s = d["labels"], d["series"]   # 오래된 순, 'Q3 2026' = 회사 회계 분기 — period 끝 달은 모델이 d['period_end']로 준다
        if not labs:
            continue
        val = lambda k, i: ((s.get(k) or [None] * len(labs))[i] or {}).get("value") if (s.get(k) or [None] * len(labs))[i] else None
        i = len(labs) - 1
        r = rows.get((industry, d["id"])) or {"industry": industry, "id": d["id"]}
        r.update({"name": names.get(d["id"], d["id"]), "source": "TradingView", "currency": d.get("currency") or "USD",
                  "period": qlabel(d["period_end"]) if d.get("period_end") else None, "rev": val("revenue", i), "rev_prev_y": val("revenue", i - 4) if i >= 4 else None,
                  "rev_prev_q": val("revenue", i - 1) if i >= 1 else None, "gp": val("gross_profit", i), "gp_prev_y": val("gross_profit", i - 4) if i >= 4 else None,
                  "op": val("oper_income", i), "ttm_rev": sum(val("revenue", j) or 0 for j in range(max(0, i - 3), i + 1)) or None,
                  "at": datetime.now(KST).isoformat(timespec="minutes")})
        rows[(industry, d["id"])] = r
        n += 1
    save(quarter, rows)
    return n


def broker_queries(industry, quarter=None, c=None):
    """가이던스·재고가 빈 아시아 종목 → Google News 한국판 검색 주소(증권사 리포트 인용 기사 제목만)"""
    c = c or cfg()
    quarter = quarter or season_quarter()[0]
    rows = load(quarter)
    out = []
    for m in members().get(industry) or []:
        r = rows.get((industry, m["id"])) or {}
        if r.get("source") == "Fiscal.ai" and r.get("next_q_cons"):
            continue
        if r.get("guide_note") and r.get("inventory_note"):
            continue
        q = c["broker_public"]["query"].format(name=m["name"])
        out.append({"id": m["id"], "name": m["name"], "url": "https://news.google.com/rss/search?" + urllib.parse.urlencode({"q": q + " when:45d", "hl": "ko", "gl": "KR", "ceid": "KR:ko"})})
    return out


def fetch_broker(industry, quarter=None, c=None):
    """검색 주소마다 RSS 제목·링크·날짜만(최대 n) — 본문은 받지 않는다"""
    from pollers import rss
    c = c or cfg()
    out = []
    for q in broker_queries(industry, quarter, c):
        try:
            items = rss.parse_feed(common.http_get(q["url"], timeout=20))[: c["broker_public"]["max_items"]]
        except Exception as exc:
            items = [{"title": f"검색 실패 {type(exc).__name__}"}]
        out.append({**q, "items": [{"title": e.get("title"), "link": e.get("link"), "date": e.get("date")} for e in items]})
    return out


def put_broker(industry, path, quarter=None):
    """[{id, guide_note, inventory_note, broker_src}] — 요지는 Chiip 말로, broker_src는 '증권사·매체·날짜·링크'"""
    quarter = quarter or season_quarter()[0]
    rows = load(quarter)
    for d in json.loads(Path(path).read_text(encoding="utf-8")):
        r = rows.get((industry, d["id"])) or {"industry": industry, "id": d["id"]}
        for k in ("guide_note", "inventory_note", "broker_note", "broker_src", "tone", "car", "layer"):
            if d.get(k) is not None:
                r[k] = d[k]
        rows[(industry, d["id"])] = r
    save(quarter, rows)
    return len(rows)


def freeze_pre(industry, quarter=None):
    """시즌 전 기대 — knowledge/models/estimates/snapshots.csv(발표 전 동결분)에서 그 분기·다음 회계연도 매출 평균을 옮긴다"""
    quarter = quarter or season_quarter()[0]
    snap = ROOT / "knowledge" / "models" / "estimates" / "snapshots.csv"
    if not snap.exists():
        return 0
    with snap.open(encoding="utf-8", newline="") as f:
        sn = [r for r in csv.DictReader(f) if r["metric"] in ("revenue", "매출")]
    rows, n = load(quarter), 0
    for (ind, cid), r in rows.items():
        if ind != industry or not r.get("key"):
            continue
        cand = [s for s in sn if s["key"] == r["key"] and s.get("period") and qlabel(s["period"]) == quarter and (not s.get("report_date") or s["saved"] <= s["report_date"])]
        if cand:
            r["cons_pre_q"] = sorted(cand, key=lambda s: s["saved"])[-1]["mean"]
            n += 1
    save(quarter, rows)
    return n


def done(industry, quarter=None):
    quarter = quarter or season_quarter()[0]
    st = common.load_state(STATE, {})
    st.setdefault("done", {}).setdefault(quarter, [])
    if industry not in st["done"][quarter]:
        st["done"][quarter].append(industry)
    common.save_state(STATE, st)


def main(argv):
    sys.stdout.reconfigure(encoding="utf-8")
    q = season_quarter()[0]
    if "--plan" in argv:
        ind = argv[argv.index("--plan") + 1]
        bodies, tv = plan(ind)
        print(json.dumps({"quarter": q, "industry": ind, "fiscal_batches": len(bodies), "tradingview": tv}, ensure_ascii=False))
        for i, b in enumerate(bodies, 1):
            print(f"----- 묶음 {i}/{len(bodies)} (execute_code 본문) -----")
            print(b)
        return 0
    for flag, fn in (("--put", put), ("--put-tv", put_tv), ("--put-broker", put_broker)):
        if flag in argv:
            i = argv.index(flag)
            print(f"[분기 결산] {argv[i + 1]} {fn(argv[i + 1], argv[i + 2])}행")
            print(f"[시즌 전 기대] {freeze_pre(argv[i + 1])}종목")
            return 0
    if "--broker" in argv:
        print(json.dumps(fetch_broker(argv[argv.index("--broker") + 1]), ensure_ascii=False, indent=1))
        return 0
    if "--collected" in argv:
        collected()
        print("[분기 결산] 수집 회차 표시")
        return 0
    if "--done" in argv:
        done(argv[argv.index("--done") + 1])
        print("[분기 결산] 작성 표시")
        return 0
    s = status()
    print(json.dumps({**s, "quarter": q, "progress": {k: progress(k, q) for k in industries()}}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
