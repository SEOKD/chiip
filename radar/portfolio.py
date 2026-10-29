"""Chiip Portfolio (마스터 지시 2026-10-29 "포트폴리오에 담고 있는 종목에 관한 정보를 팔로업 — 공시·어닝·어닝콜 스크립트·전망·
IB 커버리지·레딧 등 투자 커뮤니티 관심도 등 다양한 채널")

결정론 관문 — 모델(예약 작업 chiip-portfolio)은 이 스크립트가 새 자료를 내놓을 때만 판단한다. 대상은 config/portfolio.yaml holdings.
  공시      SEC EDGAR submissions(종목별 cik) — 8-K·10-Q·10-K·425·S-4·424B·13D/G·Form 4 등 새 제출 전부
  보도자료  Google News 색인 중 PR Newswire·Business Wire·GlobeNewswire
  보도      Google News 색인 중 9개 매체(config/alert_rules.yaml allowed_publishers)만
  IB 커버리지  Google News 제목 중 목표가·상향·하향·커버리지 개시(config/narrative_sources.yaml analyst_actions)
  커뮤니티 글   Seeking Alpha·Motley Fool·Benzinga 등 제목(narrative_sources community_headlines — 사이트 직접 접속 금지)
  커뮤니티 관심도  ApeWisdom 공개 API(레딧·4chan 언급 수 집계 — 레딧은 robots.txt 전면 차단이라 직접 수집하지 않음)
                 + 위키백과 일간 조회수(Wikimedia REST, 하루 1회) + Hacker News(하루 1회)
  일정      config/portfolio.yaml events — 당일·전날 알림
모델 몫(easyconomics MCP): 실적 요약·어닝콜 스크립트·컨센서스·목표가·포지셔닝 — 예약 작업이 '데일리'(화~토 07시 이후 첫 회차)와
실적 공시가 잡힌 회차에 부른다. 커버리지 숫자는 --record로 남겨 전일 대비를 결정론으로 계산한다.
출력: radar/portfolio/YYYYMMDD_HHMM.json(git 제외) · 상태 radar/state/portfolio.json
사용: py radar/portfolio.py                     # 수집·출력. 새 자료도 데일리도 없으면 '종료' 줄
      py radar/portfolio.py --end              # 회차 끝(잠금 해제)
      py radar/portfolio.py --record EROC price=9.0 target_mean=22.33 buy=9 hold=0 sell=0 ...   # 커버리지 기록 + 전일 대비
      py radar/portfolio.py --event 2026-11-12 EROC "3Q26 실적 발표(장 마감 후)" <출처URL> [--unconfirmed]
"""
import csv
import json
import re
import statistics
import sys
import time
import urllib.parse
from datetime import date, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from pollers import common  # noqa: E402
from pollers import sec_filings as sec  # noqa: E402
import narrative_sources as ns  # noqa: E402

CFG = "config/portfolio.yaml"
OUT = common.ROOT / "radar" / "portfolio"
COVERAGE = common.ROOT / "knowledge" / "models" / "portfolio" / "coverage.csv"
COV_FIELDS = ["date", "ticker", "price", "target_mean", "target_low", "target_high", "buy", "hold", "sell", "rec",
              "short_pct", "fwd_pe", "next_earnings", "source"]
STATE = "portfolio"
LOCK_MIN = 25
FIRST_RUN_H = 48         # 처음 보는 종목은 48시간 이내 자료만 내놓고 그 이전은 본 것으로 처리(첫 회차 폭주 방지)
SEC_DAYS = 7
SEC_SKIP = {"S-8", "S-8 POS", "EFFECT", "CORRESP", "UPLOAD", "CERT", "CERTNYS", "CERTNAS", "8-A12B", "FWP"}
PRESS_SITES = ["prnewswire.com", "businesswire.com", "globenewswire.com"]
APE = "https://apewisdom.io/api/v1.0/filter/all-stocks/page/{p}"
WIKI = "https://wikimedia.org/api/rest_v1/metrics/pageviews/per-article/en.wikipedia/all-access/user/{a}/daily/{s}/{e}"
APE_MIN, APE_X = 10, 3.0      # 언급 10회 이상이면서 24시간 전의 3배 이상 = 관심 급증
WIKI_MIN, WIKI_X = 300, 3.0   # 조회 300 이상이면서 직전 28일 중앙값의 3배 이상
SEEN_CAP = 400


