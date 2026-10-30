"""Chiip Consumer — 소비재·게임·콘텐츠IP 국면 판정·점수 (마스터 지시 2026-10-30, 렌즈 knowledge/methods/consumer_lens.md).

AI·방위(공급 병목)와 달리 수요가 실제로 팔려 나가는지와 그 여력을 본다:
  구조적 성장  — N개 기간 연속 매출 +20% 이상 + 매출총이익률 유지·개선
  상승 사이클 진입 — 최근 YoY − 직전 4개 기간 평균 YoY ≥ +10%p
  사이클 후반 경고 — 투자자 관심 쏠림 상위 10% + 성장 감속 + 재고 증가율이 매출보다 15%p 이상 빠름
  여력 — 쏠림 낮음 + 같은 지도 안 EV/매출 ÷ 성장이 싸다
입력: config/consumer.yaml(지도·문턱·가중치) · knowledge/models/consumer/fundamentals.json(Fiscal.ai consumer.js → --put, 또는 회사 결산 자료 --put-q)
      · knowledge/models/consumer/attention_latest.json(radar/consumer_attention.py 수요) · knowledge/models/discovery/attention_latest.json(radar/attention.py 리테일·투자자)
출력: outputs/discovery/consumer_<YYYYMMDD>.md · knowledge/models/consumer/latest.json(watch·국면·전환). 점수는 판단 보조 — 매수 권유 아님.
사용: py scripts/discovery/consumer.py                     # 판정·출력
      py scripts/discovery/consumer.py --stale [일수]        # Fiscal 키가 있는데 펀더멘털이 없거나 오래된 종목 'id 키'
      py scripts/discovery/consumer.py --code <id>          # consumer.js 본보기에 키를 채워 출력
      py scripts/discovery/consumer.py --put <id> <파일>     # consumer.js 출력 저장
      py scripts/discovery/consumer.py --kabutan [id…]      # 일본 종목 분기 매출·영업이익 — 株探 무료 표(Fiscal에 일본 소비재 재무가 없다)
      py scripts/discovery/consumer.py --put-q <id> <기말일 YYYY-MM-DD> revenue=… [gross_profit=… inventory=… overseas_share=…] --src <원문 URL> [--currency JPY]
"""
import json
import sys
from datetime import date
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
DIR = ROOT / "knowledge" / "models" / "consumer"
FUND = DIR / "fundamentals.json"
LATEST = DIR / "latest.json"
OUTD = ROOT / "outputs" / "discovery"
PHASE_KO = {"structural": "구조적 성장", "upcycle": "상승 사이클 진입", "late": "사이클 후반 경고", "neutral": "중립", "nodata": "자료 부족"}


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


