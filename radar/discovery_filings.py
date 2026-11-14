"""발굴 채널 공시 수집 — 행동주의·구루 지분·위임장 대결·공개매수·분할·자사주·밸류업을 법정 공시에서 하루 단위로 (마스터 지시 2026-11-15
"행동주의 표적, … 구루 포지션을 따라가는 전략 등 다양한 종목 발굴 채널", 설계 knowledge/methods/discovery_engine.md)

결정론(모델 없음, run_hourly 60분). 본문은 저장하지 않는다 — 서류 종류·제출인·대상 회사·날짜·링크, 13D는 목적(Item 4) 문장에서 행동주의 어구 수만.
  미국 SEC EDGAR 전문 검색(efts, 프로젝트 User-Agent·초당 5회 이하):
    SCHEDULE 13D(원본) — 제출인이 행동주의 명단(config/activists.yaml)이면 activist/entry, 구루 명단(config/gurus.yaml)이면 guru/stake,
      명단 밖이면 목적 문장의 행동주의 어구(이사 지명·경영진과 논의·전략적 대안·매각 등, 보일러플레이트 (a)~(j) 목록 제외)가 문턱 이상일 때만 activist/entry
    SCHEDULE 13D/A — 명단 행동주의의 목적 변경(합의·지명·위임장)만 activist/escalation
    SCHEDULE 13G(원본) — 구루 명단만 guru/stake(5% 이상 수동 보유 — 13F보다 빠르다)
    DFAN14A(반대 주주 제출)·PREC14A·DEFC14A — activist/contest
    SC TO-T(제3자 공개매수 원본) — special/tender · 10-12B(분할 등록 원본) — special/spinoff
  한국 OpenDART list.json(공시 유형 D 지분·B 주요사항·I 거래소, 기간 3개월 이내 전 회사):
    주식등의대량보유상황보고서(일반) — 행동주의 명단이면 activist/entry, 운용사·사모펀드 제출이면 activist/entry(약함 — 기관의 일반 서식 = 경영권 영향 목적),
      투자조합·개인이면 special/control(경영권 변동 단서, 적신호 표시 — 무자본 M&A 유형 주의)
    의결권대리행사권유참고서류 — 제출인 ≠ 회사이면 activist/contest
    공개매수신고서 — special/tender · 회사분할결정 — special/spinoff · 주식소각결정 — special/cancel · 자기주식취득결정(신탁 포함) — special/buyback
    기업가치제고계획 — special/valueup · 전환사채·신주인수권부사채·유상증자 결정 — 국장 테마 적신호 장부(knowledge/models/discovery/kr_flags.json)
  일본 EDINET API v2(키 EDINET_API_KEY 대기 — 없으면 건너뜀): 大量保有報告書(350) 제출인이 명단이면 activist/guru, 公開買付届出書(240) special/tender
단서 → scripts/discovery/leads.py(채널 장부). 처음 켠 날은 지난 lookback_days만 본다. 상태 radar/state/discovery_filings.json.
금지 연결: 5% 신고 → 경영권 분쟁 확정이 아니다, 공개매수 신고 → 성사 확정이 아니다, 자사주 취득 결정 → 소각이 아니다(별도 결정).
  대만 TWSE·TPEx 重大訊息 第35款(소각 목적 자사주 결의) · 일본 JPX 자본비용 공시 갱신(월간)
  넣지 않은 것: 홍콩 HKEXnews(HKEX 이용약관 5조가 서면 허락 없는 자동 수집·스크래핑 금지 — 조사 C), 영국 인수위원회 공시표(robots.txt가 ClaudeBot 전면 금지),
  영국 FCA NSM(사이트 약관 4.8(iii) 서면 동의 필요), 독일 BaFin 포털·TDnet·옛 MOPS(robots 전면 금지) — 2026-11-15 확인
  · 구루 논지 특수 상황(config/special_situations.yaml — 패니·프레디형)의 촉매 서류 · 한국 시장조치 적신호(I003)·KRX 투자경고(내부 표지)
사용: py radar/discovery_filings.py [--days N] [--dry] [--market us,kr,jp,tw,jpx,thesis]
"""
import json
import re
import sys
import time
import urllib.parse
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from pollers import common  # noqa: E402

ROOT = common.ROOT
EFTS = "https://efts.sec.gov/LATEST/search-index"
DART_LIST = "https://opendart.fss.or.kr/api/list.json"
EDINET = "https://api.edinet-fsa.go.jp/api/v2/documents.json"
FLAGS = ROOT / "knowledge" / "models" / "discovery" / "kr_flags.json"
SOURCE_ID = "src-discovery-filings"
NAME_RE = re.compile(r"^(.*?)\s*(?:\(([^)]*)\))?\s*\(CIK (\d+)\)")
# 목적 문장의 행동주의 어구 — 보일러플레이트 (a)~(j) 목록을 지운 뒤 센다
ACT_TERMS = [r"\bnominat", r"board (?:seat|representation|composition)", r"engag(?:e|ing|ement) (?:with|in discussions)", r"discussions? with (?:the )?(?:issuer|management|board|company)",
             r"strategic alternatives", r"sale of the (?:issuer|company)", r"undervalued", r"maximi[sz]e (?:shareholder|stockholder) value", r"letter to the board",
             r"special meeting", r"proxy (?:contest|solicitation)", r"cooperation agreement", r"settlement agreement", r"capital allocation", r"spin[- ]?off",
             r"buyback|repurchase program", r"change (?:in|of) (?:the )?(?:management|ceo)", r"withhold", r"shareholder proposal"]
