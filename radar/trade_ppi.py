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
UA = None   # 요청 때 common.contact_ua() — 연락처를 코드에 두지 않는다
HISTORY_MONTHS = 120   # 10년 — 리포트 매출 시계열과 같은 구간(마스터 지시 2026-11-07, 30→120)
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
MOF = "https://web02.mof.gov.tw/njswww/webMain.aspx"   # 재정부 통계 DB(정부 데이터 개방 라이선스 1판) — 대만 세부 품목·국가 교차(2026-11-07)
HK_CACHE = {}


def config():
    return yaml.safe_load(CONFIG.read_text(encoding="utf-8"))


def get(url, params=None, data=None, timeout=45):
    if params:
        url += ("&" if "?" in url else "?") + urllib.parse.urlencode(params)
    headers = {"User-Agent": common.contact_ua()}
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
    body = {"seriesid": series, "startyear": str(today.year - (19 if key else 9)), "endyear": str(today.year)}   # BLS 한 요청 상한: v1 10년·v2 20년
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
    """한국은행 ECOS 생산자물가 월별 — 기본분류 404Y014, 10자리 품목 코드(예: 30911201AA DRAM)는 품목별 404Y016(2026-11-11 점검: 반도체 대분류로 로직·메모리를 모두 대용하던 것을 품목으로)"""
    a, b = start.replace("-", ""), f"{date.today().year}12"
    table = "404Y016" if len(item) >= 10 else "404Y014"
    # 행 범위 1~80이면 시작월부터 80개월(2016-11~2023-06)에서 끊겼다(2026-11-08 WLDN 리포트 점검) — 한 번에 1,000행까지 받는다
    doc = json.loads(get(f"https://ecos.bok.or.kr/api/StatisticSearch/{key}/json/kr/1/1000/{table}/M/{a}/{b}/{item}"))
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


def roc_ym(month):
    """'2016-11' → '10511' (재정부 조회 시작 연월)"""
    return f"{int(month[:4]) - 1911}{month[5:7]}"


def mof_get(funid, start, sel):
    """재정부 통계 DB 조회 CSV — data.gov.tw 28573·8380이 가리키는 같은 엔진. sel은 품목·국가 선택 인자"""
    return get(MOF, {"sys": 220, "ym": roc_ym(start), "kind": 21, "type": 4, "funid": funid, "cycle": 41, "outmode": 12,
                     "compmode": "00", "outkind": 1, "utf": 1, **sel}, timeout=120)


def mof_table(text):
    """재정부 CSV → {(묶음, 품목): {YYYY-MM: 값}}. 머리는 '美國/ (1)電子零組件'·'按美元計算(千美元)/ 積體電路' 모양, 연간 합계 행은 건너뛴다"""
    rows = list(csv.reader(io.StringIO(text.lstrip("﻿"))))
    out = {}
    for r in rows[1:]:
        when = re.fullmatch(r"(\d+)年\s*(\d+)月", r[0].strip()) if r else None
        if not when:
            continue
        ym = f"{int(when[1]) + 1911}-{int(when[2]):02d}"
        for h, v in zip(rows[0][1:], r[1:]):
            parts = [x.strip() for x in h.split("/")]
            val = v.strip().replace(",", "")
            if len(parts) >= 2 and re.fullmatch(r"-?\d+(\.\d+)?", val):
                out.setdefault((parts[-2], parts[-1]), {})[ym] = float(val)
    return out


