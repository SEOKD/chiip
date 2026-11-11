"""상장사 IR·보도자료 채널 직접 감시 (마스터 지시 2026-11-11 "Business Wire와 GlobeNewswire 접근이 거부된다면 상장 기업들의 Press 및 IR 채널을 접근하도록 하라")

GlobeNewswire는 자동 접속 403, Business Wire는 M&A 피드만 열려 있다. 같은 보도자료는 회사 IR 사이트(Q4·Notified·자체 사이트)의 RSS에도 동시에 뜬다.
① 찾기(회사마다 30일에 한 번): SEC 최근 8-K 실적 첨부(EX-99.1)의 본문에서 회사 IR·홈페이지 주소를 뽑고(SEC 자료에는 웹사이트 칸이 비어 있다),
   그 페이지의 RSS 안내(<link type=application/rss+xml>, 'rss' 링크) → 흔한 IR 플랫폼 경로 순으로 보도자료 피드를 찾는다. 회차당 FIND_PER_RUN곳.
② 감시(run_poll 10분): 찾은 피드를 병렬로 읽어 48시간 안의 새 글을 inbox(src-ir-press, entities_matched=회사)로 낸다. 첫 회차는 기준선만.
대상: 감시·포트폴리오 종목 중 미국 상장(config/tradingview_symbols.csv). robots.txt를 지키고, 막히면 그 회사는 '없음'으로 두고 30일 뒤 다시 본다.
SEC 접속 규칙: 프로젝트 User-Agent(sec_filings._ua), 초당 10회 이하. 원문은 저장하지 않는다(제목·링크·요약 앞부분).
사용: py -m pollers.ir_press [--find N] [--show]   (radar/에서)
"""
import csv
import hashlib
import json
import re
import sys
import time
import urllib.parse
import urllib.robotparser
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta

from . import common, gate
from .rss import parse_feed, to_iso
from .sec_filings import SUB, _ua

SRC = "src-ir-press"
STATE = "ir_press"
FIND_PER_RUN = 8
RECHECK_DAYS = 30
LOOKBACK_H = 48
PATHS = ("/rss", "/press/rss", "/en/press/rss", "/media/rss", "/newsroom/rss", "/rss/news-releases.xml", "/news-releases/rss", "/rss/pressrelease.aspx", "/press-releases/rss", "/news/rss", "/feed/")
URL_RE = re.compile(r"(?:https?://)?((?:ir|investors?|investor-relations|www)\.[a-z0-9\-]+(?:\.[a-z0-9\-]+)*\.(?:com|net|io|ai|co|us|tech))", re.I)
SKIP_HOST = re.compile(r"sec\.gov|businesswire|globenewswire|prnewswire|accesswire|nasdaq\.com|nyse\.com|xbrl|w3\.org|fasb|zacks", re.I)
_robots = {}


def targets():
    """감시·포트폴리오 종목 중 미국 상장 → {티커: id}"""
    ids = set(gate.watch_ids()) | gate.portfolio_ids()
    out = {}
    with (common.ROOT / "config" / "tradingview_symbols.csv").open(encoding="utf-8", newline="") as fh:
        for r in csv.DictReader(fh):
            if r["entity_id"] in ids and r["tv_symbol"].split(":")[0] in ("NASDAQ", "NYSE", "AMEX", "NYSEARCA"):
                out[r["ticker"].upper()] = r["entity_id"]
                NAMES[r["ticker"].upper()] = r["name"]
    # 유럽·영국 감시 종목(2026-11-11 마스터 지시 — 지멘스 에너지 4분기 보도자료를 Pulse가 못 잡았다). 키 = 'EU:티커'(미국 티커와 겹치지 않게)
    for u in (common.load_yaml("config/earnings_watch.yaml") or {}).get("extra") or []:
        if u.get("region") in ("EU", "UK") and u["id"] in ids:
            k = "EU:" + str(u["code"]).split(".")[0].upper()
            out[k], NAMES[k] = u["id"], u["name"]
            EU.add(k)
    return out