def holdings():
    return [h for h in (common.load_yaml(CFG) or {}).get("holdings") or [] if h.get("status", "보유") == "보유"]


def events():
    return (common.load_yaml(CFG) or {}).get("events") or []


def _co(h):
    """narrative_sources 형식(names·ticker) — mention_re·hn_hits 재사용"""
    return {"names": h.get("names") or [h["name"]], "ticker": h["ticker"]}


def _seen(st, key):
    return st.setdefault("seen", {}).setdefault(key, [])


def _remember(st, key, ids):
    s = _seen(st, key)
    s.extend(i for i in ids if i not in s)
    del s[:-SEEN_CAP]


# ---------- 공시 ----------
def sec_score(form, items):
    if "2.02" in items:
        return 10   # 실적
    if form.startswith(("8-K", "6-K")) and re.search(r"1\.01|2\.01|1\.02|2\.05|2\.06|3\.0[1-3]|5\.0[1-3]|5\.07", items):
        return 8
    if form.startswith(("10-Q", "10-K", "20-F", "S-4", "DEFM14A", "DEF 14A", "424B", "S-1", "S-3", "SC 13D", "SCHEDULE 13D")):
        return 6
    if form.startswith("8-K"):
        return 5
    if form in ("4", "3", "SC 13G", "SC 13G/A", "SCHEDULE 13G", "SCHEDULE 13G/A", "144"):
        return 3
    if form == "425":
        return 2    # 스팩 합병 홍보물(팟캐스트·인터뷰 녹취 등)이 매일 나온다 — 모델이 훑되 점수는 낮게
    return 3


def fetch_sec(h, st, now, first):
    ua = {"User-Agent": sec._ua()}
    d = json.loads(common.http_get(sec.SUB.format(cik=h["cik"]), headers=ua))
    r = d.get("filings", {}).get("recent", {})
    since = (now - timedelta(days=SEC_DAYS)).date().isoformat()
    cut = (now - timedelta(hours=FIRST_RUN_H)).date().isoformat()
    seen, out, new_ids = set(_seen(st, f"sec:{h['ticker']}")), [], []
    for i, form in enumerate(r.get("form", [])):
        if r["filingDate"][i] < since:
            break
        acc = r["accessionNumber"][i]
        if acc in seen or form in SEC_SKIP:
            continue
        new_ids.append(acc)
        if first and r["filingDate"][i] < cut:
            continue
        items = (r.get("items") or [""] * len(r["form"]))[i] or ""
        labels = [sec.ITEM_LABEL[x] for x in items.split(",") if x in sec.ITEM_LABEL]
        doc = r["primaryDocument"][i]
        out.append({"kind": "공시", "ticker": h["ticker"], "form": form, "items": items, "labels": labels,
                    "title": f"[SEC {form}{' ' + '·'.join(labels) if labels else ''}] {d.get('name', h['name'])} — {(r.get('primaryDocDescription') or [''] * len(r['form']))[i]}",
                    "url": f"https://www.sec.gov/Archives/edgar/data/{int(h['cik'])}/{acc.replace('-', '')}/{doc}",
                    "index": f"https://www.sec.gov/Archives/edgar/data/{int(h['cik'])}/{acc.replace('-', '')}/",
                    "date": (r.get("acceptanceDateTime") or [""] * len(r["form"]))[i] or r["filingDate"][i],
                    "score": sec_score(form, items), "id": acc})
    return out, new_ids


