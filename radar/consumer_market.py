"""Consumer Trends 판매 채널 층 — TickerTrends·Jungle Scout·FastMoss·Viral Launch (마스터 지시 2026-11-24).

결정론 수집만(모델 없음), run_hourly 하루 1회. 설정 config/consumer_market.yaml(원천별 접근 방법·경계는 거기 머리말).
  ① 원천별 상위 제품을 모아 브랜드 사전(config/consumer_trends.yaml discovery.brands)으로 상장사에 매핑
  ② knowledge/models/consumer_market/latest.json(git 제외, 유료·내부용)
  ③ 매핑된 브랜드 제품이 상위 N에 처음 들면 inbox src-consumer-market → Pulse '소비재'(internal_only)
키가 없는 원천은 '키 대기'로 건너뛴다. 키는 헤더로만 보내고 출력·오류에 쓰지 않는다.
사용: py radar/consumer_market.py [--show]
"""
import csv
import json
import re
import sys
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from pollers import common  # noqa: E402

OUT = common.ROOT / "knowledge" / "models" / "consumer_market"
JS = "https://developer.junglescout.com/api/product_database_query"
FM = "https://openapi.fastmoss.com/product/v1/rank/topSelling"


def config():
    return common.load_yaml("config/consumer_market.yaml") or {}


def brand_map():
    d = (common.load_yaml("config/consumer_trends.yaml") or {}).get("discovery") or {}
    out = []
    for b in d.get("brands") or []:
        for t in b.get("terms") or []:
            out.append((re.compile(r"(?<!\w)" + re.escape(re.sub(r"\s*\(.*\)$", "", t)) + r"(?!\w)", re.I), b["ticker"], b["name"]))
    return out


def match(text, bm):
    for rx, tk, nm in bm:
        if text and rx.search(text):
            return {"ticker": tk, "company": nm}
    return None


def post(url, body, headers):
    req = urllib.request.Request(url, data=json.dumps(body).encode(), headers={"User-Agent": common.UA, **headers}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read().decode("utf-8"))
    except Exception as exc:   # 키가 메시지에 섞이지 않게 종류만
        raise RuntimeError(f"호출 실패({type(exc).__name__})") from None


def junglescout(cfg, env):
    kn, k = env.get("JUNGLESCOUT_KEY_NAME"), env.get("JUNGLESCOUT_API_KEY")
    if not (kn and k):
        return None, "키 대기(JUNGLESCOUT_KEY_NAME·JUNGLESCOUT_API_KEY)"
    h = {"Authorization": f"{kn}:{k}", "X-API-Type": "junglescout", "Accept": "application/vnd.junglescout.v1+json", "Content-Type": "application/vnd.api+json"}
    rows = []
    for q in (cfg.get("queries") or [])[: int(cfg.get("max_calls", 30))]:
        attrs = {k2: v for k2, v in q.items() if k2 not in ("marketplace", "sort", "size")}
        url = f"{JS}?marketplace={q.get('marketplace', 'us')}&sort={q.get('sort', '-revenue')}&page[size]={q.get('size', 50)}"
        d = post(url, {"data": {"type": "product_database_query", "attributes": attrs}}, h)
        for i, x in enumerate(d.get("data") or [], 1):
            a = x.get("attributes") or {}
            rows.append({"src": "junglescout", "market": q.get("marketplace"), "category": ",".join(q.get("categories") or []), "rank": i,
                         "id": x.get("id"), "title": a.get("title"), "brand": a.get("brand"), "revenue": a.get("approximate_30_day_revenue"),
                         "units": a.get("approximate_30_day_units_sold"), "price": a.get("price")})
    return rows, None


def fastmoss(cfg, env):
    k = env.get("FASTMOSS_API_KEY")
    if not k:
        return None, "키 대기(FASTMOSS_API_KEY)"
    h = {"Authorization": f"Bearer {k}", "Content-Type": "application/json"}
    day = (common.now_kst().date()).isoformat()
    rows = []
    for reg in (cfg.get("regions") or ["US"])[: int(cfg.get("max_calls", 20))]:
        body = {"filter": {"region": reg, "date_info": {"type": "day", "value": day}}, "orderby": [{"field": cfg.get("orderby", "gmv"), "order": "desc"}],
                "page": 1, "pagesize": int(cfg.get("pagesize", 50))}
        d = post(FM, body, h)
        if d.get("code") not in (0, "0", 200, None):
            raise RuntimeError(f"FastMoss 응답 {str(d.get('code'))[:20]}")
        for i, x in enumerate((d.get("data") or {}).get("list") or [], 1):
            rows.append({"src": "fastmoss", "market": reg, "category": (x.get("category") or {}).get("name") if isinstance(x.get("category"), dict) else None,
                         "rank": i, "id": x.get("product_id"), "title": x.get("title"), "brand": (x.get("shop") or {}).get("name"),
                         "revenue": x.get("gmv"), "units": x.get("units_sold"), "growth_rate": x.get("growth_rate"), "price": x.get("real_price")})
    return rows, None


def _col(head, *names):
    for i, h in enumerate(head):
        if any(n in h.lower() for n in names):
            return i
    return None


