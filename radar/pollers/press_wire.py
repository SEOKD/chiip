"""공식 보도자료 수집 — PR Newswire·Business Wire RSS (저녁 브리프 '글로벌 공식 발표' 절)

미국·일본·EU·영국·한국 상장 반도체·AI 하드웨어·소프트웨어 종목의 보도자료를
상장 표시('(NASDAQ: XXX)')로 지역을, 제목으로 5분류(계약·실적·시장 압력·M&A·혁신·확장)를 붙여 inbox에 저장한다.
모델을 부르지 않는다. 원문은 저장하지 않는다(제목·링크·발행시각·요약 앞부분).

사용: py radar/pollers/press_wire.py            (1회 수집, run_hourly가 30분마다 호출)
      py radar/pollers/press_wire.py --digest [YYYYMMDD]   (그날 수집분을 분류×지역 표로 출력 — 저녁 브리프 입력)
"""
import hashlib
import json
import re
import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from pollers import common
    from pollers.rss import parse_feed, to_iso
else:
    from . import common
    from .rss import parse_feed, to_iso

CONFIG = "config/press_wire.yaml"
SOURCE_ID = {"PRN": "src-prn", "BW": "src-bw"}
# 영어판만 남긴다(같은 보도자료의 독·불·서어 번역판 중복 제거)
NON_EN_RE = re.compile(r"[äöüßéèêàâçñóíú]|\b(und|der|die|das|mit|für|dans|pour|avec|les|des|del|para|con)\b", re.I)
TICKER_RE = re.compile(r"\(([A-Za-z][A-Za-z .]{1,40}?)\s*:\s*([A-Z0-9][A-Z0-9.\-]{0,9})\)")


def _cfg():
    c = common.load_yaml(CONFIG) or {}
    c["_sector"] = re.compile("|".join(c.get("sector_patterns", [])), re.I)
    c["_exclude"] = re.compile(c.get("exclude_pattern", r"$^"), re.I)
    c["_cats"] = [(x["key"], re.compile(x["pattern"], re.I)) for x in c.get("categories", [])]
    c["_ex"] = {r: re.compile(p) for r, p in (c.get("exchanges") or {}).items()}
    return c


def listing(text, cfg):
    """첫 상장 표시 → (지역 목록, '거래소: 티커')"""
    for m in TICKER_RE.finditer(text[:600]):
        regions = [r for r, pat in cfg["_ex"].items() if pat.search(m.group(1))]
        if regions:
            return regions, f"{m.group(1).strip()}: {m.group(2)}"
    return [], None


def categorize(title, desc, cfg):
    cats = [k for k, pat in cfg["_cats"] if pat.search(title)]
    if not cats:
        cats = [k for k, pat in cfg["_cats"] if pat.search(desc[:400])][:1]
    return cats or ["other"]


def classify(entry, feed, cfg):
    """보도자료 1건 → (지역, 티커, 분류) 또는 None(제외)"""
    title = common.strip_tags(entry["title"])
    desc = common.strip_tags(entry["desc"])
    if not title or cfg["_exclude"].search(title) or NON_EN_RE.search(title):
        return None
    if not feed.get("sector_feed") and not cfg["_sector"].search(f"{title} {desc[:600]}"):
        return None
    regions, ticker = listing(desc, cfg)
    if not regions:
        return None
    return regions, ticker, categorize(title, desc, cfg)


def run():
    cfg = _cfg()
    items, seen_titles, errors = [], set(), []
    for feed in cfg.get("feeds", []):
        try:
            entries = parse_feed(common.http_get(feed["url"], timeout=30))
        except Exception as exc:  # 피드 하나 실패는 나머지에 영향 없음
            errors.append(f"{feed['id']}: {type(exc).__name__}")
            continue
        for e in entries:
            if not e["link"]:
                continue
            res = classify(e, feed, cfg)
            if not res:
                continue
            title = common.strip_tags(e["title"])
            key = re.sub(r"\W+", "", title.lower())[:80]
            if key in seen_titles:  # 같은 보도자료의 여러 피드·언어판 중복
                continue
            seen_titles.add(key)
            regions, ticker, cats = res
            sid = SOURCE_ID.get(feed.get("wire"), "src-prn")
            items.append(common.make_item(
                sid, hashlib.sha1(e["link"].encode()).hexdigest()[:16], e["link"], title,
                to_iso(e["date"]), "보도자료", "en", common.strip_tags(e["desc"]),
                extra={"wire": feed.get("wire"), "feed_id": feed["id"], "regions": regions,
                       "ticker": ticker, "press_categories": cats}))
    new = common.save_new_items(items)
    common.record_health("src-press-wire", not errors or bool(items), "; ".join(errors) or None)
    return len(items), len(new)


def digest(day=None):
    """inbox의 그날 보도자료를 분류×지역으로 묶은 마크다운"""
    cfg = common.load_yaml(CONFIG) or {}
    labels = {c["key"]: c["label"] for c in cfg.get("categories", [])}
    labels["other"] = "Other (인사·기타)"
    day = day or common.now_kst().strftime("%Y%m%d")
    rows = []
    for f in sorted((common.INBOX / day).glob("src-*.json")):
        it = json.loads(f.read_text(encoding="utf-8"))
        if it.get("source_id") in SOURCE_ID.values() and not NON_EN_RE.search(it["title"]):
            rows.append(it)
    out = [f"# 글로벌 공식 발표 {day} — {len(rows)}건 (PR Newswire·Business Wire, 1차 분류는 규칙 기반)"]
    for key, label in labels.items():
        grp = [r for r in rows if key in r.get("press_categories", [])]
        if not grp:
            continue
        out.append(f"\n## {label} ({len(grp)})")
        for r in sorted(grp, key=lambda r: (r.get("regions") or ["~"])[0]):
            ent = ",".join(r.get("entities_matched", [])) or "-"
            out.append(f"- [{'/'.join(r.get('regions', []))}] {r.get('ticker')} | {r['title']} | {r.get('wire')} "
                       f"{r.get('published_at', '')[:16]} | 감시기업 {ent} | {r['url']}")
    return "\n".join(out)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")  # Windows 콘솔(cp949)에서 기호 출력 오류 방지
    if len(sys.argv) > 1 and sys.argv[1] == "--digest":
        print(digest(sys.argv[2] if len(sys.argv) > 2 else None))
    else:
        print(run())