# ---------- Google News 색인(제목·링크만) ----------
def _publishers():
    rule = (common.load_yaml("config/alert_rules.yaml") or {}).get("telegram_filter") or {}
    return {p.lower() for p in rule.get("allowed_publishers", [])}


def _norm(t):
    return re.sub(r"\W+", " ", (t or "").rsplit(" - ", 1)[0].lower()).strip()


def _recent(iso, hours):
    try:
        return datetime.fromisoformat(str(iso).replace("Z", "+00:00")) >= common.now_kst() - timedelta(hours=hours)
    except (TypeError, ValueError):
        return False


def fetch_news(h, st, first, days=2):
    c = ns.cfg()["auto"]
    names = h.get("names") or [h["name"]]
    name_q = " OR ".join([f'"{n}"' for n in names] + [f'"{h["ticker"]}"'])
    pat = ns.mention_re(_co(h))
    pubs = _publishers()
    terms_re = re.compile("|".join(re.escape(t) for t in c["analyst_actions"]["terms"]), re.I)
    queries = (
        ("보도자료", f"({' OR '.join('site:' + s for s in PRESS_SITES)}) ({name_q})", None, 5),
        ("IB 커버리지", f"({name_q}) ({' OR '.join(chr(34) + t + chr(34) for t in c['analyst_actions']['terms'])})", None, 6),
        ("커뮤니티 글", f"({' OR '.join('site:' + s for s in c['community_headlines']['sites'])}) ({name_q})", None, 3),
        ("보도", f"({name_q})", pubs, 6),
    )
    seen = set(_seen(st, f"news:{h['ticker']}"))
    out, new_ids, titles = [], [], set()
    for kind, q, allow, sc in queries:
        try:
            items = ns.gnews(q, days, 30)
        except Exception as exc:
            out.append({"kind": "오류", "ticker": h["ticker"], "title": f"{kind}: {type(exc).__name__}"})
            continue
        items, _ = ns.keep_titles(items, pat)
        for it in items:
            pub = (it.get("publisher") or "").strip()
            if allow is not None and pub.lower() not in allow:
                continue    # 기사 = 9개 매체만(CLAUDE.md 수집 범위)
            k = kind
            if kind == "IB 커버리지" and not terms_re.search(it["title"]):
                continue    # 검색어가 본문에만 걸린 시황·추천 글은 버린다(제목에 목표가·상향·하향·개시가 있어야)
            if kind != "IB 커버리지" and terms_re.search(it["title"]):
                k = "IB 커버리지"
            key = _norm(it["title"])
            if key in titles:
                continue
            titles.add(key)
            if key in seen or it["url"] in seen:
                continue
            new_ids.append(key)
            if first and not _recent(it.get("date"), FIRST_RUN_H):
                continue    # 첫 회차는 48시간 안 기사만 내놓는다(2026-10-29 수정 — 기준선 처리로 MRVL·Lumentum 인수 협상 보도를 놓쳤다)
            out.append({"kind": k, "ticker": h["ticker"], "title": it["title"], "url": it["url"], "date": it.get("date"),
                        "publisher": pub, "score": {"보도자료": 6, "IB 커버리지": 6, "보도": 5, "커뮤니티 글": 3}[k], "id": key})
        time.sleep(0.6)
    return out, new_ids


# ---------- 커뮤니티 관심도 ----------
def fetch_ape(tickers):
    """{ticker: {rank, mentions, mentions_24h_ago, rank_24h_ago}} — 상위 목록(약 800종목)에 없으면 빠진다(=언급 적음)"""
    found, page, pages = {}, 1, 1
    while page <= pages and page <= 12:
        d = json.loads(common.http_get(APE.format(p=page), timeout=25))
        pages = int(d.get("pages") or 1)
        for r in d.get("results", []):
            if r.get("ticker") in tickers:
                found[r["ticker"]] = {k: r.get(k) for k in ("rank", "mentions", "mentions_24h_ago", "rank_24h_ago", "upvotes")}
        page += 1
        time.sleep(0.5)
    return found


