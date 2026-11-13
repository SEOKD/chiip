"""원문 열람 — 카드를 쓰기 전에 자료 본문을 실제로 가져온다 (마스터 지시 2026-11-13 "알파 감지와 레이더/Pulse 감지 카드가
자료·정보·뉴스·공시를 감지하면 원문을 실제로 열람해 내용을 파악한 뒤 카드를 쓰게 하라")

수집은 결정론(이 파일), 해석은 모델(radar-triage·chiip-pulse·item_notes). 항목에 'fulltext'를 붙인다:
  {status: ok|fail, route: 경로, url: 읽은 주소, why: 실패 사유, excerpt: 본문 발췌(≤4,000자), kpi: [숫자 문장 ≤8]}
경로(순서대로, 하나 성공하면 끝):
  1. 원 주소 — SEC www.sec.gov는 식별 User-Agent(.env SEC_USER_AGENT)가 있어야 열린다(없으면 403 — 시도하지 않고 사유만 남긴다).
     8-K는 본문 + 첨부 보도자료(EX-99.1, 공시 폴더 index.json에서 찾음)를 함께 읽는다.
  2. 같은 회사 뉴스 와이어·IR 보도자료 — inbox 최근 3일 PR Newswire·Business Wire·GlobeNewswire·회사 뉴스룸 항목 중 회사명·티커가 맞는 것
  3. 모두 실패 → status fail + why, 재시도 대기열(radar/state/fulltext_retry.json, 1시간 간격 최대 6회).
     Fiscal.ai company_ir_events·company_earnings_summary는 MCP라 모델 회차(chiip-pulse)가 hint를 보고 시도한다.
SEC 접속 규칙: 식별 가능한 User-Agent, 초당 10회 이하. 마스터 연락처를 대신 넣지 않는다(sec_filings._ua 그대로).
Google News 중계 주소(2026-11-14 마스터 지시 "본문을 반드시 확인하는 구조"): news.google.com은 robots.txt가 기사 경로를 막아
  중계 주소를 풀지 않는다. 대신 ① inbox 3일 안 같은 제목의 다른 원천(발행사 뉴스룸·와이어·다른 매체) ② 발행사 사이트(RSS <source url>의 도메인)
  robots.txt가 허용하는 사이트맵에서 제목과 맞는 주소 — 봇 차단 화면(Incapsula·Cloudflare 등)이면 우회하지 않고 사유만 ③ 실패면 search(모델이
  WebSearch로 같은 발표의 다른 사본·상대방 발표를 찾는 질의)를 남긴다. 알림은 본문을 읽기 전에는 보내지 않는다(hold — run_poll·pulse가 쓴다).
사용: py radar/fulltext.py <inbox json 경로>   # 한 건 열람 결과 출력
      py radar/fulltext.py --retry              # 재시도 대기열 처리
"""
import json
import re
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from pollers import common  # noqa: E402

MAX_EXCERPT = 4000
MAX_KPI = 8
RETRY_MIN = 60
RETRY_MAX = 6
CACHE = "fulltext_cache"
RETRY = "fulltext_retry"
WIRE_PREFIX = ("src-prn", "src-bw", "src-gnw", "src-globenewswire", "src-accesswire", "src-ir-press", "src-newsroom-", "src-press-wire")
DOC_TYPES = ("실적", "공시", "보도자료", "IR", "IR 자료")
KPI_RE = re.compile(r"revenue|net (income|loss)|per (diluted )?share|\bEPS\b|guidance|outlook|expects?|forecast|backlog|\bARR\b|gross margin|"
                    r"operating (income|margin)|adjusted EBITDA|bookings|contract|매출|영업이익|순이익|가이던스|수주", re.I)
NUM_RE = re.compile(r"[$€¥₩£]\s?\d|\d[\d,.]*\s?(%|million|billion|M\b|B\b|억|조)")
FISCAL_HINT = "Fiscal.ai company_earnings_summary·company_ir_events(모델 회차)로 실적 수치 확인"


