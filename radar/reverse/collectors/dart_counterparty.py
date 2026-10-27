"""L1 국내 타사 공시 + 공시유보 만료 추적 (BUILD_PROMPT §11.4 L1, §7.2.1 counterparty-sweep)

1) 당일 거래소 공시(pblntf_ty=I) 중 '공급계약' 보고서 본문에서 T0 기업명을 찾는다(T0가 계약 상대방인 타사 공시).
2) T0 자신의 공급계약 공시에서 '공시유보'·'유보기한'을 파싱해 만료일을 기록한다(만료 시 상대방 공개).
DART_API_KEY 필요. 본문 조회(document.xml)는 건당 1회 — 하루 호출량을 고려해 공급계약 보고서만.
"""
import io
import json
import re
import zipfile
from datetime import timedelta

from common_rev import common, lexicon, save_candidates

SOURCE_ID = "src-dart-counterparty"
LIST_URL = "https://opendart.fss.or.kr/api/list.json"
DOC_URL = "https://opendart.fss.or.kr/api/document.xml"
RESERVE_RE = re.compile(r"유보\s*기한[^0-9]{0,20}(\d{4})[.\-년\s]*(\d{1,2})[.\-월\s]*(\d{1,2})")


def doc_text(key, rcept_no):
    raw = common.http_get(DOC_URL, {"crtfc_key": key, "rcept_no": rcept_no}, timeout=60)
    try:
        with zipfile.ZipFile(io.BytesIO(raw)) as z:
            parts = [z.read(n).decode("utf-8", errors="ignore") for n in z.namelist()]
    except zipfile.BadZipFile:
        return ""
    return common.strip_tags(" ".join(parts))


def run(days=1):
    env = common.load_env()
    key = env.get("DART_API_KEY")
    if not key:
        raise RuntimeError("DART_API_KEY 없음")
    lex = lexicon()
    t0_codes = {r["ticker"]: r["entity_id"] for r in common.load_watchlist() if r["tier"] == "T0"}
    today = common.now_kst()
    params = {"crtfc_key": key, "bgn_de": (today - timedelta(days=days)).strftime("%Y%m%d"),
              "end_de": today.strftime("%Y%m%d"), "pblntf_ty": "I", "page_count": "100"}
    cands, reserves = [], common.load_state("dart_reserve_expiry")
    page = 1
    while True:
        data = json.loads(common.http_get(LIST_URL, {**params, "page_no": str(page)}))
        if data.get("status") not in ("000",):
            break
        for d in data.get("list", []):
            if "공급계약" not in d["report_nm"]:
                continue
            text = doc_text(key, d["rcept_no"])
            url = f"https://dart.fss.or.kr/dsaf001/main.do?rcpNo={d['rcept_no']}"
            own = t0_codes.get(d.get("stock_code", ""))
            if own:  # T0 자신의 계약 → 공시유보 만료 추적
                m = RESERVE_RE.search(text)
                if "유보" in text:
                    until = f"{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3)):02d}" if m else ""
                    reserves[d["rcept_no"]] = {"entity": own, "report": d["report_nm"], "url": url,
                                               "reserve_until": until, "found_at": common.iso(today)}
                continue
            for eid, info in lex.items():  # 타사 공시에서 T0 언급
                hit = next((n for n in info["names"] if n in text), None)
                if hit and not any(neg.split()[0] in text for neg in info["negative"] if neg):
                    cands.append({"uid": d["rcept_no"], "mentioned_entity": eid, "match_text": hit,
                                  "counterparty": d["corp_name"], "form": d["report_nm"],
                                  "published_at": d["rcept_dt"], "url": url, "language": "ko",
                                  "signal_type_hint": "공시언급"})
        if page >= int(data.get("total_page", 1)):
            break
        page += 1
    common.save_state("dart_reserve_expiry", reserves)
    n = save_candidates("L1", SOURCE_ID, cands)
    common.record_health(SOURCE_ID, True)
    return len(cands), n, len(reserves)


if __name__ == "__main__":
    print("DART 타사 공시: 후보 %d, 신규 %d, 공시유보 추적 %d" % run())