BOILER = re.compile(r"\(a\)[^.]{0,200}?(?:acquisition|the acquisition by any person).*?\(j\)[^.]*\.", re.I | re.S)
KR_INST = re.compile(r"자산운용|투자자문|파트너스|캐피탈|인베스트먼트|사모|PEF|펀드|Fund|Capital|Management|Partners|Advisors|L\.P\.|LLC|Ltd", re.I)
KR_PARTNERSHIP = re.compile(r"조합|투자조합")
RED_I = re.compile(r"상장폐지|관리종목|불성실공시법인지정|실질심사|매매거래정지")   # 시장조치 적신호(조사 F 적신호 목록)
RED_I_SKIP = re.compile(r"해제|액면|병합|분할|전자등록|변경상장|배당락|미지정")
KRX_WARN = "https://open.krx.co.kr/contents/OPN/99/OPN99000001.jspx"   # 투자경고 지정 목록 — robots 'Allow: /'(조사 F 2026-11-15), 거래소 법적고지상 재배포 금지 → 내부 표지만
TW_APIS = {"twse": "https://openapi.twse.com.tw/v1/opendata/t187ap04_L", "tpex": "https://www.tpex.org.tw/openapi/v1/mopsfin_t187ap04_O"}
JPX_LIST = "https://www.jpx.co.jp/equities/follow-up/jr4eth0000004vj2-att/list.xlsx"   # 자본비용·주가 의식 경영 공시 기업 명단(매월 15일 전후, robots 허용 — 조사 H)


def _ua():
    from pollers import sec_filings
    return sec_filings._ua()


def _norm(s):
    return re.sub(r"[\s.,()㈜\-]|주식회사|\(주\)|INC|CORP|CO|LTD|LLC|LP|L\.P\.", "", str(s or "").upper())


def rosters():
    """(미국 행동주의 {CIK: 행}, 미국 구루 {CIK: 행}, 한국 [(행, 정규식)], 일본 [(행, 정규식)], 규칙)
    구루 명단은 ciks: [{cik, from, to}] 형식(config/gurus.yaml), 행동주의는 cik + filer_ciks. 행동주의와 구루에 같은 CIK가 있으면 행동주의로 본다(13D가 목적)"""
    act = common.load_yaml("config/activists.yaml") or {}
    gur = common.load_yaml("config/gurus.yaml") or {}
    us_gur = {}
    for g in gur.get("gurus") or []:
        if g.get("active") is False:
            continue
        for c in [x.get("cik") for x in g.get("ciks") or []] + list(g.get("filer_ciks") or []) + ([g["cik"]] if g.get("cik") else []):
            if c:
                us_gur[str(int(c))] = {**g, "tier": "A" if g.get("tier", "A") == "A" else g.get("tier")}
    us_act = {}
    for a in act.get("us") or []:
        for c in [a.get("cik")] + list(a.get("filer_ciks") or []):
            if c:
                us_act[str(int(c))] = a
    kr = [(a, re.compile(a["pattern"])) for a in act.get("kr") or [] if a.get("pattern")]
    jp = [(a, re.compile(a["pattern"])) for a in (act.get("jp") or []) + (gur.get("jp") or []) if a.get("pattern")]
    return us_act, us_gur, kr, jp, act.get("rules") or {}


def kr_name(s):
    """DART 제출인 일치용 — 공백 제거(DART가 외국 이름의 공백을 뺀다)"""
    return re.sub(r"\s+", "", str(s or ""))


def jp_name(s):
    """EDINET 제출인 일치용 — NFKC(전각 영문·기호 → 반각)"""
    import unicodedata
    return unicodedata.normalize("NFKC", str(s or ""))


# ---------- 미국 ----------
def efts(form, start, end, max_pages=10):
    out, seen = [], set()
    for page in range(max_pages):
        p = {"forms": form, "dateRange": "custom", "startdt": start.isoformat(), "enddt": end.isoformat(), "from": page * 100}
        d = json.loads(_get(EFTS + "?" + urllib.parse.urlencode(p)))
        hs = d.get("hits", {}).get("hits", [])
        for h in hs:
            s = h["_source"]
            if s.get("adsh") in seen:
                continue
            seen.add(s.get("adsh"))
            s["_file"] = (h.get("_id") or ":").split(":", 1)[1]
            out.append(s)
        if len(hs) < 100:
            break
    return out


def _get(url):
    import thirteenf_market
    return thirteenf_market.get(url)


def parties(s):
    """첫 표시 이름 = 대상 회사(발행사), 나머지 = 제출인(efts 표시 순서, 2026-11-15 13D·TO-T·DFAN14A 표본으로 확인)"""
    ps = []
    for dn in s.get("display_names") or []:
        m = NAME_RE.match(dn)
        if m:
            ps.append({"name": m.group(1).strip(), "tickers": (m.group(2) or "").replace(" ", "").split(",") if m.group(2) else [], "cik": str(int(m.group(3)))})
    return (ps[0] if ps else None), ps[1:]


