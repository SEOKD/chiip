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
import run_ledger  # noqa: E402

OUT = common.ROOT / "radar" / "pulse"
STATE = "pulse"
LOCK_MIN = 9           # 이전 회차가 이 시간 안에 시작돼 아직 안 끝났으면 건너뜀(회차 겹침 방지) — 5분 주기(2026-10-30 마스터 지시)에선 긴 회차가 다음 회차를 건너뛰게 하고, --end 없이 멈춘 잠금만 9분 뒤 풀린다
LAST_PEEK = []        # 마지막 peek의 원본 목록(상태를 바꾸지 않는다)
DELIVER_MAX = 10      # 한 회차에 보내는 소식 상한 — 접한 소식이 10건이면 10건 모두(2026-11-03 마스터 지시)
TOP = {"SPAC": 6, "실적": 5, "속보 판단": 10, "텔레그램": 12, "IR 질의응답": 4, "IR 자료": 6, "소비재": 6, "숏 리포트": 8, "신규 상장": 8, "파이낸싱": 12, "방위": 8, "원자력·위성": 6, "공시": 15, "보도자료": 15, "논문": 12, "정부": 8}   # 유형별 상한 — 공시가 많은 날 논문이 밀려나지 않게
EARNINGS_MAX = 5      # 같은 회차에 겹친 실적 발표는 유형 상한과 별개로 5건까지 넘긴다(2026-11-03 마스터 지시)
EARNINGS_RE = re.compile(r"earnings|quarterly results|(first|second|third|fourth|1st|2nd|3rd|4th)[- ]quarter|fiscal (year|20\d\d)|\bQ[1-4]\b|決算|業績|실적|財報|營收", re.I)
PAPER_FEEDS = {"src-arxiv-cset": "https://rss.arxiv.org/rss/cs.ET", "src-arxiv-appph": "https://rss.arxiv.org/rss/physics.app-ph"}
PAPER_EVERY_H = 6      # arXiv는 하루 한 번 갱신·robots Crawl-delay 15 — 6시간마다면 충분
DEAL_ITEMS = {"1.01": "중요 계약", "7.01": "공정공시(FD)", "8.01": "기타 중요 사건"}
# 원본 분류(소스 id 접두) — 여기 없는 소스는 넣지 않는다
CLASSES = [("IR 질의응답", ("src-jp-ir-qa", "src-kr-ir-qa", "src-tw-hk-ir-qa")),   # 일본 IR 질의응답 원문(2026-10-29 마스터 지시 — easyconomics에 일본 어닝콜 없음)
           ("IR 자료", ("src-jp-ir-docs", "src-kr-ir-docs", "src-tw-hk-ir-docs", "src-fiscal-ir-docs")),   # src-fiscal-ir-docs = 유럽 등 IR 수집기 없는 종목의 PT·보도자료(Fiscal.ai IR 이벤트, 2026-11-08 AT&S)   # 일본 決算説明会資料(PT)·決算短信·補足 — 실적 보도 뒤 늦게 올라온다(2026-10-30 마스터 지시)
           ("원자력·위성", ("src-nuclear-", "src-space-")),   # NRC·에너지부·우주개발청 등(2026-10-31 마스터 지시, knowledge/methods/nuclear_space_lens.md)
           ("방위", ("src-defense-",)),   # 각국 국방 조달·예산·방위 기업 뉴스룸(2026-10-29 마스터 지시, config/defense.yaml)
           ("논문", ("src-arxiv-", "src-openalex")),
           ("보도자료", ("src-prn", "src-bw", "src-newsroom-", "src-assoc-")),
           ("공시", ("src-sec-filings", "src-sec-self", "src-sec-deals", "src-edgar-fts", "src-dart")),   # src-dart = SK하이닉스만(2026-11-06 마스터 지시 "SK하이닉스만 켜")
           ("정부", ("src-whitehouse", "src-policy-us-", "src-fedreg"))]
