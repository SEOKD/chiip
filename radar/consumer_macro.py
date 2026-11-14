"""한국 외 소비재 시장 — 공식 통계(미국·일본·유럽·영국) 수집·지표·지표 발표 경보 (마스터 지시 2026-11-14
"나는 한국 주식종목을 투자하기도 하지만 메인은 미국, 일본, 유럽이다. 한국 외 소비재 시장 트렌드를 파악하는 파이프라인을 만들어라")

결정론(모델 없음). run_hourly 6시간마다 — 새 달이 나오면 지표를 다시 계산하고, 문턱을 넘는 업종이 있을 때만 Pulse '지표 발표'(src-consumer-macro) 한 건.
원천(2026-11-14 확인 — robots·약관 허용, 공식 API):
  us  FRED(api.stlouisfed.org, FRED_API_KEY) — Census 월간 소매 업종(계절조정·명목) + BLS CPI 업종(계절조정). 공공 자료
  jp  e-Stat(ESTAT_APP_ID) 総務省 家計調査 二人以上の世帯 品目別 支出(명목 엔/가구) + JNTO 訪日外客数 xlsx(시장별)
  eu  Eurostat sts_trtu_m 소매 판매량(VOL_SLS·SCA·2021=100) 나라×업종
  uk  ONS 소매판매지수(DRSI) 시계열 JSON
  경제산업성 商業動態統計는 robots.txt까지 비브라우저 접속을 403으로 막아 쓰지 않는다(접속 가장 금지).
지표(시계열마다): 최근 달 값, 1개월 YoY, 3개월 YoY(최근 3개월 합 ÷ 전년 같은 3개월), 가속(3개월 YoY − 3개월 전의 3개월 YoY, %p),
  5년 z(직전 60개월 3개월 YoY 분포 대비). 가격 시계열이 짝지어진 업종은 '실질 근사' = 판매 3개월 YoY − 가격 3개월 YoY.
경보 문턱 config/consumer_trends.yaml macro.alert(등록부 prm-ctrend-*). 가계조사 품목처럼 표본 잡음이 큰 것(noisy)은 문턱을 높인다.
금지표: 업종 판매 증가 → 특정 기업 매출. 노출 종목(exposure)은 가설이다. 실패하면 값을 지어내지 않는다(그 원천을 비우고 errors에 적는다).
저장: radar/state/consumer_macro.sqlite(git 제외, 전 기간) · knowledge/models/consumer_trends/macro_latest.json · macro_series.csv(최근 72개월)
사용: py radar/consumer_macro.py [--status] [--no-alert]
"""
import csv
import io
import json
import math
import re
import sqlite3
import sys
import time
import zipfile
import xml.etree.ElementTree as ET
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from pollers import common  # noqa: E402

CFG = "config/consumer_trends.yaml"
OUT = common.ROOT / "knowledge" / "models" / "consumer_trends"
LATEST = OUT / "macro_latest.json"
SERIES_CSV = OUT / "macro_series.csv"
DB = common.ROOT / "radar" / "state" / "consumer_macro.sqlite"
STATE = "consumer_macro"
FRED = "https://api.stlouisfed.org/fred/series/observations"
EUROSTAT = "https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/sts_trtu_m"
ONS = "https://www.ons.gov.uk/businessindustryandtrade/retailindustry/timeseries/{sid}/drsi/data"
ESTAT = "https://api.e-stat.go.jp/rest/3.0/app/json/getStatsData"
JNTO = "https://www.jnto.go.jp"
FAMILY_NAME = {"us": "미국 소매", "jp": "일본 가계 지출", "jp_inbound": "일본 방일객", "eu": "유럽 소매 판매량", "uk": "영국 소매"}
FAMILY_URL = {"us": "https://fred.stlouisfed.org/series/RSAFS", "jp": "https://www.e-stat.go.jp/stat-search?toukei=00200561",
              "jp_inbound": "https://www.jnto.go.jp/statistics/data/visitors-statistics/",
              "eu": "https://ec.europa.eu/eurostat/databrowser/view/sts_trtu_m/default/table", "uk": "https://www.ons.gov.uk/businessindustryandtrade/retailindustry"}
