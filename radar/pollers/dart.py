"""DART OpenAPI 공시 목록 폴러 — https://opendart.fss.or.kr (list.json)

감시 목록의 KRX 기업(T0, 확정 T1)만 조회한다. corp_code는 corpCode.xml로 한 번 받아 캐시.
"""
import io
import json
import zipfile
import xml.etree.ElementTree as ET
from datetime import timedelta

from . import common

SOURCE_ID = "src-dart"
LIST_URL = "https://opendart.fss.or.kr/api/list.json"
CORP_URL = "https://opendart.fss.or.kr/api/corpCode.xml"


def corp_codes(key):
    cache = common.load_state("dart_corp_codes")
    if cache:
        return cache
    raw = common.http_get(CORP_URL, {"crtfc_key": key}, timeout=60)
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        xml = z.read(z.namelist()[0])
    wanted = {r["ticker"] for r in common.load_watchlist() if r["market"] == "KRX"}
    out = {}
    for el in ET.fromstring(xml).iter("list"):
        stock = (el.findtext("stock_code") or "").strip()
        if stock in wanted:
            out[stock] = el.findtext("corp_code").strip()
    common.save_state("dart_corp_codes", out)
    return out


def poll(env, tiers=("T0",)):
    key = env.get("DART_API_KEY")
    if not key:
        raise RuntimeError("DART_API_KEY 없음 (D:\\local-only\\secrets\\.env)")
    codes = corp_codes(key)
    today = common.now_kst()
    bgn = (today - timedelta(days=1)).strftime("%Y%m%d")
    items = []
    for row in common.load_watchlist():
        if row["market"] != "KRX" or row["tier"] not in tiers or row["ticker"] not in codes:
            continue
        data = json.loads(common.http_get(LIST_URL, {
            "crtfc_key": key, "corp_code": codes[row["ticker"]], "bgn_de": bgn,
            "end_de": today.strftime("%Y%m%d"), "page_count": "100"}))
        status = data.get("status")
        if status == "013":
            continue
        if status != "000":
            raise RuntimeError(f"DART status {status}: {data.get('message')}")
        for d in data.get("list", []):
            rcept = d["rcept_no"]
            title = f"{d['corp_name']} {d['report_nm'].strip()}"
            dt = d["rcept_dt"]
            items.append(common.make_item(
                SOURCE_ID, rcept, f"https://dart.fss.or.kr/dsaf001/main.do?rcpNo={rcept}", title,
                f"{dt[:4]}-{dt[4:6]}-{dt[6:]}", "공시", "ko", d.get("flr_nm", ""),
                extra={"entities_matched": [row["entity_id"]], "report_nm": d["report_nm"].strip(),
                       "tier": row["tier"]}))
    return items
