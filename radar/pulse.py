"""30분 펄스 (마스터 지시 2026-10-28 "30분마다 ① 기사 거리 원본 찾기 ② 텐배거 발굴 → 알파 레이더, 영어권·미국 주식 중심")

AI 파이낸싱(2026-10-29 마스터 지시 "AI 밸류체인 투자자라면 파이낸싱 시장 파악이 중요"): config/financing_watch.yaml 발행사의
  SEC 자금 조달 서류(424B·FWP·S-3ASR·8-K 2.03·3.02 등) + inbox의 자금 조달 제목(보도자료·공시·9개 매체 기사) — 보도 여부와 무관.
결정론 관문 — 모델(예약 작업 chiip-pulse)은 이 스크립트가 새 원본을 내놓을 때만 판단한다(CLAUDE.md '모델로 고빈도 폴링하지 않는다'의
마스터 지시 예외를 좁히는 장치). 기사가 아니라 **원본**만 모은다:
  논문     arXiv cs.AR(inbox) + cs.ET·physics.app-ph(여기서 6시간마다 직접, 기술 키워드 통과분) — Nature 계열은 robots.txt가 Claude 차단
  보도자료 PR Newswire·Business Wire·기업 뉴스룸(inbox, 영어판만)
  공시     SEC 8-K — 감시 목록은 sec_filings(inbox), 목록 밖은 여기서 EDGAR 전문검색으로 Item 1.01(중요 계약)·7.01·8.01
           × AI·반도체·데이터센터 전력 업종(SIC) × 유통주식 가치 1.5억 달러 이상 = 3자 보도자료·계약의 1차 흔적
  정부     백악관·미국 연방·주 정책 원천(inbox)
뉴스 기사(Google News·9개 매체)·리서치 블로그·중국·일본 정책 원천은 넣지 않는다.
출력: radar/pulse/YYYYMMDD_HHMM.json(git 제외) — sources(점수순)·candidates(감시 목록 밖 미국 상장 티커)·queue(알파 산정 대기)
사용: py radar/pulse.py                 # 수집·출력. 새 원본도 대기열도 없으면 '종료' 줄
      py radar/pulse.py --end            # 회차 끝(잠금 해제)
      py radar/pulse.py --enqueue <id> "<이름 (티커)>" "<이유>"   # 발굴 종목을 '알파 산정' 대기열에
"""
import json
import re
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from pollers import common, rss, sec_earnings_all as sea  # noqa: E402
from pollers.press_wire import NON_EN_RE  # noqa: E402

OUT = common.ROOT / "radar" / "pulse"
STATE = "pulse"
LOCK_MIN = 9           # 이전 회차가 이 시간 안에 시작돼 아직 안 끝났으면 건너뜀(회차 겹침 방지) — 10분 주기(2026-10-29 마스터 지시)
TOP = {"속보 판단": 3, "IR 질의응답": 4, "숏 리포트": 8, "신규 상장": 8, "파이낸싱": 12, "방위": 8, "공시": 15, "보도자료": 15, "논문": 12, "정부": 8}   # 유형별 상한 — 공시가 많은 날 논문이 밀려나지 않게
PAPER_FEEDS = {"src-arxiv-cset": "https://rss.arxiv.org/rss/cs.ET", "src-arxiv-appph": "https://rss.arxiv.org/rss/physics.app-ph"}
PAPER_EVERY_H = 6      # arXiv는 하루 한 번 갱신·robots Crawl-delay 15 — 6시간마다면 충분
DEAL_ITEMS = {"1.01": "중요 계약", "7.01": "공정공시(FD)", "8.01": "기타 중요 사건"}
# 원본 분류(소스 id 접두) — 여기 없는 소스는 넣지 않는다
CLASSES = [("IR 질의응답", ("src-jp-ir-qa",)),   # 일본 IR 질의응답 원문(2026-10-29 마스터 지시 — easyconomics에 일본 어닝콜 없음)
           ("방위", ("src-defense-",)),   # 각국 국방 조달·예산·방위 기업 뉴스룸(2026-10-29 마스터 지시, config/defense.yaml)
           ("논문", ("src-arxiv-", "src-openalex")),
           ("보도자료", ("src-prn", "src-bw", "src-newsroom-", "src-assoc-")),
           ("공시", ("src-sec-filings", "src-sec-self", "src-sec-deals", "src-edgar-fts")),
           ("정부", ("src-whitehouse", "src-policy-us-", "src-fedreg"))]