def purpose_score(xml_text):
    m = re.search(r"<transactionPurpose>(.*?)</transactionPurpose>", xml_text or "", re.S | re.I)
    t = BOILER.sub(" ", common.strip_tags(m.group(1)) if m else "")
    return sum(1 for p in ACT_TERMS if re.search(p, t, re.I)), t[:400]


def pct_of(xml_text):
    v = re.findall(r"<percentOfClass>([\d.]+)</percentOfClass>", xml_text or "")
    try:
        return max(float(x) for x in v) if v else None
    except ValueError:
        return None


def _url(s, cik):
    return f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{s['adsh'].replace('-', '')}/"


def us_rows(start, end, rules, us_act, us_gur, fetch_xml=True):
    import importlib
    sys.path.insert(0, str(ROOT / "scripts" / "discovery"))
    tvsym = importlib.import_module("tvsym")
    tab = tvsym.sec_table()
    rows, notes = [], []
    min_terms = int(rules.get("us_min_terms", 2))

    def base(subj, kind, ch, strength, signal, s, extra):
        tk = (subj.get("tickers") or [""])[0]
        if not tk:
            return None
        return {"channel": ch, "kind": kind, "market": "us", "ticker": tk, "name": subj["name"], "tv": tvsym.us(tk, tab), "date": s.get("file_date"),
                "strength": strength, "signal": signal, "url": _url(s, subj["cik"]), "extra": extra}

    for s in efts("SCHEDULE 13D", start, end):
        subj, filers = parties(s)
        if not subj:
            continue
        form = s.get("form") or ""
        act = next((us_act[f["cik"]] for f in filers if f["cik"] in us_act), None)
        gur = next((us_gur[f["cik"]] for f in filers if f["cik"] in us_gur), None)
        who = ", ".join(f["name"] for f in filers)[:80]
        if form == "SCHEDULE 13D/A" and not act:
            continue
        xml, n_terms, pur, pct = "", 0, "", None
        if fetch_xml and (form == "SCHEDULE 13D" or act):
            try:
                xml = _get(_url(s, filers[0]["cik"] if filers else subj["cik"]) + s["_file"]).decode("utf-8", "ignore")
            except Exception:  # noqa: BLE001 — 목적 문장을 못 읽으면 명단 일치만으로 판단
                try:
                    xml = _get(_url(s, subj["cik"]) + s["_file"]).decode("utf-8", "ignore")
                except Exception:  # noqa: BLE001
                    xml = ""
            n_terms, pur = purpose_score(xml)
            pct = pct_of(xml)
        ex = {"form": form, "filer": who, "pct": pct, "terms": n_terms}
        if form == "SCHEDULE 13D/A":
            if n_terms >= min_terms:
                r = base(subj, "escalation", "activist", 6.5 + (0.5 if act.get("tier") == "A" else 0), f"{act['name']} 13D 정정 — 목적 어구 {n_terms}개", s, ex)
                rows.append(r) if r else None
            continue
        if act:
            r = base(subj, "entry", "activist", 7.0 + (1.0 if act.get("tier") == "A" else 0) + min(1.0, n_terms * 0.25),
                     f"{act['name']} 13D 신규" + (f" {pct:.1f}%" if pct else "") + (f" · 목적 어구 {n_terms}개" if n_terms else ""), s, ex)
        elif gur:
            r = base(subj, "stake", "guru", 6.5 + (1.0 if gur.get("tier") == "A" else 0), f"{gur['name']} 13D 신규" + (f" {pct:.1f}%" if pct else ""), s, ex)
        elif n_terms >= min_terms:
            r = base(subj, "entry", "activist", min(7.0, 4.5 + 0.5 * n_terms), f"{who} 13D 신규(명단 밖)" + (f" {pct:.1f}%" if pct else "") + f" · 목적 어구 {n_terms}개", s, ex)
        else:
            r = None
        if r:
            rows.append(r)
    for s in efts("SCHEDULE 13G", start, end):
        if s.get("form") != "SCHEDULE 13G":
            continue
        subj, filers = parties(s)
        gur = next((us_gur[f["cik"]] for f in filers if f["cik"] in us_gur), None)
        if subj and gur:
            r = base(subj, "stake", "guru", 5.5 + (1.0 if gur.get("tier") == "A" else 0), f"{gur['name']} 13G 신규(5% 이상 수동 보유)", s, {"form": "SCHEDULE 13G"})
            rows.append(r) if r else None
    for form in ("DFAN14A", "PREC14A", "DEFC14A"):
        for s in efts(form, start, end):
            subj, filers = parties(s)
            if not subj or (form == "DFAN14A" and not filers):
                continue
            act = next((us_act[f["cik"]] for f in filers if f["cik"] in us_act), None)
            who = ", ".join(f["name"] for f in filers)[:80] or "회사"
            r = base(subj, "contest", "activist", 6.5 + (1.0 if act else 0), f"위임장 대결 서류 {form} — 제출 {who}", s, {"form": form, "filer": who})
            rows.append(r) if r else None
    for s in efts("SC TO-T", start, end):
        if s.get("form") != "SC TO-T":
            continue
        subj, filers = parties(s)
        if subj:
            who = ", ".join(f["name"] for f in filers)[:80]
            r = base(subj, "tender", "special", 6.0, f"제3자 공개매수 개시 — 매수자 {who}", s, {"form": "SC TO-T", "bidder": who})
            rows.append(r) if r else None
    for s in efts("SC 13E3", start, end):   # 계열사 상장폐지 거래(going private) — 소수주주 매수, 프리미엄이 작을 수 있다
        if s.get("form") != "SC 13E3":
            continue
        subj, filers = parties(s)
        if subj:
            who = ", ".join(f["name"] for f in filers)[:80]
            r = base(subj, "tender", "special", 5.5, f"상장폐지 거래(13E3) — 제출 {who}", s, {"form": "SC 13E3"})
            rows.append(r) if r else None
    for s in efts("10-12B", start, end):
        if s.get("form") != "10-12B":
            continue
        subj, _ = parties(s)
        if subj:
            r = {"channel": "special", "kind": "spinoff", "market": "us", "ticker": (subj.get("tickers") or [""])[0], "name": subj["name"],
                 "tv": tvsym.us((subj.get("tickers") or [""])[0], tab) if subj.get("tickers") else "", "date": s.get("file_date"), "strength": 5.5,
                 "signal": "분할 신설 회사 등록(Form 10-12B) — 분할 뒤 지수 기계적 매도 구간 관찰", "url": _url(s, subj["cik"]), "extra": {"form": "10-12B"}}
            rows.append(r)
    return [r for r in rows if r], notes