CLASS_W = {"SPAC": 6, "실적": 9, "속보 판단": 8, "텔레그램": 2, "IR 질의응답": 6, "IR 자료": 6, "소비재": 5, "숏 리포트": 6, "신규 상장": 4, "파이낸싱": 4, "방위": 3, "원자력·위성": 3, "공시": 3, "보도자료": 2, "논문": 2, "정부": 1}
NS_WORD_RE = re.compile(r"contract|award|order|tranche|launch|license|permit|approval|offtake|supply agreement|HALEU|selected|backlog", re.I)
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
# Chiip Consumer(마스터 지시 2026-10-30 — 비AI 급성장 소비재·게임·콘텐츠IP): config/consumer.yaml 지도 종목의 실적·업적 수정·월차(적시공시 미러·SEC·보도자료)
# + radar/consumer_attention.py의 수요 관심 급가속(IP·브랜드 위키 조회·스팀 추천) — 렌즈 knowledge/methods/consumer_lens.md
CONSUMER_EVENT_RE = re.compile(r"決算|業績|上方修正|下方修正|月次|増配|株式分割|最高益|earnings|results|guidance|quarter|outlook|raises|record", re.I)
CONSUMER_LATEST = common.ROOT / "knowledge" / "models" / "consumer" / "attention_latest.json"
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


def consumer_hits(ents, _c={}):
    if "ids" not in _c:
        _c["ids"] = {c["id"] for c in common.consumer_companies()}
    return [e for e in ents if e in _c["ids"]]


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
    if cls in ("IR 질의응답", "IR 자료"):   # 일본어·한국어 원문이 정상 — 언어 필터 예외
        return True
    if cls == "방위":   # 독·프·이·스·일 국방부 원문이 정상 — 언어 필터 예외(원천에서 조달어로 이미 거름)
        return True
    if cls == "원자력·위성":   # 정부 문서는 회사명이 없어도 인허가·계약이면 본다(원천에서 이미 거름)
        return True
    if it.get("source_id") == "src-dart":   # 한국어 공시 원문이 정상 — 언어 필터 예외(2026-11-06)
        return True
    if cls == "소비재":   # 일본 적시공시 미러·한국어 원문 포함 — 지도 종목 + 실적·업적 문구로 이미 거름
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
            if (it.get("saved_at") or it.get("detected_at") or "") <= since:   # 저장 시각으로 본다 — detected_at은 수집 시작 쪽이라 회차가 먼저 지나가면 사라진다
                continue
            if is_financing(it, fin, pubs):
                out.append(dict(it, source_class="파이낸싱"))
                continue
            cls = "IR 질의응답" if it.get("ir_event") else class_of(it.get("source_id", ""))   # 대만 法說會 공고(2026-10-30) — 중문 원문이라 언어 필터 예외
            # 방위 지도 기업의 수주·계약 보도자료·공시(보도자료 배포처·SEC)도 방위로 모은다
            if cls in ("보도자료", "공시") and defense_hits(it.get("entities_matched") or [], it.get("title", "")) and DEF_WORD_RE.search(it.get("title", "")):
                cls = "방위"
            # 원자력·위성 지도 종목의 계약·인허가 보도자료·공시도 같이 모은다(방위와 겹치면 방위 분류)
            if cls in ("보도자료", "공시") and set(it.get("entities_matched") or []) & common.watch_theme_ids() and NS_WORD_RE.search(it.get("title", "")):
                cls = "원자력·위성"
            # 소비재 지도 종목의 실적·업적 수정·월차(일본 적시공시 미러 포함) — 기사는 제외(원문만)
            if cls in (None, "보도자료", "공시") and consumer_hits(it.get("entities_matched") or []) and CONSUMER_EVENT_RE.search(it.get("title", ""))                     and (it.get("doc_type") in ("공시", "실적", "보도자료") or "適時開示" in it.get("title", "")):
                cls = "소비재"
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