CLASS_W = {"속보 판단": 8, "IR 질의응답": 6, "숏 리포트": 6, "신규 상장": 4, "파이낸싱": 4, "방위": 3, "공시": 3, "보도자료": 2, "논문": 2, "정부": 1}
DEF_WORD_RE = re.compile(r"contract|award|order|procure|DSCA|Foreign Military|backlog|framework|Rahmenvertrag|Auftrag|commande|contrat|contrato|契約|受注", re.I)
TECH_RE = re.compile(
    r"HBM|DRAM|NAND|SRAM|memory|chiplet|hybrid bond|advanced packaging|CoWoS|interposer|substrate|EUV|lithograph|photoresist|"
    r"wafer|foundry|semiconductor|transistor|GAA|nanosheet|backside power|3D.?(IC|stack|integration)|TSV|interconnect|photonic|"
    r"co-packaged|\bCPO\b|optical (transceiver|interconnect|module)|SerDes|PCIe|\bCXL\b|NVLink|UALink|Ethernet switch|"
    r"\bGPUs?\b|\bTPU\b|\bASICs?\b|accelerator|inference|data ?cent(er|re)|power delivery|voltage regulat|\bGaN\b|\bSiC\b|"
    r"power (semiconductor|electronics|module)|liquid cool|immersion cool|transformer|power grid|gas turbine|fuel cell|"
    r"small modular reactor|\bSMR\b|superconduct|\bPCB\b|circuit board|AI (chip|server|infrastructure|factory|cluster)", re.I)
US_TICKER_RE = re.compile(r"\((?:NASDAQ|Nasdaq|NYSE|NYSE American|NYSE Arca|Cboe)\s*:\s*([A-Z][A-Z0-9.\-]{0,6})\)")
# AI 파이낸싱(마스터 지시 2026-10-29) — config/financing_watch.yaml. 보도 여부와 무관하게 모은다(기사도 9개 매체면 포함)
FIN_FORMS = {"424B2", "424B3", "424B5", "FWP", "S-3ASR", "S-3", "S-1", "F-1", "SC 13D", "SCHEDULE 13D"}
FIN_8K_ITEMS = {"1.01": "중요 계약", "2.03": "금융 채무 발생", "3.02": "미등록 증권 발행", "7.01": "공정공시", "8.01": "기타 중요 사건"}
QUEUE_BUSY = [((8, 5), (8, 45)), ((18, 5), (18, 45))]   # chiip-valuation-queue 실행 창 — 이때 펄스는 알파 산정을 건너뜀


def _fin_cfg():
    c = common.load_yaml("config/financing_watch.yaml") or {}
    c["_terms"] = re.compile(c.get("terms") or r"$^", re.I)
    c["_orgs"] = re.compile("|".join(r"\b" + re.escape(n) + r"\b" for n in c.get("org_names") or []) or r"$^", re.I)
    return c


def _allowed_publishers():
    rule = (common.load_yaml("config/alert_rules.yaml") or {}).get("telegram_filter") or {}
    return {p.lower() for p in rule.get("allowed_publishers", [])}


def is_financing(it, fin, pubs):
    """inbox 항목 중 AI 밸류체인 자금 조달 — 보도자료·공시는 그대로, 기사는 9개 매체만(국내·한국어 제외)"""
    title = it.get("title") or ""
    if it.get("source_id", "").endswith("-ko") or re.search(r"[가-힣]", title):
        return False
    if not fin["_terms"].search(title):
        return False
    if not (it.get("entities_matched") or fin["_orgs"].search(title)):
        return False
    if it.get("doc_type") == "기사":
        pub = (it.get("publisher") or (title.rsplit(" - ", 1)[1] if " - " in title else "")).strip().lower()
        return pub in pubs
    return True


