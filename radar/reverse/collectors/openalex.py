"""L4 학술 공동 저자 — OpenAlex(키 불필요): T0 소속 문자열이 있는 최근 논문 중 외부 기업 소속 공저자가 있는 것.
"""
import json
import time
from datetime import timedelta

from common_rev import common, english_names, lexicon, save_candidates

SOURCE_ID = "src-openalex"
URL = "https://api.openalex.org/works"


def run(days=30):
    since = (common.now_kst() - timedelta(days=days)).date().isoformat()
    lex = lexicon()
    cands = []
    for eid in lex:
        for name in english_names(eid, lex)[:2]:
            data = json.loads(common.http_get(URL, {
                "filter": f"raw_affiliation_strings.search:{name},from_publication_date:{since}", "per-page": "50"}))
            for w in data.get("results", []):
                insts = {i.get("display_name", "") for a in w.get("authorships", []) for i in a.get("institutions", [])}
                own = name.split()[0].lower()  # 자사 연구소(예: Samsung Advanced Institute …) 제외
                academic = ("University", "Institute", "College", "Academy", "School", "KAIST", "Laboratory", "Hospital")
                corp = ("Inc", "Corp", "Ltd", "Co.", "Company", "GmbH", "LLC", "Electronics", "Semiconductor", "Technologies")
                ext = sorted(i for i in insts if i and own not in i.lower()
                             and not any(a in i for a in academic) and any(k in i for k in corp))
                if not ext:
                    continue
                cands.append({"uid": w["id"].rsplit("/", 1)[-1], "mentioned_entity": eid, "match_text": name,
                              "counterparty": "; ".join(ext[:5]), "form": "공동논문",
                              "published_at": w.get("publication_date"), "language": "en",
                              "url": w.get("doi") or w["id"], "original_title": w.get("title"),
                              "signal_type_hint": "공동논문"})
            time.sleep(0.2)
    n = save_candidates("L4", SOURCE_ID, cands)
    common.record_health(SOURCE_ID, True)
    return len(cands), n


if __name__ == "__main__":
    print("OpenAlex 공동 논문: 후보 %d, 신규 %d" % run())