def fetch_spac(st):
    """테마가 맞은 스팩의 생애 단계 전환(마스터 지시 2026-11-04 SPAC 2단계) — radar/pollers/spac_watch.py(단계)·spac_theme.py(테마)의 결과.
    transitions.csv는 덧붙이기만 하므로 처리한 줄 수를 st["spac_idx"]에 둔다. 테마 판정 전인 줄에서 멈춰 다음 회차에 다시 본다.
    처음 켤 때는 지금까지의 줄을 '본 것'으로 친다(과거 수백 건을 한꺼번에 보내지 않게)"""
    import csv
    d = common.ROOT / "knowledge" / "models" / "spac"
    if not (d / "transitions.csv").exists():
        return []
    with (d / "transitions.csv").open(encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))
    if "spac_idx" not in st:
        st["spac_idx"] = len(rows)
        return []
    themes = {}
    if (d / "themes.csv").exists():
        with (d / "themes.csv").open(encoding="utf-8", newline="") as f:
            themes = {r["cik"]: r for r in csv.DictReader(f)}
    stages = set((common.load_yaml("config/spac.yaml") or {}).get("alert_stages") or [])
    label = {"S2": "확정 계약", "S3": "등록", "S4": "주총", "S5": "종결"}
    out, i = [], st["spac_idx"]
    while i < len(rows):
        r = rows[i]
        if r["to"] in stages and r["cik"] not in themes:
            break   # 테마 판정 대기
        th = themes.get(r["cik"]) or {}
        old = (r.get("filed") or "") < (common.now_kst().date() - timedelta(days=7)).isoformat()   # 후속 추적이 늦게 찾은 옛 서류는 알리지 않는다
        if r["to"] in stages and th.get("theme") and not old:
            tk = (r["tickers"] or "").split(",")[0]
            out.append({"source_id": "src-spac", "source_class": "SPAC", "url": r["url"],
                        "title": f"[SPAC {label.get(r['to'], r['to'])}] {r['name']}" + (f" {tk}" if tk else "") + f" — {th.get('target') or '피인수 기업 미확인'} · {th['theme']}",
                        "published_at": r["filed"], "detected_at": common.iso(common.now_kst()), "language": "en", "ticker": tk, "entities_matched": [],
                        "snippet": f"{r['from'] or '신규'}→{r['to']} · {r['form']} · 테마 어휘 {th.get('terms', '')} ({th.get('hits')}회) · 거래 서류 {th.get('doc', '')}"})
        i += 1
    st["spac_idx"] = i
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


def is_earnings(x):
    """실적 발표 건 — 8-K 2.02 또는 제목·요약의 실적 문구"""
    return "2.02" in str(x.get("sec_items") or "") or bool(EARNINGS_RE.search(f"{x.get('title') or ''} {x.get('snippet') or ''}"))


def select(sources):
    """유형별 상한대로 고르고, 상한에 밀린 실적 발표 건은 회차 실적 합계가 EARNINGS_MAX가 될 때까지 더한다"""
    picked = [s for c, n in TOP.items() for s in [x for x in sources if x["source_class"] == c][:n]]
    room = EARNINGS_MAX - sum(1 for s in picked if is_earnings(s))
    ids = {id(s) for s in picked}
    extra = [s for s in sources if id(s) not in ids and s["source_class"] in TOP and is_earnings(s)]
    return picked + extra[:max(room, 0)]


def earnings_universe():
    """실적 즉시 보고 대상 미국 티커 → 회사 id(2026-11-03 마스터 지시 "레이더 망 종목과 TradingView 와치리스트 종목 중 어닝이 나오면 즉시 보고").
    감시 목록·발굴 watch 테마(TradingView 동기화 테마 포함)·소비재·조용한 상승·보유·와치리스트·TradingView 심볼 표"""
    import csv
    u = dict(sea.watch_tickers())
    for e in common.edge_watch_entries():
        code = e.get("code") or ""
        if code.endswith(".US"):
            u.setdefault(code[:-3].upper(), e["id"])
    for h in (common.load_yaml("config/portfolio.yaml") or {}).get("holdings") or []:
        if h.get("status") in ("보유", "관심") and h.get("ticker"):
            u.setdefault(h["ticker"].upper(), h["id"])
    f = common.ROOT / "config" / "tradingview_symbols.csv"
    if f.exists():
        for r in csv.reader(f.read_text(encoding="utf-8").splitlines()):
            if len(r) >= 4 and r[1] in ("NASDAQ", "NYSE", "AMEX", "NYSEARCA", "NYSEAMERICAN") and r[2]:
                u.setdefault(r[2].upper(), r[3])
    return u


