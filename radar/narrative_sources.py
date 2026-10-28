"""내러티브 프리미엄 근거 수집 (마스터 지시 2026-10-28) — 결정론, 판단은 스킬 narrative-premium

종목(그리고 그 섹터)에 대해 약관·robots를 지키는 원천에서 제목·링크·공개 요약만 모은다(config/narrative_sources.yaml):
  ① Substack 투자·산업 뉴스레터 10곳 공개 RSS(최근 90일, 종목명·티커 언급)
  ② Hacker News(Algolia 공개 API, 최근 180일)
  ③ 미국 투자 커뮤니티 헤드라인(Seeking Alpha·Motley Fool·Benzinga·MarketBeat·Barron's·IBD 등) — Google News 색인 제목만
  ④ IB 커버리지 변화(개시·상향·하향·목표가) — Google News 색인 제목만
  ⑤ 섹터 내러티브 헤드라인(섹터 키워드 × 커뮤니티 사이트)
거르기(결정론): 제목에 종목명·티커(단어 경계)가 없거나 같은 제목 재게재면 버리고 버린 수를 dropped에 남긴다(섹터는 섹터 키워드).
저장: knowledge/narratives/evidence/<id>.json (git 제외 — 제목·링크라 다시 받을 수 있음)
사용: py radar/narrative_sources.py <id> [<id> ...]
"""
import json
import re
import sys
import time
import urllib.parse
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from pollers import common, rss  # noqa: E402

OUT = common.ROOT / "knowledge" / "narratives" / "evidence"
GNEWS = "https://news.google.com/rss/search?q={q}&hl=en-US&gl=US&ceid=US:en"
SECTOR_TERMS = {   # 하위 섹터 → (섹터 내러티브 검색어, 제목 필터 정규식) — 2026-10-28 검색어 시험 후 확정
    "semicap": ('("wafer fab equipment" OR WFE OR "chip equipment" OR "semiconductor equipment" OR "chip-gear")',
                r"WFE|wafer fab|equipment|chip.gear|Lam Research|Applied Materials|KLA|ASML|Tokyo Electron"),
    "substrate": ('(PCB OR "circuit board" OR substrate) stocks', r"PCB|circuit board|substrate|Celestica|TTM|Sanmina|Jabil|AI infrastructure"),
    "networking": ('(optical OR transceiver OR "AI networking" OR switch) stocks', r"optic|transceiver|network|switch|photonic"),
    "power_infra": ('(power grid OR transformer OR "AI power") stocks', r"power|grid|transformer|voltage|electric|energy|gas turbine"),
    "memory": ('(HBM OR DRAM OR "memory chip") stocks', r"HBM|DRAM|NAND|memory"),
    "accelerator": ('("AI chip" OR GPU OR ASIC) stocks', r"AI chip|GPU|ASIC|accelerat"),
    "eda_ip": ('(EDA OR "semiconductor IP" OR "chip design software")', r"EDA|IP|design"),
    "server": ('("AI server" OR "server rack") stocks', r"server|rack"),
    "components": ('("passive components" OR MLCC OR connector) AI stocks', r"MLCC|passive|connector|component"),
    "software": ('("AI software" OR SaaS) stocks', r"software|SaaS"),
    "analog": ('(analog OR "power semiconductor") chip stocks', r"analog|power semi"),
    "storage": ('("data storage" OR HDD OR SSD) AI stocks', r"storage|HDD|SSD|drive"),
    "foundry": ('(foundry OR TSMC) stocks', r"foundry|TSMC"),
    "hyperscaler": ('(hyperscaler capex OR "AI capex")', r"capex|spending|data cent"),
}


def cfg():
    return common.load_yaml("config/narrative_sources.yaml") or {}


def company(eid):
    for path in ("config/valuation.yaml", "config/earnings_watch.yaml"):
        y = common.load_yaml(path) or {}
        for u in (y.get("universe") or []) + (y.get("extra") or []):
            if u["id"] == eid:
                code = u.get("code") or ""
                tk = code.split(".")[0] if code.endswith(".US") else (u.get("sec_ticker") or "")
                names = [n for n in (u.get("aliases") or []) if len(n) >= 3] or [u["name"]]
                return {"id": eid, "name": u["name"], "names": names[:2], "ticker": tk, "sub": u.get("sub", "")}
    return None


def mention_re(co):
    """종목명·티커 언급(단어 경계) — 색인 검색이 본문만 맞은 기사·접두 매칭(Vicor→Victorian)을 거른다"""
    alts = [rf"\b{re.escape(n)}\b" for n in co["names"]]
    if co["ticker"]:
        alts.append(rf"\b{re.escape(co['ticker'])}\b")
    return re.compile("|".join(alts), re.I)