# ---------- 한국 ----------
def dart_list(key, start, end, ty, max_pages=20):
    out = []
    for pg in range(1, max_pages + 1):
        d = json.loads(common.http_get(DART_LIST, {"crtfc_key": key, "bgn_de": start.strftime("%Y%m%d"), "end_de": end.strftime("%Y%m%d"),
                                                   "pblntf_ty": ty, "page_count": "100", "page_no": str(pg)}, timeout=40))
        if d.get("status") == "013":
            break
        if d.get("status") != "000":
            raise RuntimeError(f"DART status {d.get('status')}")
        out += d.get("list") or []
        if pg >= int(d.get("total_page") or 1):
            break
        time.sleep(0.2)
    return out


def kr_rows(key, start, end, kr_act):
    rows, flags = [], {}

    def row(d, ch, kind, strength, signal, ex=None):
        code = (d.get("stock_code") or "").strip()
        if not code:
            return None
        dt = d["rcept_dt"]
        return {"channel": ch, "kind": kind, "market": "kr", "ticker": code, "name": d["corp_name"], "tv": f"KRX:{code}",
                "date": f"{dt[:4]}-{dt[4:6]}-{dt[6:]}", "strength": strength, "signal": signal,
                "url": f"https://dart.fss.or.kr/dsaf001/main.do?rcpNo={d['rcept_no']}",
                "extra": {"report": d["report_nm"].strip(), "filer": d.get("flr_nm", ""), "board": {"Y": "KOSPI", "K": "KOSDAQ", "N": "KONEX"}.get(d.get("corp_cls"), "")} | (ex or {})}

    for d in dart_list(key, start, end, "D"):
        rn, flr, corp = d["report_nm"].replace("[기재정정]", "").strip(), d.get("flr_nm", ""), d.get("corp_name", "")
        if rn.startswith("주식등의대량보유상황보고서(일반)") and "정정" not in d["report_nm"]:
            hit = next((a for a, pat in kr_act if pat.search(kr_name(flr))), None)
            if hit:
                rows.append(row(d, "activist", "entry", 7.5 + (0.5 if hit.get("tier") == "A" else 0), f"{hit['name']} 5% 보고(일반 서식)"))
            elif KR_PARTNERSHIP.search(flr):
                rows.append(row(d, "special", "control", 3.5, f"투자조합 5% 보고(일반 서식) — 제출 {flr} · 경영권 변동 단서(적신호: 무자본 M&A 유형 확인)", {"red_flag": True}))
            elif KR_INST.search(flr) and _norm(flr) != _norm(corp):
                rows.append(row(d, "activist", "entry", 5.0, f"기관 5% 보고(일반 서식 = 경영권 영향 목적 가능) — 제출 {flr}"))
        elif rn.startswith("의결권대리행사권유참고서류") and _norm(flr) and _norm(flr) != _norm(corp):
            hit = next((a for a, pat in kr_act if pat.search(kr_name(flr))), None)
            rows.append(row(d, "activist", "contest", 7.0 + (1.0 if hit else 0), f"주주 측 의결권 권유 — 제출 {flr}"))
        elif rn.startswith("공개매수신고서"):
            rows.append(row(d, "special", "tender", 6.0, f"공개매수 신고 — 매수자 {flr}"))
    i_list = dart_list(key, start, end, "I")
    for d in i_list:   # 시장조치/안내(I003 포함) — 상장폐지·관리종목 우려·불성실공시·실질심사·거래정지 = 국장 적신호(조사 F)
        rn = re.sub(r"\s+", " ", d["report_nm"])
        code = (d.get("stock_code") or "").strip()
        if code and RED_I.search(rn) and not RED_I_SKIP.search(rn):
            dt = d["rcept_dt"]
            flags.setdefault(code, []).append({"date": f"{dt[:4]}-{dt[4:6]}-{dt[6:]}", "kind": "시장조치: " + rn[:40], "rcept_no": d["rcept_no"], "severe": True})
    for d in dart_list(key, start, end, "B") + i_list:
        rn = d["report_nm"]
        if "정정" in rn:
            continue
        code = (d.get("stock_code") or "").strip()
        if "회사분할결정" in rn:
            rows.append(row(d, "special", "spinoff", 5.0, "회사 분할 결정 — 인적·물적 분할 여부 원문 확인(물적분할은 소액주주 불리 가능)"))
        elif "주식소각결정" in rn:
            rows.append(row(d, "special", "cancel", 5.0, "자기주식 소각 결정"))
        elif "자기주식취득결정" in rn or "자기주식취득신탁계약체결결정" in rn:
            rows.append(row(d, "special", "buyback", 4.0, "자기주식 취득 결정" + ("(신탁)" if "신탁" in rn else "") + " — 소각은 별도 결정"))
        elif "기업가치제고계획" in rn:
            rows.append(row(d, "special", "valueup", 4.0, "기업가치 제고 계획 공시"))
        elif code and any(k in rn for k in ("전환사채권발행결정", "신주인수권부사채권발행결정", "유상증자결정", "교환사채권발행결정")):
            dt = d["rcept_dt"]
            flags.setdefault(code, []).append({"date": f"{dt[:4]}-{dt[4:6]}-{dt[6:]}", "kind": re.sub(r"주요사항보고서|\(|\)|결정", "", rn).strip(), "rcept_no": d["rcept_no"]})
    return [r for r in rows if r], flags