def fetch_earnings(st, days=1):
    """레이더·와치리스트 종목의 8-K Item 2.02(실적)를 회차마다 SEC 전문 검색으로 찾는다 — 실적은 펄스 회차에서 바로 Dean's Ticker 3단으로"""
    from pollers import sec_filings as sec
    uni = earnings_universe()
    today = common.now_kst().date()
    first = "earn_seen" not in st   # 처음 켤 때는 이미 나온 실적을 다시 보내지 않는다
    seen, out = set(st.get("earn_seen", [])), []
    for adsh, s in sea.fetch_hits(today - timedelta(days=days), today):
        if first and adsh:
            seen.add(adsh)
            continue
        if not adsh or adsh in seen or "2.02" not in (s.get("items") or []):
            continue
        hit = None
        for name in s.get("display_names") or []:
            m = sea.NAME_RE.match(name)
            if m:
                for tk in re.split(r"[ ,]+", m.group(2)):
                    if tk.upper() in uni:
                        hit = (tk.upper(), m.group(1), m.group(3))
                        break
            if hit:
                break
        if not hit:
            continue
        seen.add(adsh)
        tk, name, cik = hit
        folder = f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{adsh.replace('-', '')}/"
        out.append({"source_id": "src-sec-earnings-now", "source_class": "실적", "url": folder, "title": f"[SEC 8-K 2.02 실적] {name} ({tk})",
                    "published_at": s.get("file_date"), "detected_at": common.iso(common.now_kst()), "language": "en", "ticker": tk,
                    "entities_matched": [uni[tk]], "snippet": f"8-K {','.join(s.get('items') or [])} · 실적 보도자료는 색인의 Ex.99.1", "sec_items": ",".join(s.get("items") or [])})
    st["earn_seen"] = sorted(seen)[-3000:]
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
                    "alert_ref": ref, "level": a.get("level"), "relay": a.get("relay")})
    out.sort(key=lambda x: (x["level"] != "P0", x["detected_at"] or ""), reverse=False)
    p0 = [x for x in out if x["level"] == "P0"]
    p1 = sorted([x for x in out if x["level"] == "P1"], key=lambda x: x["detected_at"] or "", reverse=True)
    return p0 + p1


def fetch_consumer_spikes(st):
    """수요 관심 급가속(하루 1회 갱신) — 새 관측일 때만, 상위 5건"""
    if not CONSUMER_LATEST.exists():
        return []
    d = json.loads(CONSUMER_LATEST.read_text(encoding="utf-8"))
    if (d.get("as_of") or "") <= st.get("consumer_spikes_at", ""):
        return []
    st["consumer_spikes_at"] = d.get("as_of") or ""
    out = []
    for s in (d.get("spikes") or [])[:5]:
        what = f"위키 '{s['key'].split(':', 1)[-1]}' 7일 조회 {s.get('views7')}" if s["source"] == "wiki" else f"스팀 앱 {s['key']} 7일 추천 +{s.get('gain7')}"
        out.append({"source_id": "consumer-attention", "source_class": "소비재", "url": "", "title": f"{s['name']} 수요 관심 급가속 ×{s['accel']} — {what}",
                    "published_at": d.get("as_of"), "detected_at": common.iso(common.now_kst()), "snippet": "radar/consumer_attention.py", "language": "ko",
                    "entities_matched": [s["id"]], "consumer_spike": s})
    return out


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


