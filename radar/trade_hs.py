"""HS 품목별 수출입 시계열 저장소와 급등 품목 산출 (마스터 지시 2026-11-02 "데이터 수집 체계를 갖춰라. 오로지 파이프라인만")

공식 공개 통계만 쓴다. 다른 서비스의 데이터·내부 구조는 쓰지 않는다. 품목별 현재 지표는 radar/trade_ppi.py, 이 파일은 전 품목 시계열이다.
- 미국 Census: 호출 한 번에 HS 6단위 전 품목. 관심 품목 목록도 여기서 만든다
- EU Comext: 관심 장(config hs_scan.chapters)의 HS 6단위를 묶어 조회, EU 역외 합계
- 일본 e-Stat: 관심 장의 수입, 나라별
- 대만·홍콩: 공개된 분류 단위(HS 류, SITC 대분류)
저장 radar/state/trade_hs.sqlite(git 제외). 급등 결과 knowledge/models/trade_ppi/surge.json. 값은 원 단위 그대로 두고 나라끼리 더하지 않는다.
사용: py radar/trade_hs.py --run · --status · --surge [n] · --series <hs> · --company <회사 id>
"""
import argparse
import json
import sqlite3
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from pollers import common  # noqa: E402
import trade_ppi as tp  # noqa: E402

DB = common.ROOT / "radar" / "state" / "trade_hs.sqlite"
SURGE = common.ROOT / "knowledge" / "models" / "trade_ppi" / "surge.json"
FLOWS = {"import": ("imports", "I_COMMODITY", "GEN_VAL_MO", 1), "export": ("exports", "E_COMMODITY", "ALL_VAL_MO", 2)}
WORLD = "WORLD"
CHUNK = 50
PAUSE = 0.4


def scan_config():
    return tp.config()["hs_scan"]


def connect(path=DB):
    path.parent.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(path)
    c.execute("CREATE TABLE IF NOT EXISTS obs(reporter TEXT, flow TEXT, partner TEXT, hs TEXT, period TEXT, value REAL, unit TEXT, PRIMARY KEY(reporter, flow, partner, hs, period))")
    c.execute("CREATE TABLE IF NOT EXISTS names(hs TEXT PRIMARY KEY, name TEXT)")
    return c


def store(c, rows):
    c.executemany("INSERT OR REPLACE INTO obs VALUES(?,?,?,?,?,?,?)", rows)
    c.commit()
    return len(rows)


def months_between(start, end):
    y, m = int(start[:4]), int(start[5:7])
    out = []
    while f"{y}-{m:02d}" <= end:
        out.append(f"{y}-{m:02d}")
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    return out


def missing_months(c, reporter, flow, start, end, cap, refresh=2):
    """아직 없는 달을 최신부터 cap개, 수정치를 받을 최근 refresh달을 더한다"""
    have = {r[0] for r in c.execute("SELECT DISTINCT period FROM obs WHERE reporter=? AND flow=?", (reporter, flow))}
    want = months_between(start, end)
    todo = [p for p in reversed(want) if p not in have][:cap]
    known = sorted(have)[-refresh:]
    return sorted(set(todo) | set(known))


def census_month(flow, period, key):
    """{hs6: 달러}, {hs6: 이름}. 아직 안 나온 달은 빈 값"""
    path, code, val, _ = FLOWS[flow]
    text = tp.get(f"https://api.census.gov/data/timeseries/intltrade/{path}/hs?get={code},{code}_SDESC,{val}&COMM_LVL=HS6&time={period}&key={key}", timeout=120)
    if not text.strip():
        return {}, {}
    rows = json.loads(text)
    head = rows[0]
    a, b, n = head.index(code), head.index(val), head.index(f"{code}_SDESC")
    return {r[a]: float(r[b]) for r in rows[1:] if r[b] not in ("", "0")}, {r[a]: r[n] for r in rows[1:]}


def universe(c, chapters):
    """관심 장에 드는 HS 6단위 — 미국 자료에 나온 코드로 만든다"""
    rows = c.execute("SELECT DISTINCT hs FROM obs WHERE reporter='us'").fetchall()
    return sorted(r[0] for r in rows if r[0].startswith(tuple(chapters)))