def sec_ua():
    """SEC용 User-Agent — .env SEC_USER_AGENT만(없으면 None). 일반 UA는 www.sec.gov가 403을 준다(2026-11-13 확인)"""
    return common.load_env().get("SEC_USER_AGENT") or None


def is_sec(url):
    return "www.sec.gov/" in (url or "") or "sec.gov/Archives" in (url or "")


def clean_html(raw):
    raw = re.sub(r"(?is)<(script|style|nav|header|footer|noscript)[^>]*>.*?</\1>", " ", raw)
    raw = re.sub(r"(?i)<br\s*/?>|</p>|</tr>|</div>|</li>", "\n", raw)
    text = common.strip_tags(raw)
    text = re.sub(r"[ \t\xa0]+", " ", text)
    return re.sub(r"\n\s*\n+", "\n", text).strip()


def _get(url, ua=None, timeout=20):
    headers = {"User-Agent": ua} if ua else None
    return common.http_get(url, headers=headers, timeout=timeout).decode("utf-8", "ignore")


def kpi_lines(text):
    """숫자와 실적 낱말이 함께 있는 문장 ≤ MAX_KPI개(중복 제거)"""
    out, seen = [], set()
    for s in re.split(r"(?<=[.!?。])\s+|\n", text):
        s = s.strip()
        if 25 <= len(s) <= 320 and KPI_RE.search(s) and NUM_RE.search(s):
            k = s[:80].lower()
            if k not in seen:
                seen.add(k)
                out.append(s)
        if len(out) >= MAX_KPI:
            break
    return out


def sec_exhibits(url, ua):
    """8-K 공시 폴더 index.json에서 EX-99.x 문서 주소"""
    folder = url.rsplit("/", 1)[0]
    try:
        idx = json.loads(_get(folder + "/index.json", ua))
    except Exception:
        return []
    names = [x.get("name", "") for x in (idx.get("directory") or {}).get("item") or []]
    return [f"{folder}/{n}" for n in names if re.search(r"ex[-_]?99|dex99", n, re.I) and n.lower().endswith((".htm", ".html", ".txt"))][:2]


def from_sec(item):
    ua = sec_ua()
    if not ua:
        return None, "SEC 403 — .env SEC_USER_AGENT 미설정(www.sec.gov는 식별 User-Agent가 없으면 거부)"
    try:
        body = clean_html(_get(item["url"], ua))
        parts = [body]
        if "2.02" in str(item.get("sec_items") or "") or "8-K" in str(item.get("report_nm") or ""):
            for ex in sec_exhibits(item["url"], ua):
                time.sleep(0.15)
                parts.append(clean_html(_get(ex, ua)))
        return "\n".join(parts), ""
    except Exception as exc:
        return None, f"SEC {getattr(exc, 'code', '') or type(exc).__name__}"


def company_keys(item):
    """회사명 핵심어·티커 — '[SEC 8-K 실적] Corvex, Inc.' → ('corvex', 'MOVE')"""
    title = re.sub(r"^\[[^\]]*\]\s*", "", item.get("title") or "")
    name = re.split(r",| Inc\b| Corp\b| Corporation\b| Ltd\b| Holdings\b| plc\b", title)[0].strip().lower()
    tick = None
    for e in item.get("entities_matched") or []:
        if e.startswith("us-"):
            tick = e[3:].upper()
    m = re.search(r"\b(?:Nasdaq|NYSE)[^:]*:\s*([A-Z.]{1,6})", item.get("ticker") or item.get("snippet") or "")
    if m:
        tick = m[1]
    return name, tick