def tw_goods(cfg, start):
    """대만 세부 품목(수출 i9161·수입 i9162)과 국가×주요 품목(i8201·i8202), 천 달러 → {'detail': {방향: {품목: 시계열}}, 'cross': {방향: {(나라, 품목): 시계열}}}"""
    conf, out = cfg["taiwan"]["mof"], {"detail": {}, "cross": {}}
    for flow, d in conf["detail"].items():
        out["detail"][flow] = {item: x for (_, item), x in mof_table(mof_get(d["funid"], start, {"fld0": 1, "codlst0": "1" * d["items"]})).items()}
        time.sleep(PAUSE)
    for flow, d in conf["cross"].items():
        out["cross"][flow] = mof_table(mof_get(d["funid"], start, {"fldspc": f"0,{d['countries']},", "codspc0": f"{d['goods'][0]},{d['goods'][1]},"}))
        time.sleep(PAUSE)
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
    tw_mof = (attempt("tw mof", lambda: tw_goods(cfg, start)) or {}) if cfg["taiwan"].get("mof") else {}
    countries = (cfg["taiwan"].get("mof") or {}).get("partners") or []
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
        if v.get("tw_goods") and tw_mof:   # 재정부 세부 품목(천 달러) — 방향별 최근 3개월 합과 전년 대비
            names = v["tw_goods"] if isinstance(v["tw_goods"], dict) else {"export": v["tw_goods"], "import": v["tw_goods"]}   # 수출입 품목 이름이 다를 때(DRAM·記憶體)
            g = {"item": names["export"], "items": names, "label": (cfg["taiwan"].get("labels") or {}).get(names["export"]), "unit": "USD thousand"}
            for flow in ("export", "import"):
                g[flow] = tm(f"tw:{flow}", tw_mof["detail"].get(flow, {}).get(names.get(flow)))
            if v.get("tw_main"):   # 나라별 몫은 주요 품목군(전자부품·정보통신 등) 단위로만 공개된다
                g["main"] = v["tw_main"]
                g["partners"] = shares({c: x for (c, item), x in tw_mof["cross"].get("export", {}).items() if item == v["tw_main"] and c in countries})
            o["trade"]["tw_goods"] = g
        if tables:
            total, parts = attempt(f"e-stat {k}", lambda: trade_estat(estat, v["hs"], tables, metas)) or ({}, {})
            o["trade"]["jp"] = {**(tm("jp", total) or {}), "partners": shares(parts), "unit": "JPY thousand"}
    collect.hist = hist
    collect.taiwan = taiwan_view(cfg, tw_ppi, tw_mof)
    return out, gaps, errors


def taiwan_view(cfg, tw_ppi, tw_mof):
    """대만 업종 PPI·세부 품목 수출입·국가별 주요 품목 수출입 요약(--status 대만 절, 2026-11-07)"""
    conf = cfg["taiwan"]
    countries = (conf.get("mof") or {}).get("partners") or []
    goods = {f"{flow}:{item}": trade_metric(x) for flow, items in (tw_mof.get("detail") or {}).items() for item, x in items.items() if item in conf.get("goods_watch", [])}
    cross = {f"{flow}:{item}": shares({c: x for (c, i), x in table.items() if i == item and c in countries})
             for flow, table in (tw_mof.get("cross") or {}).items() for item in conf.get("main_watch", [])}
    return {"ppi": {k: ppi_metric(tw_ppi.get(k)) for k in conf.get("ppi_watch", [])}, "goods": goods, "partners": cross, "labels": conf.get("labels") or {}}