def krx_warnings(start, end):
    """{코드: [{date, kind: '투자경고'}]} — 내부 표지(국장 테마 과열·적신호)로만 쓴다. 목록을 다시 싣지 않는다(거래소 법적고지)"""
    import urllib.request
    body = urllib.parse.urlencode({"bld": "MKD/10/1002/10020406/mkd10020406", "ind_tp": "ALL", "period_strt_dd": start.strftime("%Y%m%d"),
                                   "period_end_dd": end.strftime("%Y%m%d")}).encode()
    req = urllib.request.Request(KRX_WARN, data=body, headers={"User-Agent": common.UA, "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8"})
    d = json.loads(urllib.request.urlopen(req, timeout=30).read().decode("utf-8", "ignore"))
    out = {}
    for r in d.get("block1") or []:
        code = str(r.get("isu_cd") or "").strip()
        dd = str(r.get("design_dd") or "").replace("/", "-")
        if code and dd:
            out.setdefault(code, []).append({"date": dd, "kind": "투자경고", "rcept_no": f"krx-warn-{code}-{dd}", "severe": False, "alert": True})
    return out


def save_flags(flags, today, keep_days=365):
    old = json.loads(FLAGS.read_text(encoding="utf-8")) if FLAGS.exists() else {"rows": {}}
    rows = old.get("rows") or {}
    lo = (today - timedelta(days=keep_days)).isoformat()
    for code, fs in flags.items():
        have = {f["rcept_no"] for f in rows.get(code, [])}
        rows[code] = [f for f in rows.get(code, []) + [f for f in fs if f["rcept_no"] not in have] if f["date"] >= lo]
    FLAGS.parent.mkdir(parents=True, exist_ok=True)
    FLAGS.write_text(json.dumps({"as_of": today.isoformat(), "note": "전환사채·신주인수권부사채·교환사채·유상증자 결정(OpenDART) — 국장 테마 적신호", "rows": rows},
                                ensure_ascii=False, indent=0), encoding="utf-8")


# ---------- 대만 ----------
def tw_rows():
    """TWSE·TPEx 每日重大訊息(공식 OpenAPI, 그날 것만 — 매 회차 받아 장부가 쌓는다): 第35款 이사회 자사주 매입 결의 중 목적이 '維護公司信用及股東權益'(소각 전제)만.
    직원 양도 목적(轉讓股份予員工)·집행 완료 공고는 뺀다(조사 H — 목적이 소각인지가 관건)"""
    rows = []
    for market, api in TW_APIS.items():
        try:
            data = json.loads(common.http_get(api, timeout=30))
        except Exception:  # noqa: BLE001 — 한쪽이 막혀도 다른 쪽은 낸다
            continue
        for r in data:
            clause = str(r.get("符合條款") or "")
            subj = " ".join(str(r.get("主旨 ") or r.get("主旨") or "").split())
            desc = str(r.get("說明") or "")
            code = str(r.get("公司代號") or r.get("SecuritiesCompanyCode") or "").strip()
            if "第35款" not in clause or "決議" not in subj or "買回" not in subj or not code:
                continue
            if "維護公司信用及股東權益" not in desc:
                continue
            d = str(r.get("發言日期") or "")
            day = f"{int(d[:3]) + 1911}-{d[3:5]}-{d[5:7]}" if len(d) == 7 else common.now_kst().date().isoformat()
            amt = re.search(r"買回股份總金額上限[^:：]*[:：]\s*([\d,]+)", desc)
            rows.append({"channel": "special", "kind": "buyback", "market": "tw", "ticker": code, "name": r.get("公司名稱") or r.get("CompanyName") or code,
                         "tv": f"{'TWSE' if market == 'twse' else 'TPEX'}:{code}", "date": day, "strength": 5.0,
                         "signal": f"자사주 매입 결의(목적: 회사 신용·주주 권익 유지 = 소각 전제)" + (f" · 상한 {amt.group(1)} 대만달러" if amt else ""),
                         "url": f"{api}#{code}-{d}", "extra": {"clause": "第35款", "subject": subj[:80]}})
    return rows


