"""내부자 매수 채널 — 미국 Form 4 장내 매수(거래 코드 P)·한국 임원·주요주주 소유보고 장내매수(보고사유 01)에서 기회형 내부자만 골라
'여러 명이 30일 안에 매수(cluster)'·'CEO·CFO 매수(ceo)' 단서를 단서 장부에 넣는다
(마스터 지시 2026-11-15 "다양한 종목 발굴 채널", 알파 발굴 엔진 ADR-043 — 채널 insider, 규칙 config/discovery_channels.yaml channels.insider.rules)

근거(조사 B §5.1, knowledge/methods/discovery_engine.md):
  Cohen·Malloy·Pomorski(2012 JF 67(3); NBER WP 16454 본문 확인 2026-11-15) — "앞선 3년 각 해에 거래가 있고, 같은 달에 3년 연속 거래한 내부자"가 일상형이다.
    일상형 거래의 초과수익은 0에 가깝고 나머지(기회형) 매수 포트폴리오는 월 82bp(가치가중, 동일가중 180bp)다. 정보가 가장 많은 쪽은 비임원급 기회형이다.
    논문은 3년 이력이 없는 내부자를 분류하지 않았다. Chiip은 일상형만 빼고, 이력이 모자란 내부자는 '기회형(이력 부족)'으로 남겨 성적표가 나눠 잰다.
  Lakonishok·Lee(2001 RFS 14(1)) — 예측력은 매수(주로 작은 회사)에 있고 매도에는 없다. 그래서 매도는 단서로 쓰지 않고 일상형 판정에만 쓴다.
수집(결정론, run_hourly 60분, 회차 시간 예산 rules.budget_min):
  미국: SEC EDGAR 전문 검색(efts, forms=4 원본, 접수일별)으로 목록을 받고, 원문 XML(ownershipDocument) 비파생 거래표에서 코드 P·취득(A)·보통주만 센다.
    10b5-1 계획 표시(aff10b5One, 2023 개정 서식)가 있는 서류는 미리 정한 매매라 뺀다.
    일상형 판정: 보고자 CIK 제출 목록(data.sec.gov)에서 같은 달 Form 4를 앞선 3년 해마다 연다. 해마다 같은 회사의 P·S 거래가 있으면 일상형이다.
    SEC 프로젝트 User-Agent로 초당 5회 이하(thirteenf_market.get — 429면 전역 휴식). 13F 시장 수집 잠금이 살아 있으면 이 회차는 쉰다(동시 호출 방지).
  한국: OpenDART list.json(지분공시 D, 접수일별) '임원ㆍ주요주주특정증권등소유상황보고서' → elestock.json(회사별 보고자·직위·등기·주요주주·증감).
    elestock에는 매매 사유 칸이 없다(개발가이드 확인 2026-11-15). 그래서 증감이 양(+)인 보고만 원본(document.xml) 세부변동내역에서
    보고사유 코드 01 장내매수(+)·변동일·단가·거래계획보고일자를 읽는다.
    거래계획보고일자가 있는 매수(2024-07 거래계획 사전공시 제도)는 미리 알린 매매라 뺀다.
    일상형: list.json(회사 고유번호, 앞선 3년 같은 달)에서 같은 보고자의 소유상황보고서를 찾는다. 해마다 원본에 장내매수·장내매도(01·02)가 있으면 일상형이다.
    키는 .env DART_API_KEY를 common.load_env()로만 읽는다.
판정(단서 장부 scripts/discovery/leads.py add):
  cluster — 같은 회사에서 30일(rules.cluster_days) 안에 서로 다른 기회형 내부자 2명(rules.cluster_min) 이상이 샀다.
            한 서류의 공동 보고자는 1명으로 센다. 임원·이사가 아닌 10% 주주(주요주주)는 모두 합쳐 1명으로 센다.
  ceo     — CEO·CFO(대표이사·재무 책임자)의 기회형 매수. 여러 명이면 cluster로 한 번만 넣는다.
  빼는 것: 펀드형 발행사(SEC entityType 'other' + SIC 없음 — 폐쇄형 펀드·ETF, SPAC SIC 6770), 늦은 제출(접수 − 매수 > rules.max_lag_days),
          작은 매수(rules.min_value), 공모·사모 참여(코드 P지만 그 거래의 각주·비고가 공모·사모·PIPE를 말하면 장내 매수가 아니다).
          한국 변동일은 장내 매매면 결제일이라 접수일과 비교해 이른 날을 매수일로 쓴다.
  CEO·CFO 가점은 본인 매수가 ceo_tiers 첫 문턱($250K·3억 원) 이상일 때만 준다(소액 동반 매수로 경보 문턱을 넘지 않게, 2026-11-15 첫 실수집 점검).
  강도 = 기본 + 인원·금액·CEO 가점(rules). 시장 배수(rules.market_mult — 미국 1·영국 1.2·유럽 0.8·아시아 0.5, 조사 B 표 F1 [U])를 (강도 − 5)에 곱한다.
저장: 본문을 저장하지 않는다. 이름·직위는 임원·이사·법인 보고자만 남긴다(공개 직업 정보). 임원이 아닌 개인 주요주주는 '주요주주(개인)'로만 적는다.
  주소·생년월일은 읽지 않는다. 상태 radar/state/insider_buys.json(git 제외), 요약 knowledge/models/discovery/insider_latest.json.
금지 연결: 내부자 매수 → 주가 상승이 아니다. 대표 매수 → 실적 개선 확정이 아니다(금지표). 단서는 주장(claim)이 아니다.
사용: py radar/insider_buys.py [--market us,kr] [--days N] [--dry] [--budget-min M] · --show
"""
import io
import json
import re
import sys
import threading
import time
import urllib.parse
import xml.etree.ElementTree as ET
import zipfile
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from pollers import common  # noqa: E402