MON = {m: i + 1 for i, m in enumerate(["JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"])}


def cfg():
    return common.load_yaml(CFG) or {}


def ua():
    return {"User-Agent": common.contact_ua()}


def _json(url, params=None, timeout=90):
    raw = common.http_get(url, params, headers=ua(), timeout=timeout) if params is not None else common.http_get(url, headers=ua(), timeout=timeout)
    return json.loads(raw)


# ── 월 계산 ───────────────────────────────────────────────

def shift(month, k):
    y, m = int(month[:4]), int(month[5:7]) + k
    y, m = y + (m - 1) // 12, (m - 1) % 12 + 1
    return f"{y}-{m:02d}"


def metrics(s, kind="level"):
    """s = {YYYY-MM: 값}. kind level(수준·지수) 또는 yoy(이미 전년 동월비 %). 최근 달 기준 지표 — 계산할 수 없으면 None 칸"""
    if not s:
        return None
    last = max(s)

    def yoy3(m):
        ms = [shift(m, -k) for k in range(3)]
        if kind == "yoy":
            return sum(s[x] for x in ms) / 300 if all(x in s for x in ms) else None
        ly = [shift(x, -12) for x in ms]
        if not all(x in s for x in ms + ly):
            return None
        den = sum(s[x] for x in ly)
        return sum(s[x] for x in ms) / den - 1 if den > 0 else None

    def yoy1(m):
        if kind == "yoy":
            return s[m] / 100 if m in s else None
        p = shift(m, -12)
        return s[m] / s[p] - 1 if m in s and p in s and s[p] > 0 else None

    # 최근 달의 전년 비교가 비면(예: 2025-10 미국 정부 셧다운으로 BLS 10월 CPI 미공표) 두 달까지 물러서 계산한다 — month = 계산 기준 달
    at = next((shift(last, -k) for k in range(3) if yoy3(shift(last, -k)) is not None), last)
    y3 = yoy3(at)
    prev = yoy3(shift(at, -3))
    hist = [v for v in (yoy3(shift(at, -k)) for k in range(3, 63)) if v is not None]
    z = None
    if y3 is not None and len(hist) >= 24:
        mu = sum(hist) / len(hist)
        sd = math.sqrt(sum((v - mu) ** 2 for v in hist) / (len(hist) - 1))
        z = (y3 - mu) / sd if sd > 0 else None
    r = lambda v, n=4: None if v is None else round(v, n)
    return {"month": at, "latest": last, "value": s.get(at), "yoy1": r(yoy1(at)), "yoy3": r(y3),
            "accel_pp": r((y3 - prev) * 100, 2) if y3 is not None and prev is not None else None, "z": r(z, 2), "n_hist": len(hist)}


def flag(m, noisy, alert):
    """이례적인 가속 'up' 또는 감속 'down' — 가속 폭과 5년 z가 같은 방향으로 함께 문턱을 넘어야 한다
    (성장률이 이례적으로 높은데 둔화하는 경우는 경보가 아니다 — 2026-11-14 일본 게임 소프트 +62%·가속 −13.5%p)"""
    if not m or m.get("accel_pp") is None or m.get("z") is None:
        return None
    thr = alert["accel_pp_noisy"] if noisy else alert["accel_pp"]
    if m["accel_pp"] >= thr and m["z"] >= alert["z"]:
        return "up"
    if m["accel_pp"] <= -thr and m["z"] <= -alert["z"]:
        return "down"
    return None


# ── 원천 ─────────────────────────────────────────────────

def fetch_us(c, env, start):
    key = env.get("FRED_API_KEY")
    if not key:
        raise RuntimeError("FRED_API_KEY 없음")
    out = {}
    for it in c["us"]:
        js = _json(FRED, {"series_id": it["series"], "api_key": key, "file_type": "json", "observation_start": f"{start}-01"})
        out[it["id"]] = {o["date"][:7]: float(o["value"]) for o in js.get("observations") or [] if o.get("value") not in (".", "", None)}
        time.sleep(0.3)
    return out