def ape_signal(t, row):
    m, prev = int(row.get("mentions") or 0), int(row.get("mentions_24h_ago") or 0)
    if m >= APE_MIN and m >= APE_X * max(prev, 1):
        return f"레딧 등 언급 급증: {m}회(24시간 전 {prev}회), 순위 {row.get('rank')}위(전일 {row.get('rank_24h_ago')}위)"
    return None


def fetch_wiki(article, day):
    s = (day - timedelta(days=28)).strftime("%Y%m%d")
    e = day.strftime("%Y%m%d")
    d = json.loads(common.http_get(WIKI.format(a=urllib.parse.quote(article), s=s, e=e), timeout=25))
    return [(x["timestamp"][:8], int(x["views"])) for x in d.get("items", [])]


def wiki_signal(series):
    if len(series) < 8:
        return None, None
    last = series[-1][1]
    med = statistics.median(v for _, v in series[:-1]) or 1
    sig = f"위키백과 조회 급증: {last}회(직전 28일 중앙값 {med:.0f}회의 {last / med:.1f}배)" if last >= WIKI_MIN and last >= WIKI_X * med else None
    return sig, {"views": last, "median28": med}


# ---------- 일정 ----------
def due_events(today, st):
    out = []
    sent = st.setdefault("events_sent", [])
    for ev in events():
        try:
            d = date.fromisoformat(str(ev["date"]))
        except (KeyError, ValueError):
            continue
        for tag, when in (("D-1", d - timedelta(days=1)), ("D-0", d)):
            key = f"{ev['date']}|{ev.get('ticker')}|{tag}|{str(ev.get('what'))[:30]}"
            if when == today and key not in sent:
                out.append({"kind": "일정", "ticker": ev.get("ticker"), "title": f"[{'내일' if tag == 'D-1' else '오늘'}] {ev.get('what')}" +
                            ("" if ev.get("confirmed", True) else " (미확정)"), "url": ev.get("source"), "date": str(ev["date"]),
                            "score": 9, "id": key})
    return out


def upcoming(today, days=14):
    rows = []
    for ev in events():
        try:
            d = date.fromisoformat(str(ev["date"]))
        except (KeyError, ValueError):
            continue
        if today <= d <= today + timedelta(days=days):
            rows.append({"date": str(ev["date"]), "ticker": ev.get("ticker"), "what": ev.get("what"), "confirmed": ev.get("confirmed", True)})
    return sorted(rows, key=lambda r: r["date"])


# ---------- 회차 ----------
def is_daily(now, st):
    """데일리 = 화~토(미국 월~금 장 마감 다음 날 아침) 07시 이후 그날 첫 회차"""
    return now.weekday() in (1, 2, 3, 4, 5) and now.hour >= 7 and st.get("daily_day") != now.date().isoformat()


