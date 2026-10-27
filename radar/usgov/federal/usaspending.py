"""미국 연방 지출 실적 — USASpending API (키 불필요, BUILD_PROMPT §13.2 v2)
'발표'가 아니라 '실제 집행'(보조금·계약)을 본다. 수혜자명은 config/us_gov/sites.yaml 거점 법인 + lexicon legal_entities.
"""
import json
import sys
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "reverse" / "collectors"))
from common_rev import common, lexicon, save_candidates  # noqa: E402

SOURCE_ID = "src-usaspending"
URL = "https://api.usaspending.gov/api/v2/search/spending_by_award/"
TYPES = {"grants": ["02", "03", "04", "05"], "contracts": ["A", "B", "C", "D"]}


def search(names, codes, start):
    body = json.dumps({"filters": {"recipient_search_text": names, "award_type_codes": codes,
                                   "time_period": [{"start_date": start, "end_date": common.now_kst().date().isoformat()}]},
                       "fields": ["Award ID", "Recipient Name", "Award Amount", "Awarding Agency", "Start Date", "Description"],
                       "limit": 50}).encode()
    req = urllib.request.Request(URL, data=body, headers={"Content-Type": "application/json", "User-Agent": common.UA})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read()).get("results", [])


def run(start="2024-01-01"):
    lex = lexicon()
    cands = []
    for eid, info in lex.items():
        names = [n for n in info["names"] if any(k in n for k in ("Samsung", "SK hynix", "Hynix"))][:4]
        if not names:
            continue
        for kind, codes in TYPES.items():
            for a in search(names, codes, start):
                cands.append({"uid": f"{a.get('Award ID')}", "mentioned_entity": eid, "match_text": a.get("Recipient Name"),
                              "counterparty": a.get("Awarding Agency"), "form": f"연방 {kind}",
                              "published_at": a.get("Start Date"), "language": "en",
                              "url": f"https://www.usaspending.gov/search/?hash=&query={a.get('Award ID')}",
                              "original_title": (a.get("Description") or "")[:200],
                              "data": {"amount_usd": a.get("Award Amount")}, "signal_type_hint": "보조금"})
    n = save_candidates("L2", SOURCE_ID, cands)
    common.record_health(SOURCE_ID, True)
    return len(cands), n


if __name__ == "__main__":
    print("USASpending: 후보 %d, 신규 %d" % run())