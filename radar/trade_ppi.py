"""무역·PPI 세부 항목 수집 (마스터 지시 2026-11-02 "BOM과 공급망 파악, 밸류에이션 계산할 때 미국, 대만, 유럽연합, 영국, 일본, 한국의 무역 지표의 세부항목 데이터와
생산자물가지수(PPI)의 세부항목 데이터를 가져오도록 파이프라인을 설계하라")

공식 공개 API만 쓴다(모델 없음). 대상 품목·코드·경로 상태는 config/trade_ppi.yaml. 결과 knowledge/models/trade_ppi/latest.json.
못 가져온 나라·지표는 gaps에 남기고 빈칸을 채우지 않는다. 키는 common.load_env()로만 읽고 출력하지 않는다.
사용: py radar/trade_ppi.py --run · --status · --need <회사 id>   (run_hourly가 하루 1회 돈다)
"""
import argparse
import csv
import io
import json
import re
import sys
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import date
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
from pollers import common  # noqa: E402

CONFIG = common.ROOT / "config" / "trade_ppi.yaml"
LATEST = common.ROOT / "knowledge" / "models" / "trade_ppi" / "latest.json"
HISTORY = common.ROOT / "knowledge" / "models" / "trade_ppi" / "history.json"   # 월별 원 시계열 — 거시 지표 싱크로율(scripts/tenbagger/sync_view.py, 2026-11-03)
UA = "Chiip research fhteo1101@gmail.com"
HISTORY_MONTHS = 30
PAUSE = 0.4
WINDOW = 3   # 무역은 월별 변동이 커서 최근 3개월 합을 전년 같은 3개월과 비교한다
MONTHS = {m: i + 1 for i, m in enumerate("JAN FEB MAR APR MAY JUN JUL AUG SEP OCT NOV DEC".split())}
EUROSTAT = "https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/sts_inpp_m"
COMEXT = "https://ec.europa.eu/eurostat/api/comext/dissemination/statistics/1.0/data/DS-045409"
BOJ = "https://www.stat-search.boj.or.jp/api/v1/getDataCode"
ONS = "https://www.ons.gov.uk/economy/inflationandpriceindices/timeseries/{cdid}/ppi/data"   # 내려받기 파일 ppi.csv·mm22.csv는 갱신이 끊겼다
HMRC = "https://api.uktradeinfo.com"
BLS = "https://api.bls.gov/publicAPI/{v}/timeseries/data/"
CENSUS = "https://api.census.gov/data/timeseries/intltrade/imports/hs"
HK_CACHE = {}


def config():
    return yaml.safe_load(CONFIG.read_text(encoding="utf-8"))


def get(url, params=None, data=None, timeout=45):
    if params:
        url += ("&" if "?" in url else "?") + urllib.parse.urlencode(params)
    headers = {"User-Agent": UA}
    if data is not None:
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=json.dumps(data).encode() if data is not None else None, headers=headers)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", "replace")


def start_month(today, months=HISTORY_MONTHS):
    i = today.year * 12 + today.month - 1 - months
    return f"{i // 12}-{i % 12 + 1:02d}"