def defense_hits(ents, title):
    from promote import defense_hits as hits   # 방위 지도 기업(not_titles 제외) — 판정 상향과 같은 기준
    return hits(ents, title)


def class_of(source_id):
    for name, prefixes in CLASSES:
        if source_id.startswith(prefixes) and not source_id.endswith("-ko"):
            return name
    return None


def score(it, cls):
    text = f"{it.get('title', '')} {it.get('snippet', '')}"
    s = CLASS_W.get(cls, 0) + min(len(TECH_RE.findall(text)), 4)
    s += 3 if it.get("entities_matched") else 0
    s += 2 if US_TICKER_RE.search(text) else 0
    s += 2 if any(k in str(it.get("sec_items", "")) for k in ("1.01", "8.01")) else 0
    s -= 2 if re.search(r"\b10-[QK]\b|\b425\b", it.get("title", "")) else 0   # 정기 보고서·합병 서류는 기사 원본으로 약함
    return s


def relevant(it, cls):
    text = f"{it.get('title', '')} {it.get('snippet', '')}"
    if cls == "IR 질의응답":   # 일본어 원문이 정상 — 언어 필터 예외
        return True
    if cls == "방위":   # 독·프·이·스·일 국방부 원문이 정상 — 언어 필터 예외(원천에서 조달어로 이미 거름)
        return True
    if it.get("language") not in (None, "en") or NON_EN_RE.search(it.get("title", "")):
        return False
    if cls == "공시" or it.get("entities_matched"):
        return True
    return bool(TECH_RE.search(text))