EU = set()
# 유럽 회사 도메인 — 이름 추측이 틀린 곳(2026-11-11 1차 찾기 점검: alfa.com·be.com·nordic.de·vat.co.uk 등 남의 사이트)은 여기서 고정한다
DOMAINS = {"EU:ALFA": "www.alfalaval.com", "EU:BESI": "www.besi.com", "EU:BA": "www.baesystems.com", "EU:HEXA-B": "hexagon.com",
           "EU:HUBN": "www.hubersuhner.com", "EU:LDO": "www.leonardo.com", "EU:NOD": "www.nordicsemi.com", "EU:VACN": "www.vatgroup.com",
           "EU:HO": "www.thalesgroup.com", "EU:MTX": "www.mtu.de", "EU:HAG": "www.hensoldt.net", "EU:SAP": "news.sap.com", "EU:STMPA": "newsroom.st.com"}
JOBS = re.compile(r"career|jobs?\b|vacanc|stellen|\(f/m/d\)|\(m/w/d\)|engineer -|apprentice|graduate", re.I)


NAMES = {}
CORP = re.compile(r"\b(inc|corp|corporation|co|company|ltd|plc|holdings?|group|technologies|technology|n\.?v|s\.?a|lp|the|class [a-z])\b\.?", re.I)


def guess_hosts(t):
    """SEC 원문 서버가 막힐 때(연락처 User-Agent 없음 → www.sec.gov 403) 쓰는 IR 호스트 후보 — 티커·회사명 첫 단어·붙여 쓴 이름"""
    name = CORP.sub(" ", NAMES.get(t, "")).lower()
    words = re.findall(r"[a-z0-9]+", name)
    stems = list(dict.fromkeys([t.lower().replace(".", "")] + words[:1] + ["".join(words[:2])] + ["".join(words)]))
    if t in EU:   # 유럽 회사는 IR 하위 도메인보다 회사 사이트 보도자료 RSS가 흔하다 — 티커는 추측에서 뺀다(ENR → enr.com 같은 남의 회사)
        stems = list(dict.fromkeys(["-".join(words[:2])] + stems[1:]))
        return [f"www.{w}{tld}" for w in stems if len(w) > 1 for tld in (".com", ".de", ".co.uk")]
    return [f"{p}.{w}.com" for w in stems if len(w) > 1 for p in ("investors", "ir", "investor")]


def robots_ok(url):
    p = urllib.parse.urlparse(url)
    host = f"{p.scheme}://{p.netloc}"
    if host not in _robots:
        rp = urllib.robotparser.RobotFileParser()
        try:
            rp.parse(common.http_get(host + "/robots.txt", timeout=15).decode("utf-8", "ignore").splitlines())
        except Exception:
            rp = None   # robots.txt가 없으면 허용(표준)
        _robots[host] = rp
    rp = _robots[host]
    return rp is None or rp.can_fetch(common.UA, url)


def sec_get(url):
    time.sleep(0.12)
    return common.http_get(url, headers={"User-Agent": _ua()}, timeout=25)


def hosts_from_8k(cik):
    """최근 실적 8-K 첨부 본문에 나온 IR·홈페이지 호스트(IR 먼저)"""
    d = json.loads(sec_get(SUB.format(cik=cik)))
    r = d.get("filings", {}).get("recent", {})
    for i, form in enumerate(r.get("form", [])[:120]):
        if form not in ("8-K", "6-K") or (form == "8-K" and "2.02" not in (r.get("items", [""] * 999)[i] or "")):
            continue
        base = f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{r['accessionNumber'][i].replace('-', '')}"
        files = json.loads(sec_get(base + "/index.json")).get("directory", {}).get("item", [])
        ex = [f["name"] for f in files if re.search(r"ex-?99|exhibit99|pr\.htm|press", f["name"], re.I) and f["name"].lower().endswith((".htm", ".html", ".txt"))]
        if not ex:
            continue
        text = sec_get(f"{base}/{ex[0]}").decode("utf-8", "ignore")
        hosts = [h.lower() for h in URL_RE.findall(text) if not SKIP_HOST.search(h)]
        uniq = list(dict.fromkeys(hosts))
        return sorted(uniq, key=lambda h: 0 if re.match(r"(ir|investor)", h) else 1)
    return []


def is_feed(raw, t=None):
    """RSS로 읽히고, t가 있으면 글 제목·요약에 그 회사 이름이 나와야 한다 — 추측한 호스트가 남의 회사 IR일 수 있다(AAOI → ir.applied.com, 2026-11-11 시험)"""
    try:
        entries = parse_feed(raw)
    except Exception:
        return False
    if not entries:
        return False
    if not t:
        return True
    words = re.findall(r"[a-z0-9]+", CORP.sub(" ", NAMES.get(t, "")).lower())
    key = " ".join(words[:2]) if len(words) > 1 else (words[0] if words else t.lower())
    text = " ".join((e["title"] + " " + e["desc"]).lower() for e in entries[:20])
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return key in text or re.search(r"\b" + re.escape(t.lower()) + r"\b", text) is not None