def fetch_telegram(st):
    """공개 텔레그램 채널(마스터 지시 2026-11-01). 걸린 글은 원본으로, 나머지는 st['tg_other']에 모아 회차가 열릴 때 넘긴다"""
    from pollers import tg_channels as tg
    if "unittest" not in sys.modules:   # 시험이 실제 채널을 읽지 않게 한다
        tg.poll_if_stale()
    now = common.iso(common.now_kst())
    mark = st.get("tg_mark")
    st["tg_mark"] = now
    st.setdefault("tg_start", mark or now)
    if not mark:   # 처음 켤 때는 지금 이후 글만
        return []
    cfg, out, other = tg.config(), [], st.setdefault("tg_other", [])
    for r in tg.dedupe(tg.since(mark)):
        text = r["text"]
        if not tg.relevant(r, cfg, TECH_RE):
            if text or r.get("image"):
                other.append({"channel": r["channel"], "at": r["at"][:16], "text": text[:100] or "[사진]", "url": r["url"], "image": r.get("image") or ""})
            continue
        out.append({"source_id": f"src-tg-{r['channel']}", "source_class": "텔레그램", "url": r["url"], "title": text.split(chr(10))[0][:120], "published_at": r["at"], "detected_at": r.get("seen"),
                    "snippet": text[:600], "entities_matched": common.match_entities(text), "publisher": r["channel"], "also": r.get("also"), "forwarded_from": r.get("forwarded_from"), "link": r.get("link")})
    out.sort(key=lambda x: -len(x["entities_matched"]))
    for x in out[TOP["텔레그램"]:]:   # 회차 상한을 넘은 글도 버리지 않고 목록으로 넘긴다
        other.append({"channel": x["publisher"], "at": x["published_at"][:16], "text": x["snippet"][:100], "url": x["url"]})
    st["tg_other"] = other[-150:]
    return out[:TOP["텔레그램"]]