def inbox_items(since):
    out = []
    today = common.now_kst()
    fin, pubs = _fin_cfg(), _allowed_publishers()
    for day in {today.strftime("%Y%m%d"), (today - timedelta(days=1)).strftime("%Y%m%d")}:
        folder = common.ROOT / "radar" / "inbox" / day
        if not folder.exists():
            continue
        for f in folder.glob("src-*.json"):
            try:
                it = json.loads(f.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if (it.get("detected_at") or "") <= since:
                continue
            if is_financing(it, fin, pubs):
                out.append(dict(it, source_class="파이낸싱"))
                continue
            cls = class_of(it.get("source_id", ""))
            # 방위 지도 기업의 수주·계약 보도자료·공시(보도자료 배포처·SEC)도 방위로 모은다
            if cls in ("보도자료", "공시") and defense_hits(it.get("entities_matched") or [], it.get("title", "")) and DEF_WORD_RE.search(it.get("title", "")):
                cls = "방위"
            if not cls or not relevant(it, cls):
                continue
            out.append(dict(it, source_class=cls))
    return out


def fetch_papers(st):
    """cs.ET·physics.app-ph — 6시간마다, 기술 키워드 통과 + 처음 본 것만"""
    last = st.get("paper_fetch") or ""
    if last and datetime.fromisoformat(last) > common.now_kst() - timedelta(hours=PAPER_EVERY_H):
        return []
    seen, out = set(st.get("papers_seen", [])), []
    for sid, url in PAPER_FEEDS.items():
        try:
            entries = rss.parse_feed(common.http_get(url, timeout=30))
        except Exception:
            continue
        for e in entries:
            title, desc = common.strip_tags(e["title"]), common.strip_tags(e["desc"])
            if e["link"] in seen or not TECH_RE.search(f"{title} {desc}"):
                continue
            seen.add(e["link"])
            out.append({"source_id": sid, "source_class": "논문", "url": e["link"], "title": title, "published_at": rss.to_iso(e["date"]),
                        "detected_at": common.iso(common.now_kst()), "snippet": desc[:300], "language": "en", "entities_matched": []})
        time.sleep(1)
    st["paper_fetch"] = common.iso(common.now_kst())
    st["papers_seen"] = sorted(seen)[-3000:]
    return out


def fetch_deals(st, days=2):
    """감시 목록 밖 AI·전력 업종 8-K의 1.01·7.01·8.01 — 계약·3자 발표의 1차 흔적"""
    today = common.now_kst().date()
    watch = sea.watch_tickers()
    seen, floats, out = set(st.get("deals_seen", [])), st.get("float_cache", {}), []
    for adsh, s in sea.fetch_hits(today - timedelta(days=days), today):
        items = [i for i in (s.get("items") or []) if i in DEAL_ITEMS]
        if not items or adsh in seen:
            continue
        seen.add(adsh)
        sic = (s.get("sics") or [""])[0]
        name, ticker, cik = sea.parse_name((s.get("display_names") or [""])[0])
        if not ticker or ticker.upper() in watch or not sea.relevant(sic):
            continue
        cached = floats.get(cik)
        if cached and cached[1] >= str(today - timedelta(days=30)):
            fl = cached[0]
        else:
            fl = sea.public_float(cik)
            floats[cik] = [fl, str(today)]
            time.sleep(0.15)
        if fl is not None and fl < sea.MIN_FLOAT:
            continue
        url = f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{adsh.replace('-', '')}/"
        label = "·".join(f"{i} {DEAL_ITEMS[i]}" for i in items)
        out.append({"source_id": "src-sec-deals", "source_class": "공시", "url": url, "title": f"[SEC 8-K {label}] {name} ({ticker})",
                    "published_at": s.get("file_date"), "detected_at": common.iso(common.now_kst()), "language": "en",
                    "snippet": f"SIC {sic} {sea.relevant(sic)} · 유통주식 가치 {('%.1f억$' % (fl / 1e8)) if fl else '미상'}",
                    "sec_items": ",".join(items), "ticker": ticker, "entities_matched": []})
    st["deals_seen"] = sorted(seen)[-5000:]
    st["float_cache"] = floats
    return out


def fetch_financing(st, days=3):
    """발행사 SEC 제출 중 자금 조달 서류(424B·FWP·S-3ASR·8-K 2.03·3.02 등). FWP는 회사·날짜당 1건으로 묶는다"""
    from pollers import sec_filings as sec
    ua = {"User-Agent": sec._ua()}
    tickers = [t for ts in (_fin_cfg().get("issuers") or {}).values() for t in ts or []]
    since = (common.now_kst() - timedelta(days=days)).date().isoformat()
    cikst = st.setdefault("fin_ciks", {})
    seen, out, fwp_day = set(st.get("fin_seen", [])), [], set()
    for tk in tickers:
        cik = sec.cik_for(tk, cikst)
        time.sleep(0.12)
        if not cik:
            continue
        try:
            d = json.loads(common.http_get(sec.SUB.format(cik=cik), headers=ua))
        except Exception:
            continue
        time.sleep(0.12)
        r = d.get("filings", {}).get("recent", {})
        for i, form in enumerate(r.get("form", [])):
            if r["filingDate"][i] < since:
                break
            acc = r["accessionNumber"][i]
            if acc in seen:
                continue
            items = [x for x in ((r.get("items") or [""] * len(r["form"]))[i] or "").split(",") if x in FIN_8K_ITEMS]
            if not (form in FIN_FORMS or (form.startswith("8-K") and items)):
                continue
            seen.add(acc)
            if form == "FWP":
                if (tk, r["filingDate"][i]) in fwp_day:
                    continue
                fwp_day.add((tk, r["filingDate"][i]))
            if form.startswith("8-K") and set(items) <= {"7.01", "8.01"} and "2.02" in str((r.get("items") or [""])[i]):
                continue   # 실적 8-K의 부수 항목은 파이낸싱이 아니다
            label = "·".join(f"{x} {FIN_8K_ITEMS[x]}" for x in items) if items else form
            out.append({"source_id": "src-sec-financing", "source_class": "파이낸싱",
                        "url": f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{acc.replace('-', '')}/{r['primaryDocument'][i]}",
                        "title": f"[SEC {form} {label}] {d.get('name', tk)} ({tk})", "published_at": (r.get("acceptanceDateTime") or [""] * len(r["form"]))[i] or r["filingDate"][i],
                        "detected_at": common.iso(common.now_kst()), "language": "en", "ticker": tk, "entities_matched": [],
                        "snippet": f"{form} {(r.get('primaryDocDescription') or [''] * len(r['form']))[i]} · 색인 https://www.sec.gov/Archives/edgar/data/{int(cik)}/{acc.replace('-', '')}/",
                        "sec_items": ",".join(items)})
    st["fin_seen"] = sorted(seen)[-5000:]
    return out


def _short_cfg():
    c = common.load_yaml("config/short_watch.yaml") or {}
    c["_firms"] = re.compile("|".join(r"\b" + re.escape(n) + r"\b" for n in (c.get("firms") or []) + (c.get("firm_short") or [])) or r"$^", re.I)
    c["_terms"] = re.compile(c.get("terms") or r"$^", re.I)
    return c


def fetch_shorts(st, days=2):
    """숏 리포트(2026-10-29 마스터 지시 — Culper의 Cerebras 리포트 누락 뒤): Google News 색인 제목에서 숏 운용사 이름 또는
    숏 문구 + AI 밸류체인 이름. 운용사 이름은 8개씩 묶어 묻는다(포화 방지). 국내 언론 제외, 매체 제한 없음(숏 리포트 첫 보도는 업계지가 많다)"""
    from pollers import rss as prss
    import urllib.parse
    sc, fin = _short_cfg(), _fin_cfg()
    firms = sc.get("firms") or []
    queries = [" OR ".join(f'"{n}"' for n in firms[i:i + 8]) for i in range(0, len(firms), 8)]
    queries.append('("short report" OR "short seller" OR "we are short" OR "short position") (AI OR chip OR semiconductor OR "data center" OR GPU OR power OR optical)')
    seen, out = set(st.get("shorts_seen", [])), []
    for q in queries:
        url = prss.GNEWS.format(q=urllib.parse.quote(f"({q}) when:{days}d"), hl="en-US", gl="US")
        try:
            entries = prss.parse_feed(common.http_get(url, timeout=30))
        except Exception:
            continue
        for e in entries:
            title = common.strip_tags(e["title"])
            key = re.sub(r"\W+", " ", title.rsplit(" - ", 1)[0].lower()).strip()[:90]
            if key in seen or re.search(r"[가-힣]", title):
                continue
            firm = sc["_firms"].search(title)
            short = sc["_terms"].search(title) or re.search(r"\bshort", title, re.I)
            org = fin["_orgs"].search(title)
            tk = US_TICKER_RE.search(title) or re.search(r"\((?:NASDAQ|NYSE)?:?\s*([A-Z]{2,5})\)", title)
            if not ((firm and (short or org or tk or re.search(r"alleg|report|says|shares (fall|drop|slide|sink|tumble)", title, re.I)))
                    or (short and (org or tk))):
                continue    # 운용사 이름만 걸린 다른 글(다큐·소송 기사 등)·대상 불명 숏 문구는 버린다
            seen.add(key)
            out.append({"source_id": "src-short-reports", "source_class": "숏 리포트", "url": e["link"], "title": title,
                        "published_at": prss.to_iso(e["date"]), "detected_at": common.iso(common.now_kst()), "language": "en",
                        "publisher": e.get("publisher"), "entities_matched": [],
                        "snippet": f"운용사 {firm.group(0) if firm else '미상'} · 대상 {org.group(0) if org else (tk.group(1) if tk else '미상')}"})
        time.sleep(0.5)
    st["shorts_seen"] = sorted(seen)[-3000:]
    return out


def fetch_new_listings(st, days=3):
    """신규 상장(424B4·S-1) 중 AI·반도체·데이터센터 전력 업종(SIC)·감시 목록 밖 — Cerebras(2026-05 상장)가 감시 목록에 없던 구멍 보완"""
    today = common.now_kst().date()
    watch = sea.watch_tickers()
    seen, out = set(st.get("ipo_seen", [])), []
    for form in ("424B4", "S-1"):
        for adsh, s in sea.fetch_hits(today - timedelta(days=days), today, max_pages=3, forms=form):
            if adsh in seen:
                continue
            seen.add(adsh)
            sic = (s.get("sics") or [""])[0]
            name, ticker, cik = sea.parse_name((s.get("display_names") or [""])[0])
            if not sea.relevant(sic) or (ticker and ticker.upper() in watch):
                continue
            out.append({"source_id": "src-sec-ipo", "source_class": "신규 상장",
                        "url": f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{adsh.replace('-', '')}/",
                        "title": f"[SEC {form} 신규 상장] {name}" + (f" ({ticker})" if ticker else ""), "published_at": s.get("file_date"),
                        "detected_at": common.iso(common.now_kst()), "language": "en", "ticker": ticker, "entities_matched": [],
                        "snippet": f"SIC {sic} {sea.relevant(sic)}"})
    st["ipo_seen"] = sorted(seen)[-3000:]
    return out


def fetch_alerts(st, since=None):
    """속보 판단(2026-10-29 마스터 지시 "단순 정보 전달이 아니라 밸류 판단과 인사이트가 핵심"): 실시간 레이더가 지난 회차 이후 보낸
    P0·P1(radar/state/alerts.json) 중 아직 판단하지 않은 것 — 펄스가 인사이트 판단 틀(knowledge/methods/insight_framework.md)로 깊게 본다.
    P0 먼저, 같은 등급은 최근 순. 회차당 TOP['속보 판단']건, 나머지는 다음 회차로(판단한 것만 judged에 남는다 — 모델이 --judged로 표시)"""
    judged = set(st.get("judged", []))
    out = []
    for ref, a in common.load_state("alerts", {}).items():
        if ref in judged or a.get("level") not in ("P0", "P1"):
            continue
        if since and (a.get("sent_at") or "") <= (st.get("alerts_floor") or ""):
            continue
        out.append({"source_id": "src-alerts", "source_class": "속보 판단", "url": a.get("url"), "title": a.get("title"),
                    "published_at": a.get("published_at"), "detected_at": a.get("sent_at"), "language": "en",
                    "entities_matched": a.get("entities") or [], "snippet": f"{a.get('level')} · {a.get('what') or ''}"[:300],
                    "alert_ref": ref, "level": a.get("level")})
    out.sort(key=lambda x: (x["level"] != "P0", x["detected_at"] or ""), reverse=False)
    p0 = [x for x in out if x["level"] == "P0"]
    p1 = sorted([x for x in out if x["level"] == "P1"], key=lambda x: x["detected_at"] or "", reverse=True)
    return p0 + p1


def candidates(sources, watch):
    """원본에 나온 미국 상장 티커 중 감시 목록 밖 — 텐배거 발굴 재료(결정은 모델)"""
    c = {}
    for it in sources:
        tks = set(US_TICKER_RE.findall(f"{it.get('title', '')} {it.get('snippet', '')}"))
        if it.get("ticker") and it.get("source_id") in ("src-sec-deals", "src-sec-ipo"):
            tks.add(it["ticker"])
        for tk in tks:
            if tk.upper() in watch:
                continue
            c.setdefault(tk, {"ticker": tk, "id": "us-" + re.sub(r"[^a-z0-9]", "", tk.lower()), "urls": []})
            if len(c[tk]["urls"]) < 3:
                c[tk]["urls"].append(it["url"])
    return sorted(c.values(), key=lambda x: -len(x["urls"]))


def queue_busy(now):
    hm = (now.hour, now.minute)
    return any(a <= hm <= b for a, b in QUEUE_BUSY)


def alpha_queue():
    p = common.STATE / "v2_queue.json"
    q = json.loads(p.read_text(encoding="utf-8")) if p.exists() else []
    return [x for x in q if x.get("kind") == "알파 산정"]


def run(now=None):
    now = now or common.now_kst()
    st = common.load_state(STATE, {})
    lock = st.get("lock")
    if lock and datetime.fromisoformat(lock) > now - timedelta(minutes=LOCK_MIN):
        return None, f"[펄스] 이전 회차 진행 중({lock[11:16]} 시작) → 종료"
    since = st.get("watermark") or common.iso(now - timedelta(hours=2))
    sources, errors = inbox_items(since), []
    if "alerts_floor" not in st:   # 처음 켤 때는 지금 이후 알림만(과거 알림 수백 건을 한꺼번에 판단하지 않게)
        st["alerts_floor"] = common.iso(now - timedelta(hours=6))
    try:
        sources += fetch_alerts(st, since)
    except Exception as exc:
        errors.append(f"속보 판단: {type(exc).__name__}")
    for key, fn in (("논문", fetch_papers), ("공시", fetch_deals), ("파이낸싱", fetch_financing), ("숏 리포트", fetch_shorts), ("신규 상장", fetch_new_listings)):
        try:
            sources += fn(st)
        except Exception as exc:
            errors.append(f"{key}: {type(exc).__name__}")
    for it in sources:
        it["score"] = score(it, it["source_class"])
    sources.sort(key=lambda x: -x["score"])
    q = alpha_queue()
    busy = queue_busy(now)
    st["watermark"] = common.iso(now)
    if not sources and (not q or busy):
        common.save_state(STATE, st)
        return None, f"[펄스] 새 원본 없음 · 알파 산정 대기 {len(q)}{'(valuation-queue 실행 창)' if busy and q else ''} → 종료"
    counts = {c: sum(1 for s in sources if s["source_class"] == c) for c in TOP}
    watch = sea.watch_tickers()
    keep = ("source_id", "source_class", "score", "url", "title", "published_at", "detected_at", "snippet", "entities_matched", "sec_items", "ticker", "publisher", "alert_ref", "level", "local_text", "chars")
    data = {"run_at": common.iso(now), "since": since, "counts": counts, "errors": errors,
            "sources": [{k: s.get(k) for k in keep} for c, n in TOP.items() for s in [x for x in sources if x["source_class"] == c][:n]],
            "candidates": candidates(sources, watch)[:20],
            "queue": {"alpha": [{"id": x["id"], "name": x.get("name"), "reason": x.get("reason")} for x in q], "busy": busy}}
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / f"{now.strftime('%Y%m%d_%H%M')}.json"
    path.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    st["lock"] = common.iso(now)
    common.save_state(STATE, st)
    rel = path.relative_to(common.ROOT).as_posix()
    msg = (f"[펄스] 원본 {len(sources)}(" + "·".join(f"{c} {n}" for c, n in counts.items()) + f") · 후보 티커 {len(data['candidates'])}"
           f" · 알파 산정 대기 {len(q)}{'(valuation-queue 실행 창 — 이번엔 건너뜀)' if busy else ''} → {rel}" + (f" · 실패 {errors}" if errors else ""))
    return path, msg


def mark_judged(refs):
    st = common.load_state(STATE, {})
    st["judged"] = (st.get("judged", []) + [r for r in refs if r])[-3000:]
    common.save_state(STATE, st)


def end():
    st = common.load_state(STATE, {})
    st.pop("lock", None)
    common.save_state(STATE, st)


def main(argv):
    if "--end" in argv:
        end()
        print("[펄스] 회차 종료")
        return 0
    if "--judged" in argv:   # 모델이 속보 판단을 마친 알림 ref를 표시
        refs = argv[argv.index("--judged") + 1:]
        mark_judged(refs)
        print(f"[펄스] 속보 판단 완료 표시 {len(refs)}건")
        return 0
    if "--enqueue" in argv:
        i = argv.index("--enqueue")
        eid, name, reason = argv[i + 1:i + 4]
        added = sea.enqueue(eid, name, reason)
        print(f"[펄스] 알파 산정 대기열 {'추가' if added else '이미 있음'}: {eid}")
        return 0
    _, msg = run()
    print(msg)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