# ---------- 일본 JPX 자본비용 공시 명단 ----------
def _xl_date(v):
    """엑셀 일련번호('46196') 또는 'YYYY/MM/DD' → 'YYYY-MM-DD'(없으면 '')"""
    v = str(v or "").strip()
    if not v:
        return ""
    if v.replace(".", "", 1).isdigit():
        return (date(1899, 12, 30) + timedelta(days=int(float(v)))).isoformat()
    m = re.match(r"(\d{4})[/.-](\d{1,2})[/.-](\d{1,2})", v)
    return f"{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3)):02d}" if m else ""


def jpx_rows(st, today, every_days=5):
    """JPX 월간 명단(xlsx, 2026-11-15 형식 확인: 8번째 줄 머리 — 칸 이름에 줄바꿈, 갱신일은 엑셀 일련번호).
    최신 시트(○年○月末時点)에서 '開示内容のアップデート日'이 그 달인 기업 = 공시 갱신(조사 H 신호 — 첫 공시는 프라임 94%가 이미 해 정보가 낮다),
    '前月からの開示状況の変更'이 있는 기업 = 상태 변화(첫 공시 등). 시트 이름이 바뀐 달만 처리한다.
    1년 넘게 갱신 없는 프라임 공시 기업은 행동주의 표적 참고 명단(knowledge/models/discovery/jpx_stale.json — 그 자체로 신호 아님)"""
    last = st.get("jpx", {})
    if last.get("checked") and (today - date.fromisoformat(last["checked"])).days < every_days:
        return []
    import consumer_macro as cm
    sheets = cm.xlsx_sheets(common.http_get(JPX_LIST, timeout=90))
    name = next((n for n in sheets if n.startswith("開示企業一覧")), None)
    st["jpx"] = {**last, "checked": today.isoformat()}
    if not name or name.strip() == (last.get("sheet") or "").strip():
        return []
    rows_x = sheets[name]
    norm = lambda c: re.sub(r"\s+", "", str(c or ""))
    hdr_i = next((i for i, r in enumerate(rows_x[:30]) if r and any("証券コード" in norm(c) for c in r)), None)
    if hdr_i is None:
        raise RuntimeError("JPX 명단 머리행을 못 찾음 — 형식 변경")
    hdr = [norm(c) for c in rows_x[hdr_i]]
    sub = [norm(c) for c in (rows_x[hdr_i + 1] if hdr_i + 1 < len(rows_x) else [])]
    col = lambda key, row=hdr: next((i for i, h in enumerate(row) if key in h), None)
    ci, ni, ui, mi, si = col("証券コード"), col("銘柄名"), col("アップデート"), col("市場区分"), col("開示状況")
    chg = col("前月からの開示状況の変更", sub)
    m = re.search(r"(\d{4})年(\d{1,2})月末", name)
    if not m or ci is None:
        raise RuntimeError("JPX 명단 시트 이름·칸 해석 실패")
    y, mo = int(m.group(1)), int(m.group(2))
    ym = f"{y}-{mo:02d}"
    cutoff = f"{y - 1}-{mo:02d}"
    cell = lambda r, i: (r[i] if i is not None and i < len(r) else None)
    rows, stale = [], []
    for r in rows_x[hdr_i + 2:]:
        code = str(cell(r, ci) or "").strip()[:4]
        if not code[:4].isalnum() or len(code) < 4:
            continue
        upd = _xl_date(cell(r, ui))
        nm = str(cell(r, ni) or code)
        mk = str(cell(r, mi) or "")
        status = str(cell(r, si) or "")
        change = str(cell(r, chg) or "").strip()
        if upd.startswith(ym) or change:
            why = f"공시 갱신 {upd}" if upd.startswith(ym) else f"상태 변화: {change}"
            rows.append({"channel": "special", "kind": "valueup", "market": "jp", "ticker": code, "name": nm, "tv": f"TSE:{code}", "date": today.isoformat(),
                         "strength": 4.5 if upd.startswith(ym) else 4.0, "signal": f"JPX 자본비용·주가 의식 경영 — {why}({mk})", "url": JPX_LIST,
                         "extra": {"sheet": name.strip(), "update": upd, "change": change}})
        elif "プライム" in mk and "開示済" in status and (not upd or upd[:7] < cutoff):
            stale.append({"code": code, "name": nm, "update": upd or "초기 공시 뒤 갱신 없음"})
    st["jpx"]["sheet"] = name.strip()
    pth = common.ROOT / "knowledge" / "models" / "discovery" / "jpx_stale.json"
    pth.write_text(json.dumps({"as_of": today.isoformat(), "sheet": name.strip(), "note": "1년 넘게 공시 갱신 없는 프라임 기업(조사 H — 행동주의 표적 참고, 그 자체로 신호 아님)",
                               "n": len(stale), "rows": stale}, ensure_ascii=False, indent=0), encoding="utf-8")
    return rows


