"""투자자 관심도 추적 — Chiip Ten-bagger Discovery 후보의 관심 가속·쏠림 (마스터 지시 2026-10-29 "telegram, x, substack, seekingalpha 등
투자 커뮤니티의 투자자 관심도를 잘 트래킹하라").

결정론 수집(하루 1회, run_hourly). 원천은 config/discovery.yaml attention.sources 중 enabled만 — CLAUDE.md 컴플라이언스 안에서:
  google_news(영문명 글로벌 + 일본어/중국어/한국어 현지명), seeking_alpha·substack(Google News 색인 제목만), research_feeds(공개 RSS 수집분),
  reddit(ApeWisdom, 미국 티커). X·텔레그램은 CLAUDE.md 제외 원천이라 꺼져 있다(마스터 승인 시 집계 수만).
쓰는 것: knowledge/models/discovery/attention.csv(날짜·종목·원천·7일 언급 수 — 누적), attention_latest.json(가속 = 오늘 7일 수 ÷ 직전
4주 같은 원천 평균, 쏠림 = 후보 안 백분위). 기사 본문은 저장하지 않는다(수만).
"""
import csv
import json
import sys
import time
import urllib.parse
from datetime import timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from pollers import common  # noqa: E402
from pollers import rss  # noqa: E402

OUT = common.ROOT / "knowledge" / "models" / "discovery"
CSV = OUT / "attention.csv"
LATEST = OUT / "attention_latest.json"
INVESTOR_SOURCES = ("news_global", "seeking_alpha", "substack", "research_feeds")
LOCALE = {"jp": ("ja", "JP"), "tw": ("zh-TW", "TW"), "kr": ("ko", "KR"), "us": ("en-US", "US")}


def candidates():
    cfg = common.load_yaml("config/discovery.yaml") or {}
    jp = {c["id"]: c for c in (common.load_yaml("config/jp_watch.yaml") or {}).get("companies") or []}
    out = {}
    for t in cfg.get("themes") or []:
        for c in t.get("candidates") or []:
            local = c.get("local") or ((jp.get(c["id"]) or {}).get("ja") or [None])[0]
            out.setdefault(c["id"], {**c, "theme": t["id"], "local": local})
    for c in (common.load_yaml("config/coverage.yaml") or {}).get("companies") or []:
        out.setdefault(c["id"], c)
    return out


def gnews_count(query, hl="en-US", gl="US", days=7):
    url = rss.GNEWS.format(q=urllib.parse.quote(f"{query} when:{days}d"), hl=hl, gl=gl)
    try:
        return len(rss.parse_feed(common.http_get(url, timeout=25)))
    except Exception:
        return None


