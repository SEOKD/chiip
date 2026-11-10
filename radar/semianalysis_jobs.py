"""SemiAnalysis 채용 공고 감시 — Memory Analyst(South Korea) (마스터 지시 2026-11-11 "SemiAnalysis Memory Analyst (South Korea) 채용이 나오면 알려줘. 공식 커리어 채널과 링크드인을 참조해")

원천: 공식 채용 페이지 https://semianalysis.com/semianalysis-careers/ 의 JSON-LD JobPosting(제목·근무지·직무 주소). 지원 링크는 Dover(jobs.dover.com, /api/는 robots 금지라 쓰지 않는다).
링크드인은 쓰지 않는다 — robots.txt 전체 금지·로그인 벽이고 CLAUDE.md 제외 원천이다. 같은 공고는 공식 페이지에 먼저 올라온다.
규칙: 제목·근무지가 WANT(메모리 + 한국)에 맞는 새 공고만 inbox src-semianalysis-jobs로 넣는다 → Pulse '채용 공고'가 텔레그램으로 보낸다. 다른 직무는 상태에만 남긴다.
"""
import html
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from pollers import common  # noqa: E402

SRC = "src-semianalysis-jobs"
URL = "https://semianalysis.com/semianalysis-careers/"
WANT = [re.compile(r"memory|DRAM|HBM|NAND", re.I), re.compile(r"korea|seoul|한국|서울", re.I)]
LD_RE = re.compile(r'<script[^>]*application/ld\+json[^>]*>(.*?)</script>', re.S)


def postings(page):
    out = []
    for blob in LD_RE.findall(page):
        try:
            d = json.loads(blob)
        except ValueError:
            continue
        stack = d if isinstance(d, list) else [d]
        while stack:
            x = stack.pop()
            if isinstance(x, list):
                stack += x
            elif isinstance(x, dict):
                if x.get("@type") == "JobPosting":
                    loc = json.dumps([x.get("jobLocation"), x.get("applicantLocationRequirements")], ensure_ascii=False)
                    desc = re.sub(r"<[^>]+>", " ", html.unescape(x.get("description") or ""))
                    out.append({"title": html.unescape(x.get("title") or "").strip(), "url": x.get("url") or URL, "where": loc + " " + desc[:600]})
                stack += [v for v in x.values() if isinstance(v, (list, dict))]
    return out


def wanted(p):
    text = f"{p['title']} {p['where']}"
    return WANT[0].search(p["title"]) is not None and WANT[1].search(text) is not None


def run():
    st = common.load_state("semianalysis_jobs", {"seen": []})
    seen = set(st["seen"])
    try:
        ps = postings(common.http_get(URL, timeout=30).decode("utf-8", "ignore"))
    except Exception as e:
        common.record_health("semianalysis-jobs", False, str(e)[:120])
        return "semianalysis-jobs", 0
    items = []
    for p in ps:
        k = p["title"].lower()
        if k in seen:
            continue
        seen.add(k)
        if wanted(p):
            items.append(common.make_item(SRC, re.sub(r"\W+", "-", k)[:80], p["url"], f"[채용 공고] SemiAnalysis — {p['title']}",
                                          common.iso(common.now_kst()), "채용", "en", "공식 채용 페이지 새 공고(메모리·한국). 지원: " + URL,
                                          extra={"source_class": "채용 공고"}))
    st["seen"] = sorted(seen)
    st["titles"] = [p["title"] for p in ps]
    common.save_state("semianalysis_jobs", st)
    common.record_health("semianalysis-jobs", bool(ps), None if ps else "공고 0건 — 페이지 구조 확인")
    saved = common.save_new_items(items) if items else []
    return "semianalysis-jobs", len(saved)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    print(run())
    print("\n".join(common.load_state("semianalysis_jobs", {}).get("titles", [])))