def keep_titles(items, pat):
    """(제목 정규식 일치·같은 제목 재게재 1건만 남긴 목록, 버린 수)"""
    out, seen = [], set()
    for e in items:
        title = e.get("title") or ""
        key = re.sub(r"\s+-\s+[^-]+$", "", title).lower()
        key = re.sub(r"[^a-z0-9$]", "", key)
        if not pat.search(title) or key in seen:
            continue
        seen.add(key)
        out.append(e)
    return out, len(items) - len(out)


def _age_ok(date_s, days):
    iso = rss.to_iso(date_s) if date_s else None
    if not iso:
        return True
    try:
        return datetime.now(timezone.utc) - datetime.fromisoformat(iso.replace("Z", "+00:00")) <= timedelta(days=days)
    except ValueError:
        return True


def gnews(query, days=30, limit=25):
    url = GNEWS.format(q=urllib.parse.quote(f"{query} when:{days}d"))   # 바깥 괄호를 더 씌우면 Google News가 빈 결과(2026-10-28 시험)
    out = []
    for e in rss.parse_feed(common.http_get(url, timeout=30))[:limit]:
        if not _age_ok(e["date"], days):   # 색인의 오래된 종목 개요 페이지(2011년 등) 제외
            continue
        out.append({"title": common.strip_tags(e["title"]), "url": e["link"], "date": rss.to_iso(e["date"]), "publisher": e.get("publisher")})
    return out


def substack_hits(co, days=90):
    pat = mention_re(co)
    out = []
    for s in cfg().get("auto", {}).get("substack", []):
        try:
            entries = rss.parse_feed(common.http_get(s["feed"], timeout=25))
        except Exception:
            continue
        for e in entries:
            text = f"{e['title']} {common.strip_tags(e['desc'])}"
            if _age_ok(e["date"], days) and pat.search(text):
                out.append({"newsletter": s["name"], "title": common.strip_tags(e["title"]), "url": e["link"],
                            "date": rss.to_iso(e["date"]), "snippet": common.strip_tags(e["desc"])[:300]})
        time.sleep(0.2)
    return out


def hn_hits(co, days=180):
    since = int((datetime.now(timezone.utc) - timedelta(days=days)).timestamp())
    q = {"query": co["names"][0], "tags": "story", "numericFilters": f"created_at_i>{since}", "hitsPerPage": 15}
    d = json.loads(common.http_get(cfg()["auto"]["hacker_news"]["api"] + "?" + urllib.parse.urlencode(q), timeout=25))
    pat = mention_re(co)
    return [{"title": h.get("title"), "url": h.get("url") or f"https://news.ycombinator.com/item?id={h['objectID']}",
             "points": h.get("points"), "comments": h.get("num_comments"), "date": h.get("created_at")} for h in d.get("hits", []) if pat.search(h.get("title") or "")]


def collect(eid):
    co = company(eid)
    if not co:
        raise SystemExit(f"{eid}: 감시 목록에 없음")
    c = cfg()["auto"]
    sites = " OR ".join(f"site:{s}" for s in c["community_headlines"]["sites"])
    name_q = " OR ".join([f'"{n}"' for n in co["names"]] + ([co["ticker"]] if co["ticker"] else []))
    terms = " OR ".join(f'"{t}"' for t in c["analyst_actions"]["terms"])
    sq, sre = SECTOR_TERMS.get(co["sub"], (f'"{co["sub"]}" stocks', re.escape(co["sub"])))
    pat = mention_re(co)
    ev = {"id": eid, "company": co, "collected_at": common.iso(common.now_kst()), "errors": [], "dropped": {}}
    for key, fn, title_re in (("community_headlines", lambda: gnews(f"({sites}) ({name_q})", 45), pat),
                              ("analyst_actions", lambda: gnews(f"({name_q}) ({terms})", 60), pat),
                              ("sector_headlines", lambda: gnews(f"({sites}) {sq}", 30, 25), re.compile(sre, re.I)),
                              ("substack", lambda: substack_hits(co), None),
                              ("hacker_news", lambda: hn_hits(co), None)):
        try:
            items = fn()
            if title_re is not None:
                items, ev["dropped"][key] = keep_titles(items, title_re)
            ev[key] = items
        except Exception as exc:
            ev[key] = []
            ev["errors"].append(f"{key}: {type(exc).__name__}")
        time.sleep(0.5)
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / f"{eid}.json").write_text(json.dumps(ev, ensure_ascii=False, indent=1), encoding="utf-8")
    return ev


def main(argv):
    for eid in argv:
        ev = collect(eid)
        counts = {k: len(ev.get(k, [])) for k in ("community_headlines", "analyst_actions", "sector_headlines", "substack", "hacker_news")}
        print(f"[내러티브 근거] {eid} {counts} 걸러냄 {ev['dropped']}" + (f" 실패: {ev['errors']}" if ev["errors"] else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