# ---------- 구루 논지 특수 상황(패니·프레디형) ----------
def thesis_rows(st, today):
    """config/special_situations.yaml 논지 종목의 촉매 서류(EDGAR 제출 목록) — 상장 재등록 8-A12B·공모 S-1·8-K 핵심 항목. 첫 회차는 기준선만"""
    cfgx = common.load_yaml("config/special_situations.yaml") or {}
    rows = []
    for t in cfgx.get("theses") or []:
        forms = t.get("watch_forms") or []
        for sec in t.get("securities") or []:
            cik = str(sec.get("cik") or "")
            if not cik:
                continue
            sub = json.loads(_get(f"https://data.sec.gov/submissions/CIK{cik.zfill(10)}.json"))
            r = sub.get("filings", {}).get("recent", {})
            k = f"thesis:{cik}"
            last = st.get(k)
            newest = max(r.get("filingDate") or [""])
            if last is None:
                st[k] = newest
                continue
            for i in range(len(r.get("form", []))):
                fd, form, items = r["filingDate"][i], r["form"][i], str(r.get("items", [""] * len(r["form"]))[i] or "")
                if fd <= last:
                    continue
                hit = any(form == f.split(":")[0] and (":" not in f or f.split(":")[1] in items) for f in forms)
                if hit:
                    ad = r["accessionNumber"][i]
                    rows.append({"channel": "guru", "kind": "thesis", "market": "us", "ticker": sec.get("ticker", ""), "name": sec.get("name") or t["name"],
                                 "tv": sec.get("tv", ""), "date": fd, "strength": 7.0,
                                 "signal": f"논지 '{t['name']}' 촉매 서류 {form}" + (f" {items}" if items else "") + f" — {', '.join(t.get('gurus') or [])}",
                                 "url": f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{ad.replace('-', '')}/", "extra": {"thesis": t["id"], "form": form, "items": items}})
            st[k] = max(newest, last)
    return rows


# ---------- 일본(키 대기) ----------
EDINET_CODES = "https://disclosure2dl.edinet-fsa.go.jp/searchdocument/codelist/Edinetcode.zip"   # EDINET 코드 목록(공식 내려받기) — 키가 들어오면 약관 재확인


def edinet_seccodes():
    """{EDINET 코드: 증권 코드 4자리} — EDINET 공식 코드 목록(zip CSV, 30일 캐시). 대량보유·공개매수 '대상 회사'를 종목으로 잇는다"""
    import io
    import time as _t
    import zipfile
    cache = common.ROOT / "radar" / "state" / "edinet_codes.json"
    if cache.exists() and _t.time() - cache.stat().st_mtime < 30 * 86400:
        return json.loads(cache.read_text(encoding="utf-8"))
    raw = common.http_get(EDINET_CODES, timeout=60)
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        text = z.read(z.namelist()[0]).decode("cp932", "ignore")
    out = {}
    for line in text.splitlines()[2:]:
        cols = [c.strip().strip('"') for c in line.split(",")]
        if len(cols) > 11 and cols[0].startswith("E") and cols[11][:4].isdigit():
            out[cols[0]] = cols[11][:4]
    cache.write_text(json.dumps(out), encoding="utf-8")
    return out


def jp_rows(key, start, end, jp_roster):
    """EDINET API v2 목록(type=2). 조사 C·H 서식 코드:
      大量保有 docTypeCode 350·ordinanceCode 060 — formCode 010000(일반)·010002(변경)만(030000·030002 특례 = 기관 수동 보유, 020002 단기 대량 양도 = 이탈)
        대상 회사 = issuerEdinetCode. 제출인이 명단이면 activist/entry(구루 명단이면 guru/stake). 특례 → 일반 전환은 행동주의 전환 신호(같은 제출인)
      公開買付届出書 docTypeCode 240 — ordinanceCode 040(제3자)만, 050(자기 공개매수)은 할인 매입이 많아 뺀다. 대상 회사 = subjectEdinetCode
    약관: 웹 화면 스크래핑 금지·API만·짧은 시간 대량 접속 금지·출처 표시(PDL1.0) — 하루 단위로 천천히"""
    rows = []
    codes = edinet_seccodes()
    d = start
    while d <= end:
        try:
            raw = common.http_get(EDINET, {"date": d.isoformat(), "type": 2, "Subscription-Key": key}, timeout=30)
        except Exception as exc:  # noqa: BLE001 — 키가 든 주소를 메시지에 남기지 않는다
            raise RuntimeError(f"EDINET 목록 실패({type(exc).__name__})") from None
        for x in json.loads(raw).get("results") or []:
            filer = jp_name(x.get("filerName") or "")
            dt, oc, fc = x.get("docTypeCode"), x.get("ordinanceCode"), x.get("formCode")
            url = f"https://disclosure2.edinet-fsa.go.jp/WEEK0010.aspx?docID={x.get('docID')}"
            if dt == "350" and oc == "060" and fc in ("010000", "010002"):
                code = codes.get(x.get("issuerEdinetCode") or "", "")
                hit = next((a for a, pat in jp_roster if pat.search(filer)), None)
                if code and hit:
                    ch = hit.get("channel", "activist")
                    rows.append({"channel": ch, "kind": "entry" if ch == "activist" else "stake", "market": "jp", "ticker": code, "name": code, "tv": f"TSE:{code}",
                                 "date": d.isoformat(), "strength": 7.5 if fc == "010000" else 6.5, "url": url,
                                 "signal": f"{hit['name']} 大量保有報告書({'신규' if fc == '010000' else '변경'}) — 保有目的 원문 확인(重要提案行為等이면 행동주의)",
                                 "extra": {"doc": dt, "form": fc, "filer": filer, "issuer_edinet": x.get("issuerEdinetCode")}})
            elif dt == "240" and oc == "040":
                code = codes.get(x.get("subjectEdinetCode") or "", "")
                if code:
                    rows.append({"channel": "special", "kind": "tender", "market": "jp", "ticker": code, "name": code, "tv": f"TSE:{code}", "date": d.isoformat(),
                                 "strength": 6.0, "url": url, "signal": f"公開買付届出書(제3자 공개매수) — 매수자 {filer}",
                                 "extra": {"doc": dt, "filer": filer, "subject_edinet": x.get("subjectEdinetCode")}})
        d += timedelta(days=1)
        time.sleep(1.0)
    return rows


MARKETS = ("us", "kr", "jp", "tw", "jpx", "thesis")   # 홍콩 HKEXnews(이용약관 5조 자동 수집 금지)·영국 인수위원회(robots ClaudeBot 금지)는 넣지 않는다(2026-11-15 확인)


def collect(days=None, dry=False, markets=MARKETS, today=None):
    today = today or common.now_kst().date()
    env = common.load_env()
    st = common.load_state("discovery_filings", {})
    c = common.load_yaml("config/discovery_channels.yaml") or {}
    look = int((c.get("filings") or {}).get("lookback_days", 3))
    us_act, us_gur, kr_act, jp_roster, rules = rosters()
    rows, errors, done = [], [], []
    for m in markets:
        last = st.get(f"last_{m}")
        start = today - timedelta(days=days) if days else (date.fromisoformat(last) if last else today - timedelta(days=look))
        try:
            if m == "us":
                r, _ = us_rows(start, today, rules, us_act, us_gur)
            elif m == "kr":
                if not env.get("DART_API_KEY"):
                    continue
                r, flags = kr_rows(env["DART_API_KEY"], start, today, kr_act)
                try:
                    for code, fs in krx_warnings(today - timedelta(days=30), today).items():
                        flags.setdefault(code, []).extend(fs)
                except Exception as exc:  # noqa: BLE001 — 투자경고 표지는 보조 입력
                    errors.append(f"krx 투자경고: {type(exc).__name__}")
                if not dry:
                    save_flags(flags, today)
            elif m == "jp":
                if not env.get("EDINET_API_KEY"):
                    done.append("jp 키 대기")
                    continue
                r = jp_rows(env["EDINET_API_KEY"], start, today, jp_roster)
            elif m == "tw":
                r = tw_rows()
            elif m == "jpx":
                r = jpx_rows(st, today)
            elif m == "thesis":
                r = thesis_rows(st, today)
            else:
                continue
            rows += r
            st[f"last_{m}"] = today.isoformat()
            done.append(f"{m} {len(r)}")
        except Exception as exc:  # noqa: BLE001 — 한 시장 실패가 다른 시장을 막지 않게
            errors.append(f"{m}: {type(exc).__name__} {str(exc)[:120]}")
    if dry:
        return rows, errors
    sys.path.insert(0, str(ROOT / "scripts" / "discovery"))
    import leads
    new = leads.add(rows, today=today)
    common.save_state("discovery_filings", st)
    common.record_health(SOURCE_ID, not errors, "; ".join(errors)[:300] or None)
    return new, errors, done


def triage():
    """새 단서가 들어오면 채널 선별(scripts/discovery/channels.py)을 다시 — Pulse 경보 파일이 이어서 갱신된다"""
    sys.path.insert(0, str(ROOT / "scripts" / "discovery"))
    import channels
    rows, q, al = channels.run()
    return len(rows), len(al)


def run():
    """run_hourly용 — (요약, 새 단서 수)"""
    new, errors, done = collect()
    n_rows, n_al = triage()
    if errors and not new:
        raise RuntimeError("; ".join(errors)[:200])
    return f"새 단서 {len(new)} · {' · '.join(done)} · 채널 선별 {n_rows}종목 · 경보 후보 {n_al}" + (f" · 오류 {len(errors)}" if errors else ""), len(new)


def main(argv):
    sys.stdout.reconfigure(encoding="utf-8")
    days = int(argv[argv.index("--days") + 1]) if "--days" in argv else None
    mk = tuple(argv[argv.index("--market") + 1].split(",")) if "--market" in argv else MARKETS
    if "--dry" in argv:
        rows, errors = collect(days, dry=True, markets=mk)
        for r in rows:
            print(f"{r['date']} {r['channel']}/{r['kind']} {r['market']} {r['ticker']} {r['name']} {r['strength']} — {r['signal']}")
        print("오류:", errors)
        return 0
    new, errors, done = collect(days, markets=mk)
    triage()
    print(f"[발굴 공시] 새 단서 {len(new)} · {' · '.join(done)}" + (f" · 오류 {'; '.join(errors)}" if errors else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