def run(today=None):
    today = today or common.now_kst().date()
    cfg = config()
    inputs, gaps, errors = collect(cfg, today, common.load_env())
    filled = sum(1 for v in inputs.values() for x in v["ppi"].values() if x)
    if not filled:   # 전부 실패하면 어제 값을 지우지 않는다
        raise RuntimeError("PPI를 하나도 받지 못했다: " + "; ".join(errors[:3]))
    LATEST.parent.mkdir(parents=True, exist_ok=True)
    LATEST.write_text(json.dumps({"as_of": today.isoformat(), "inputs": inputs, "taiwan": getattr(collect, "taiwan", {}), "gaps": gaps, "errors": errors}, ensure_ascii=False, indent=1), encoding="utf-8")
    old = json.loads(HISTORY.read_text(encoding="utf-8")) if HISTORY.exists() else {}
    new_hist = getattr(collect, "hist", {})
    revs = list(old.get("revisions") or [])   # 개정 기록은 남긴다(2026-11-13 마스터 지시 — 9월 28.801 → 28.810이 기록 없이 덮였다)
    for k, v in new_hist.items():
        for mkt, s in (v.get("ppi") or {}).items():
            prev = ((old.get("inputs") or {}).get(k) or {}).get("ppi", {}).get(mkt) or {}
            for p, val in (s or {}).items():
                if prev.get(p) is not None and abs(prev[p] - val) > 1e-9 and not any(r.get("input") == k and r["market"] == mkt and r["period"] == p and r["new"] == val for r in revs):
                    revs.append({"input": k, "series": (cfg["inputs"][k]["ppi"].get(mkt)), "market": mkt, "period": p, "old": prev[p], "new": val, "at": common.iso(common.now_kst())})
    HISTORY.write_text(json.dumps({"as_of": today.isoformat(), "inputs": new_hist, "us_raw": old.get("us_raw") or {}, "revisions": revs[-500:]}, ensure_ascii=False), encoding="utf-8")
    return f"입력 {len(inputs)}개, PPI {filled}칸, 공백 {len(gaps)}건, 오류 {len(errors)}건"


def load():
    return json.loads(LATEST.read_text(encoding="utf-8")) if LATEST.exists() else {}


def line(key, v):
    pct = lambda m: "미확인" if not m or m.get("yoy") is None else f"{m['yoy'] * 100:+.1f}%({m['period']})"
    ppi = " · ".join(f"{c.upper()}{'*' if c in v.get('proxy', []) else ''} {pct(m)}" for c, m in v["ppi"].items())
    eu = sorted(v["trade"].get("eu", {}).get("partners", {}).items(), key=lambda kv: -kv[1]["value"])[:3]
    top = " · ".join(f"{c} {m['share'] * 100:.0f}%" for c, m in eu) or "미확인"
    tw = v["trade"].get("tw_goods")
    tw = f" | TW 수출 {tw.get('label') or tw['item']} {pct(tw.get('export'))}" if tw else ""
    return f"{key} {v['name']} HS{v['hs']} | PPI 전년비 {ppi} | EU 수입처 {top} | UK 수입 {pct(v['trade'].get('uk'))}{tw} | * 업종 대용"


def taiwan_lines(tw):
    """--status 대만 절 — 업종 PPI, 세부 품목 수출입(최근 3개월 합), 주요 품목군 상대국 몫"""
    pct = lambda m: "미확인" if not m or m.get("yoy") is None else f"{m['yoy'] * 100:+.1f}%({m['period']})"
    usd = lambda m: "미확인" if not m else f"${m['value'] / 1e6:,.1f}B"   # 천 달러 → $B
    labels = tw.get("labels") or {}
    ko = lambda x: f"{labels[x]}({x})" if x in labels else x   # 한국어 표기, 원문은 괄호
    side = lambda k: ("수출" if k.startswith("export") else "수입", ko(k.split(":", 1)[1]))
    out = ["대만 업종 PPI 전년비: " + " · ".join(f"{ko(k)} {pct(m)}" for k, m in (tw.get("ppi") or {}).items())]
    out += ["대만 %s %s 3개월 %s 전년비 %s" % (*side(k), usd(m), pct(m)) for k, m in (tw.get("goods") or {}).items()]
    for k, parts in (tw.get("partners") or {}).items():
        top = " · ".join(f"{labels.get(c, c)} {m['share'] * 100:.0f}%({pct(m)})" for c, m in list(parts.items())[:5])
        out.append("대만 %s %s 상대국: %s" % (*side(k), top or "미확인"))
    return out


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
        print("\n".join(taiwan_lines(d.get("taiwan") or {})))
        print("공백:", *d.get("gaps", []), sep="\n  ")
        print("오류:", *d.get("errors", []), sep="\n  ")


if __name__ == "__main__":
    main()
