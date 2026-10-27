"""공개 잡보드 API — Greenhouse·Lever (§11.4 L6 타사 공고 속 T0 언급, §12 해외 법인 채용)
config/job_boards.yaml 대상만. 채용 담당자 개인 정보는 저장하지 않는다.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "reverse" / "collectors"))
from common_rev import common, lexicon, save_candidates  # noqa: E402

SOURCE_ID = "src-job-boards"


def run():
    cfg = common.load_yaml("config/job_boards.yaml") or {}
    lex = lexicon()
    cands = []
    jobs = []
    for token in cfg.get("greenhouse") or []:
        data = json.loads(common.http_get(f"https://boards-api.greenhouse.io/v1/boards/{token}/jobs", {"content": "true"}))
        for j in data.get("jobs", []):
            jobs.append((token, str(j["id"]), j.get("title", ""), (j.get("location") or {}).get("name", ""),
                         j.get("absolute_url", ""), common.strip_tags(j.get("content", ""))))
    for slug in cfg.get("lever") or []:
        for j in json.loads(common.http_get(f"https://api.lever.co/v0/postings/{slug}", {"mode": "json"})):
            jobs.append((slug, j["id"], j.get("text", ""), (j.get("categories") or {}).get("location", ""),
                         j.get("hostedUrl", ""), common.strip_tags(j.get("descriptionPlain", "") or "")))
    for board, jid, title, loc, url, body in jobs:
        text = f"{title} {body}"
        for eid, info in lex.items():
            hit = next((n for n in info["names"] if n.lower() in text.lower()), None)
            if hit:
                i = text.lower().find(hit.lower())
                cands.append({"uid": f"{board}:{jid}", "mentioned_entity": eid, "match_text": hit,
                              "counterparty": board, "form": "채용", "published_at": "", "language": "en",
                              "url": url, "snippet": text[max(0, i - 100):i + 100], "location": loc,
                              "signal_type_hint": "채용"})
    n = save_candidates("L6", SOURCE_ID, cands)
    common.record_health(SOURCE_ID, True)
    return len(jobs), n


if __name__ == "__main__":
    print("잡보드: 공고 %d, 후보 %d" % run())