def run(now=None):
    now = now or common.now_kst()
    st = common.load_state(STATE, {})
    lock = st.get("lock")
    if lock and datetime.fromisoformat(lock) > now - timedelta(minutes=LOCK_MIN):
        return None, f"[포트폴리오] 이전 회차 진행 중({lock[11:16]} 시작) → 종료"
    hs = holdings()
    if not hs:
        return None, "[포트폴리오] 보유 종목 없음(config/portfolio.yaml) → 종료"
    today = now.date()
    items, errors, attention = [], [], {}
    known = set(st.setdefault("known", []))
    for h in hs:
        t = h["ticker"]
        first = t not in known
        first_news = f"news:{t}" not in st.get("seen", {})
        for name, fn in (("SEC", lambda: fetch_sec(h, st, now, first)), ("뉴스", lambda: fetch_news(h, st, first_news))):
            try:
                got, ids = fn()
                errs = [g for g in got if g.get("kind") == "오류"]
                errors += [f"{t} {e['title']}" for e in errs]
                items += [g for g in got if g.get("kind") != "오류"]
                _remember(st, f"{'sec' if name == 'SEC' else 'news'}:{t}", ids)
            except Exception as exc:
                errors.append(f"{t} {name}: {type(exc).__name__}")
            time.sleep(0.2)
        known.add(t)
    st["known"] = sorted(known)

    tickers = {h["ticker"] for h in hs}
    try:
        ape = fetch_ape(tickers)
        hist = st.setdefault("ape", {})
        for t in tickers:
            row = ape.get(t)
            attention.setdefault(t, {})["apewisdom"] = row or "상위 목록 밖(언급 적음)"
            sig = ape_signal(t, row) if row else None
            if sig and hist.get(t, {}).get("alerted") != today.isoformat():
                items.append({"kind": "관심도", "ticker": t, "title": sig, "url": "https://apewisdom.io/", "score": 5, "id": f"ape|{t}|{today}"})
                hist.setdefault(t, {})["alerted"] = today.isoformat()
            if row:
                hist.setdefault(t, {})["last"] = {**row, "at": common.iso(now)}
    except Exception as exc:
        errors.append(f"ApeWisdom: {type(exc).__name__}")

    if st.get("wiki_day") != today.isoformat() and now.hour >= 10:   # 전일(UTC) 조회수가 반영된 뒤 하루 1회
        for h in hs:
            if not h.get("wiki"):
                continue
            try:
                sig, info = wiki_signal(fetch_wiki(h["wiki"], today - timedelta(days=1)))
                attention.setdefault(h["ticker"], {})["wikipedia"] = info
                if sig:
                    items.append({"kind": "관심도", "ticker": h["ticker"], "title": f"{sig} — {h['wiki']}",
                                  "url": f"https://en.wikipedia.org/wiki/{h['wiki']}", "score": 4, "id": f"wiki|{h['ticker']}|{today}"})
            except Exception as exc:
                errors.append(f"{h['ticker']} 위키: {type(exc).__name__}")
            time.sleep(0.3)
        for h in hs:
            try:
                hn = ns.hn_hits(_co(h), days=2)
                seen = set(_seen(st, f"hn:{h['ticker']}"))
                new = [x for x in hn if x["url"] not in seen]
                _remember(st, f"hn:{h['ticker']}", [x["url"] for x in new])
                items += [{"kind": "커뮤니티 글", "ticker": h["ticker"], "title": f"[HN {x.get('points') or 0}점·댓글 {x.get('comments') or 0}] {x['title']}",
                           "url": x["url"], "date": x.get("date"), "score": 3, "id": x["url"]} for x in new]
            except Exception as exc:
                errors.append(f"{h['ticker']} HN: {type(exc).__name__}")
            time.sleep(0.3)
        st["wiki_day"] = today.isoformat()

    items += due_events(today, st)
    daily = is_daily(now, st)
    earnings_hit = sorted({i["ticker"] for i in items if i.get("kind") == "공시" and "2.02" in (i.get("items") or "")})
    common.save_state(STATE, st)
    if not items and not daily:
        return None, f"[포트폴리오] 새 자료 없음({len(hs)}종목)" + (f" · 실패 {errors}" if errors else "") + " → 종료"

    items.sort(key=lambda i: (-i.get("score", 0), i.get("ticker") or ""))
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / f"{now:%Y%m%d_%H%M}.json"
    data = {"run_at": common.iso(now), "daily": daily, "earnings_hit": earnings_hit,
            "holdings": [{k: h.get(k) for k in ("ticker", "name", "id", "kind", "names")} for h in hs],
            "items": items, "attention": attention, "upcoming": upcoming(today), "coverage_last": coverage_last(), "errors": errors}
    path.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    st = common.load_state(STATE, {})
    st["lock"] = common.iso(now)
    if daily:
        st["daily_day"] = today.isoformat()
    st.setdefault("events_sent", []).extend(i["id"] for i in items if i["kind"] == "일정")
    del st["events_sent"][:-200]
    common.save_state(STATE, st)
    by = {}
    for i in items:
        by[i["kind"]] = by.get(i["kind"], 0) + 1
    rel = path.relative_to(common.ROOT).as_posix()
    return path, (f"[포트폴리오] {len(hs)}종목 · 새 자료 {len(items)}건 {by}" + (" · 데일리" if daily else "") +
                  (f" · 실적 공시 {earnings_hit}" if earnings_hit else "") + f" → {rel}" + (f" · 실패 {errors}" if errors else ""))


