"""논문·실무 리서치 수집기 (BUILD_PROMPT §21.14, ADR-010 §4) — 결정론, 판단은 스킬 model-lab

영어권 학계·금융업계의 새 논문·기술 자료를 매일 모아 관련도 점수(키워드 가중합, 결정론)로 줄 세운다.
레이더 수집(run_poll → 판정 → 텔레그램)과 분리 — 논문은 알림이 아니라 모델 고도화의 재료다.
저장: radar/literature/inbox/YYYYMMDD.jsonl (git 제외) · 상태: radar/state/literature.json (본 링크)
유료 학술지 원문은 받지 않는다(제목·초록·링크만). 피드 주소는 2026-10-28 접속 확인.
사용: py radar/literature.py [--top 15]   # 수집 후 오늘 상위 목록 출력
      py radar/literature.py --show [--top 15]   # 수집 없이 오늘 목록만
"""
import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from pollers import common, rss  # noqa: E402

INBOX = common.ROOT / "radar" / "literature" / "inbox"
FEEDS = {
    # arXiv 계량금융 전 분야(매일 공지분)
    "arxiv-qfin": "https://rss.arxiv.org/rss/q-fin.PM+q-fin.PR+q-fin.ST+q-fin.GN+q-fin.CP+q-fin.RM+q-fin.TR+q-fin.MF",
    "nber": "https://www.nber.org/rss/new.xml",
    "fed-feds": "https://www.federalreserve.gov/feeds/feds.xml",
    "fed-ifdp": "https://www.federalreserve.gov/feeds/ifdp.xml",
    "damodaran": "https://aswathdamodaran.blogspot.com/feeds/posts/default",
    "alpha-architect": "https://alphaarchitect.com/feed/",
}
# 확인 실패(2026-10-28): BIS 워킹페이퍼 RSS(항목 0), ECB(SSL 인증서 오류), RePEc NEP RSS(항목 0), SSRN(공식 API·RSS 없음)

# 관련도 키워드 — (이름, 정규식, 가중치). 치입 모델 아키텍처에 쓸 수 있는 주제일수록 높다
KEYWORDS = [
    ("밸류에이션", r"valuation|discounted cash flow|DCF|intrinsic value|terminal value", 3),
    ("할인율·ERP", r"equity (risk )?premium|cost of (equity|capital)|WACC", 3),
    ("애널리스트 추정", r"analysts?'? (forecast|estimate|recommendation)|earnings forecast|(forecast|estimate) revision", 3),
    ("실적 반응", r"post[- ]earnings|earnings announcement|earnings surprise|PEAD", 3),
    ("멀티배거", r"multibagger|ten[- ]?bagger|extreme (winners|returns)|lottery stocks|right[- ]tail", 4),
    ("반도체·AI HW", r"semiconductor|chips?|DRAM|NAND|HBM|GPU|AI (hardware|capex|infrastructure|investment)|data cent(er|re)", 4),
    ("사이클·캐파", r"capacity (investment|utilization|expansion)|capital expenditure|capex|investment cycle|inventory cycle", 2),
    ("가치·수익성", r"price[- ]to[- ]book|book[- ]to[- ]market|return on equity|profitability (premium|factor)|quality (factor|minus)", 2),
    ("요인·이상현상", r"momentum|cross[- ]section of (stock |expected )?returns|factor (model|zoo|investing)|anomal(y|ies)", 2),
    ("내러티브·관심", r"narratives?|news sentiment|textual analysis|investor attention|media coverage", 2),
    ("ML·LLM", r"machine learning|neural network|large language model|LLMs?", 1),
    ("검증·재현", r"replication|out[- ]of[- ]sample|overfitting|data[- ]snooping|p[- ]hacking", 2),
    ("내포 기대", r"expectations investing|implied (growth|expectations)|market[- ]implied", 3),
    ("주식", r"stocks?|equit(y|ies)|firms?'? (value|returns)", 1),
]
_KW = [(name, re.compile(p, re.I), w) for name, p, w in KEYWORDS]


def relevance(title, abstract=""):
    text = f"{title} {abstract}"
    hits = [(name, w) for name, m, w in _KW if m.search(text)]
    return sum(w for _, w in hits), [n for n, _ in hits]


def collect():
    st = common.load_state("literature", {"seen": []})
    seen = set(st["seen"])
    day = common.now_kst().strftime("%Y%m%d")
    INBOX.mkdir(parents=True, exist_ok=True)
    out, errors = [], []
    for fid, url in FEEDS.items():
        try:
            entries = rss.parse_feed(common.http_get(url, timeout=30))
        except Exception as exc:  # 피드 하나가 죽어도 계속
            errors.append(f"{fid}: {type(exc).__name__}")
            continue
        for e in entries:
            link = e["link"]
            if not link:
                continue
            key = hashlib.sha1(link.encode()).hexdigest()[:16]
            if key in seen:
                continue
            seen.add(key)
            title = common.strip_tags(e["title"])
            abstract = common.strip_tags(e["desc"])[:1500]
            score, tags = relevance(title, abstract)
            out.append({"lit_id": f"lit-{day}-{key[:8]}", "feed": fid, "title": title, "url": link,
                        "published_at": rss.to_iso(e["date"]), "collected_at": common.iso(common.now_kst()),
                        "abstract": abstract, "relevance": score, "tags": tags})
    if out:
        with (INBOX / f"{day}.jsonl").open("a", encoding="utf-8") as f:
            for r in out:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
    st["seen"] = sorted(seen)[-20000:]
    common.save_state("literature", st)
    common.record_health("src-literature", not (errors and len(errors) == len(FEEDS)), "; ".join(errors) or None)
    return out, errors


def run():
    """run_hourly용 — (신규 건수, 실패 목록)"""
    new, errors = collect()
    return len(new), errors


def today(top=15, day=None):
    p = INBOX / f"{day or common.now_kst().strftime('%Y%m%d')}.jsonl"
    if not p.exists():
        return []
    rows = [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines() if l.strip()]
    return sorted(rows, key=lambda r: -r["relevance"])[:top]


def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument("--show", action="store_true")
    ap.add_argument("--top", type=int, default=15)
    a = ap.parse_args(argv)
    if not a.show:
        new, errors = collect()
        print(f"[논문 수집] 신규 {len(new)}건" + (f", 실패: {'; '.join(errors)}" if errors else ""))
    for r in today(a.top):
        if r["relevance"] <= 0:
            break
        print(f"- ({r['relevance']}) [{r['feed']}] {r['title'][:110]} | {','.join(r['tags'][:4])} | {r['url']}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