def research_feed_count(names, days=7):
    """radar/inbox의 공개 리서치 RSS(Substack 등) 수집분에서 제목·요약 언급 수"""
    n, today = 0, common.now_kst()
    for i in range(days):
        folder = common.ROOT / "radar" / "inbox" / (today - timedelta(days=i)).strftime("%Y%m%d")
        for f in folder.glob("src-research-feeds_*.json") if folder.exists() else []:
            try:
                it = json.loads(f.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            text = f"{it.get('title', '')} {it.get('snippet', '')}".lower()
            n += any(nm and nm.lower() in text for nm in names)
    return n


SELLSIDE_RE = __import__("re").compile(r"受邀參加.{0,20}(證券|銀行|Securities|Capital).{0,20}(法人|座談|論壇|說明會|conference)|法人說明會|Investor Conference|IR Day|説明会|スモールミーティング", __import__("re").I)


def sellside_count(cid, days=7):
    """IB 관심 신호 — 회사 원문 공시 속 증권사 투자자 행사 초청·법인설명회(대만 重大訊息·일본 적시공시 미러) 수.
    IB가 기관 투자자 앞에 세우는 회사 = 커버리지 관심이 붙는 회사(2026-10-29 — Elite Material의 BofA·골드만·푸본 행사 공시에서 착안)"""
    n, today = 0, common.now_kst()
    for i in range(days):
        folder = common.ROOT / "radar" / "inbox" / (today - timedelta(days=i)).strftime("%Y%m%d")
        if not folder.exists():
            continue
        for f in list(folder.glob("src-tw-disclosure_*.json")) + list(folder.glob("src-jp-disclosure_*.json")):
            try:
                it = json.loads(f.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            n += cid in (it.get("entities_matched") or []) and bool(SELLSIDE_RE.search(it.get("title", "")))
    return n


def collect():
    cfg = (common.load_yaml("config/discovery.yaml") or {}).get("attention") or {}
    src = {k: v.get("enabled") for k, v in (cfg.get("sources") or {}).items()}
    days = int(cfg.get("window_days", 7))
    today = common.now_kst().strftime("%Y-%m-%d")
    rows = []
    for cid, c in candidates().items():
        en, local = c.get("name"), c.get("local")
        q = f'"{en}"'
        if src.get("google_news"):
            rows.append((today, cid, "news_global", gnews_count(q, days=days)))
            if local:
                hl, gl = LOCALE.get(c.get("market", "us"), ("en-US", "US"))
                rows.append((today, cid, "news_local", gnews_count(f'"{local}"', hl, gl, days)))
        if src.get("seeking_alpha"):
            rows.append((today, cid, "seeking_alpha", gnews_count(f"{q} site:seekingalpha.com", days=days)))
        if src.get("substack"):
            rows.append((today, cid, "substack", gnews_count(f"{q} site:substack.com", days=days)))
            rows.append((today, cid, "research_feeds", research_feed_count([en, local], days)))
        rows.append((today, cid, "sellside_events", sellside_count(cid, days)))
        time.sleep(0.3)
    return rows


def summarize(all_rows, today):
    """가속 = 오늘 값 ÷ 7·14·21·28일 전 같은 원천 값 평균(없으면 None), 쏠림 = 합계의 후보 내 백분위"""
    hist = {}
    for d, cid, s, n in all_rows:
        if n not in (None, ""):
            hist.setdefault((cid, s), {})[d] = float(n)
    from datetime import date
    t = date.fromisoformat(today)
    out = {}
    for (cid, s), series in hist.items():
        cur = series.get(today)
        if cur is None:
            continue
        past = [series.get((t - timedelta(days=k)).isoformat()) for k in (7, 14, 21, 28)]
        past = [x for x in past if x is not None]
        base = sum(past) / len(past) if past else None
        o = out.setdefault(cid, {"total": 0.0, "by_source": {}, "accel": None})
        o["total"] += cur
        o["by_source"][s] = {"n": cur, "accel": (cur + 1) / (base + 1) if base is not None else None}
    for cid, o in out.items():
        acc = [v["accel"] for v in o["by_source"].values() if v["accel"] is not None]
        o["accel"] = sum(acc) / len(acc) if acc else None
    # 쏠림은 투자자 원천으로만 — 현지 언론은 Google News 상한(100건)에 자주 걸리고 투자자 관심과 다르다(2026-10-29 첫 기준선)
    for o in out.values():
        o["investor"] = sum(v["n"] for s, v in o["by_source"].items() if s in INVESTOR_SOURCES)
        o["saturated"] = [s for s, v in o["by_source"].items() if v["n"] >= 100]
    inv = sorted(o["investor"] for o in out.values())
    for o in out.values():
        o["crowding_pct"] = round(100 * sum(1 for x in inv if x <= o["investor"]) / len(inv)) if inv else None
    return out


def run():
    OUT.mkdir(parents=True, exist_ok=True)
    rows = collect()
    new = not CSV.exists()
    with CSV.open("a", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        if new:
            w.writerow(["date", "id", "source", "count7d"])
        w.writerows(rows)
    with CSV.open(encoding="utf-8", newline="") as f:
        all_rows = [(r["date"], r["id"], r["source"], r["count7d"]) for r in csv.DictReader(f)]
    today = common.now_kst().strftime("%Y-%m-%d")
    latest = summarize(all_rows, today)
    LATEST.write_text(json.dumps({"date": today, "rows": latest}, ensure_ascii=False, indent=1), encoding="utf-8")
    top = sorted(latest.items(), key=lambda kv: -(kv[1]["accel"] or 0))[:3]
    return f"관심도 {len(latest)}종목 · 가속 상위 " + ", ".join(f"{k} {v['accel']:.2f}" for k, v in top if v["accel"]), 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    print(run())