def end():
    st = common.load_state(STATE, {})
    st.pop("lock", None)
    common.save_state(STATE, st)


# ---------- 커버리지 기록(모델이 easyconomics로 읽은 숫자) ----------
def coverage_rows():
    if not COVERAGE.exists():
        return []
    with COVERAGE.open(encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def coverage_last():
    last = {}
    for r in coverage_rows():
        last[r["ticker"]] = r
    return last


def _num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def coverage_diff(prev, cur):
    out = []
    for k in COV_FIELDS[2:]:
        a, b = (prev or {}).get(k), cur.get(k)
        if b in (None, "") or a == b:
            continue
        na, nb = _num(a), _num(b)
        if na is not None and nb is not None:
            pct = f" ({(nb / na - 1) * 100:+.1f}%)" if na else ""
            out.append(f"{k} {a}→{b}{pct}")
        elif a not in (None, ""):
            out.append(f"{k} {a}→{b}")
    return out


def record(ticker, pairs, today=None):
    cur = {"date": (today or common.now_kst().date()).isoformat(), "ticker": ticker.upper()}
    for p in pairs:
        k, _, v = p.partition("=")
        if k not in COV_FIELDS:
            raise SystemExit(f"모르는 항목: {k} (가능: {', '.join(COV_FIELDS[2:])})")
        cur[k] = v
    prev = coverage_last().get(cur["ticker"])
    COVERAGE.parent.mkdir(parents=True, exist_ok=True)
    new = not COVERAGE.exists()
    with COVERAGE.open("a", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=COV_FIELDS)
        if new:
            w.writeheader()
        w.writerow(cur)
    return prev, coverage_diff(prev, cur)


def add_event(d, ticker, what, url, confirmed=True):
    date.fromisoformat(d)
    for ev in events():
        if str(ev.get("date")) == d and ev.get("ticker") == ticker and str(ev.get("what"))[:20] == what[:20]:
            return False
    line = "  - " + json.dumps({"date": d, "ticker": ticker, "what": what, "source": url, "confirmed": confirmed}, ensure_ascii=False) + "\n"
    p = common.ROOT / CFG
    text = p.read_text(encoding="utf-8")
    p.write_text(text + ("" if text.endswith("\n") else "\n") + line, encoding="utf-8")
    return True


def main(argv):
    sys.stdout.reconfigure(encoding="utf-8")
    if "--end" in argv:
        end()
        print("[포트폴리오] 회차 종료")
        return 0
    if "--record" in argv:
        i = argv.index("--record")
        prev, diff = record(argv[i + 1], argv[i + 2:])
        print(f"[포트폴리오] {argv[i + 1].upper()} 기록 · 이전 {prev['date'] if prev else '없음'} 대비: " + ("; ".join(diff) or "변화 없음"))
        return 0
    if "--event" in argv:
        i = argv.index("--event")
        d, t, what, url = argv[i + 1:i + 5]
        ok = add_event(d, t.upper(), what, url, "--unconfirmed" not in argv)
        print(f"[포트폴리오] 일정 {'추가' if ok else '이미 있음'}: {d} {t.upper()} {what}")
        return 0
    _, msg = run()
    print(msg)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
