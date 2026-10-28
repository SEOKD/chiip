"""지방정부 회의 플랫폼 어댑터 — Legistar 공개 Web API (webapi.legistar.com/v1/<client>)
config/us_gov/sites.yaml 의 meeting_platforms 에 {platform: legistar, client: <id>} 가 있는 거점만.
다가오는 회의·안건 항목에서 lexicon 이름·코드명 패턴('Project ')을 찾는다.
"""
import json
import re
import sys
from datetime import timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "reverse" / "collectors"))
from common_rev import common, lexicon, save_candidates  # noqa: E402

SOURCE_ID = "src-legistar"
API = "https://webapi.legistar.com/v1/{client}"
CODENAME = re.compile(r"\bProject\s+[A-Z][A-Za-z]+")


def run():
    sites = common.load_yaml("config/us_gov/sites.yaml") or []
    lex = lexicon()
    since = (common.now_kst() - timedelta(days=7)).strftime("%Y-%m-%d")
    cands = []
    for s in sites:
        for mp in s.get("meeting_platforms") or []:
            if mp.get("platform") != "legistar":
                continue
            base = API.format(client=mp["client"])
            events = json.loads(common.http_get(f"{base}/events", {"$filter": f"EventDate ge datetime'{since}'"}))
            for ev in events:
                items = json.loads(common.http_get(f"{base}/events/{ev['EventId']}/eventitems"))
                for it in items:
                    title = it.get("EventItemTitle") or ""
                    names = [eid for eid, info in lex.items() if any(n.lower() in title.lower() for n in info["names"])]
                    code = CODENAME.search(title)
                    if not names and not code:
                        continue
                    cands.append({"uid": f"{mp['client']}:{it.get('EventItemId')}", "mentioned_entity": (names or [s["company"]])[0],
                                  "match_text": code.group(0) if code else "", "counterparty": f"{s['site_id']}:{ev.get('EventBodyName')}",
                                  "form": "지방안건", "published_at": ev.get("EventDate"), "language": "en",
                                  "url": ev.get("EventInSiteURL") or base, "original_title": title[:300],
                                  "signal_type_hint": "인허가"})
    n = save_candidates("L2", SOURCE_ID, cands)
    # 실시간 보고(§21.12): 같은 안건을 레이더 항목으로도 넣어 radar-triage → 텔레그램 흐름을 탄다
    radar = common.save_new_items([common.make_item(
        SOURCE_ID, c["uid"], c["url"], f"[지방안건 {c['counterparty']}] {c['original_title'][:160]}",
        str(c.get("published_at") or ""), "규제·정책", "en", c["original_title"][:200],
        extra={"policy_level": "지방", "codename": c["match_text"]}) for c in cands])
    common.record_health(SOURCE_ID, True)
    print(f"Legistar: 역방향 후보 신규 {n}")
    return len(cands), len(radar)


if __name__ == "__main__":
    print("Legistar: 안건 %d, 레이더 신규 %d" % run())