def jsonstat_months(doc):
    """Eurostat JSON-stat에서 시간 축만 남은 조회를 {YYYY-MM: 값}으로"""
    dims, sizes = doc["id"], doc["size"]
    if sum(s > 1 for k, s in zip(dims, sizes) if k != "time"):
        raise ValueError("시간 외 차원이 하나로 좁혀지지 않았다")
    index = doc["dimension"]["time"]["category"]["index"]
    step = 1
    for k, s in zip(reversed(dims), reversed(sizes)):
        if k == "time":
            break
        step *= s
    label = {v: k for k, v in index.items()}
    return {label[int(i) // step % len(label)]: float(v) for i, v in doc.get("value", {}).items()}


def ppi_eurostat(nace, start):
    doc = json.loads(get(EUROSTAT, {"lang": "EN", "geo": "EU27_2020", "nace_r2": nace, "unit": "I21", "s_adj": "NSA", "indic_bt": "PRC_PRR", "sinceTimePeriod": start}))
    return jsonstat_months(doc)


def ppi_bls(series, today, key=None):
    """{시리즈: {YYYY-MM: 값}} — 키가 없으면 v1(하루 25회), 있으면 v2"""
    body = {"seriesid": series, "startyear": str(today.year - 2), "endyear": str(today.year)}
    if key:
        body["registrationkey"] = key
    doc = json.loads(get(BLS.format(v="v2" if key else "v1"), data=body))
    if doc.get("status") != "REQUEST_SUCCEEDED":
        raise ValueError(str(doc.get("message"))[:120])
    return {s["seriesID"]: {f"{d['year']}-{d['period'][1:]}": float(d["value"]) for d in s["data"] if re.fullmatch(r"M(0[1-9]|1[0-2])", d["period"]) and d["value"] not in ("-", "")} for s in doc["Results"]["series"]}


def ppi_boj(code, start):
    doc = json.loads(get(BOJ, {"format": "json", "lang": "en", "db": "PR01", "code": code, "startDate": start.replace("-", "")}))
    v = doc["RESULTSET"][0]["VALUES"]
    return {f"{str(d)[:4]}-{str(d)[4:6]}": float(x) for d, x in zip(v["SURVEY_DATES"], v["VALUES"]) if x is not None}


def ppi_ons(cdid):
    """영국 시리즈 하나 → {YYYY-MM: 값}"""
    out = {}
    for r in json.loads(get(ONS.format(cdid=cdid.lower()))).get("months", []):
        m = re.fullmatch(r"(\d{4}) ([A-Z]{3})", r.get("date", ""))
        if m and m[2] in MONTHS and r.get("value") not in (None, ""):
            out[f"{m[1]}-{MONTHS[m[2]]:02d}"] = float(r["value"])
    return out


def trade_comext(hs, partner, start):
    doc = json.loads(get(COMEXT, {"format": "JSON", "reporter": "EU27_2020", "partner": partner, "product": hs, "flow": 1, "indicators": "VALUE_IN_EUROS", "freq": "M", "sinceTimePeriod": start}))
    return jsonstat_months(doc)


def odata(path, flt):
    out, url = [], f"{HMRC}/{path}?" + urllib.parse.urlencode({"$filter": flt})
    while url:
        doc = json.loads(get(url))
        out += doc.get("value", [])
        url = doc.get("@odata.nextLink")
        time.sleep(1.1)   # 분당 60회 제한
    return out


def trade_hmrc(hs, start):
    """영국 수입(EU·비EU 합) — 파운드, {YYYY-MM: 값}"""
    ids = [c["CommodityId"] for c in odata("Commodity", f"Hs6Code eq '{hs}'")]
    if not ids:
        return {}
    rows = []
    for n in range(0, len(ids), 10):   # 필터 노드 100개 제한 — 10개씩 나눠 묻는다(경유 271019는 CN8 36개)
        who = " or ".join(f"CommodityId eq {i}" for i in ids[n:n + 10])
        rows += odata("OTS", f"MonthId ge {start.replace('-', '')} and FlowTypeId ne 2 and FlowTypeId ne 4 and ({who})")
    out = {}
    for r in rows:
        k = f"{str(r['MonthId'])[:4]}-{str(r['MonthId'])[4:6]}"
        out[k] = out.get(k, 0.0) + float(r.get("Value") or 0)
    return out


def trade_census(hs, start, key):
    rows = json.loads(get(CENSUS, {"get": "GEN_VAL_MO,I_COMMODITY", "I_COMMODITY": hs, "COMM_LVL": "HS6", "time": f"from {start}", "key": key}))
    head = rows[0]
    return {r[head.index("time")]: float(r[head.index("GEN_VAL_MO")]) for r in rows[1:]}


def ppi_ecos(item, start, key):
    """한국은행 ECOS 404Y014(생산자물가 기본분류) 월별"""
    a, b = start.replace("-", ""), f"{date.today().year}12"
    doc = json.loads(get(f"https://ecos.bok.or.kr/api/StatisticSearch/{key}/json/kr/1/80/404Y014/M/{a}/{b}/{item}"))
    return {f"{r['TIME'][:4]}-{r['TIME'][4:6]}": float(r["DATA_VALUE"]) for r in doc["StatisticSearch"]["row"]}


def dataset_url(nid, want=""):
    """data.gov.tw 데이터셋의 현재 내려받기 주소 — 주소가 바뀌어도 따라간다"""
    dist = json.loads(get(f"https://data.gov.tw/api/v2/rest/dataset/{nid}"))["result"]["distribution"]
    return next(d["resourceDownloadUrl"] for d in dist if want in str(d.get("resourceFormat")))


def tw_ppi_table(text):
    """주계총처 생산자물가 기본분류 XML → {품목명: {YYYY-MM: 지수}}"""
    out = {}
    for o in ET.fromstring(text):
        d = {c.tag: c.text for c in o}
        if d.get("TYPE") == "原始值" and d.get("FREQ") == "M" and d.get("Item_VALUE"):
            p = d["TIME_PERIOD"]
            out.setdefault(d["Item"].split("(指數")[0], {})[f"{p[:4]}-{p[5:7]}"] = float(d["Item_VALUE"])
    return out


def tw_trade_table(text):
    """재정부 28573 CSV → {(방향, HS류, 나라): {YYYY-MM: 천 달러}}. 첫 칸은 민국 연월(115년 9월)"""
    rows = list(csv.reader(io.StringIO(text.lstrip("﻿"))))
    head, out = rows[0], {}
    for r in rows[1:]:
        when = re.fullmatch(r"(\d+)年\s*(\d+)月", r[0].strip()) if r else None   # 연간 합계 행은 건너뛴다
        if not when:
            continue
        ym = f"{int(when[1]) + 1911}-{int(when[2]):02d}"
        for h, v in zip(head[1:], r[1:]):
            m = re.fullmatch(r"(.+?)/ (進口|出口)/ (\d+)\..*", h)
            if m and v.strip().replace(",", "").replace(".", "").isdigit():
                out.setdefault((m[2], m[3], m[1]), {})[ym] = float(v.replace(",", ""))
    return out


def hk_table(table, sv, key_field=None, key=None):
    """홍콩 C&SD 표 API → {YYYY-MM: 값}"""
    rows = HK_CACHE.get(table)
    if rows is None:
        rows = HK_CACHE[table] = json.loads(get(f"https://www.censtatd.gov.hk/api/get.php?id={table}&lang=en&full_series=1", timeout=90))["dataSet"]
    return {f"{r['period'][:4]}-{r['period'][4:6]}": float(r["figure"]) for r in rows
            if r.get("sv") == sv and "%" not in str(r.get("svDesc")) and r.get("freq") in ("M", "Q") and isinstance(r.get("figure"), (int, float)) and (key_field is None or str(r.get(key_field)) == key)}


def estat_tables(app, today, flow="輸入"):
    """올해·작년 '品別国別表 輸入(또는 輸出)' 표 번호 — 해마다 번호가 바뀌어 이름으로 찾는다. 輸出은 2026-11-04 추가(일본 수출이 비어 있었다)"""
    out = {}
    for y in (today.year, today.year - 1):
        q = urllib.parse.quote(f"品別国別表 {flow}")
        doc = json.loads(get(f"https://api.e-stat.go.jp/rest/3.0/app/json/getStatsList?appId={app}&statsCode=00350300&searchWord={q}&surveyYears={y}&limit=60&lang=J"))
        tb = doc["GET_STATS_LIST"]["DATALIST_INF"].get("TABLE_INF") or []
        hit = [t for t in (tb if isinstance(tb, list) else [tb]) if str(t.get("STATISTICS_NAME", "")).startswith(f"貿易統計_全国分 品別国別表 {flow}")]
        if hit:
            out[y] = hit[0]["@id"]
    return out


def estat_meta(app, table):
    m = json.loads(get(f"https://api.e-stat.go.jp/rest/3.0/app/json/getMetaInfo?appId={app}&statsDataId={table}&lang=J"))["GET_META_INFO"]["METADATA_INF"]["CLASS_INF"]["CLASS_OBJ"]
    cl = {c["@id"]: (c["CLASS"] if isinstance(c["CLASS"], list) else [c["CLASS"]]) for c in m}
    months = {c["@code"]: int(c["@name"].split("月")[0]) for c in cl["cat02"] if re.fullmatch(r"\d+月_金額", c["@name"])}
    return {"codes": [c["@code"] for c in cl["cat01"]], "months": months, "area": {c["@code"]: c["@name"].split("_", 1)[-1] for c in cl["area"]}}


def trade_estat(app, hs, tables, metas):
    """일본 수입(또는 수출 — tables가 輸出 표면) → ({YYYY-MM: 천 엔}, {나라: {YYYY-MM: 천 엔}})"""
    total, parts = {}, {}
    for y, table in tables.items():
        meta = metas.setdefault(table, estat_meta(app, table))
        codes = [c for c in meta["codes"] if c.startswith(hs)]
        if not codes:
            continue
        doc = json.loads(get(f"https://api.e-stat.go.jp/rest/3.0/app/json/getStatsData?appId={app}&statsDataId={table}&lang=J&cdCat01={','.join(codes[:100])}&cdCat02={','.join(meta['months'])}&metaGetFlg=N&cntGetFlg=N", timeout=90))
        rows = doc["GET_STATS_DATA"]["STATISTICAL_DATA"].get("DATA_INF", {}).get("VALUE") or []
        for r in rows if isinstance(rows, list) else [rows]:
            try:
                v = float(r["$"])
            except ValueError:
                continue
            k = f"{y}-{meta['months'][r['@cat02']]:02d}"
            total[k] = total.get(k, 0.0) + v
            if v:   # 아직 나오지 않은 달은 0으로 온다
                s = parts.setdefault(meta["area"].get(r["@area"], r["@area"]), {})
                s[k] = s.get(k, 0.0) + v
    return {k: v for k, v in total.items() if v}, parts


def shares(parts):
    """나라별 최근 합과 몫 — 0인 나라는 뺀다"""
    months = sorted({p for v in parts.values() for p in v})[-WINDOW:]   # 나라마다 마지막 달이 달라도 같은 달로 잰다
    out = {}
    for c, v in parts.items():
        now = sum(v.get(p, 0.0) for p in months)
        prev = sum(v.get(f"{int(p[:4]) - 1}{p[4:]}", 0.0) for p in months)
        if now:
            out[c] = {"period": months[-1], "value": now, "yoy": now / prev - 1 if prev else None}
    total = sum(m["value"] for m in out.values())
    return {c: {**m, "share": m["value"] / total} for c, m in sorted(out.items(), key=lambda kv: -kv[1]["value"])[:8]}


def ppi_metric(series):
    """최신 달과 전년 같은 달 대비 변화"""
    if not series:
        return None
    p = max(series)
    prev = f"{int(p[:4]) - 1}{p[4:]}"
    return {"period": p, "value": series[p], "yoy": series[p] / series[prev] - 1 if series.get(prev) else None}


def trade_metric(series, window=WINDOW):
    """최근 window개월 합과 전년 같은 달들의 합"""
    if len(series) < window:
        return None
    now = sorted(series)[-window:]
    prev = [f"{int(p[:4]) - 1}{p[4:]}" for p in now]
    base = sum(series.get(p, 0) for p in prev) if all(p in series for p in prev) else None
    total = sum(series[p] for p in now)
    return {"period": now[-1], "value": total, "yoy": total / base - 1 if base else None}


def collect(cfg, today, env):
    start = start_month(today)
    gaps = [f"{c} {kind}: {s.get('why', '경로 미확인')}" for c, v in cfg["sources"].items() for kind, s in v.items() if s["status"] == "todo"]
    errors = []
    out = {k: {"name": v["name"], "hs": v["hs"], "ppi": {}, "trade": {}, "proxy": v.get("proxy") or []} for k, v in cfg["inputs"].items()}

    def attempt(label, fn):
        try:
            return fn()
        except Exception as e:
            errors.append(f"{label}: {type(e).__name__}")
            return None

    bls = sorted({v["ppi"]["us"] for v in cfg["inputs"].values() if v["ppi"].get("us")})
    us = attempt("bls", lambda: ppi_bls(bls, today, env.get("BLS_API_KEY"))) or {}
    census, ecos, estat = env.get("CENSUS_API_KEY"), env.get("ECOS_API_KEY"), env.get("ESTAT_APP_ID")
    gaps += [f"{name} 키 없음" for name, v in (("CENSUS_API_KEY", census), ("ECOS_API_KEY", ecos), ("ESTAT_APP_ID", estat)) if not v]
    tw_ppi = attempt("tw ppi", lambda: tw_ppi_table(get(dataset_url(cfg["taiwan"]["ppi_dataset"]), timeout=90))) or {}
    tw_trade = attempt("tw trade", lambda: tw_trade_table(get(dataset_url(cfg["taiwan"]["trade_dataset"]), timeout=90))) or {}
    tables = (attempt("e-stat 표", lambda: estat_tables(estat, today)) or {}) if estat else {}
    metas = {}
    hist = {k: {"ppi": {}, "trade": {}} for k in cfg["inputs"]}
    for k, v in cfg["inputs"].items():
        p, o = v["ppi"], out[k]
        pm = lambda c, s: (hist[k]["ppi"].__setitem__(c, s) if s else None) or ppi_metric(s)
        tm = lambda c, s: (hist[k]["trade"].__setitem__(c, s) if s else None) or trade_metric(s or {})
        o["ppi"]["us"] = pm("us", us.get(p.get("us")))
        if p.get("uk"):
            o["ppi"]["uk"] = pm("uk", attempt(f"ons {k}", lambda: ppi_ons(p["uk"])))
        if p.get("jp"):
            o["ppi"]["jp"] = pm("jp", attempt(f"boj {k}", lambda: ppi_boj(p["jp"], start)))
            time.sleep(PAUSE)
        if p.get("eu"):
            o["ppi"]["eu"] = pm("eu", attempt(f"eurostat {k}", lambda: ppi_eurostat(p["eu"], start)))
        parts = {}
        for c in cfg["partners"]:
            m = tm(f"eu:{c}", attempt(f"comext {k} {c}", lambda: trade_comext(v["hs"], c, start)))
            if m:
                parts[c] = m
            time.sleep(PAUSE)
        total = sum(m["value"] for m in parts.values())
        o["trade"]["eu"] = {"partners": {c: {**m, "share": m["value"] / total if total else None} for c, m in parts.items()}, "unit": "EUR"}
        o["trade"]["uk"] = tm("uk", attempt(f"hmrc {k}", lambda: trade_hmrc(v["hs"], start)))
        if census:
            o["trade"]["us"] = tm("us", attempt(f"census {k}", lambda: trade_census(v["hs"], start, census)))
        if ecos and p.get("kr"):
            o["ppi"]["kr"] = pm("kr", attempt(f"ecos {k}", lambda: ppi_ecos(p["kr"], start, ecos)))
        if p.get("tw"):
            o["ppi"]["tw"] = pm("tw", tw_ppi.get(p["tw"]))
        if p.get("hk"):
            o["ppi"]["hk"] = pm("hk", attempt(f"c&sd ppi {k}", lambda: hk_table("520-62001", "PPI", "IND", p["hk"])))
        if v.get("sitc"):
            o["trade"]["hk"] = tm("hk", attempt(f"c&sd trade {k}", lambda: hk_table("410-50031", "VAL_IM", "COMMD", v["sitc"])))
        if v.get("tw_section"):
            ex = {c: x for (flow, sec, c), x in tw_trade.items() if flow == "出口" and sec == v["tw_section"]}
            o["trade"]["tw"] = {"partners": shares(ex), "unit": "USD thousand", "flow": "수출", "scope": f"HS {v['tw_section']}류"}
        if tables:
            total, parts = attempt(f"e-stat {k}", lambda: trade_estat(estat, v["hs"], tables, metas)) or ({}, {})
            o["trade"]["jp"] = {**(tm("jp", total) or {}), "partners": shares(parts), "unit": "JPY thousand"}
    collect.hist = hist
    return out, gaps, errors


def run(today=None):
    today = today or common.now_kst().date()
    cfg = config()
    inputs, gaps, errors = collect(cfg, today, common.load_env())
    filled = sum(1 for v in inputs.values() for x in v["ppi"].values() if x)
    if not filled:   # 전부 실패하면 어제 값을 지우지 않는다
        raise RuntimeError("PPI를 하나도 받지 못했다: " + "; ".join(errors[:3]))
    LATEST.parent.mkdir(parents=True, exist_ok=True)
    LATEST.write_text(json.dumps({"as_of": today.isoformat(), "inputs": inputs, "gaps": gaps, "errors": errors}, ensure_ascii=False, indent=1), encoding="utf-8")
    HISTORY.write_text(json.dumps({"as_of": today.isoformat(), "inputs": getattr(collect, "hist", {})}, ensure_ascii=False), encoding="utf-8")
    return f"입력 {len(inputs)}개, PPI {filled}칸, 공백 {len(gaps)}건, 오류 {len(errors)}건"


def load():
    return json.loads(LATEST.read_text(encoding="utf-8")) if LATEST.exists() else {}


def line(key, v):
    pct = lambda m: "미확인" if not m or m.get("yoy") is None else f"{m['yoy'] * 100:+.1f}%({m['period']})"
    ppi = " · ".join(f"{c.upper()}{'*' if c in v.get('proxy', []) else ''} {pct(m)}" for c, m in v["ppi"].items())
    eu = sorted(v["trade"].get("eu", {}).get("partners", {}).items(), key=lambda kv: -kv[1]["value"])[:3]
    top = " · ".join(f"{c} {m['share'] * 100:.0f}%" for c, m in eu) or "미확인"
    return f"{key} {v['name']} HS{v['hs']} | PPI 전년비 {ppi} | EU 수입처 {top} | UK 수입 {pct(v['trade'].get('uk'))} | * 업종 대용"


def need(entity):
    """이 회사 datapack BOM·공급 품목의 input 지표를 보여 준다"""
    dp = json.loads((common.ROOT / "knowledge" / "models" / "companies" / entity / "datapack.json").read_text(encoding="utf-8"))
    tags = [b.get("input") for p in (dp.get("margin") or {}).get("products") or [] for b in p.get("bom") or []] + [x.get("input") for x in (dp.get("supply") or {}).get("links") or []]
    data = load().get("inputs", {})
    return [line(k, data[k]) for k in dict.fromkeys(t for t in tags if t in data)] or ["연결된 input 없음 — config/trade_ppi.yaml의 키를 BOM item의 input에 쓴다"]


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", action="store_true")
    ap.add_argument("--status", action="store_true")
    ap.add_argument("--need")
    a = ap.parse_args()
    if a.run:
        print(run())
    if a.need:
        print("\n".join(need(a.need)))
    if a.status:
        d = load()
        print("기준일", d.get("as_of"))
        for k, v in d.get("inputs", {}).items():
            print(line(k, v))
        print("공백:", *d.get("gaps", []), sep="\n  ")
        print("오류:", *d.get("errors", []), sep="\n  ")


if __name__ == "__main__":
    main()
