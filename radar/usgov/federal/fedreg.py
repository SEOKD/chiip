"""미국 관보(Federal Register) — 정식 게재 + 사전 공람(Public Inspection) (BUILD_PROMPT §13.2)

사전 공람 문서는 정식 게재 전날 공개된다 → 하루 앞서 포착. 결과는 레이더 inbox 항목(doc_type 규제·정책)으로
저장해 radar-triage → policy-analyst 흐름을 탄다. 키 불필요.
"""
import json
import sys
from datetime import timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))  # radar/
from pollers import common  # noqa: E402

DOCS = "https://www.federalregister.gov/api/v1/documents.json"
PI = "https://www.federalregister.gov/api/v1/public-inspection-documents/current.json"


def config():
    c = common.load_yaml("config/us_gov/sources.yaml") or {}
    return [t.lower() for t in c.get("terms", [])], set(c.get("agencies_of_interest", []))


def relevant(title, abstract, agency_slugs, terms, agencies):
    text = f"{title} {abstract}".lower()
    return any(t in text for t in terms) or bool(agencies & set(agency_slugs)) and any(
        k in text for k in ("semiconductor", "export", "tariff", "chip", "computing", "memory", "232"))


def poll_docs(days=2):
    terms, agencies = config()
    since = (common.now_kst() - timedelta(days=days)).date().isoformat()
    items = []
    for term in terms:
        params = {"conditions[term]": term, "conditions[publication_date][gte]": since,
                  "per_page": "50", "order": "newest"}
        data = json.loads(common.http_get(DOCS, params))
        for d in data.get("results", []):
            slugs = [a.get("slug", "") for a in d.get("agencies", [])]
            if not relevant(d.get("title", ""), d.get("abstract") or "", slugs, terms, agencies):
                continue
            items.append(common.make_item(
                "src-fedreg", d["document_number"], d["html_url"], f"[관보 {d.get('type', '')}] {d['title']}",
                d.get("publication_date", ""), "규제·정책", "en", (d.get("abstract") or "")[:200],
                extra={"agencies": slugs, "fr_type": d.get("type"), "policy_stage_hint": d.get("type")}))
    return items


def poll_public_inspection():
    terms, agencies = config()
    data = json.loads(common.http_get(PI))
    items = []
    for d in data.get("results", []):
        slugs = [a.get("slug", "") for a in d.get("agencies", [])]
        title = d.get("title") or ""
        if not relevant(title, "", slugs, terms, agencies):
            continue
        items.append(common.make_item(
            "src-fedreg-pi", d.get("document_number") or d.get("filename", title[:40]), d.get("html_url") or d.get("pdf_url", ""),
            f"[관보 사전공람·{d.get('type', '')}] {title}", d.get("publication_date", ""), "규제·정책", "en",
            f"정식 게재 예정일 {d.get('publication_date', '')}",
            extra={"agencies": slugs, "fr_type": d.get("type"), "public_inspection": True}))
    return items


def run():
    items = poll_docs() + poll_public_inspection()
    new = common.save_new_items(items)
    common.record_health("src-fedreg", True)
    return len(items), len(new)


if __name__ == "__main__":
    print("관보: 관련 %d, 신규 %d" % run())
