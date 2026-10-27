"""L1 상대방 공시 — SEC EDGAR 전문 검색 (efts.sec.gov/LATEST/search-index)

T0 영문명이 미국 상장사 공시 본문(8-K·10-K·10-Q·S-1·20-F·6-K)에 나오면 후보로 저장.
SEC 접속 규칙: 식별 가능한 User-Agent, 초당 10회 이하. SEC_USER_AGENT(.env)를 쓰면 그 값을 쓴다.
"""
import json
import time
import urllib.parse
from datetime import timedelta

from common_rev import common, english_names, lexicon, save_candidates

SOURCE_ID = "src-edgar-fts"
URL = "https://efts.sec.gov/LATEST/search-index"
FORMS = "8-K,10-K,10-Q,S-1,20-F,6-K,DEF 14A"


def run(days=7):
    env = common.load_env()
    ua = env.get("SEC_USER_AGENT") or common.UA
    lex = lexicon()
    end = common.now_kst().date()
    start = end - timedelta(days=days)
    cands, self_items = [], []
    for eid in lex:
        own_names = [n.lower() for n in english_names(eid, lex)]
        for name in english_names(eid, lex)[:4]:
            q = {"q": f'"{name}"', "forms": FORMS, "dateRange": "custom",
                 "startdt": start.isoformat(), "enddt": end.isoformat()}
            data = json.loads(common.http_get(URL, q, {"User-Agent": ua}))
            for h in data.get("hits", {}).get("hits", []):
                s = h["_source"]
                adsh, fname = h["_id"].split(":", 1)
                cik = (s.get("ciks") or ["0"])[0].lstrip("0")
                url = f"https://www.sec.gov/Archives/edgar/data/{cik}/{adsh.replace('-', '')}/{fname}"
                filer = " ".join(s.get("display_names", [])).lower()
                if any(n in filer for n in own_names):
                    # T0 자사 SEC 공시(6-K 등) = 1차 출처 → 메인 레이더 inbox로
                    self_items.append(common.make_item(
                        "src-sec-self", adsh, url, f"[SEC {s.get('form')}] {s.get('display_names', [''])[0]}",
                        s.get("file_date", ""), "공시", "en", s.get("file_description") or "",
                        extra={"entities_matched": [eid], "tier": "T0", "report_nm": s.get("form")}))
                    continue
                cands.append({"uid": h["_id"], "mentioned_entity": eid, "match_text": name,
                              "counterparty": "; ".join(s.get("display_names", [])), "form": s.get("form"),
                              "published_at": s.get("file_date"), "url": url, "language": "en",
                              "signal_type_hint": "공시언급"})
            time.sleep(0.2)
    n = save_candidates("L1", SOURCE_ID, cands)
    self_new = common.save_new_items(self_items)
    common.record_health(SOURCE_ID, True)
    return len(cands), n, len(self_new)


if __name__ == "__main__":
    print("EDGAR 전문 검색: 후보 %d, 신규 %d" % run())