def metrics(q):
    """분기·반기·연간 표 → 성장·가속·연속·이익률 변화·재고 괴리. YoY 간격 = 365일 ÷ 기간 간격 중앙값(분기 4·반기 2·연간 또는 같은 분기만 1)"""
    q = sorted((r for r in q if r.get("revenue")), key=lambda r: r["period"])
    if len(q) < 3:
        return {}
    gaps = sorted((date.fromisoformat(b["period"]) - date.fromisoformat(a["period"])).days for a, b in zip(q, q[1:]))
    step = max(1, min(4, round(365 / max(gaps[len(gaps) // 2], 1))))
    yoy = [(q[i]["revenue"] / q[i - step]["revenue"] - 1) if i >= step and q[i - step]["revenue"] else None for i in range(len(q))]
    ys = [y for y in yoy if y is not None]
    if not ys:
        return {"step": step, "periods": len(q)}
    m = {"step": step, "periods": len(q), "growth": ys[-1], "yoy": [round(y, 3) for y in ys[-6:]], "last_period": q[-1]["period"]}
    prev = ys[-5:-1]
    m["accel"] = ys[-1] - sum(prev) / len(prev) if prev else None
    gmin = (_y("config/consumer.yaml").get("phase") or {}).get("structural", {}).get("min_growth", 0.20)
    run = 0
    for y in reversed(ys):
        if y < gmin:
            break
        run += 1
    m["persistence"] = run

    def ttm_margin(end, field):
        rows = q[max(0, end - step + 1):end + 1]
        if len(rows) < step or any(r.get(field) is None for r in rows):
            return None
        return sum(r[field] for r in rows) / sum(r["revenue"] for r in rows)
    # 매출총이익률이 없으면(株探 무료 표 등) 영업이익률로 대신하고 기준을 적는다
    for field, basis in (("gross_profit", "GPM"), ("operating_profit", "OPM")):
        now, ago = ttm_margin(len(q) - 1, field), ttm_margin(len(q) - 1 - step, field)
        if now is not None:
            break
    m["gm"], m["margin_basis"] = now, basis if now is not None else None
    m["gm_change"] = now - ago if now is not None and ago is not None else None
    a, b = q[-1].get("inventory"), q[-1 - step].get("inventory") if len(q) > step else None
    m["inv_gap"] = (a / b - 1) - ys[-1] if a and b else None
    os_now, os_ago = q[-1].get("overseas_share"), q[-1 - step].get("overseas_share") if len(q) > step else None
    m["overseas_share"] = os_now
    m["overseas_change"] = os_now - os_ago if os_now is not None and os_ago is not None else None
    return m


def valuation_rank(rows):
    """같은 지도 안 EV/매출 ÷ 성장(성장 5% 하한) — 싼 쪽 10점"""
    pts = sorted((r["id"], r["ev_sales"] / max(r["growth"], 0.05)) for r in rows if r.get("ev_sales") and r.get("growth") is not None)
    order = sorted(pts, key=lambda x: x[1])
    n = len(order)
    return {cid: (10.0 if n == 1 else 10.0 - 9.0 * i / (n - 1)) for i, (cid, _) in enumerate(order)}


def evaluate(cfg=None, fund=None, demand=None, retail=None, prev=None):
    cfg = cfg or _y("config/consumer.yaml")
    fund = _j(FUND) if fund is None else fund
    demand = (_j(DIR / "attention_latest.json").get("rows") or {}) if demand is None else demand
    retail = (_j(ROOT / "knowledge" / "models" / "discovery" / "attention_latest.json").get("rows") or {}) if retail is None else retail
    prev = (_j(LATEST).get("rows") or {}) if prev is None else prev
    ph, w = cfg.get("phase") or {}, cfg.get("weights") or {}
    rows = []
    for co in cfg.get("companies") or []:
        f = fund.get(co["id"]) or {}
        m = metrics(f.get("q") or [])
        rows.append({"id": co["id"], "name": co["name"], "market": co["market"], "code": co["code"], "segment": co.get("segment"),
                     "ev_sales": f.get("ev_sales"), "as_of": f.get("as_of"), "fund_source": f.get("source"), **m})
    val = valuation_rank(rows)
    for r in rows:
        d, a = demand.get(r["id"]) or {}, retail.get(r["id"]) or {}
        crowd = a.get("crowding_pct")
        comp = {"growth": lin(r.get("growth"), 0.0, 2.0, 0.5, 10.0), "accel": lin(r.get("accel"), -0.10, 2.0, 0.20, 10.0),
                "persistence": lin(r.get("persistence"), 0, 2.0, 6, 10.0) if "persistence" in r else None,
                "margin": lin(r.get("gm_change"), -0.03, 2.0, 0.04, 10.0),
                "sell_through": lin(-r["inv_gap"], -0.20, 1.0, 0.15, 10.0) if r.get("inv_gap") is not None else None,
                "demand_attention": lin(d.get("demand_accel"), 0.7, 2.0, 2.0, 10.0), "retail_buzz": lin(a.get("accel"), 0.5, 2.0, 3.0, 10.0)}
        run = [x for x in (None if crowd is None else 10.0 - crowd / 10.0, val.get(r["id"]),
                           lin(r.get("overseas_change"), -0.02, 2.0, 0.05, 10.0)) if x is not None]
        comp["runway"] = sum(run) / len(run) if run else None
        have = {k: v for k, v in comp.items() if v is not None and w.get(k)}
        tw = sum(w[k] for k in have)
        r["components"] = {k: (round(v, 1) if v is not None else None) for k, v in comp.items()}
        r["score"] = round(sum(w[k] * v for k, v in have.items()) / tw, 1) if tw else None
        r["coverage"] = round(tw, 2)
        r["demand_accel"], r["crowding_pct"] = d.get("demand_accel"), crowd
        if "growth" not in r:
            r["phase"] = "nodata"
        elif crowd is not None and crowd >= ph.get("late", {}).get("crowding_pct", 90) and (r.get("accel") or 0) < 0 \
                and (r.get("inv_gap") or 0) >= ph.get("late", {}).get("inv_gap_pp", 0.15):
            r["phase"] = "late"
        elif r.get("persistence", 0) >= ph.get("structural", {}).get("min_periods", 4) and (r.get("gm_change") is None or r["gm_change"] >= -ph.get("structural", {}).get("max_gm_drop", 0.02)):
            r["phase"] = "structural"
        elif (r.get("accel") or 0) >= ph.get("upcycle", {}).get("accel_pp", 0.10) and r["growth"] > 0:
            r["phase"] = "upcycle"
        else:
            r["phase"] = "neutral"
        r["runway"] = comp["runway"] is not None and comp["runway"] >= 6.0
        was = (prev.get(r["id"]) or {}).get("phase")
        r["transition"] = f"{PHASE_KO.get(was, was)} → {PHASE_KO[r['phase']]}" if was and was != r["phase"] else None
    wmin = ph.get("watch_min", 6.0)
    watch = [r["id"] for r in rows if r["phase"] != "late" and ((r["score"] or 0) >= wmin or r["phase"] in ("structural", "upcycle"))]
    return sorted(rows, key=lambda r: -(r["score"] or 0)), watch


def _pct(x):
    return "—" if x is None else f"{x * 100:+.0f}%"


def render(rows, watch, today):
    out = [f"# Chiip Consumer 국면 판정 {today}", "", "> 소비재·게임·콘텐츠IP — 수요가 팔려 나가는가와 여력(knowledge/methods/consumer_lens.md). 점수는 판단 보조, 연구 후보이지 매수 권유 아님.", "",
           "| 종목 | 시장 | 국면 | 점수 | 성장 | 가속 | 연속 | 이익률 변화 | 재고 괴리 | 수요 가속 | 쏠림 | 여력 | 자료 |", "|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for r in rows:
        out.append(f"| {r['name']} ({r['code']}) | {r['market']} | {PHASE_KO[r['phase']]}{' ⚑' if r.get('transition') else ''} | {r['score'] if r['score'] is not None else '—'} "
                   f"| {_pct(r.get('growth'))} | {('%+.0f%%p' % (r['accel'] * 100)) if r.get('accel') is not None else '—'} | {r.get('persistence', '—')} "
                   f"| {('%+.1f%%p ' % (r['gm_change'] * 100) + r['margin_basis']) if r.get('gm_change') is not None else '—'} | {('%+.0f%%p' % (r['inv_gap'] * 100)) if r.get('inv_gap') is not None else '—'} "
                   f"| {r.get('demand_accel') or '—'} | {r.get('crowding_pct') if r.get('crowding_pct') is not None else '—'} | {'예' if r['runway'] else '—'} "
                   f"| {r.get('last_period') or '펀더멘털 없음'} · 가중치 {r['coverage']} |")
    tr = [r for r in rows if r.get("transition")]
    out += ["", f"watch {len(watch)}: " + (", ".join(watch) or "없음")]
    if tr:
        out += ["", "## 국면 전환"] + [f"- {r['name']}: {r['transition']}" for r in tr]
    miss = [r["name"] for r in rows if r["phase"] == "nodata"]
    if miss:
        out += ["", "## 펀더멘털 없음(회사 결산 자료로 --put-q 필요)", ", ".join(miss)]
    return "\n".join(out) + "\n"


def run(today=None):
    today = today or date.today().isoformat()
    rows, watch = evaluate()
    DIR.mkdir(parents=True, exist_ok=True)
    OUTD.mkdir(parents=True, exist_ok=True)
    LATEST.write_text(json.dumps({"date": today, "watch": watch, "transitions": [r["id"] for r in rows if r.get("transition")],
                                  "rows": {r["id"]: r for r in rows}}, ensure_ascii=False, indent=1), encoding="utf-8")
    path = OUTD / f"consumer_{today.replace('-', '')}.md"
    path.write_text(render(rows, watch, today), encoding="utf-8")
    return path, rows, watch


def put(cid, data):
    fund = _j(FUND)
    fund[cid] = {"as_of": date.today().isoformat(), "source": data.get("source"), "key": data.get("key"), "currency": data.get("currency"),
                 "q": data.get("q") or [], "mcap": data.get("mcap"), "ev_sales": data.get("ev_sales"), "n_analysts": data.get("n_analysts")}
    DIR.mkdir(parents=True, exist_ok=True)
    FUND.write_text(json.dumps(fund, ensure_ascii=False, indent=1), encoding="utf-8")


def put_q(cid, period, kv, src, currency=None):
    """회사 결산 자료(決算短信·사업보고서·실적 발표)에서 모델이 읽은 한 기간 — 출처 URL 필수"""
    if not src:
        raise SystemExit("--src(원문 URL)가 없으면 넣지 않는다")
    fund = _j(FUND)
    f = fund.setdefault(cid, {"source": "회사 결산 자료", "q": []})
    row = next((r for r in f["q"] if r["period"] == period), None) or {"period": period}
    row.update({k: float(v) for k, v in kv.items()})
    row["src"] = src
    f["q"] = sorted([r for r in f["q"] if r["period"] != period] + [row], key=lambda r: r["period"])
    f["as_of"], f["currency"] = date.today().isoformat(), currency or f.get("currency")
    DIR.mkdir(parents=True, exist_ok=True)
    FUND.write_text(json.dumps(fund, ensure_ascii=False, indent=1), encoding="utf-8")


def kabutan_quarters(page):
    """株探 종목 재무 페이지의 무료 표(3개월 결산 실적 — 매출·영업이익, 성장성 — 매출 20개 분기) → [{period, revenue, operating_profit}] (백만 엔)"""
    import calendar
    import re
    import html as htmllib
    txt = re.sub(r"\s+", " ", htmllib.unescape(re.sub(r"<[^>]+>", " ", page)))   # &nbsp;가 칸 사이에 끼어 있다
    out = {}
    num = lambda s: None if s in ("－", "-", "") else float(s.replace(",", ""))

    def end(yy, m1, m2):
        y = 2000 + int(yy) + (1 if int(m2) < int(m1) else 0)
        return f"{y}-{int(m2):02d}-{calendar.monthrange(y, int(m2))[1]:02d}"
    i = txt.find("3ヵ月決算")
    if i >= 0:
        seg = txt[i:txt.find("前年同期比", i)]
        for m in re.finditer(r"(\d\d)\.(\d\d)-(\d\d) ([\d,]+|－) (-?[\d,]+|－)", seg):
            out[end(*m.group(1, 2, 3))] = {"revenue": num(m.group(4)), "operating_profit": num(m.group(5))}
    g = re.search(r"決算期 売上高 前年 ?同期比 営業益", txt)   # 성장성 표(매출은 무료, 이익 칸은 유료 — 읽지 않는다)
    if g:
        for m in re.finditer(r"(\d\d)\.(\d\d)-(\d\d) ([\d,]+) [+\-]?[\d.]+", txt[g.start():g.start() + 6000]):
            out.setdefault(end(*m.group(1, 2, 3)), {"revenue": num(m.group(4))})
    return [dict(period=k, **v) for k, v in sorted(out.items()) if v.get("revenue")]


def kabutan(ids=None):
    """일본 소비재 지도 종목의 분기 매출·영업이익 — 株探 무료 표(robots 허용, Crawl-delay 3초). 유료(프리미엄) 영역은 읽지 않는다"""
    import time
    import urllib.request
    cfg, fund, done = _y("config/consumer.yaml"), _j(FUND), []
    ua = (cfg.get("attention") or {}).get("user_agent") or "Chiip research"
    for co in cfg.get("companies") or []:
        if co.get("market") != "jp" or (ids and co["id"] not in ids):
            continue
        url = f"https://kabutan.jp/stock/finance?code={co['code']}"
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": ua}), timeout=30) as r:
                q = kabutan_quarters(r.read().decode("utf-8", "ignore"))
        except Exception as exc:
            print(co["id"], "실패", type(exc).__name__)
            continue
        if q:
            f = fund.get(co["id"]) or {}
            manual = {r["period"]: r for r in f.get("q") or [] if r.get("src") and "kabutan" not in r["src"]}
            rows = [dict(r, src=url) for r in q if r["period"] not in manual] + list(manual.values())   # 회사 원문(--put-q)이 우선
            fund[co["id"]] = {"as_of": date.today().isoformat(), "source": "株探 무료 표(백만 엔) + 회사 결산 자료", "currency": "JPY",
                              "q": sorted(rows, key=lambda r: r["period"])}
            done.append(co["id"])
        time.sleep(3)
    DIR.mkdir(parents=True, exist_ok=True)
    FUND.write_text(json.dumps(fund, ensure_ascii=False, indent=1), encoding="utf-8")
    return done


def main(argv):
    sys.stdout.reconfigure(encoding="utf-8")
    cfg = _y("config/consumer.yaml")
    by = {c["id"]: c for c in cfg.get("companies") or []}
    if argv[:1] == ["--stale"]:
        days, fund = int(argv[1]) if len(argv) > 1 else 7, _j(FUND)
        for cid, c in by.items():
            a = (fund.get(cid) or {}).get("as_of")
            if c.get("fiscal") and (not a or (date.today() - date.fromisoformat(a)).days > days):
                print(cid, c["fiscal"])
        return 0
    if argv[:1] == ["--code"]:
        print((ROOT / "scripts" / "fiscal" / "templates" / "consumer.js").read_text(encoding="utf-8").replace("__KEY__", by[argv[1]]["fiscal"]))
        return 0
    if argv[:1] == ["--kabutan"]:
        print("株探", kabutan(argv[1:] or None))
        return 0
    if argv[:1] == ["--put"]:
        put(argv[1], json.loads(Path(argv[2]).read_text(encoding="utf-8")))
        print("저장", argv[1])
        return 0
    if argv[:1] == ["--put-q"]:
        kv = dict(a.split("=", 1) for a in argv[3:] if "=" in a and not a.startswith("--"))
        src = argv[argv.index("--src") + 1] if "--src" in argv else None
        cur = argv[argv.index("--currency") + 1] if "--currency" in argv else None
        put_q(argv[1], argv[2], kv, src, cur)
        print("저장", argv[1], argv[2])
        return 0
    path, rows, watch = run()
    print(path.relative_to(ROOT), f"· {len(rows)}종목 · watch {len(watch)} · 전환 {sum(1 for r in rows if r.get('transition'))}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