ROOT = common.ROOT
EFTS = "https://efts.sec.gov/LATEST/search-index"
SUBMISSIONS = "https://data.sec.gov/submissions/"
DART = "https://opendart.fss.or.kr/api"
SOURCE_ID = "src-insider-buys"
STATE = "insider_buys"
LATEST = ROOT / "knowledge" / "models" / "discovery" / "insider_latest.json"
KR_REPORT = "임원ㆍ주요주주특정증권등소유상황보고서"
KEEP_DAYS = 45      # 상태에 남기는 매수 기록(cluster 30일 창 + 늦은 제출 여유)
DONE_DAYS = 10      # 처리한 서류 번호를 기억하는 기간(다시 목록에 나와도 건너뛴다)
ROUTINE_KEEP = 400  # 일상형 판정 캐시(해가 바뀌면 다시 본다)
WORKERS = 3         # SEC 동시 요청 — 전역 간격 0.2초(thirteenf_market)라 합계 초당 5회를 넘지 않는다
DART_GAP = 0.15     # OpenDART 호출 간격(초) — 일 한도 20,000건(개발가이드 오류 020)
MAX_TRIES = 3
EXCLUDE_SIC = {"6770", "6726"}   # SPAC(백지수표 회사 — SPAC 채널 몫)·폐쇄형 펀드
DEF = {"cluster_days": 30, "cluster_min": 2, "routine_years": 3, "routine_codes_us": ["P", "S"], "routine_codes_kr": ["01", "02"], "kr_buy_codes": ["01"],
       "routine_max_docs": 2, "exclude_plan": True, "min_value": {"USD": 10000, "KRW": 10000000},
       "value_tiers": {"USD": [1000000, 5000000], "KRW": [1000000000, 5000000000]}, "ceo_tiers": {"USD": [250000, 1000000], "KRW": [300000000, 1000000000]},
       "tier_bonus": [0.5, 1.0], "cluster_base": 6.5, "cluster_step": 0.5, "cluster_step_cap": 1.5, "ceo_bonus": 0.5, "ceo_base": 5.5, "ceo_cap": 7.0,
       "market_mult": {"us": 1.0, "uk": 1.2, "eu": 0.8, "kr": 0.5, "hk": 0.5, "tw": 0.5}, "max_lag_days": 10, "budget_min": 6, "lookback_days": 3}

CEO_RE = re.compile(r"\bC\.?E\.?O\b|chief\s+executive|principal\s+executive", re.I)
CFO_RE = re.compile(r"\bC\.?F\.?O\b|chief\s+financial|principal\s+financial", re.I)
FORMER_RE = re.compile(r"\bformer\b|\bex-|\bretired\b", re.I)
ENTITY_RE = re.compile(r"\b(?:LLC|L\.?L\.?C|L\.?P|LP|INC|CORP|CORPORATION|COMPANY|LTD|LIMITED|FUNDS?|TRUST|CAPITAL|PARTNERS|HOLDINGS?|MANAGEMENT|ADVIS[EO]RS?"
                       r"|GROUP|PLC|S\.?A|N\.?V|AG|GMBH|FOUNDATION|BANK|INVESTMENTS?|VENTURES?|ASSOCIATES|LLP)\b", re.I)
NOT_EQUITY_RE = re.compile(r"preferred|\bnotes?\b|debenture|\bbonds?\b|warrant|\brights?\b|\boptions?\b|convertible|\bunits?\b(?<!common unit)(?<!common units)", re.I)
# 공모·사모 참여도 코드 P로 적는다(장내 매수가 아니다) — 그 거래가 가리키는 각주·비고에 이런 말이 있으면 뺀다
OFFERING_RE = re.compile(r"underwritten (?:public )?offering|public offering|initial public offering|\bIPO\b|private placement|registered direct|\bPIPE\b"
                         r"|subscription agreement|securities purchase agreement|directed share program|rights offering|at the offering price|concurrent (?:private|offering)", re.I)
KR_CEO_RE = re.compile(r"(?<!부)대표|CEO", re.I)
KR_CFO_RE = re.compile(r"CFO|최고재무|재무\s*(?:담당|총괄|책임|최고)", re.I)
KR_ENTITY_RE = re.compile(r"주식회사|㈜|\(주\)|유한회사|투자|펀드|조합|재단|은행|증권|자산운용|캐피탈|파트너스|홀딩스|그룹|공사|"
                          r"\b(?:Inc|LLC|L\.P|Ltd|Limited|Fund|Capital|Partners|Holdings|Management|Corp|Co)\b", re.I)
_dart_lock = threading.Lock()
_dart_last = [0.0]


def rules():
    c = common.load_yaml("config/discovery_channels.yaml") or {}
    r = ((c.get("channels") or {}).get("insider") or {}).get("rules") or {}
    return {**DEF, **r}


def _f(v):
    try:
        return float(str(v).replace(",", "").strip())
    except (TypeError, ValueError):
        return 0.0


def _b(v):
    return str(v or "").strip().lower() in ("1", "true", "y")


def money(v, ccy):
    """$1.2M · $540K / 12.3억 원 · 3,200만 원(마스터 지시 2026-10-29 금액 단위)"""
    if ccy == "USD":
        import units
        return units.usd(v)
    if abs(v) >= 1e8:
        return f"{v / 1e8:,.1f}억 원"
    return f"{v / 1e4:,.0f}만 원"


# ---------- 미국: SEC Form 4 ----------
def _get(url):
    import thirteenf_market
    return thirteenf_market.get(url)


def busy_13f():
    """13F 시장 수집이 다른 프로세스에서 도는 중이면 True — 두 수집기가 겹치면 SEC 한도(초당 10회)를 넘는다(2026-11-14 429)"""
    import thirteenf_market as tm
    lk = tm.CACHE / "collect.lock"
    try:
        return lk.exists() and float(lk.read_text() or 0) > time.time()
    except (OSError, ValueError):
        return False


def efts_day(d, max_pages=100):
    """[[adsh, 파일명, cik, 접수일, 시도 수]] — 그날 접수한 Form 4 원본(정정 4/A 제외). 같은 접수번호는 XML 문서를 고른다(첨부 EX-24 말고)"""
    out = {}
    for page in range(max_pages):
        p = {"forms": "4", "dateRange": "custom", "startdt": d.isoformat(), "enddt": d.isoformat(), "from": page * 100}
        hits = json.loads(_get(EFTS + "?" + urllib.parse.urlencode(p))).get("hits", {}).get("hits", [])
        for h in hits:
            s = h.get("_source") or {}
            if s.get("form") != "4" or set(s.get("sics") or []) & EXCLUDE_SIC:
                continue
            adsh, _, fn = (h.get("_id") or "").partition(":")
            adsh = s.get("adsh") or adsh
            if not adsh or not s.get("ciks"):
                continue
            cur = out.get(adsh)
            if cur is None or (not cur[1].lower().endswith(".xml") and fn.lower().endswith(".xml")):
                out[adsh] = [adsh, fn, str(int(s["ciks"][0])), s.get("file_date") or d.isoformat(), 0]
        if len(hits) < 100:
            break
    return list(out.values())