def find_feed(host, t=None):
    """IR 호스트 → 보도자료 RSS 주소(없으면 None)"""
    home = f"https://{host}/"
    cands = []
    if not robots_ok(home):
        return None
    try:
        html = common.http_get(home, timeout=12).decode("utf-8", "ignore")
    except Exception:
        return None   # 호스트가 없거나 막혔다 — 경로 추측을 하지 않는다
    cands += re.findall(r'<link[^>]+type="application/(?:rss|atom)\+xml"[^>]+href="([^"]+)"', html, re.I)
    cands += [h for h in re.findall(r'href="([^"]+)"', html) if re.search(r"rss|feed", h, re.I) and re.search(r"news|press|release", h, re.I)]
    cands += PATHS
    for c in dict.fromkeys(cands):
        url = urllib.parse.urljoin(home, c.replace("&amp;", "&"))
        if not robots_ok(url):
            continue
        try:
            if is_feed(common.http_get(url, timeout=15), t):
                return url
        except Exception:
            continue
    if t in EU:   # 유럽 회사 사이트는 RSS가 드물고 목록을 스크립트로 그린다(지멘스 에너지·라인메탈·BAE 2026-11-11 확인)
        # → 회사 도메인으로 한정한 Google News RSS('site:' 검색): 지멘스 에너지 4분기 보도자료가 게재 수분 뒤 잡혔다. 회사 1차 문서만 나온다
        return "gn:" + host
    if False:   # 유럽 회사 사이트는 RSS가 드물다(지멘스 에너지·라인메탈·BAE 2026-11-11 확인) — 보도자료 목록 페이지 링크 비교로 대신한다
        pages = [h for h in re.findall(r'href="([^"]+)"', html) if PRESS_PAGE.search(h)][:6]
        for c in dict.fromkeys(pages):
            url = urllib.parse.urljoin(home, c.replace("&amp;", "&"))
            if urllib.parse.urlparse(url).netloc != host or not robots_ok(url):
                continue
            try:
                if len(page_links(url)) >= 5:
                    return "page:" + url
            except Exception:
                continue
    return None


PRESS_PAGE = re.compile(r"/(?:[a-z]{2}(?:-[a-z]{2})?/)?(?:[a-z\-]+/)*(?:press-releases?|pressemitteilungen|newsroom|press|news|media)(?:[./][a-z]*)?$", re.I)
PRESS_LINK = re.compile(r"(press|news|release|media|pressemitteilung)[^\s\"]*(20\d\d|[a-z0-9]+-[a-z0-9]+-[a-z0-9]+)", re.I)


def page_links(url):
    """보도자료 목록 페이지 → [{title, link}] (같은 호스트, 보도자료 같은 주소, 글자 있는 링크)"""
    html = common.http_get(url, timeout=20).decode("utf-8", "ignore")
    host = urllib.parse.urlparse(url).netloc
    out, seen = [], set()
    for href, text in re.findall(r'<a[^>]+href="([^"]+)"[^>]*>(.*?)</a>', html, re.S | re.I):
        link = urllib.parse.urljoin(url, href.replace("&amp;", "&")).split("#")[0]
        title = re.sub(r"\s+", " ", common.strip_tags(text)).strip()
        if urllib.parse.urlparse(link).netloc != host or link in seen or link.rstrip("/") == url.rstrip("/") or len(title) < 25 or not PRESS_LINK.search(link):
            continue
        seen.add(link)
        out.append({"title": title, "link": link, "date": "", "desc": ""})
    return out


def discover(st, tmap, n=FIND_PER_RUN):
    ciks = common.load_state("sec_filings", {}).get("ciks") or {}
    now = common.now_kst()
    feeds = st.setdefault("feeds", {})
    todo = [t for t in tmap if (t not in feeds or now - datetime.fromisoformat(feeds[t]["checked"]) > timedelta(days=RECHECK_DAYS))]
    found = 0
    for t in todo[:n]:
        feed, host = None, None
        try:
            hosts = hosts_from_8k(ciks[t])[:3] if ciks.get(t) else []
        except Exception as exc:   # www.sec.gov 403(SEC_USER_AGENT 없음) 등 — 이름 추측으로 넘어간다
            print(f"ir_press 8-K {t}: {type(exc).__name__}")
            hosts = []
        if t in DOMAINS:   # 고정 도메인 — 추측하지 않는다
            feed, host = "gn:" + DOMAINS[t], DOMAINS[t]
            hosts = []
        for host in ([] if feed else hosts + [h for h in guess_hosts(t) if h not in hosts]):
            feed = find_feed(host, t)
            if feed:
                break
        feeds[t] = {"id": tmap[t], "feed": feed, "host": host if feed else None, "checked": common.iso(now)}
        found += bool(feed)
    return len(todo[:n]), found