def wire_candidates(item, days=3, now=None):
    """inbox 최근 days일의 와이어·IR 보도자료 중 같은 회사"""
    now = now or common.now_kst()
    name, tick = company_keys(item)
    if not name and not tick:
        return []
    out = []
    for k in range(days):
        d = common.INBOX / (now - timedelta(days=k)).strftime("%Y%m%d")
        if not d.exists():
            continue
        for f in d.glob("*.json"):
            if not f.name.startswith(WIRE_PREFIX):
                continue
            try:
                it = json.loads(f.read_text(encoding="utf-8"))
            except ValueError:
                continue
            hay = f"{it.get('title', '')} {it.get('snippet', '')} {it.get('ticker', '')}"
            if (name and len(name) >= 3 and name in hay.lower()) or (tick and re.search(rf"[:\s]{re.escape(tick)}\b", hay)):
                out.append(it)
    earn = re.compile(r"results|earnings|quarter|financial", re.I)
    return sorted(out, key=lambda x: (not earn.search(x.get("title", "")), x.get("published_at", "")), reverse=False)


BOT_WALL = re.compile(r"_Incapsula_Resource|cf-browser-verification|Attention Required! \| Cloudflare|challenge-platform|captcha", re.I)


def from_url(url):
    try:
        raw = _get(url)
    except Exception as exc:
        return None, f"{getattr(exc, 'code', '') or type(exc).__name__}"
    if BOT_WALL.search(raw[:5000]):
        return None, "봇 차단 화면 — 우회하지 않음"
    text = clean_html(raw)
    return (text, "") if len(text) >= 400 else (None, "본문 짧음")


def is_relay(url):
    return "news.google.com" in (url or "")


def base_title(title):
    """'제목 - 매체' → 제목(구글 뉴스 꼬리 매체명 제거)"""
    return re.sub(r"\s+[-–|]\s+[^-–|]{2,60}$", "", (title or "").strip())


def _tokens(t):
    return {w for w in re.findall(r"[a-z0-9가-힣]{3,}", (t or "").lower())}


def title_sim(a, b):
    ta, tb = _tokens(base_title(a)), _tokens(base_title(b))
    return len(ta & tb) / max(1, min(len(ta), len(tb))) if ta and tb else 0.0


def same_title_copies(item, days=3, now=None, min_sim=0.8):
    """inbox 최근 days일에서 같은 제목의 다른 원천(중계 주소가 아닌 것) — 발행사 뉴스룸·와이어·다른 매체"""
    now = now or common.now_kst()
    out = []
    for k in range(days):
        d = common.INBOX / (now - timedelta(days=k)).strftime("%Y%m%d")
        if not d.exists():
            continue
        for f in d.glob("*.json"):
            try:
                it = json.loads(f.read_text(encoding="utf-8"))
            except ValueError:
                continue
            if is_relay(it.get("url")) or it.get("item_id") == item.get("item_id") or not it.get("url"):
                continue
            if title_sim(item.get("title"), it.get("title")) >= min_sim:
                out.append(it)
    return out


def robots_ok(url, ua="ChiipResearch"):
    """(robots.txt가 이 주소를 허용하나 — 못 읽으면 None, 사이트맵 목록)"""
    from urllib import robotparser
    from urllib.parse import urlsplit
    sp = urlsplit(url)
    try:
        raw = _get(f"{sp.scheme}://{sp.netloc}/robots.txt", timeout=10)
    except Exception:
        return None, []
    if BOT_WALL.search(raw[:3000]):
        return None, []
    rp = robotparser.RobotFileParser()
    rp.parse(raw.splitlines())
    maps = re.findall(r"(?im)^\s*sitemap:\s*(\S+)", raw)
    return rp.can_fetch(ua, url), maps