def run(now=None, peek=False):
    """peek=True면 판정만 하고 상태·자료 파일을 건드리지 않는다(결정론 문턱, ADR-013 H2)"""
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
    for key, fn in (("실적", fetch_earnings), ("텔레그램", fetch_telegram), ("논문", fetch_papers), ("공시", fetch_deals), ("파이낸싱", fetch_financing), ("숏 리포트", fetch_shorts), ("신규 상장", fetch_new_listings), ("SPAC", fetch_spac), ("소비재", fetch_consumer_spikes)):
        try:
            sources += fn(st)
        except Exception as exc:
            errors.append(f"{key}: {type(exc).__name__}")
    for it in sources:
        it["score"] = score(it, it["source_class"])
    sources.sort(key=lambda x: -x["score"])
    import ir_ledger   # 당기 전문·Q&A는 처리 기록이 남을 때까지 다시 싣는다(2026-11-01 마스터 지시)
    if not peek:
        ir_ledger.track(sources, now)
    waiting = [dict(d["item"]) for d in ir_ledger.due(now)]
    urls = {w.get("url") for w in waiting}
    sources = waiting + [s for s in sources if s.get("url") not in urls]
    q = alpha_queue()
    busy = queue_busy(now)
    st["watermark"] = common.iso(now)
    try:   # 어닝콜 전문 신규 게재(마스터 지시 2026-10-30) — 대기 건이 있고 20분이 지났거나 정리할 전문이 남았으면 회차를 연다
        import transcript_watch
        tw = transcript_watch.due()
    except Exception as exc:
        tw = {"due": False, "error": type(exc).__name__}
    try:   # 일본 어닝콜 전사(TradingView 문서, 2026-11-02 마스터 지시)
        import jp_tv_docs
        jp = jp_tv_docs.status(now)
    except Exception as exc:
        jp = {"due": False, "error": type(exc).__name__}
    try:   # Exclusive Source 단서의 공개 근거 후보(2026-11-02 마스터 지시)
        import exclusive_leads
        ex = exclusive_leads.status(now)
    except Exception as exc:
        ex = {"due": False, "error": type(exc).__name__}
    try:   # 자동 재시도로 안 풀린 수집 채널(2026-11-02 마스터 지시)
        import self_heal
        heal = self_heal.status(now)
    except Exception as exc:
        heal = {"due": False, "error": type(exc).__name__}
    try:   # 커뮤니티 관심 급증(Quantral, 2026-11-07 마스터 지시) — 받을 종목이 있으면 회차를 연다(1시간 간격)
        import social_surge
        soc = social_surge.status(now)
    except Exception as exc:
        soc = {"due": False, "error": type(exc).__name__}
    try:   # Fiscal.ai IR 문서(PT·보도자료) — 유럽 등 회사 IR 수집기가 없는 종목(2026-11-08 마스터 지시 "AT&S 실적 발표 프레젠테이션을 가져오고 있는지")
        import fiscal_ir_docs
        fdocs = fiscal_ir_docs.status(now)
    except Exception as exc:
        fdocs = {"due": False, "error": type(exc).__name__}
    try:   # 분기 결산 산업 리포트(ADR-018, 2026-11-08 마스터 결정) — 시즌 중 하루 한 번 수집, 산업별 80% 발표면 작성
        import industry_quarter
        iq = industry_quarter.status(now)
    except Exception as exc:
        iq = {"due": False, "error": type(exc).__name__}
    try:   # 13F 시즌 기관 매입·매도 순위(2026-11-08 마스터 지시) — 마감 기준 잠정·주·확정 차례에 회차를 연다
        import thirteenf
        i13 = thirteenf.status(now)
    except Exception as exc:
        i13 = {"due": False, "error": type(exc).__name__}
    if not sources and (not q or busy) and not tw.get("due") and not jp.get("due") and not ex.get("due") and not heal.get("due") and not soc.get("due") and not i13.get("due") and not fdocs.get("due") and not iq.get("due"):
        if not peek:
            common.save_state(STATE, st)
        return None, (f"[펄스] 새 원본 없음 · 알파 산정 대기 {len(q)}{'(valuation-queue 실행 창)' if busy and q else ''}"
                      f" · 어닝콜 전문 대기 {tw.get('waiting', 0)} → 종료")
    if peek:
        global LAST_PEEK
        LAST_PEEK = sources   # 긴급 문턱(pulse_trigger urgent)이 점수·게재 시각을 본다
        return True, f"[펄스] 새 자료 {len(sources)}건 · 알파 산정 대기 {len(q)} · 어닝콜 전문 {'있음' if tw.get('due') else '없음'} → 모델 회차"
    counts = {c: sum(1 for s in sources if s["source_class"] == c) for c in TOP}
    watch = sea.watch_tickers()
    keep = ("source_id", "source_class", "score", "url", "title", "published_at", "detected_at", "snippet", "entities_matched", "sec_items", "ticker", "publisher", "alert_ref", "level", "local_text", "chars",
            "also", "forwarded_from", "link", "kind", "period", "doc_date", "local_pdf", "prev_text", "prev_url", "prev_period", "grade", "tier", "fallback", "material", "consumer_spike", "relay")   # IR 자료·Q&A·소비재 필드(2026-10-30)
    import origin   # 재인용 기사는 원보도로 바꿔 모델에 넘긴다(2026-11-02 마스터 지시)
    data = {"run_at": common.iso(now), "since": since, "counts": counts, "errors": errors,
            "sources": [{k: origin.apply(s, now).get(k) for k in keep} for s in select(sources)],
            "candidates": candidates(sources, watch)[:20],
            "queue": {"alpha": [{"id": x["id"], "name": x.get("name"), "reason": x.get("reason")} for x in q], "busy": busy},
            "transcripts": tw, "jp_transcripts": jp, "exclusive": ex, "repair": heal, "social": soc, "inst13f": i13, "fiscal_ir_docs": fdocs, "industry_quarter": iq, "tg_other": st.pop("tg_other", []), "deliver_max": DELIVER_MAX, "earnings_max": EARNINGS_MAX}
    ir_ledger.offered([s["url"] for s in data["sources"] if s.get("source_class") == ir_ledger.CLASS], now)
    if ex.get("due"):
        exclusive_leads.offered(now)
    if heal.get("due"):
        self_heal.offered(now)
    if soc.get("due"):
        social_surge.offered(now)
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / f"{now.strftime('%Y%m%d_%H%M')}.json"
    path.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    st["lock"] = common.iso(now)
    common.save_state(STATE, st)
    rel = path.relative_to(common.ROOT).as_posix()
    msg = (f"[펄스] 원본 {len(sources)}(" + "·".join(f"{c} {n}" for c, n in counts.items()) + f") · 후보 티커 {len(data['candidates'])}"
           f" · 알파 산정 대기 {len(q)}{'(valuation-queue 실행 창 — 이번엔 건너뜀)' if busy else ''}"
           f" · 어닝콜 전문 {'확인 차례' if tw.get('check') else '대기'} {tw.get('waiting', 0)}·정리 {tw.get('to_summarize', 0)} → {rel}" + (f" · 실패 {errors}" if errors else ""))
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
    run_ledger.record("gate", "chiip-pulse", outcome="종료" if msg.rstrip().endswith("종료") else "진행")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
