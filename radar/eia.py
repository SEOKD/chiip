"""EIA(미국 에너지정보청) 전력 통계 — Open Data API v2, 공공 저작물·무료 키 (마스터 승인 2026-11-09, TODO 21-41).

데이터센터 전력·가스터빈·엔진 수요의 1차 통계. 결정론 수집만(모델 없음), run_hourly 하루 1회.
  ① RTO(전력 계통 운영자) 일별 수요 — ERCOT·PJM·MISO·CAISO·SPP·NYISO·ISO-NE, 최근 28일 평균 전년 대비
  ② 주별 상업용 전력 판매(월별) — 데이터센터가 잡히는 상업 부문, 버지니아·텍사스·조지아·오하이오·애리조나·오리건·아이오와·일리노이, 전년 대비
  ③ 계획 중인 발전 설비(월별 발전기 목록) — 가스 터빈·왕복 엔진·배터리 계획 용량(MW) 합계와 전월 대비 변화
출력: knowledge/models/eia/latest.json · 큰 변화(①·② 전년 대비 +10% 이상 새 달, ③ 계획 용량 전월 대비 ±10% 이상)는 inbox src-eia → Pulse '정부'.
키: EIA_API_KEY(https://www.eia.gov/opendata/register.php) — 없으면 '키 대기'로 건너뛴다. 값은 출력하지 않는다.
사용: py radar/eia.py          # 수집·저장
      py radar/eia.py --show   # 저장된 요약
"""
import json
import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from pollers import common  # noqa: E402

API = "https://api.eia.gov/v2/"
OUT = common.ROOT / "knowledge" / "models" / "eia"
RTOS = ["ERCO", "PJM", "MISO", "CISO", "SWPP", "NYIS", "ISNE"]
STATES = ["VA", "TX", "GA", "OH", "AZ", "OR", "IA", "IL"]
TECH = {"Natural Gas Fired Combustion Turbine": "가스터빈(단순)", "Natural Gas Fired Combined Cycle": "가스 복합",
        "Natural Gas Internal Combustion Engine": "가스 엔진", "Batteries": "배터리"}
SURGE = 10.0


def _get(route, params, key):
    q = [("api_key", key)] + [(k, v) for k, vs in params.items() for v in (vs if isinstance(vs, list) else [vs])]
    import urllib.parse
    raw = common.http_get(API + route + "?" + urllib.parse.urlencode(q), timeout=60)
    return (json.loads(raw.decode("utf-8")).get("response") or {}).get("data") or []


def rto_demand(key, today):
    start = (today - timedelta(days=400)).isoformat()
    rows = _get("electricity/rto/daily-region-data/data/", {"frequency": "daily", "data[0]": "value", "facets[type][]": ["D"],
                "facets[respondent][]": RTOS, "facets[timezone][]": ["Eastern"], "start": start, "length": 5000}, key)
    out = {}
    for r in RTOS:
        v = {x["period"]: float(x["value"]) for x in rows if x.get("respondent") == r and x.get("value") is not None}
        if not v:
            continue
        last = max(v)
        d = date.fromisoformat(last)
        cur = [v.get((d - timedelta(days=i)).isoformat()) for i in range(28)]
        prev = [v.get((d - timedelta(days=364 + i)).isoformat()) for i in range(28)]
        cur, prev = [x for x in cur if x], [x for x in prev if x]
        if len(cur) >= 20 and len(prev) >= 20:
            out[r] = {"as_of": last, "avg_mwh": round(sum(cur) / len(cur)), "yoy_pct": round((sum(cur) / len(cur)) / (sum(prev) / len(prev)) * 100 - 100, 1)}
    return out


def commercial_sales(key):
    rows = _get("electricity/retail-sales/data/", {"frequency": "monthly", "data[0]": "sales", "facets[sectorid][]": ["COM"],
                "facets[stateid][]": STATES, "sort[0][column]": "period", "sort[0][direction]": "desc", "length": 400}, key)
    out = {}
    for s in STATES:
        v = {x["period"]: float(x["sales"]) for x in rows if x.get("stateid") == s and x.get("sales") is not None}
        if not v:
            continue
        last = max(v)
        y, m = map(int, last.split("-"))
        ly = f"{y - 1}-{m:02d}"
        if ly in v and v[ly]:
            out[s] = {"period": last, "gwh": round(v[last] / 1000, 1), "yoy_pct": round(v[last] / v[ly] * 100 - 100, 1)}
    return out