def from_publisher(item, max_maps=4):
    """발행사 사이트맵에서 제목과 맞는 주소 → 본문. (text, url, why)"""
    site = item.get("publisher_url") or ""
    if not site.startswith("http"):
        return None, None, "발행사 주소 없음"
    ok, maps = robots_ok(site.rstrip("/") + "/")
    if ok is None:
        return None, None, "robots.txt 못 읽음(봇 차단 가능) — 우회하지 않음"
    want = _tokens(base_title(item.get("title")))
    seen, best = 0, (0.0, None)
    queue = list(maps)
    while queue and seen < max_maps:
        sm = queue.pop(0)
        seen += 1
        try:
            raw = _get(sm, timeout=15)
        except Exception:
            continue
        locs = re.findall(r"<loc>\s*([^<\s]+)\s*</loc>", raw)
        if "<sitemapindex" in raw:   # 색인이면 뉴스·보도자료 쪽, 뒤쪽(최근) 먼저
            locs = sorted(locs, key=lambda u: (not re.search(r"news|press|article|media", u, re.I), -locs.index(u)))
            queue = locs[:max_maps] + queue
            continue
        for u in locs:
            slug = _tokens(re.sub(r"[-_/]", " ", u.rstrip("/").rsplit("/", 1)[-1]))
            sim = len(want & slug) / max(1, len(want))
            if sim > best[0]:
                best = (sim, u)
    if best[0] < 0.7:
        return None, None, "사이트맵에 같은 제목 주소 없음"
    allowed, _ = robots_ok(best[1])
    if not allowed:
        return None, best[1], "robots.txt가 기사 주소를 막음"
    text, why = from_url(best[1])
    return text, best[1], why


def _trim(text, item, route_item=None):
    """머리 메뉴를 건너뛰고 본문 시작(날짜선·스니펫)부터"""
    snip = ((route_item or item).get("snippet") or "")[:40]
    i = text.find(snip) if snip else -1
    if i < 0:
        m = re.search(r"/(PRNewswire|GLOBE NEWSWIRE|Business Wire)/", text)
        i = m.start() if m else 0
    return text[max(0, i - 200):]


def fetch(item, now=None):
    """항목 → fulltext dict(네트워크). 캐시·재시도는 enrich가 다룬다"""
    whys = []
    url = item.get("url") or ""
    if is_sec(url):
        text, why = from_sec(item)
        if text:
            return done(text, "SEC 원문" + ("+EX-99" if "2.02" in str(item.get("sec_items")) else ""), url)
        whys.append(why)
    elif url and not is_relay(url):
        text, why = from_url(url)
        if text:
            return done(_trim(text, item), "원 주소", url)
        whys.append(f"원 주소 {why}")
    else:
        whys.append("Google News 중계 주소(robots.txt가 막아 풀지 않음)")
        for c in same_title_copies(item, now=now)[:3]:
            text, why = from_url(c["url"])
            if text:
                return done(_trim(text, item, c), f"같은 제목 다른 원천: {c.get('source_id')}", c["url"], whys)
            whys.append(f"같은 제목 {c.get('source_id')} {why}")
        try:
            text, purl, why = from_publisher(item)
        except Exception as exc:
            text, purl, why = None, None, f"경로 오류 {type(exc).__name__}"
        if text:
            return done(_trim(text, item), "발행사 사이트맵", purl, whys)
        whys.append(f"발행사 {why}")
    for w in wire_candidates(item, now=now)[:2]:
        if w.get("url") == url:
            continue
        text, why = from_url(w["url"])
        if text:
            return done(_trim(text, item, w), f"대체: {w.get('source_id')}", w["url"], whys)
        whys.append(f"와이어 {why}")
    if not wire_candidates(item, now=now):
        whys.append("같은 회사 와이어·IR 보도자료 없음")
    return {"status": "fail", "why": " · ".join(whys), "hint": FISCAL_HINT if item.get("doc_type") == "실적" else "",
            "search": search_query(item)}


def search_query(item):
    """모델 회차가 WebSearch로 같은 발표의 다른 사본(와이어·상대방 발표·다른 매체)을 찾을 질의"""
    t = base_title(item.get("title"))
    return {"query": f'"{t[:90]}"', "publisher": item.get("publisher") or "",
            "also": "상대방(고객·정부기관) 발표·와이어(PR Newswire·Business Wire·GlobeNewswire)·업계 매체 사본"}