def viral_launch(cfg):
    d = common.ROOT / cfg.get("drop_dir", "radar/drop/viral_launch")
    files = sorted(d.glob("*.csv")) if d.exists() else []
    if not files:
        return None, f"내보내기 대기({cfg.get('drop_dir', 'radar/drop/viral_launch')}에 CSV)"
    f = files[-1]
    with f.open(encoding="utf-8-sig", newline="") as fh:
        rd = list(csv.reader(fh))
    if not rd:
        return [], None
    head = rd[0]
    ix = {k: _col(head, *v) for k, v in {"title": ("product", "title", "name"), "brand": ("brand",), "id": ("asin",), "rank": ("rank", "bsr"),
                                          "revenue": ("revenue",), "units": ("sales", "units")}.items()}
    rows = []
    for n, r in enumerate(rd[1:], 1):
        g = {k: (r[i] if i is not None and i < len(r) else None) for k, i in ix.items()}
        rows.append({"src": "viral_launch", "market": "us", "category": f.stem, "rank": int(g["rank"]) if (g["rank"] or "").isdigit() else n,
                     "id": g["id"], "title": g["title"], "brand": g["brand"], "revenue": g["revenue"], "units": g["units"]})
    return rows, None


def tickertrends():
    f = common.ROOT / "knowledge" / "models" / "tickertrends" / "latest.json"
    if not f.exists():
        return None, "키 대기(TICKERTRENDS_API_KEY — radar/tickertrends.py)"
    sig = json.loads(f.read_text(encoding="utf-8")).get("signals") or {}
    return [{"src": "tickertrends", "id": k, "title": k.split("|")[0], "brand": k.split("|")[0], "signal": v} for k, v in sig.items()], None


def run():
    cfg, env, now = config(), common.load_env(), common.now_kst()
    bm = brand_map()
    OUT.mkdir(parents=True, exist_ok=True)
    f = OUT / "latest.json"
    old = json.loads(f.read_text(encoding="utf-8")) if f.exists() else {}
    seen_old = {(r["src"], r.get("market"), r.get("id")) for r in old.get("rows") or [] if r.get("rank") and r["rank"] <= cfg["alert"]["new_top"]}
    status, rows = {}, []
    jobs = {"tickertrends": tickertrends, "junglescout": lambda: junglescout(cfg.get("junglescout") or {}, env),
            "fastmoss": lambda: fastmoss(cfg.get("fastmoss") or {}, env), "viral_launch": lambda: viral_launch(cfg.get("viral_launch") or {})}
    for name, fn in jobs.items():
        try:
            r, wait = fn()
        except Exception as exc:
            status[name] = f"실패 {exc}"
            rows += [x for x in old.get("rows") or [] if x["src"] == name]   # 지난 값 유지
            continue
        if r is None:
            status[name] = wait
            continue
        for x in r:
            x["map"] = match(f"{x.get('brand') or ''} {x.get('title') or ''}", bm)
        rows += r
        status[name] = f"{len(r)}건"
    items = []
    if old:   # 첫 회차는 기준선만
        for x in rows:
            if x["src"] == "tickertrends" or not x.get("map") or (x.get("rank") or 99) > cfg["alert"]["new_top"]:
                continue
            if (x["src"], x.get("market"), x.get("id")) in seen_old:
                continue
            items.append(common.make_item("src-consumer-market", f"{x['src']}:{x.get('market')}:{x.get('id')}:{now.date()}", "",
                                          f"[판매 순위 진입] {x['map']['company']}({x['map']['ticker']}) — {x['src']} {x.get('market')} {x.get('category') or ''} {x['rank']}위: {(x.get('title') or '')[:60]}",
                                          common.iso(now), "대체 데이터", "ko", "채널 하나의 추정 순위 — 회사 매출 확정 아님",
                                          extra={"internal_only": True, "source_class": "판매 채널 대체 데이터(유료·내부용)"}))
    f.write_text(json.dumps({"as_of": common.iso(now), "status": status, "rows": rows}, ensure_ascii=False, indent=1), encoding="utf-8")
    saved = common.save_new_items(items)
    ok = not any(v.startswith("실패") for v in status.values())
    msg = " · ".join(f"{k} {v}" for k, v in status.items()) + f" · 알림 {len(saved)}"
    common.record_health("consumer_market", ok, msg)
    return msg


def board_lines():
    """주간 보드용 — 연결 상태와 매핑 건수만(유료 수치는 보드 파일에 옮기지 않는다)"""
    f = OUT / "latest.json"
    if not f.exists():
        return ["- 판매 채널 층: 아직 실행 전."]
    d = json.loads(f.read_text(encoding="utf-8"))
    mapped = {}
    for r in d.get("rows") or []:
        if r.get("map"):
            mapped.setdefault(r["map"]["company"], set()).add(r["src"])
    L = [f"- {k}: {v}" for k, v in (d.get("status") or {}).items()]
    if mapped:
        L.append("- 상장사 매핑(원천 수): " + ", ".join(f"{k}({len(v)})" for k, v in sorted(mapped.items(), key=lambda kv: -len(kv[1]))[:15]))
    L.append("- 수치는 유료·내부용이라 이 보드에 옮기지 않는다(knowledge/models/consumer_market/latest.json, git 제외).")
    return L


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    if "--show" in sys.argv:
        print("\n".join(board_lines()))
    else:
        print(run())