def planned_capacity(key):
    rows = _get("electricity/operating-generator-capacity/data/", {"frequency": "monthly", "data[0]": "nameplate-capacity-mw",
                "facets[status][]": ["P", "L", "T", "U", "V"], "facets[technology][]": list(TECH),
                "sort[0][column]": "period", "sort[0][direction]": "desc", "length": 5000}, key)
    periods = sorted({x["period"] for x in rows}, reverse=True)[:2]
    out = {}
    for t, ko in TECH.items():
        tot = [round(sum(float(x["nameplate-capacity-mw"] or 0) for x in rows if x["period"] == p and x.get("technology") == t)) for p in periods]
        if tot:
            out[ko] = {"period": periods[0], "mw": tot[0], "prev_mw": tot[1] if len(tot) > 1 else None,
                       "mom_pct": round(tot[0] / tot[1] * 100 - 100, 1) if len(tot) > 1 and tot[1] else None}
    return out


def alerts(new, old):
    items, now = [], common.iso(common.now_kst())
    for r, v in (new.get("rto") or {}).items():
        if v["yoy_pct"] >= SURGE and (old.get("rto") or {}).get(r, {}).get("as_of", "")[:7] != v["as_of"][:7]:
            items.append((f"rto-{r}-{v['as_of'][:7]}", f"[EIA] {r} 계통 수요 최근 28일 전년 대비 {v['yoy_pct']:+.1f}%", f"일평균 {v['avg_mwh']:,} MWh · 기준 {v['as_of']}"))
    for s, v in (new.get("sales") or {}).items():
        if v["yoy_pct"] >= SURGE and (old.get("sales") or {}).get(s, {}).get("period") != v["period"]:
            items.append((f"com-{s}-{v['period']}", f"[EIA] {s} 상업용 전력 판매 {v['period']} 전년 대비 {v['yoy_pct']:+.1f}%", f"{v['gwh']:,} GWh — 데이터센터가 잡히는 부문"))
    for t, v in (new.get("planned") or {}).items():
        if v.get("mom_pct") is not None and abs(v["mom_pct"]) >= SURGE and (old.get("planned") or {}).get(t, {}).get("period") != v["period"]:
            items.append((f"plan-{t}-{v['period']}", f"[EIA] 계획 발전 설비 {t} {v['period']} {v['mw']:,} MW(전월 대비 {v['mom_pct']:+.1f}%)", "EIA-860M 계획·인허가·건설 중 합계"))
    return [common.make_item("src-eia", uid, "https://www.eia.gov/opendata/", t, now, "정부", "ko", s, extra={"source_class": "정부"}) for uid, t, s in items]


def run():
    key = common.load_env().get("EIA_API_KEY")
    if not key:
        return "키 대기(EIA_API_KEY) — docs/TODO_MASTER.md 21-41"
    today = common.now_kst().date()
    OUT.mkdir(parents=True, exist_ok=True)
    f = OUT / "latest.json"
    old = json.loads(f.read_text(encoding="utf-8")) if f.exists() else {}
    new, errs = {"as_of": today.isoformat()}, []
    for k, fn in (("rto", lambda: rto_demand(key, today)), ("sales", lambda: commercial_sales(key)), ("planned", lambda: planned_capacity(key))):
        try:
            new[k] = fn()
        except Exception as exc:
            errs.append(f"{k} {type(exc).__name__}")
            new[k] = old.get(k) or {}
    f.write_text(json.dumps(new, ensure_ascii=False, indent=1), encoding="utf-8")
    saved = common.save_new_items(alerts(new, old)) if old else []
    return f"EIA 저장 RTO {len(new['rto'])}·주 {len(new['sales'])}·설비 {len(new['planned'])} · 알림 {len(saved)}" + (f" · 실패 {', '.join(errs)}" if errs else "")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    if "--show" in sys.argv:
        p = OUT / "latest.json"
        print(p.read_text(encoding="utf-8") if p.exists() else "저장 없음")
    else:
        print(run())