def _strip_ns(root):
    for el in root.iter():
        if isinstance(el.tag, str) and "}" in el.tag:
            el.tag = el.tag.split("}", 1)[1]
    return root


def _t(el, path):
    x = el.find(path) if el is not None else None
    return (x.text or "").strip() if x is not None and x.text else ""


def parse_form4(xml_bytes):
    """원문 XML → {issuer_cik, issuer, ticker, period, plan, owners[], txs[]} — 주소는 읽지 않는다"""
    root = _strip_ns(ET.fromstring(xml_bytes))
    iss = root.find("issuer")
    owners = []
    for o in root.findall("reportingOwner"):
        rel = o.find("reportingOwnerRelationship")
        cik = _t(o, "reportingOwnerId/rptOwnerCik")
        owners.append({"cik": str(int(cik)) if cik.isdigit() else cik, "name": _t(o, "reportingOwnerId/rptOwnerName"),
                       "director": _b(_t(rel, "isDirector")), "officer": _b(_t(rel, "isOfficer")), "ten": _b(_t(rel, "isTenPercentOwner")),
                       "other": _b(_t(rel, "isOther")), "title": _t(rel, "officerTitle") or _t(rel, "otherText")})
    notes = {f.get("id"): "".join(f.itertext()) for f in root.iter("footnote")}
    remark_offer = bool(OFFERING_RE.search(_t(root, "remarks")))
    txs = []
    for tx in root.iter("nonDerivativeTransaction"):
        refs = {x.get("id") for x in tx.iter("footnoteId")}
        txs.append({"code": _t(tx, "transactionCoding/transactionCode").upper(), "ad": _t(tx, "transactionAmounts/transactionAcquiredDisposedCode/value").upper(),
                    "date": _t(tx, "transactionDate/value")[:10], "shares": _f(_t(tx, "transactionAmounts/transactionShares/value")),
                    "price": _f(_t(tx, "transactionAmounts/transactionPricePerShare/value")), "title": _t(tx, "securityTitle/value"),
                    "offering": remark_offer or any(OFFERING_RE.search(notes.get(i) or "") for i in refs)})
    ic = _t(iss, "issuerCik")
    tk = (re.split(r"[,;/\s]+", _t(iss, "issuerTradingSymbol").upper().strip()) or [""])[0]   # 'ABC, ABC.WS' 같은 여러 기호는 첫 것
    tk = tk.split(":")[-1]   # 'NYSE:FLG'처럼 거래소를 붙여 쓴 서류(2026-11-15 실측)
    return {"issuer_cik": str(int(ic)) if ic.isdigit() else ic, "issuer": _t(iss, "issuerName"), "ticker": "" if tk in ("NONE", "N/A", "NA") else tk,
            "period": _t(root, "periodOfReport")[:10], "plan": _b(_t(root, "aff10b5One")), "owners": owners, "txs": txs}


def open_market_buys(doc, r):
    """코드 P·취득(A)·보통주(우선주·채권·워런트·권리·옵션 제외) 거래 — 10b5-1 계획 서류는 비우고, 공모·사모 참여(각주·비고)는 뺀다"""
    if r["exclude_plan"] and doc.get("plan"):
        return []
    return [t for t in doc["txs"] if t["code"] == "P" and t["ad"] in ("A", "") and t["shares"] > 0 and not t.get("offering")
            and not NOT_EQUITY_RE.search(t["title"] or "")]


def owner_role(owners):
    """(역할 표시, CEO, CFO, 임원·이사 여부, 표시 이름) — 개인 10% 주주는 이름 대신 '10% 주주(개인)'"""
    titles = " / ".join(o["title"] for o in owners if o.get("title"))
    live = not FORMER_RE.search(titles)
    ceo = live and bool(CEO_RE.search(titles))
    cfo = live and bool(CFO_RE.search(titles))
    exe = any(o["director"] or o["officer"] for o in owners)
    if ceo:
        role = "CEO"
    elif cfo:
        role = "CFO"
    elif any(o["officer"] for o in owners):
        role = "임원"
    elif any(o["director"] for o in owners):
        role = "이사"
    elif any(o["ten"] for o in owners):
        role = "10% 주주"
    else:
        role = "기타"
    o0 = owners[0] if owners else {"name": ""}
    name = o0["name"] if (exe or ENTITY_RE.search(o0["name"] or "")) else ("10% 주주(개인)" if any(o["ten"] for o in owners) else "보고자(개인)")
    return role, ceo, cfo, exe, name, titles[:80]


def _raw_url(cik, adsh, doc):
    """제출 목록의 primaryDocument('xslF345X05/파일.xml') → 원문 XML 경로"""
    return f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{adsh.replace('-', '')}/{doc.split('/')[-1]}"


def _sub_rows(blk):
    n = len(blk.get("form") or [])
    return [(blk["reportDate"][i] or "", blk["filingDate"][i] or "", blk["form"][i], blk["accessionNumber"][i], blk["primaryDocument"][i] or "") for i in range(n)]


def owner_filings(cik, since, cache):
    """보고자 CIK의 [(보고 기간, 접수일, 서류, 접수번호, 문서)] — 최근 묶음이 since까지 닿지 않으면 오래된 묶음(files)도 최대 2개"""
    if cik in cache:
        return cache[cik]
    sub = json.loads(_get(f"{SUBMISSIONS}CIK{str(cik).zfill(10)}.json"))
    rows = _sub_rows(sub.get("filings", {}).get("recent", {}))
    for f in (sub.get("filings", {}).get("files") or [])[:2]:
        if min((r[1] for r in rows if r[1]), default="9999") <= since:
            break
        try:
            rows += _sub_rows(json.loads(_get(SUBMISSIONS + f["name"])))
        except Exception:  # noqa: BLE001 — 오래된 묶음을 못 읽으면 있는 것으로 판정(이력 부족 쪽)
            break
    cache[cik] = rows
    return rows