def jsonstat_rows(d):
    """Eurostat JSON-stat 2.0 → [({차원: 코드}, 값)]"""
    dims, sizes = d["id"], d["size"]
    pos = {k: {v: c for c, v in d["dimension"][k]["category"]["index"].items()} for k in dims}
    strides = [1] * len(dims)
    for i in range(len(dims) - 2, -1, -1):
        strides[i] = strides[i + 1] * sizes[i + 1]
    out = []
    for idx, val in (d.get("value") or {}).items():
        n, coord = int(idx), {}
        for k, st in zip(dims, strides):
            coord[k], n = pos[k][n // st], n % st
        out.append((coord, float(val)))
    return out


def eu_id(geo, cat):
    return f"eu-{'eu27' if geo.startswith('EU27') else geo.lower()}-{cat}"


def fetch_eu(c, start):
    e = c["eu"]
    q = "&".join(["format=JSON", "lang=EN", "indic_bt=VOL_SLS", "s_adj=SCA", "unit=I21", f"sinceTimePeriod={start}"]
                 + [f"geo={g}" for g in e["geos"]] + [f"nace_r2={n['code']}" for n in e["nace"]])
    d = _json(f"{EUROSTAT}?{q}", timeout=120)
    cat = {n["code"]: n["cat"] for n in e["nace"]}
    out = {}
    for coord, v in jsonstat_rows(d):
        out.setdefault(eu_id(coord["geo"], cat[coord["nace_r2"]]), {})[coord["time"]] = v
    return out


def ons_month(label):
    """'2026 SEP' → '2026-09' — 분기·연간 행은 None"""
    m = re.match(r"^(\d{4}) ([A-Z]{3})$", (label or "").strip())
    return f"{m.group(1)}-{MON[m.group(2)]:02d}" if m and m.group(2) in MON else None


def fetch_uk(c):
    out = {}
    for it in c["uk"]:
        d = _json(ONS.format(sid=it["series"]), timeout=60)
        out[it["id"]] = {ons_month(x.get("date")): float(x["value"]) for x in d.get("months") or [] if ons_month(x.get("date")) and x.get("value") not in ("", None)}
        time.sleep(0.4)
    return out


def estat_month(code):
    """'2026000909' → '2026-09'"""
    return f"{code[:4]}-{code[-2:]}" if re.match(r"^\d{10}$", code or "") else None


def fetch_jp(c, env, start):
    app = env.get("ESTAT_APP_ID")
    if not app:
        raise RuntimeError("ESTAT_APP_ID 없음")
    j = c["jp"]
    by_code = {it["code"]: it["id"] for it in j["items"]}
    d = _json(ESTAT, {"appId": app, "statsDataId": j["table"], "lang": "J", "cdCat01": ",".join(by_code), "cdCat02": j["household"],
                      "cdArea": j["area"], "cdTimeFrom": f"{start[:4]}00{start[5:7]}{start[5:7]}", "metaGetFlg": "N", "cntGetFlg": "N", "limit": "100000"}, timeout=120)
    vals = ((d.get("GET_STATS_DATA") or {}).get("STATISTICAL_DATA") or {}).get("DATA_INF", {}).get("VALUE") or []
    out = {}
    for v in vals:
        m, x = estat_month(v.get("@time")), (v.get("$") or "").replace(",", "")
        if m and v.get("@cat01") in by_code and re.match(r"^-?\d+(\.\d+)?$", x):
            out.setdefault(by_code[v["@cat01"]], {})[m] = float(x)
    if not out:
        raise RuntimeError("e-Stat 가계조사 응답에 값이 없다")
    return out


# xlsx(표준 라이브러리) — openpyxl이 없다(새 패키지는 승인 필요). 공유 문자열의 후리가나(rPh)는 뺀다
NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"


def xlsx_sheets(blob):
    """{시트 이름: [[셀 값…]…]}"""
    z = zipfile.ZipFile(io.BytesIO(blob))
    ss = []
    if "xl/sharedStrings.xml" in z.namelist():
        for si in ET.fromstring(z.read("xl/sharedStrings.xml")).findall(f"{NS}si"):
            parts = [t.text or "" for t in si.findall(f"{NS}t")] + [t.text or "" for r in si.findall(f"{NS}r") for t in r.findall(f"{NS}t")]
            ss.append("".join(parts))
    rels = {r.get("Id"): r.get("Target") for r in ET.fromstring(z.read("xl/_rels/workbook.xml.rels"))}
    out = {}
    for s in ET.fromstring(z.read("xl/workbook.xml")).find(f"{NS}sheets"):
        rid = s.get("{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id")
        target = rels.get(rid, "")
        path = "xl/" + target.lstrip("/").removeprefix("xl/")
        if path not in z.namelist():
            continue
        rows = []
        for r in ET.fromstring(z.read(path)).iter(f"{NS}row"):
            vals = {}
            for cell in r.findall(f"{NS}c"):
                v, t = cell.find(f"{NS}v"), cell.get("t")
                if t == "s" and v is not None:
                    val = ss[int(v.text)]
                elif t == "inlineStr":
                    val = "".join(x.text or "" for x in cell.iter(f"{NS}t"))
                else:
                    val = v.text if v is not None else None
                col = 0
                for ch in re.match(r"[A-Z]+", cell.get("r")).group():
                    col = col * 26 + ord(ch) - 64
                vals[col - 1] = val
            rows.append([vals.get(i) for i in range(max(vals) + 1)] if vals else [])
        out[s.get("name")] = rows
    return out


def jnto_series(sheets, markets):
    """연도 시트(이름 = 연도)의 시장 행 → {시장 id: {YYYY-MM: 인원}}. 월 열은 머리행의 'N月' 위치에서 찾는다"""
    labels = {m["label"]: m["id"] for m in markets}
    out = {}
    for name, rows in sheets.items():
        if not re.match(r"^\d{4}$", name.strip()):
            continue
        year, cols = int(name), {}
        for row in rows[:12]:
            for i, cell in enumerate(row):
                m = re.match(r"^\s*(\d{1,2})月", str(cell or ""))
                if m and 1 <= int(m.group(1)) <= 12:
                    cols.setdefault(int(m.group(1)), i)
            if len(cols) >= 12:
                break
        if not cols:
            continue
        for row in rows:
            lab = str(row[0] or "").strip() if row else ""
            if lab in labels:
                for mo, i in cols.items():
                    v = row[i] if i < len(row) else None
                    if v not in (None, "") and re.match(r"^\d+(\.\d+)?$", str(v)):
                        out.setdefault(labels[lab], {})[f"{year}-{mo:02d}"] = float(v)
    return out


def fetch_jp_inbound(c):
    j = c["jp_inbound"]
    page = common.http_get(j["page"], headers=ua(), timeout=60)
    page = page.decode("utf-8", "replace") if isinstance(page, bytes) else page
    links = re.findall(r'href="(/statistics/data/_files/[^"]+\.xlsx)"', page)
    if not links:
        raise RuntimeError("JNTO 통계 페이지에 xlsx 링크가 없다")
    blob = common.http_get(JNTO + links[0], headers=ua(), timeout=90)
    out = jnto_series(xlsx_sheets(blob), j["markets"])
    if not out:
        raise RuntimeError("JNTO xlsx에서 시장 행을 찾지 못했다")
    return out


# ── 저장·지표·경보 ───────────────────────────────────────

def connect(path=DB):
    path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(path)
    con.execute("create table if not exists obs(id text, month text, value real, primary key(id, month))")
    return con


def store(con, data):
    n = 0
    for sid, s in data.items():
        con.executemany("insert or replace into obs values(?,?,?)", [(sid, m, v) for m, v in s.items()])
        n += len(s)
    con.commit()
    return n


def load(con):
    out = {}
    for sid, m, v in con.execute("select id, month, value from obs"):
        out.setdefault(sid, {})[m] = v
    return out


def catalog(c):
    """{id: {family, region, name, cat, kind, noisy, cpi, exposure}}"""
    ex = c.get("exposure") or {}
    out = {}
    for it in c["macro"]["us"]:
        out[it["id"]] = {"family": "us", "region": "미국", "name": it["name"], "cat": it["cat"], "kind": "level", "cpi": it.get("cpi"), "exposure": ex.get(it["id"], [])}
    for it in c["macro"]["jp"]["items"]:
        out[it["id"]] = {"family": "jp", "region": "일본", "name": it["name"], "cat": it["cat"], "kind": "level", "noisy": bool(it.get("noisy")), "exposure": ex.get(it["id"], [])}
    for it in c["macro"]["jp_inbound"]["markets"]:
        out[it["id"]] = {"family": "jp_inbound", "region": "일본", "name": it["name"], "cat": "inbound", "kind": "level", "exposure": ex.get(it["id"], [])}
    e = c["macro"]["eu"]
    for g, gname in e["geos"].items():
        for n in e["nace"]:
            out[eu_id(g, n["cat"])] = {"family": "eu", "region": gname, "name": f"{gname} {n['name']}", "cat": n["cat"], "kind": "level", "exposure": ex.get(f"eu-{n['cat']}", [])}
    for it in c["macro"]["uk"]:
        out[it["id"]] = {"family": "uk", "region": "영국", "name": it["name"], "cat": it["cat"], "kind": it.get("kind", "level"), "exposure": ex.get(it["id"], [])}
    return out


def compute(data, cat_, alert):
    rows = {}
    for sid, meta in cat_.items():
        m = metrics(data.get(sid) or {}, meta["kind"])
        if not m:
            continue
        rows[sid] = {**meta, **m, "flag": None if meta["cat"] == "price" else flag(m, meta.get("noisy"), alert)}
    newest = {}
    for r in rows.values():
        newest[r["family"]] = max(newest.get(r["family"], ""), r["month"])
    for r in rows.values():   # 같은 원천의 최신 달보다 3개월 넘게 뒤처진 시계열은 끊긴 것으로 보고 경보에서 뺀다
        if r["month"] < shift(newest[r["family"]], -3):
            r["stale"], r["flag"] = True, None
    for sid, r in rows.items():   # 판매 − 가격 = 실질 근사(같은 달끼리만)
        p = rows.get(r.get("cpi") or "")
        if p and p["month"] == r["month"] and r.get("yoy3") is not None and p.get("yoy3") is not None:
            r["real_yoy3"] = round(r["yoy3"] - p["yoy3"], 4)
    return rows


def pct(x, nd=1):
    return "—" if x is None else f"{x * 100:+.{nd}f}%"


def release_text(fam, month, flagged):
    parts = []
    for r in flagged[:6]:
        ex = ", ".join(str(e).split(" ")[-1] if " " in str(e) else str(e) for e in (r.get("exposure") or [])[:4])
        real = f" · 실질 근사 {pct(r['real_yoy3'])}" if r.get("real_yoy3") is not None else ""
        parts.append(f"{r['name']} 3개월 YoY {pct(r['yoy3'])}(가속 {r['accel_pp']:+.1f}%p, 5년 z {r['z']:+.1f}){real}" + (f" → {ex}" if ex else ""))
    return f"{FAMILY_NAME[fam]} {month}: " + "; ".join(parts)


def releases(rows, st, today):
    """원천 묶음마다 새 달이 나왔는지 — 새 달이고 문턱을 넘는 업종이 있으면 radar 항목 한 건(없으면 상태만)"""
    items, seen = [], st.setdefault("months", {})
    fams = {}
    for r in rows.values():
        fams.setdefault(r["family"], []).append(r)
    for fam, rs in fams.items():
        month = max(r["month"] for r in rs)
        if seen.get(fam) == month:
            continue
        first = fam not in seen
        seen[fam] = month
        flagged = sorted([r for r in rs if r["month"] == month and r.get("flag")], key=lambda r: -abs(r["accel_pp"]))
        if first or not flagged:   # 처음 켠 날은 기준만 잡는다(지난 달을 새 발표처럼 보내지 않게)
            continue
        text = release_text(fam, month, flagged)
        items.append(common.make_item("src-consumer-macro", f"{fam}:{month}", FAMILY_URL[fam],
                                      f"[지표 발표] {FAMILY_NAME[fam]} {month} — 업종 {len(flagged)}개 문턱", common.iso(common.now_kst()), "지표", "ko", text,
                                      extra={"tier": "T2", "kind": "consumer_macro", "family": fam, "month": month,
                                             "flags": [{"id": r.get("id"), "name": r["name"], "flag": r["flag"], "yoy3": r["yoy3"], "accel_pp": r["accel_pp"], "z": r["z"]} for r in flagged]}))
    return items


def write(rows, data, errors):
    OUT.mkdir(parents=True, exist_ok=True)
    for sid, r in rows.items():
        r["id"] = sid
    LATEST.write_text(json.dumps({"as_of": common.iso(common.now_kst()), "series": rows, "errors": errors,
                                  "note": "업종 통계 → 노출 종목은 가설(금지표: 업종 판매 증가 → 특정 기업 매출). 가계조사 품목은 표본 잡음이 크다."},
                                 ensure_ascii=False, indent=1), encoding="utf-8")
    with SERIES_CSV.open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["id", "month", "value"])
        for sid in sorted(rows):
            s = data.get(sid) or {}
            for m in sorted(s)[-72:]:
                w.writerow([sid, m, s[m]])