def done(text, route, url, whys=None):
    return {"status": "ok", "route": route, "url": url, "excerpt": text[:MAX_EXCERPT], "kpi": kpi_lines(text),
            "note": (" · ".join(whys) + " → 대체 경로") if whys else ""}


def wanted(item, all_types=False):
    """all_types: 알림으로 보낼 건(빠른 길·Pulse 선택분)은 유형과 무관하게 연다(2026-11-14)"""
    return all_types or item.get("doc_type") in DOC_TYPES or item.get("source_class") in ("실적", "공시", "보도자료", "IR 자료")


def enrich(items, now=None, limit=12, fetcher=None, all_types=False):
    """항목 목록에 fulltext를 붙인다(캐시 우선, 새 열람은 limit건). 실패는 재시도 대기열에. 붙인 수"""
    now = now or common.now_kst()
    cache, retry = common.load_state(CACHE, {}), common.load_state(RETRY, {})
    n_new = n = 0
    for it in items:
        if not wanted(it, all_types) or it.get("fulltext"):
            continue
        key = it.get("item_id") or it.get("url")
        c = cache.get(key)
        stale_fail = c and c.get("status") == "fail" and (now - datetime.fromisoformat(c["at"])).total_seconds() > RETRY_MIN * 60 \
            and (retry.get(key) or {}).get("attempts", 0) < RETRY_MAX
        if c and not stale_fail:
            it["fulltext"] = {k: v for k, v in c.items() if k != "at"}
            n += 1
            continue
        if n_new >= limit:
            continue
        ft = (fetcher or fetch)(it, now)
        n_new += 1
        n += 1
        it["fulltext"] = ft
        cache[key] = {**ft, "at": common.iso(now)}
        if ft["status"] == "fail":
            r = retry.get(key) or {"item_id": key, "url": it.get("url"), "title": it.get("title"), "attempts": 0}
            r.update({"attempts": r["attempts"] + 1, "why": ft["why"], "last": common.iso(now)})
            retry[key] = r
        else:
            retry.pop(key, None)
    common.save_state(CACHE, dict(list(cache.items())[-800:]))
    common.save_state(RETRY, {k: v for k, v in retry.items() if v["attempts"] < RETRY_MAX})
    return n


def card_text(ft):
    """카드·피드용 한 덩어리 — 성공이면 숫자 문장, 실패면 '본문 미확인 — 사유'"""
    if not ft:
        return "본문 미확인 — 열람 시도 전"
    if ft.get("status") != "ok":
        return f"본문 미확인 — {ft.get('why') or '사유 미상'}" + (f" (다음: {ft['hint']})" if ft.get("hint") else "")
    return "\n".join(f"• {x}" for x in ft.get("kpi") or []) or "본문 열람 — 숫자 문장 없음"


def retry_due(now=None):
    """재시도 대기열을 다시 연다 — inbox 원 항목을 찾아 enrich"""
    now = now or common.now_kst()
    retry = common.load_state(RETRY, {})
    items = []
    for key in retry:
        src, _, uid = key.partition(":")
        for k in range(4):
            f = common.INBOX / (now - timedelta(days=k)).strftime("%Y%m%d") / f"{src}_{uid}.json"
            if f.exists():
                items.append(json.loads(f.read_text(encoding="utf-8")))
                break
    return enrich(items, now)


def run():
    """run_hourly용 — 재시도 대기열 처리. (처리 수, 0)"""
    n = retry_due()
    common.record_health("src-fulltext-retry", True, None)
    return n, 0