def routine_us(owner_cik, issuer_cik, trade_date, r, ocache, xcache):
    """CMP 일상형 — {"routine", "hist"(앞선 3년 해마다 Form 4 있음), "same"(같은 달 Form 4가 있는 앞선 해 수, Y−1부터 연속), "verified"(그중 원문에 P·S 확인)}"""
    y, m = int(trade_date[:4]), int(trade_date[5:7])
    n = int(r["routine_years"])
    years = [y - k for k in range(1, n + 1)]
    rows = owner_filings(owner_cik, f"{y - n}-01-01", ocache)
    any_year, same_month = {yy: False for yy in years}, {}
    for rd, _fd, form, adsh, doc in rows:
        if form != "4" or len(rd) < 7:
            continue
        ry, rm = int(rd[:4]), int(rd[5:7])
        if ry in any_year:
            any_year[ry] = True
            if rm == m:
                same_month.setdefault(ry, []).append((adsh, doc))
    same = 0
    for yy in years:
        if not same_month.get(yy):
            break
        same += 1
    out = {"routine": False, "hist": all(any_year.values()), "same": same, "verified": 0}
    if same < n:
        return out
    for yy in years:   # 해마다 같은 달 원문에 같은 회사 P·S가 있어야 일상형
        ok = False
        for adsh, doc in same_month[yy][: int(r["routine_max_docs"])]:
            if adsh not in xcache:
                xcache[adsh] = parse_form4(_get(_raw_url(owner_cik, adsh, doc)))
            d = xcache[adsh]
            if d["issuer_cik"] == issuer_cik and any(t["code"] in r["routine_codes_us"] and t["date"][5:7] == f"{m:02d}" for t in d["txs"]):
                ok = True
                break
        if not ok:
            return out
        out["verified"] += 1
    out["routine"] = True
    return out


def fund_like(cik, cache, today):
    """발행사가 펀드형이면 True — SEC 제출 목록 entityType 'other'이면서 SIC가 없거나 0000(폐쇄형 펀드·ETF), 또는 SIC 6770(SPAC)·6726.
    외국 발행사도 entityType이 'other'라(NOMD·AUDC, 2026-11-15 확인) SIC로 가른다. 캐시 180일"""
    v = cache.get(cik)
    if v is None or (today - date.fromisoformat(v.get("at") or "2000-01-01")).days > 180:
        s = json.loads(_get(f"{SUBMISSIONS}CIK{str(cik).zfill(10)}.json"))
        v = {"type": s.get("entityType") or "", "sic": str(s.get("sic") or ""), "at": today.isoformat()}
        cache[cik] = v
    return (v["type"] == "other" and v["sic"] in ("", "0000")) or v["sic"] in EXCLUDE_SIC