def comext_rows(hs, flow, start):
    """EU 역외 교역 → [(hs, 기간, 유로)]"""
    q = "&".join(f"product={h}" for h in hs)
    doc = json.loads(tp.get(f"{tp.COMEXT}?format=JSON&reporter=EU27_2020&partner=EXT_EU27_2020&flow={FLOWS[flow][3]}&indicators=VALUE_IN_EUROS&freq=M&sinceTimePeriod={start}&{q}", timeout=120))
    prod = {v: k for k, v in doc["dimension"]["product"]["category"]["index"].items()}
    time_ = {v: k for k, v in doc["dimension"]["time"]["category"]["index"].items()}
    dims, sizes = doc["id"], doc["size"]
    if max(s for k, s in zip(dims, sizes) if k not in ("product", "time")) > 1:
        raise ValueError("Comext 조회가 한 나라·방향으로 좁혀지지 않았다")
    n = len(time_)
    return [(prod[int(i) // n], time_[int(i) % n], float(v)) for i, v in doc.get("value", {}).items()]


def collect(c, cfg, today, env, errors):
    start = tp.start_month(today, cfg["backfill_months"])
    end = tp.start_month(today, 1)
    got = 0

    def guard(label, fn):
        try:
            return fn()
        except Exception as e:
            errors.append(f"{label}: {type(e).__name__}")
            return None

    key = env.get("CENSUS_API_KEY")
    for flow in FLOWS:
        for p in missing_months(c, "us", flow, start, end, cfg["months_per_run"]) if key else []:
            res = guard(f"census {flow} {p}", lambda: census_month(flow, p, key))
            if res and res[0]:
                got += store(c, [("us", flow, WORLD, h, p, v, "USD") for h, v in res[0].items()])
                c.executemany("INSERT OR REPLACE INTO names VALUES(?,?)", list(res[1].items()))
                c.commit()
            time.sleep(PAUSE)
    codes = universe(c, cfg["chapters"])
    for flow in FLOWS:
        for i in range(0, len(codes), CHUNK):
            rows = guard(f"comext {flow} {i}", lambda: comext_rows(codes[i:i + CHUNK], flow, start)) or []
            got += store(c, [("eu", flow, WORLD, h, p, v, "EUR") for h, p, v in rows])
            time.sleep(PAUSE)
    app = env.get("ESTAT_APP_ID")
    tables = (guard("e-stat 표", lambda: tp.estat_tables(app, today)) or {}) if app else {}
    metas = {}
    for hs in cfg["chapters"] if tables else []:
        res = guard(f"e-stat {hs}", lambda: tp.trade_estat(app, hs, tables, metas))
        if res:
            got += store(c, [("jp", "import", WORLD, hs, p, v, "JPY thousand") for p, v in res[0].items()])
            got += store(c, [("jp", "import", a, hs, p, v, "JPY thousand") for a, s in res[1].items() for p, v in s.items()])
        time.sleep(PAUSE)
    conf = tp.config()["taiwan"]
    table = guard("tw trade", lambda: tp.tw_trade_table(tp.get(tp.dataset_url(conf["trade_dataset"]), timeout=90))) or {}
    got += store(c, [("tw", {"出口": "export", "進口": "import"}[f], a, f"HS류{s}", p, v, "USD thousand") for (f, s, a), series in table.items() for p, v in series.items() if p >= start])
    for table_id, flow, sv in (("410-50031", "import", "VAL_IM"), ("410-50032", "export", "VAL_TX")):
        rows = guard(f"c&sd {table_id}", lambda: hk_rows(table_id, sv)) or []
        got += store(c, [("hk", flow, WORLD, f"SITC{h}", p, v, "HKD million") for h, p, v in rows if p >= start])
    return got


def hk_rows(table, sv):
    tp.hk_table(table, sv)
    return [(str(r["COMMD"]), f"{r['period'][:4]}-{r['period'][4:6]}", float(r["figure"])) for r in tp.HK_CACHE[table]
            if r.get("sv") == sv and r.get("freq") == "M" and "%" not in str(r.get("svDesc")) and r.get("COMMD") != "" and isinstance(r.get("figure"), (int, float))]


def surge(c, cfg):
    """각 나라의 최근 window개월 합을 전년 같은 달과 비교해, 늘어난 금액이 큰 품목부터. 작은 품목의 큰 비율은 min_value로 거른다"""
    s = cfg["surge"]
    out = []
    for reporter, flow in c.execute("SELECT DISTINCT reporter, flow FROM obs").fetchall():
        rows = c.execute("SELECT hs, period, value, unit FROM obs WHERE reporter=? AND flow=? AND partner=?", (reporter, flow, WORLD)).fetchall()
        months = sorted({r[1] for r in rows})[-s["window"]:]
        if len(months) < s["window"]:
            continue
        floor = s["min_value"].get(reporter)
        series, unit = {}, {}
        for hs, p, v, u in rows:
            series.setdefault(hs, {})[p] = v
            unit[hs] = u
        for hs, v in series.items():
            now = sum(v.get(p, 0.0) for p in months)
            prev_months = [f"{int(p[:4]) - 1}{p[4:]}" for p in months]
            if not all(p in v for p in prev_months):
                continue
            prev = sum(v[p] for p in prev_months)
            if floor is None or now < floor or prev <= 0:
                continue
            yoy = now / prev - 1
            if yoy >= s["min_yoy"]:
                out.append({"reporter": reporter, "flow": flow, "hs": hs, "period": months[-1], "value": now, "yoy": yoy, "gain": now - prev, "unit": unit[hs]})
    names = dict(c.execute("SELECT hs, name FROM names").fetchall())
    per = {}
    for r in sorted(out, key=lambda x: -x["gain"]):
        k = (r["reporter"], r["flow"])
        if len(per.setdefault(k, [])) < s["top"]:
            r["name"] = names.get(r["hs"], "")
            per[k].append(r)
    return [r for rows in per.values() for r in rows]


def company_tags(entity):
    """이 회사 datapack BOM·공급 품목의 HS 코드"""
    dp = json.loads((common.ROOT / "knowledge" / "models" / "companies" / entity / "datapack.json").read_text(encoding="utf-8"))
    inputs = tp.config()["inputs"]
    tags = [b.get("input") for p in (dp.get("margin") or {}).get("products") or [] for b in p.get("bom") or []] + [x.get("input") for x in (dp.get("supply") or {}).get("links") or []]
    return sorted({inputs[t]["hs"] for t in tags if t in inputs} | {b["hs"] for p in (dp.get("margin") or {}).get("products") or [] for b in p.get("bom") or [] if b.get("hs")})


def series(c, hs):
    return c.execute("SELECT reporter, flow, period, value, unit FROM obs WHERE hs=? AND partner=? ORDER BY reporter, flow, period", (hs, WORLD)).fetchall()


def run(today=None, env=None):
    today = today or common.now_kst().date()
    cfg, errors = scan_config(), []
    c = connect()
    got = collect(c, cfg, today, env or common.load_env(), errors)
    if not got and errors:
        raise RuntimeError("무역 시계열을 받지 못했다: " + "; ".join(errors[:3]))
    rows = surge(c, cfg)
    SURGE.parent.mkdir(parents=True, exist_ok=True)
    SURGE.write_text(json.dumps({"as_of": today.isoformat(), "rows": rows, "errors": errors[:20]}, ensure_ascii=False, indent=1), encoding="utf-8")
    c.close()
    return f"저장 {got}행, 급등 {len(rows)}건, 오류 {len(errors)}건"


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", action="store_true")
    ap.add_argument("--status", action="store_true")
    ap.add_argument("--surge", nargs="?", const=15, type=int)
    ap.add_argument("--series")
    ap.add_argument("--company")
    a = ap.parse_args()
    if a.run:
        print(run())
    c = connect()
    if a.status:
        for r in c.execute("SELECT reporter, flow, COUNT(DISTINCT hs), COUNT(*), MIN(period), MAX(period) FROM obs GROUP BY 1, 2"):
            print(r)
    if a.surge:
        rows = json.loads(SURGE.read_text(encoding="utf-8"))["rows"]
        for r in sorted(rows, key=lambda x: -x["yoy"])[:a.surge]:
            print(r["reporter"], r["flow"], r["hs"], r["name"][:40], f"{r['yoy'] * 100:+.0f}%", f"{r['value']:,.0f} {r['unit']}", r["period"])
    if a.series:
        for r in series(c, a.series)[-36:]:
            print(r)
    if a.company:
        rows = json.loads(SURGE.read_text(encoding="utf-8"))["rows"] if SURGE.exists() else []
        tags = company_tags(a.company)
        print("연결 HS:", tags or "없음 — BOM에 input 또는 hs를 쓴다")
        for r in rows:
            if r["hs"] in tags or any(r["hs"].startswith(t[:4]) for t in tags):
                print(r["reporter"], r["flow"], r["hs"], f"{r['yoy'] * 100:+.0f}%", r["period"])


if __name__ == "__main__":
    main()
