"""대만 원문 공시(重大訊息) — Chiip Ten-bagger 발굴·커버리지 대만 종목 (마스터 지시 2026-10-29 "발굴하고 관련 보도(반드시 원문)를 팔로업하라").

TWSE OpenAPI 上市公司每日重大訊息(t187ap04_L, 공식 공개 API)에서 config/discovery.yaml·config/coverage.yaml의 대만 종목만 거른다.
회사가 직접 낸 공시라 '원문'이다(event_gate의 1차 자료). 월매출은 src-twse-monthly가 따로 받는다. TPEx(상장 장외) 종목은 다음 단계.
"""
import hashlib
from datetime import datetime

from pollers import common

SRC = "src-tw-disclosure"
API = "https://openapi.twse.com.tw/v1/opendata/t187ap04_L"


def tw_codes():
    out = {}
    for t in (common.load_yaml("config/discovery.yaml") or {}).get("themes") or []:
        for c in t.get("candidates") or []:
            if c.get("market") == "tw":
                out[str(c["code"])] = c
    for c in (common.load_yaml("config/coverage.yaml") or {}).get("companies") or []:
        if c.get("market") == "tw":
            out[str(c["code"])] = c
    return out


def roc_to_iso(d, t="0"):
    """민국 날짜 1151028 + 시각 70003 → 2026-10-28T07:00:03+08:00"""
    d, t = str(d).strip(), str(t).strip().zfill(6)
    y, m, dd = int(d[:-4]) + 1911, int(d[-4:-2]), int(d[-2:])
    return datetime(y, m, dd, int(t[:2]), int(t[2:4]), int(t[4:6])).isoformat() + "+08:00"


def poll(env=None):
    import json
    codes = tw_codes()
    rows = json.loads(common.http_get(API, timeout=30))
    items = []
    for r in rows:
        code = str(r.get("公司代號", "")).strip()
        if code not in codes:
            continue
        c = codes[code]
        subj = " ".join(str(r.get("主旨 ") or r.get("主旨") or "").split())
        title = f"{r.get('公司名稱', c.get('name'))}({code}) 重大訊息: {subj}"
        uid = hashlib.sha1(f"{code}|{r.get('發言日期')}|{r.get('發言時間')}|{subj}".encode()).hexdigest()[:16]
        items.append(common.make_item(SRC, uid, f"{API}#{code}-{r.get('發言日期')}-{r.get('發言時間')}", title,
                                      roc_to_iso(r.get("發言日期"), r.get("發言時間")), "공시", "zh",
                                      " ".join(str(r.get("說明", "")).split())[:200],
                                      extra={"entities_matched": [c["id"]], "publisher": "TWSE 重大訊息"}))
    return items