def run(alert_items=True):
    c, env = cfg(), common.load_env()
    m = c["macro"]
    start = m.get("history_from", "2015-01")
    errors, got = [], {}
    for fam, fn in (("us", lambda: fetch_us(m, env, start)), ("jp", lambda: fetch_jp(m, env, start)), ("jp_inbound", lambda: fetch_jp_inbound(m)),
                    ("eu", lambda: fetch_eu(m, start)), ("uk", lambda: fetch_uk(m))):
        try:
            got.update(fn())
        except Exception as exc:
            errors.append(f"{fam}: {type(exc).__name__}: {str(exc)[:120]}")
    con = connect()
    n = store(con, got)
    data = load(con)
    con.close()
    rows = compute(data, catalog(c), m["alert"])
    for sid in rows:
        rows[sid]["id"] = sid
    st = common.load_state(STATE, {})
    items = releases(rows, st, common.now_kst().date())
    if alert_items and items:
        common.save_new_items(items)
    common.save_state(STATE, st)
    write(rows, data, errors)
    common.record_health("consumer-macro", not (errors and not got), "; ".join(errors[:3]) or None)
    if errors and not got:
        raise RuntimeError("소비 통계를 하나도 받지 못했다: " + "; ".join(errors[:3]))
    flagged = sum(1 for r in rows.values() if r.get("flag"))
    return f"소비 통계 {len(rows)}개 시계열 · 저장 {n}값 · 문턱 {flagged}개 · 새 발표 경보 {len(items)}건 · 오류 {len(errors)}"


def status():
    d = json.loads(LATEST.read_text(encoding="utf-8"))
    for sid, r in sorted(d["series"].items(), key=lambda x: (x[1]["family"], x[0])):
        print(f"{sid:22} {r['month']} 3M {pct(r.get('yoy3')):>7} 가속 {r.get('accel_pp') if r.get('accel_pp') is not None else '—':>6} z {r.get('z') if r.get('z') is not None else '—':>5} {r.get('flag') or ''} {r['name']}")
    print("오류:", d.get("errors"))


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    if "--status" in sys.argv:
        status()
    else:
        print(run(alert_items="--no-alert" not in sys.argv))