def us_one(item, r, caches):
    """서류 하나 → 매수 기록(없으면 None)"""
    adsh, fn, cik, fdate = item[0], item[1], item[2], item[3]
    if not fn.lower().endswith(".xml"):
        idx = json.loads(_get(f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{adsh.replace('-', '')}/index.json"))
        xs = [x["name"] for x in idx["directory"]["item"] if x["name"].lower().endswith(".xml")]
        if not xs:
            return None
        fn = xs[0]
    doc = parse_form4(_get(f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{adsh.replace('-', '')}/{fn}"))
    caches["x"][adsh] = doc
    if doc.get("plan") and any(t["code"] == "P" for t in doc["txs"]):
        caches["plan"][0] += 1
    buys = open_market_buys(doc, r)
    if not buys or not doc["ticker"] or not doc["owners"]:
        return None
    sh = sum(t["shares"] for t in buys)
    val = sum(t["shares"] * t["price"] for t in buys)
    if val < r["min_value"]["USD"]:
        return None
    if doc["issuer_cik"] and fund_like(doc["issuer_cik"], caches["iss"], caches["today"]):
        caches["fund"][0] += 1
        return None
    role, ceo, cfo, exe, name, title = owner_role(doc["owners"])
    last = max(t["date"] for t in buys if t["date"]) if any(t["date"] for t in buys) else (doc["period"] or fdate)
    last = min(last, fdate) if fdate else last
    key = f"{doc['owners'][0]['cik']}|{doc['issuer_cik']}|{last[:7]}"
    rt = caches["rt"].get(key)
    if rt is None:
        try:
            rt = routine_us(doc["owners"][0]["cik"], doc["issuer_cik"], last, r, caches["o"], caches["x"])
        except Exception as exc:  # noqa: BLE001 — 이력을 못 읽으면 기회형(이력 미확인)으로 두고 표시
            rt = {"routine": False, "hist": None, "same": None, "verified": 0, "error": type(exc).__name__}
        caches["rt"][key] = rt
    return {"m": "us", "id": adsh, "issuer": doc["issuer_cik"], "ticker": doc["ticker"], "name": doc["issuer"], "owners": [o["cik"] for o in doc["owners"]],
            "role": role, "ceo": ceo, "cfo": cfo, "exec": exe, "who": name, "title": title, "date": last, "filed": fdate, "shares": sh,
            "value": round(val, 2), "price": round(val / sh, 4) if sh else 0.0, "ccy": "USD", "routine": bool(rt.get("routine")),
            "rt": {k: rt.get(k) for k in ("hist", "same", "verified", "error") if rt.get(k) is not None},
            "url": f"https://www.sec.gov/Archives/edgar/data/{int(doc['issuer_cik'] or cik)}/{adsh.replace('-', '')}/"}


def us_collect(st, r, t_end, today, days=None, log=print):
    S = st.setdefault("us", {})
    queue, done = S.setdefault("queue", []), S.setdefault("done", {})
    last = S.get("listed_through")
    start = today - timedelta(days=days) if days else (date.fromisoformat(last) - timedelta(days=1) if last else today - timedelta(days=int(r["lookback_days"])))
    have = {q[0] for q in queue} | set(done)
    d = start
    while d <= today and time.time() < t_end:
        for it in efts_day(d):
            if it[0] not in have:
                queue.append(it)
                have.add(it[0])
        S["listed_through"] = max(S.get("listed_through") or "", d.isoformat())
        d += timedelta(days=1)
    caches = {"o": {}, "x": {}, "rt": st.setdefault("routine", {}), "plan": [0], "fund": [0], "iss": st.setdefault("issuers", {}), "today": today}
    out, errs, n = [], [], 0
    with ThreadPoolExecutor(WORKERS) as ex:
        while queue and time.time() < t_end:
            chunk, queue[:] = queue[:30], queue[30:]
            futs = [(it, ex.submit(us_one, it, r, caches)) for it in chunk]
            for it, f in futs:
                try:
                    b = f.result()
                    n += 1
                    done[it[0]] = today.isoformat()
                    if b:
                        out.append(b)
                except Exception as exc:  # noqa: BLE001 — 서류 하나 실패가 회차를 막지 않게(3번까지 다시)
                    it[4] = (it[4] if len(it) > 4 else 0) + 1
                    if it[4] < MAX_TRIES:
                        queue.append(it)
                    else:
                        done[it[0]] = today.isoformat()
                    if len(errs) < 5:
                        errs.append(f"{it[0]}: {type(exc).__name__} {getattr(exc, 'code', '')}".strip())
    S["processed"] = n
    S["plan_excluded"] = caches["plan"][0]
    S["fund_excluded"] = caches["fund"][0]
    return out, errs


# ---------- 한국: OpenDART ----------
def _dart(path, params, key, binary=False, timeout=40):
    with _dart_lock:
        wait = DART_GAP - (time.time() - _dart_last[0])
        if wait > 0:
            time.sleep(wait)
        _dart_last[0] = time.time()
    raw = common.http_get(f"{DART}/{path}", {"crtfc_key": key, **params}, timeout=timeout)
    if binary:
        return raw
    d = json.loads(raw)
    st = d.get("status")
    if st == "013":
        return {"list": [], "total_page": 0}
    if st != "000":
        raise RuntimeError(f"DART {path} status {st}")   # 020 = 요청 한도, 010·011 = 키
    return d


def dart_list(key, start, end, corp_code=None, max_pages=20):
    out = []
    for pg in range(1, max_pages + 1):
        p = {"bgn_de": start.strftime("%Y%m%d"), "end_de": end.strftime("%Y%m%d"), "pblntf_ty": "D", "page_count": "100", "page_no": str(pg)}
        if corp_code:
            p["corp_code"] = corp_code
        d = _dart("list.json", p, key)
        out += d.get("list") or []
        if pg >= int(d.get("total_page") or 1):
            break
    return out


def _kname(s):
    return re.sub(r"\s+", "", str(s or ""))


def _cells(row):
    """원본 표의 한 줄 → [(속성 dict, 글자)] — DART 원본 XML의 TU·TE 칸"""
    out = []
    for tag, attrs, text in re.findall(r"<(TU|TE|TD)\b([^>]*)>(.*?)</\1>", row, re.S):
        out.append((dict(re.findall(r'(\w+)="([^"]*)"', attrs)), re.sub(r"<[^>]+>", "", text).strip()))
    return out


def parse_kr_doc(raw_zip):
    """document.xml(zip) → 세부변동내역 줄 [{code, label, date, kind, chg, price, plan}] — 보고자 인적 사항(생년월일·주소)은 읽지 않는다"""
    try:
        zf = zipfile.ZipFile(io.BytesIO(raw_zip))
    except zipfile.BadZipFile:
        return []
    rows = []
    for n in zf.namelist():
        raw = zf.read(n)
        try:
            t = raw.decode("utf-8")
        except UnicodeDecodeError:
            t = raw.decode("cp949", "ignore")
        for tr in re.findall(r"<TR\b[^>]*>(.*?)</TR>", t, re.S):
            if 'AUNIT="RPT_RSN"' not in tr:
                continue
            cells = _cells(tr)
            g = {}
            for a, txt in cells:
                k = a.get("AUNIT") or a.get("ACODE")
                if k:
                    g[k] = (a.get("AUNITVALUE", ""), txt)
            code, label = g.get("RPT_RSN", ("", ""))
            dt = re.sub(r"\D", "", g.get("MDF_DM", ("", ""))[0] or g.get("MDF_DM", ("", ""))[1])
            plan = g.get("TRD_PLN_RD", ("", ""))
            plan_v = re.sub(r"\D", "", plan[0] or plan[1])
            rows.append({"code": code, "label": label, "date": f"{dt[:4]}-{dt[4:6]}-{dt[6:8]}" if len(dt) >= 8 else "",
                         "kind": g.get("STR_KND", ("", ""))[0] or g.get("STR_KND", ("", ""))[1], "kind_text": g.get("STR_KND", ("", ""))[1],
                         "chg": _f(g.get("MDF_STK_CNT", ("", "0"))[1]), "price": _f(g.get("ACI_AMT2", ("", "0"))[1]), "plan": plan_v[:8] if len(plan_v) >= 8 else ""})
    return rows


def kr_doc(key, rcept_no, cache):
    if rcept_no not in cache:
        cache[rcept_no] = parse_kr_doc(_dart("document.xml", {"rcept_no": rcept_no}, key, binary=True, timeout=60))
    return cache[rcept_no]


def routine_kr(key, corp_code, reporter, trade_date, r, lcache, dcache):
    """같은 보고자가 앞선 3년 해마다 같은 달 소유상황보고서를 내고 원본에 장내매수·매도(01·02)가 있으면 일상형"""
    y, m = int(trade_date[:4]), int(trade_date[5:7])
    n = int(r["routine_years"])
    out = {"routine": False, "same": 0, "verified": 0}
    for k in range(1, n + 1):
        first = date(y - k, m, 1)
        end = (first.replace(day=28) + timedelta(days=4)).replace(day=1) + timedelta(days=6)   # 그달 말 + 7일(월말 매매의 늦은 보고)
        ck = (corp_code, y - k, m)
        if ck not in lcache:
            lcache[ck] = dart_list(key, first, end, corp_code=corp_code, max_pages=5)
        mine = [x for x in lcache[ck] if x.get("report_nm", "").startswith(KR_REPORT) and _kname(x.get("flr_nm")) == _kname(reporter)]
        if not mine:
            return out
        out["same"] += 1
        ok = any(rw["code"] in r["routine_codes_kr"] and rw["date"][5:7] == f"{m:02d}"
                 for x in mine[: int(r["routine_max_docs"])] for rw in kr_doc(key, x["rcept_no"], dcache))
        if not ok:
            return out
        out["verified"] += 1
    out["routine"] = True
    return out


def kr_role(es):
    """elestock 한 줄 → (역할, CEO, CFO, 임원 여부, 표시 이름, 직위)"""
    pos = (es.get("isu_exctv_ofcps") or "").strip()
    pos = "" if pos == "-" else pos
    reg = (es.get("isu_exctv_rgist_at") or "").strip()
    major = (es.get("isu_main_shrholdr") or "").strip()
    exe = bool(pos) or reg in ("등기임원", "비등기임원")
    ceo, cfo = bool(KR_CEO_RE.search(pos)), bool(KR_CFO_RE.search(pos))
    role = "대표이사" if ceo else ("CFO" if cfo else ("임원" if exe else ("주요주주" if major and major != "-" else "기타")))
    who = es.get("repror") or ""
    name = who if (exe or KR_ENTITY_RE.search(who)) else "주요주주(개인)"
    return role, ceo, cfo, exe, name, pos or major


def kr_collect(st, r, key, t_end, today, days=None):
    S = st.setdefault("kr", {})
    queue, done = S.setdefault("queue", []), S.setdefault("done", {})
    last = S.get("listed_through")
    start = today - timedelta(days=days) if days else (date.fromisoformat(last) - timedelta(days=1) if last else today - timedelta(days=int(r["lookback_days"])))
    have = {q["rcept_no"] for q in queue} | set(done)
    for x in dart_list(key, start, today):
        rn = x.get("report_nm") or ""
        if not rn.startswith(KR_REPORT) or "정정" in rn or not (x.get("stock_code") or "").strip() or x["rcept_no"] in have:
            continue
        queue.append({k: x.get(k, "") for k in ("rcept_no", "corp_code", "stock_code", "corp_name", "corp_cls", "rcept_dt", "flr_nm")} | {"tries": 0})
        have.add(x["rcept_no"])
    S["listed_through"] = today.isoformat()
    escache, dcache, lcache = {}, {}, {}
    rt_cache = st.setdefault("routine", {})
    out, errs, n, plan_n = [], [], 0, 0
    keep = []
    for q in list(queue):
        if time.time() > t_end:
            keep.append(q)
            continue
        try:
            if q["corp_code"] not in escache:
                escache[q["corp_code"]] = {e["rcept_no"]: e for e in (_dart("elestock.json", {"corp_code": q["corp_code"]}, key).get("list") or [])}
            es = escache[q["corp_code"]].get(q["rcept_no"])
            if es is None:   # elestock에 아직 안 올라왔다 — 다음 회차에 다시
                q["tries"] += 1
                if q["tries"] < MAX_TRIES * 2:
                    keep.append(q)
                else:
                    done[q["rcept_no"]] = today.isoformat()
                continue
            n += 1
            done[q["rcept_no"]] = today.isoformat()
            if _f(es.get("sp_stock_lmp_irds_cnt")) <= 0:
                continue
            rows = [x for x in kr_doc(key, q["rcept_no"], dcache) if x["code"] in r["kr_buy_codes"] and x["chg"] > 0 and (x["kind"] in ("1", "") or "보통" in x["kind_text"])]
            if r["exclude_plan"] and any(x["plan"] for x in rows):
                plan_n += sum(1 for x in rows if x["plan"])
                rows = [x for x in rows if not x["plan"]]
            if not rows:
                continue
            sh = sum(x["chg"] for x in rows)
            val = sum(x["chg"] * x["price"] for x in rows)
            if val < r["min_value"]["KRW"]:
                continue
            role, ceo, cfo, exe, name, pos = kr_role(es)
            filed = es.get("rcept_dt") or f"{q['rcept_dt'][:4]}-{q['rcept_dt'][4:6]}-{q['rcept_dt'][6:]}"
            # 변동일은 장내 매매면 결제일(원본 각주 '계약결제일')이라 접수일보다 늦을 수 있다 — 둘 중 이른 날을 매수일로
            last_d = min(max((x["date"] for x in rows if x["date"]), default=filed), filed)
            rk = f"kr|{_kname(es.get('repror'))}|{q['corp_code']}|{last_d[:7]}"
            rt = rt_cache.get(rk)
            if rt is None:
                try:
                    rt = routine_kr(key, q["corp_code"], es.get("repror") or q["flr_nm"], last_d, r, lcache, dcache)
                except Exception as exc:  # noqa: BLE001
                    rt = {"routine": False, "same": None, "verified": 0, "error": type(exc).__name__}
                rt_cache[rk] = {**rt, "at": today.isoformat()}
            out.append({"m": "kr", "id": q["rcept_no"], "issuer": q["corp_code"], "ticker": q["stock_code"].strip(), "name": q["corp_name"],
                        "owners": [_kname(es.get("repror") or q["flr_nm"])], "role": role, "ceo": ceo, "cfo": cfo, "exec": exe, "who": name, "title": pos,
                        "date": last_d, "filed": filed, "shares": sh, "value": round(val), "price": round(val / sh) if sh else 0, "ccy": "KRW",
                        "routine": bool(rt.get("routine")), "rt": {k: rt.get(k) for k in ("same", "verified", "error") if rt.get(k) is not None},
                        "board": {"Y": "KOSPI", "K": "KOSDAQ", "N": "KONEX"}.get(q.get("corp_cls"), ""),
                        "url": f"https://dart.fss.or.kr/dsaf001/main.do?rcpNo={q['rcept_no']}"})
        except Exception as exc:  # noqa: BLE001
            q["tries"] += 1
            if q["tries"] < MAX_TRIES:
                keep.append(q)
            else:
                done[q["rcept_no"]] = today.isoformat()
            if len(errs) < 5:
                errs.append(f"{q['rcept_no']}: {type(exc).__name__} {str(exc)[:60]}")
            if "status 020" in str(exc) or "status 01" in str(exc):   # 한도·키 — 이 회차 한국은 멈춘다
                keep += [x for x in queue if x is not q and x not in keep and x["rcept_no"] not in done]
                break
    queue[:] = keep
    S["processed"] = n
    S["plan_excluded"] = plan_n
    return out, errs


# ---------- 판정 ----------
def count_groups(win):
    """서로 다른 매수자 수 — 같은 서류의 공동 보고자(CIK 겹침)는 하나로 묶고, 임원·이사가 없는 묶음(10% 주주)은 모두 합쳐 1명"""
    parent = {}

    def find(x):
        parent.setdefault(x, x)
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for b in win:
        ks = b["owners"] or [b["id"]]
        for k in ks[1:]:
            parent[find(k)] = find(ks[0])
        find(ks[0])
    grp = {}
    for b in win:
        grp.setdefault(find((b["owners"] or [b["id"]])[0]), []).append(b)
    exe = sum(1 for bs in grp.values() if any(x["exec"] for x in bs))
    major = 1 if any(not any(x["exec"] for x in bs) for bs in grp.values()) else 0
    return exe + major


def _tier(v, tiers, bonus):
    b = 0.0
    for lim, add in zip(tiers or [], bonus or []):
        if v >= lim:
            b = add
    return b


def strength(kind, market, n, total, ccy, has_ceo, r):
    if kind == "cluster":
        s = r["cluster_base"] + min(r["cluster_step_cap"], r["cluster_step"] * max(0, n - r["cluster_min"])) + (r["ceo_bonus"] if has_ceo else 0.0) \
            + _tier(total, r["value_tiers"].get(ccy), r["tier_bonus"])
    else:
        s = min(r["ceo_cap"], r["ceo_base"] + _tier(total, r["ceo_tiers"].get(ccy), r["tier_bonus"]))
    s = 5.0 + (s - 5.0) * float((r.get("market_mult") or {}).get(market, 1.0))
    return round(max(0.0, min(10.0, s)), 1)


def lag_days(b):
    """접수일 − 매수일(일) — 미국 Form 4 기한은 2영업일, 한국 소유상황보고는 5영업일"""
    try:
        return (date.fromisoformat(b["filed"]) - date.fromisoformat(b["date"])).days
    except (KeyError, TypeError, ValueError):
        return 0


def evaluate(buys, new_ids, r):
    """새 매수가 들어온 회사마다 cluster(30일 안 2명 이상) 또는 ceo 단서 하나 — 일상형·늦은 제출(rules.max_lag_days 초과)은 세지 않는다"""
    import tvsym
    tab = None
    by = {}
    for b in buys:
        if not b.get("routine") and lag_days(b) <= int(r["max_lag_days"]):
            by.setdefault((b["m"], b["issuer"]), []).append(b)
    rows = []
    for (m, _iss), bs in by.items():
        if not any(b["id"] in new_ids for b in bs):
            continue
        last = max(b["date"] for b in bs)
        lo = (date.fromisoformat(last) - timedelta(days=int(r["cluster_days"]))).isoformat()
        win = sorted((b for b in bs if b["date"] >= lo), key=lambda x: x["date"])
        news = [b for b in win if b["id"] in new_ids]
        if not news:
            continue
        n = count_groups(win)
        total = sum(b["value"] for b in win)
        ccy = win[-1]["ccy"]
        ceo_min = (r["ceo_tiers"].get(ccy) or [0])[0]
        has_ceo = any((b["ceo"] or b["cfo"]) and b["value"] >= ceo_min for b in win)   # CEO·CFO 가점은 본인 매수가 첫 문턱($250K·3억 원) 이상일 때만
        if n >= int(r["cluster_min"]):
            kind, use = "cluster", win
        elif any(b["ceo"] or b["cfo"] for b in news):
            kind, use = "ceo", [b for b in news if b["ceo"] or b["cfo"]]
            total = sum(b["value"] for b in use)
        else:
            continue
        top = use[-1]
        roles = sorted({b["role"] for b in use if b["role"] in ("CEO", "CFO", "대표이사")})
        thin = sum(1 for b in use if (b.get("rt") or {}).get("hist") is False or (b.get("rt") or {}).get("same") == 0)
        if kind == "cluster":
            who = "내부자" if m == "us" else "임원·주요주주"
            sig = f"{who} {n}명 {r['cluster_days']}일 안 장내 매수" + (f"({'·'.join(roles)} 포함)" if roles else "") + f" 합계 {money(total, ccy)} · 기회형(같은 달 3년 반복 거래 아님)"
        else:
            sig = f"{top['role']} 장내 매수 {money(total, ccy)}({top['date'][5:].replace('-', '/')}) · 기회형(같은 달 3년 반복 거래 아님)"
        if m == "us":
            tab = tab if tab is not None else tvsym.sec_table()
            tv = tvsym.us(top["ticker"], tab)
        else:
            tv = f"KRX:{top['ticker']}"
        ex = {"n_buyers": n, "total": round(total, 2), "ccy": ccy, "window_d": int(r["cluster_days"]), "thin_history": thin,
              "buyers": [{"who": b["who"], "role": b["role"], "title": b["title"], "date": b["date"], "value": b["value"], "rt": b.get("rt") or {}} for b in use][-8:],
              "issuer_id": top["issuer"]}
        if m == "kr" and top.get("board"):
            ex["board"] = top["board"]
        rows.append({"channel": "insider", "kind": kind, "market": m, "ticker": top["ticker"], "name": top["name"], "tv": tv,
                     "date": max(b["filed"] for b in use), "strength": strength(kind, m, n, total, ccy, has_ceo, r), "signal": sig,
                     "url": max(use, key=lambda b: b["filed"])["url"], "ccy": ccy, "extra": ex})
    return rows


def _prune(st, today):
    lo = (today - timedelta(days=KEEP_DAYS)).isoformat()
    st["buys"] = [b for b in st.get("buys") or [] if (b.get("filed") or "") >= lo]
    lo_d = (today - timedelta(days=DONE_DAYS)).isoformat()
    for m in ("us", "kr"):
        S = st.get(m) or {}
        S["done"] = {k: v for k, v in (S.get("done") or {}).items() if v >= lo_d}
    lo_r = (today - timedelta(days=ROUTINE_KEEP)).isoformat()
    st["routine"] = {k: v for k, v in (st.get("routine") or {}).items() if (v.get("at") or today.isoformat()) >= lo_r}
    for v in st["routine"].values():
        v.setdefault("at", today.isoformat())


def collect(markets=("us", "kr"), days=None, dry=False, budget_min=None, today=None, log=print):
    """(새 단서, 새 매수 기록, 오류, 요약) — 건강 기록은 시장 단위 실패(목록·키·한도)만 센다. 서류 하나의 실패는 다음 회차에 다시 돈다"""
    r = rules()
    today = today or common.now_kst().date()
    t_end = time.time() + 60 * float(budget_min if budget_min is not None else r["budget_min"])
    st = common.load_state(STATE, {})
    env = common.load_env()
    new_buys, errors, fatal, notes = [], [], [], []
    if "kr" in markets:
        if env.get("DART_API_KEY"):
            try:
                b, e = kr_collect(st, r, env["DART_API_KEY"], t_end, today, days)
                new_buys += b
                errors += [f"kr {x}" for x in e]
                fatal += [f"kr {x}" for x in e if "status 020" in x or "status 01" in x]
            except Exception as exc:  # noqa: BLE001 — 한국 실패가 미국을 막지 않게
                fatal.append(f"kr: {type(exc).__name__} {str(exc)[:100]}")
        else:
            notes.append("kr DART_API_KEY 없음 — 건너뜀")
    if "us" in markets:
        import thirteenf_market
        if not thirteenf_market.ua():
            notes.append("us SEC_USER_AGENT 없음 — 건너뜀")
        elif busy_13f():
            notes.append("us 13F 시장 수집 중 — 다음 회차(SEC 동시 호출 방지)")
        else:
            try:
                b, e = us_collect(st, r, t_end, today, days, log)
                new_buys += b
                errors += [f"us {x}" for x in e]
            except Exception as exc:  # noqa: BLE001
                fatal.append(f"us: {type(exc).__name__} {str(exc)[:100]}")
    errors = fatal + errors
    have = {b["id"] for b in st.get("buys") or []}
    fresh = [b for b in new_buys if b["id"] not in have]
    st.setdefault("buys", []).extend(fresh)
    sys.path.insert(0, str(ROOT / "scripts" / "discovery"))
    rows = evaluate(st["buys"], {b["id"] for b in fresh}, r)
    if dry:
        return rows, fresh, errors, {"notes": notes}
    import leads
    new = leads.add(rows, today=today) if rows else []
    _prune(st, today)
    common.save_state(STATE, st)
    summary = write_latest(st, fresh, new, errors, notes, today)
    common.record_health(SOURCE_ID, not fatal, "; ".join(fatal)[:300] or None)
    return new, fresh, errors, summary


def write_latest(st, fresh, new, errors, notes, today):
    """요약(이름 없이 역할만) — 파이프라인 건강 확인(config/pipeline_health.yaml files)과 Ten-bagger 회차가 읽는다"""
    buys = sorted(st.get("buys") or [], key=lambda b: (b.get("filed") or "", b.get("date") or ""), reverse=True)
    summary = {"as_of": common.iso(common.now_kst()), "note": "기회형 내부자 장내 매수(미 Form 4 P·한 소유보고 01) — 단서는 매수 권유가 아니다",
               "markets": {m: {k: (st.get(m) or {}).get(k) for k in ("listed_through", "processed", "plan_excluded", "fund_excluded")}
                           | {"queue": len((st.get(m) or {}).get("queue") or [])} for m in ("us", "kr")},
               "buys_45d": len(buys), "routine_45d": sum(1 for b in buys if b.get("routine")), "new_buys": len(fresh),
               "new_leads": [{"lead_id": x["lead_id"], "kind": x["kind"], "market": x["market"], "ticker": x["ticker"], "name": x["name"], "strength": x["strength"],
                              "signal": x["signal"]} for x in new],
               "recent": [{"m": b["m"], "ticker": b["ticker"], "name": b["name"], "role": b["role"], "value": b["value"], "ccy": b["ccy"], "date": b["date"],
                           "filed": b["filed"], "routine": b.get("routine")} for b in buys[:40]],
               "errors": errors[:10], "notes": notes}
    LATEST.parent.mkdir(parents=True, exist_ok=True)
    LATEST.write_text(json.dumps(summary, ensure_ascii=False, indent=1), encoding="utf-8")
    return summary


def run():
    """run_hourly용 — (요약, 새 단서 수). 새 단서가 있으면 채널 선별을 다시 돈다"""
    new, fresh, errors, summary = collect()
    if new:
        sys.path.insert(0, str(ROOT / "scripts" / "discovery"))
        import channels
        channels.run()
    mk = summary.get("markets") or {}
    return (f"새 매수 {len(fresh)} · 새 단서 {len(new)} · 미국 처리 {(mk.get('us') or {}).get('processed') or 0}(대기 {(mk.get('us') or {}).get('queue', 0)}) · "
            f"한국 처리 {(mk.get('kr') or {}).get('processed') or 0}" + (f" · {'; '.join(summary.get('notes') or [])}" if summary.get("notes") else "")
            + (f" · 오류 {len(errors)}" if errors else "")), len(new)


def main(argv):
    sys.stdout.reconfigure(encoding="utf-8")
    if "--show" in argv:
        d = json.loads(LATEST.read_text(encoding="utf-8")) if LATEST.exists() else {}
        print(json.dumps({k: d.get(k) for k in ("as_of", "markets", "buys_45d", "routine_45d", "new_leads", "errors", "notes")}, ensure_ascii=False, indent=1))
        return 0
    mk = tuple(argv[argv.index("--market") + 1].split(",")) if "--market" in argv else ("us", "kr")
    days = int(argv[argv.index("--days") + 1]) if "--days" in argv else None
    bm = float(argv[argv.index("--budget-min") + 1]) if "--budget-min" in argv else None
    if "--dry" in argv:
        rows, fresh, errors, _ = collect(mk, days, dry=True, budget_min=bm)
        for b in fresh:
            print(f"{b['filed']} {b['m']} {b['ticker']} {b['name'][:28]} · {b['role']} {money(b['value'], b['ccy'])} {b['date']} · 일상형 {b['routine']} {b.get('rt')}")
        for x in rows:
            print(f"단서 {x['kind']} {x['market']} {x['ticker']} {x['strength']} — {x['signal']}")
        print("오류:", errors)
        return 0
    new, fresh, errors, summary = collect(mk, days, budget_min=bm)
    if new:   # run()과 같게 — 새 단서가 있으면 채널 선별(경보 파일)을 다시
        sys.path.insert(0, str(ROOT / "scripts" / "discovery"))
        import channels
        channels.run()
    print(f"[내부자 매수] 새 매수 {len(fresh)} · 새 단서 {len(new)} · {json.dumps(summary.get('markets'), ensure_ascii=False)}" + (f" · 오류 {'; '.join(errors)}" if errors else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