def read(t, info):
    try:
        if info["feed"].startswith("gn:"):
            es = parse_feed(common.http_get("https://news.google.com/rss/search", {"q": "site:" + info["feed"][3:], "hl": "en-US", "gl": "US", "ceid": "US:en"}, timeout=20))
            return t, info, [e for e in es if not JOBS.search(e["title"])]
        if info["feed"].startswith("page:"):
            return t, info, page_links(info["feed"][5:])
        return t, info, parse_feed(common.http_get(info["feed"], timeout=20))
    except Exception:
        return t, info, None


def poll(env=None, find=0):
    """run_poll 10분 — 읽기만(찾기는 run_hourly ir-press-find가 느리게 한다: 회사당 수십 초)"""
    st = common.load_state(STATE, {})
    tmap = targets()
    tried, found = discover(st, tmap, find)
    seen = set(st.get("seen") or [])
    first = not st.get("baseline_done")
    cutoff = common.now_kst() - timedelta(hours=LOOKBACK_H)
    live = [(t, i) for t, i in st.get("feeds", {}).items() if i.get("feed") and t in tmap]
    items, fails = [], 0
    with ThreadPoolExecutor(max_workers=8) as ex:
        based = set(st.get("based") or [])
        for t, info, entries in ex.map(lambda x: read(*x), live):
            if entries is None:
                fails += 1
                continue
            if t not in based and not first:
                seen.update(e["link"] for e in entries if e["link"])
                based.add(t)
                continue
            based.add(t)
            for e in entries[:20]:
                if not e["link"] or e["link"] in seen:
                    continue
                seen.add(e["link"])
                pub = to_iso(e["date"])
                if first or (pub and datetime.fromisoformat(pub) < cutoff):
                    continue
                items.append(common.make_item(SRC, hashlib.sha1(e["link"].encode()).hexdigest()[:16], e["link"],
                                              f"[IR] {t}: {common.strip_tags(e['title'])}", pub or common.iso(common.now_kst()), "보도자료", "en",
                                              common.strip_tags(e["desc"])[:400], extra={"entities_matched": [info["id"]], "ticker": t,
                                                                                          "source_class": "회사 IR 보도자료(1차)"}))
    if not find:   # 찾기(run_hourly)가 그 사이 피드를 더했을 수 있다 — 다시 읽고 본 글만 덮는다
        st = dict(common.load_state(STATE, {}), seen=st.get("seen"))
    st["seen"] = list(seen)[-20000:]
    st["based"] = sorted(based)
    st["baseline_done"] = True
    common.save_state(STATE, st)
    print(f"ir_press: 찾기 {tried}곳(피드 {found}) · 감시 피드 {len(live)} · 읽기 실패 {fails} · 새 글 {len(items)}")
    return items


def show():
    st = common.load_state(STATE, {})
    f = st.get("feeds", {})
    ok = {t: i for t, i in f.items() if i.get("feed")}
    print(f"대상 {len(targets())} · 확인 {len(f)} · 피드 찾음 {len(ok)}")
    for t, i in sorted(ok.items()):
        print(f"  {t:6s} {i['feed']}")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    if "--show" in sys.argv:
        show()
    elif "--find-only" in sys.argv:
        st = common.load_state(STATE, {})
        print("ir_press 찾기", discover(st, targets(), FIND_PER_RUN))
        common.save_state(STATE, st)
    else:
        n = int(sys.argv[sys.argv.index("--find") + 1]) if "--find" in sys.argv else FIND_PER_RUN
        its = poll(find=n)
        common.save_new_items(its)


def run():
    """run_hourly ir-press-find(30분) — 회차당 FIND_PER_RUN곳의 피드를 찾는다"""
    st = common.load_state(STATE, {})
    tried, found = discover(st, targets(), FIND_PER_RUN)
    common.save_state(STATE, st)
    return tried, found