def main(argv):
    sys.stdout.reconfigure(encoding="utf-8")
    if argv and argv[0] == "--retry":
        print(f"[원문 재시도] {retry_due()}건")
        return 0
    if argv and argv[0] == "--held":   # Pulse 모델 회차: 다른 사본을 찾아 읽을 보류 건
        print(json.dumps(for_model(), ensure_ascii=False, indent=1))
        return 0
    if argv and argv[0] == "--release":   # --release <item_id> sent|model|given_up
        h = release(argv[1], argv[2] if len(argv) > 2 else "model")
        print("[보류 해제]" if h else "[보류 없음]", argv[1])
        return 0
    if argv and argv[0] == "--hold":   # --hold <item_id> — 모델이 본문을 못 읽어 피드에서 뺀 건을 보류 대기열로
        f = next(common.INBOX.glob(f"*/{argv[1].replace(':', '_')}.json"), None)
        it = json.loads(f.read_text(encoding="utf-8")) if f else {"item_id": argv[1]}
        h = hold(it, "PULSE", "Pulse 모델 — 본문 미확인", it.get("fulltext") or {"why": "모델 회차 열람 실패"})
        print(f"[보류] {argv[1]} ({h['tries']}회)")
        return 0
    if argv:
        it = json.loads(Path(argv[0]).read_text(encoding="utf-8"))
        ft = fetch(it)
        print(json.dumps({k: v for k, v in ft.items() if k != "excerpt"}, ensure_ascii=False, indent=1))
        print("--- 카드 ---")
        print(card_text(ft))
        return 0
    print(__doc__)
    return 0



# ---------- 본문 확인 전 보류(2026-11-14 마스터 지시 "본문을 반드시 확인하는 구조") ----------
HOLD = "fulltext_hold"
HOLD_TRIES = 6        # 빠른 길 회차마다 다시 연다(약 10분 간격)
HOLD_MODEL_AFTER = 2  # 이만큼 실패하면 Pulse 모델 회차에도 넘긴다(WebSearch로 다른 사본)
HOLD_FIELDS = ("item_id", "source_id", "url", "title", "snippet", "published_at", "detected_at", "entities_matched", "doc_type",
               "publisher", "publisher_url", "relay", "ticker", "tier", "language")


def hold(item, level, why_rule, ft, now=None):
    """본문을 못 읽은 알림 건을 보류 대기열에(보내지 않는다)"""
    now = now or common.now_kst()
    st = common.load_state(HOLD, {})
    k = item.get("item_id")
    h = st.get(k) or {"item": {x: item.get(x) for x in HOLD_FIELDS if item.get(x) is not None},
                      "level": level, "rule": why_rule, "first": common.iso(now), "tries": 0}
    h.update({"tries": h["tries"] + 1, "last": common.iso(now), "why": (ft or {}).get("why"), "search": (ft or {}).get("search")})
    st[k] = h
    common.save_state(HOLD, st)
    return h


def held():
    """보류 중인 건(오래된 것부터)"""
    return sorted(common.load_state(HOLD, {}).values(), key=lambda h: h["first"])


def release(item_id, result="sent"):
    """보류를 끝낸다 — sent(본문 읽고 보냄)·given_up(시도 다 함, 보내지 않음)·model(모델 회차가 처리)"""
    st = common.load_state(HOLD, {})
    h = st.pop(item_id, None)
    common.save_state(HOLD, st)
    if h:
        with (common.STATE / "fulltext_hold.log").open("a", encoding="utf-8") as fh:
            fh.write(f"{common.iso(common.now_kst())}\t{result}\t{item_id}\t{h.get('tries')}\t{(h.get('item') or {}).get('title', '')[:80]}\t{(h.get('why') or '')[:160]}\n")
    return h


def for_model(now=None, every_min=60):
    """Pulse 모델 회차가 다른 사본을 찾아 읽을 보류 건(HOLD_MODEL_AFTER회 이상 실패, 같은 건은 every_min분에 한 번만 넘긴다)"""
    now = now or common.now_kst()
    return [h for h in held() if h["tries"] >= HOLD_MODEL_AFTER
            and (not h.get("offered") or (now - datetime.fromisoformat(h["offered"])).total_seconds() >= every_min * 60)]


def offered(ids, now=None):
    st = common.load_state(HOLD, {})
    for k in ids:
        if k in st:
            st[k]["offered"] = common.iso(now or common.now_kst())
    common.save_state(HOLD, st)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
