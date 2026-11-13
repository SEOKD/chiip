"""대형 기업 상장(IPO) 서류 실시간 감지·풀이 (마스터 지시 2026-11-13 "Anthropic처럼 큰 회사의 상장 소식이 나오면 SEC에 S-1이
뜨는 즉시 가져와 풀이", 설계 docs/decisions/ADR-030-ipo-watch.md, 감시 대상 config/ipo_watch.yaml)

감지(결정론, 10분 — run_poll 원천 src-ipo-watch):
  EDGAR 전문검색(efts.sec.gov — 문서 메타데이터, 일반 User-Agent로도 열린다)에서 최근 2일 S-1·S-1/A·F-1·F-1/A·424B4·DRS·DRS/A·FWP·RW.
  ① 감시 대상(CIK 또는 이름) → 즉시 텔레그램 첫 카드(핵심 5줄) + inbox 항목(sec_always — 판정 모델이 카드 yaml)
  ② 감시 밖 첫 S-1·F-1 중 최대 공모 총액(EX-FILING FEES) ≥ large_offering_usd → inbox 항목(Pulse '신규 상장' 후보). 공모 총액은
     원문이 필요해 SEC_USER_AGENT가 없으면 판정하지 않는다.
풀이:
  - 원문 없이도: EDGAR 전문검색으로 한국·글로벌 공급망 이름 언급 여부(supply_probe) — 서류 단위 존재 여부만
  - 원문(.env SEC_USER_AGENT 있을 때): 사업 개요·매출·손실·현금흐름 숫자 문장, 주관사, 이중 의결권, 공모 조건(가격 범위·주식 수),
    위험 요인 머리말, S-1/A는 이전 판 대비 새 숫자 문장만(radar/state/ipo_watch.json 판별 숫자 보관)
  - 원문이 없으면 '원문 미열람 — SEC_USER_AGENT 필요'와 inbox의 같은 회사 보도 제목(보도 기준)을 붙이고, 마스터에게 설정 필요를 한 번 알린다.
SEC 접속 규칙: 식별 User-Agent, 초당 10회 이하(요청 사이 0.15초). 마스터 연락처를 대신 넣지 않는다.
사용: py radar/pollers/ipo_watch.py [--dry]          # 감지만 출력
      py radar/pollers/ipo_watch.py --card <CIK> <접수번호> <서식> <제출일>   # 한 서류 카드 출력(발송 없음)
"""
import json
import re
import sys
import time
import urllib.parse
from datetime import timedelta
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from pollers import common, sec_filings  # noqa: E402

SOURCE_ID = "src-ipo-watch"
EFTS = "https://efts.sec.gov/LATEST/search-index"
STATE = "ipo_watch"
FORM_KO = {"S-1": "상장 신청서(S-1) 공개 제출", "S-1/A": "상장 신청서 수정본(S-1/A)", "F-1": "외국 기업 상장 신청서(F-1)",
           "F-1/A": "외국 기업 상장 신청서 수정본(F-1/A)", "424B4": "최종 투자설명서(424B4) — 공모가 확정", "DRS": "비공개 제출(DRS) 공개분",
           "DRS/A": "비공개 제출 수정본(DRS/A) 공개분", "FWP": "공모 마케팅 자료(FWP)", "RW": "등록 철회(RW)"}
LEVEL = {"S-1": "P0", "F-1": "P0", "424B4": "P0", "RW": "P0", "S-1/A": "P1", "F-1/A": "P1", "DRS": "P1", "DRS/A": "P1", "FWP": "P1"}
BANKS = ["Goldman Sachs", "Morgan Stanley", "J.P. Morgan", "BofA Securities", "Citigroup", "Barclays", "Deutsche Bank", "Wells Fargo",
         "Jefferies", "UBS", "RBC Capital", "Evercore", "Allen & Company", "Mizuho", "SMBC", "Nomura", "Truist", "Needham"]
NUM_RE = re.compile(r"[$€¥]\s?\d[\d,.]*\s?(million|billion|thousand)?|\d[\d,.]*%")
FIN_RE = re.compile(r"revenue|net loss|net income|operating (loss|income)|free cash flow|cash flows? (used in|provided by)|gross margin|"
                    r"compute|capacity|purchase obligations?|commitments?", re.I)


def cfg():
    return common.load_yaml("config/ipo_watch.yaml") or {}


def efts(params):
    time.sleep(0.15)
    return json.loads(common.http_get(EFTS + "?" + urllib.parse.urlencode(params), headers={"User-Agent": sec_filings._ua()}, timeout=40))


def recent_filings(c, days=2, today=None):
    """[(adsh, _source)] 최근 days일 IPO 서식(본문 문서만 — 첨부는 file_type으로 거른다)"""
    today = today or common.now_kst().date()
    forms = ",".join(c.get("forms") or FORM_KO)
    out, seen = [], set()
    for page in range(4):
        d = efts({"forms": forms, "dateRange": "custom", "startdt": (today - timedelta(days=days)).isoformat(), "enddt": today.isoformat(), "from": page * 100})
        hits = d.get("hits", {}).get("hits", [])
        for h in hits:
            s = h["_source"]
            adsh = s.get("adsh") or h["_id"].split(":")[0]
            if adsh in seen:
                continue
            seen.add(adsh)
            out.append((adsh, {**s, "_doc": h["_id"].split(":", 1)[-1]}))
        if len(hits) < 100:
            break
    return out


def _name_re(n):
    return re.compile(rf"(?<![A-Za-z]){re.escape(n)}(?![A-Za-z])", re.I)


def match(s, companies):
    """감시 대상 dict 또는 None — CIK 우선, 다음 이름"""
    ciks = {str(int(x)) for x in s.get("ciks") or [] if str(x).isdigit()}
    disp = " ".join(s.get("display_names") or [])
    for co in companies:
        if co.get("cik") and str(int(co["cik"])) in ciks:
            return co
    for co in companies:
        if any(_name_re(n).search(disp) for n in co.get("names") or [co["name"]]):
            return co
    return None


def probe(cik, form, day, names):
    """EDGAR 전문검색으로 그 서류(같은 CIK·서식·제출일)에 이름이 나오는지 — {이름: True/False}. 원문 없이 된다"""
    out = {}
    for n in names:
        try:
            d = efts({"q": f'"{n}"', "ciks": str(cik).zfill(10), "forms": form, "dateRange": "custom", "startdt": day, "enddt": day})
            out[n] = d.get("hits", {}).get("total", {}).get("value", 0) > 0
        except Exception:
            out[n] = None
    return out


def doc_url(cik, adsh, doc):
    return f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{adsh.replace('-', '')}/{doc}"


def read_doc(url):
    """(본문, 실패 사유) — SEC_USER_AGENT가 없으면 시도하지 않는다(www.sec.gov 403)"""
    import fulltext
    ua = fulltext.sec_ua()
    if not ua:
        return None, "원문 미열람 — SEC_USER_AGENT 필요(.env, www.sec.gov 403)"
    try:
        time.sleep(0.15)
        return fulltext.clean_html(common.http_get(url, headers={"User-Agent": ua}, timeout=60).decode("utf-8", "ignore")), ""
    except Exception as exc:
        return None, f"원문 열람 실패 — SEC {getattr(exc, 'code', '') or type(exc).__name__}"


WORD_NUM = {"one": "1", "two": "2", "five": "5", "ten": "10", "twenty": "20", "fifty": "50", "zero": "0", "no": "0"}


def join_lines(text):
    """줄 중간에서 끊긴 문장을 잇는다(EDGAR HTML은 문단 안에서도 줄이 나뉜다)"""
    return re.sub(r"(?<![.!?:;])\n(?=[a-z0-9$(“\"%,])", " ", text)


def parse(text):
    """원문 → 풀이 재료(결정론). 해석·요약 문장은 모델(판정·Pulse 회차)이 쓴다"""
    text = join_lines(text)
    sents = [re.sub(r"\s+", " ", s).strip() for s in re.split(r"(?<=[.!?])\s+|\n", text) if 40 <= len(s.strip()) <= 420]
    fin = [s for s in sents if FIN_RE.search(s) and NUM_RE.search(s)]
    key = re.compile(r"revenue (grew|was|of|increased)|net loss|net income|commitments?|free cash flow|run-rate", re.I)
    fin = sorted(fin, key=lambda x: not key.search(x))[:12]
    m = re.search(r"(?is)\n\s*(?:Overview|Our Company)\s*\n(.{200,2000}?)\n", text)
    overview = re.sub(r"\s+", " ", m[1])[:600] if m else ""
    price = re.search(r"between \$\s?(\d+(?:\.\d+)?) and \$\s?(\d+(?:\.\d+)?)", text)
    shares = re.search(r"[Ww]e are (?:offering|selling) ([\d,]{6,}) shares", text)
    votes = re.findall(r"(?:holders of )?(?:our )?Class ([A-Z]) common stock (?:is|are|will be) entitled to (\w+) votes? per share", text) + re.findall(r"Class ([A-Z]) common stock will be entitled to (\w+) votes? per share", text)
    rs = re.search(r"(?is)(summary (?:of )?risk factors|risk factors summary)(.{0,8000})", text)
    risks = [re.sub(r"\s+", " ", x).strip() for x in re.findall(r"\n\s*[•●]\s*([^\n]{30,260})", rs[2])][:6] if rs else []
    return {"overview": overview, "fin": fin, "banks": [b for b in BANKS if b in text[:30000]],
            "price_range": f"${price[1]}~${price[2]}" if price else "", "shares": shares[1] if shares else "",
            "dual_class": sorted({f"Class {a} {WORD_NUM.get(b.lower(), b)}표" for a, b in votes})[:3], "risks": risks}


def prev_numbers(cik, adsh, form, read_fn=None):
    """S-1/A의 직전 판(같은 CIK의 S-1·S-1/A 중 이 서류 바로 앞) 숫자 문장 — data.sec.gov 제출 목록 → 원문"""
    try:
        sub = json.loads(common.http_get(f"https://data.sec.gov/submissions/CIK{str(cik).zfill(10)}.json", headers={"User-Agent": sec_filings._ua()}))
    except Exception:
        return None
    r = sub.get("filings", {}).get("recent", {})
    base = form.split("/")[0]
    rows = [(r["accessionNumber"][i], r["primaryDocument"][i]) for i in range(len(r.get("form", []))) if r["form"][i] in (base, base + "/A")]
    acc = [a for a, _ in rows]
    if adsh not in acc or acc.index(adsh) + 1 >= len(rows):
        return None
    pa, pd = rows[acc.index(adsh) + 1]
    text, _ = (read_fn or read_doc)(doc_url(cik, pa, pd))
    return parse(text)["fin"] if text else None


def news_titles(co, now, days=3):
    """inbox 최근 days일의 같은 회사 보도 제목(원문을 못 읽을 때 '보도 기준'으로)"""
    pats = [_name_re(n) for n in co.get("names") or [co["name"]]]
    ipo = re.compile(r"IPO|S-1|prospectus|listing|상장|공모|price range|valuation|roadshow", re.I)
    out = []
    for k in range(days):
        d = common.INBOX / (now - timedelta(days=k)).strftime("%Y%m%d")
        if not d.exists():
            continue
        for f in d.glob("*.json"):
            if f.name.startswith(SOURCE_ID):
                continue
            try:
                it = json.loads(f.read_text(encoding="utf-8"))
            except ValueError:
                continue
            t = it.get("title", "")
            if any(p.search(t) for p in pats) and ipo.search(t):
                out.append((it.get("published_at", ""), t[:110], it.get("source_id", "")))
    return [x[1:] for x in sorted(out, reverse=True)[:3]]


def new_numbers(prev, cur):
    """S-1/A — 이전 판에 없던 숫자 문장만"""
    old = {re.sub(r"\s+", " ", x)[:120] for x in prev or []}
    return [x for x in cur if re.sub(r"\s+", " ", x)[:120] not in old]


def card(co, form, adsh, s, now, st, probe_fn=None, read_fn=None):
    """(첫 카드 5줄 텍스트, 상세 dict)"""
    c = cfg()
    cik = (s.get("ciks") or [co.get("cik") or ""])[0]
    day = s.get("file_date", "")
    url = doc_url(cik, adsh, s["_doc"]) if cik and s.get("_doc") else ""
    names = (c.get("supply_probe") or {})
    hits = (probe_fn or probe)(cik, form, day, list(names.get("korea", [])) + list(names.get("global", []))) if cik else {}
    kr = [n for n in names.get("korea", []) if hits.get(n)]
    gl = [n for n in names.get("global", []) if hits.get(n)]
    text, why = (read_fn or read_doc)(url) if url else (None, "원문 주소 없음")
    detail = {"form": form, "adsh": adsh, "day": day, "url": url, "korea": kr, "global": gl, "read": bool(text), "why": why}
    if text:
        p = parse(text)
        prev = (st.get("numbers") or {}).get(co["id"])
        if form.endswith("/A") and not prev:
            prev = prev_numbers(cik, adsh, form, read_fn)
        p["fin_new"] = new_numbers(prev, p["fin"]) if form.endswith("/A") and prev else p["fin"]
        st.setdefault("numbers", {})[co["id"]] = p["fin"]
        detail.update(p)
        flat = re.sub(r"\s+", " ", join_lines(text))
        detail["korea_ctx"] = {}
        for n in kr:   # 한국 기업 이름 앞뒤 90자 — 어떤 맥락(공급사·위험 요인·고객)인지 카드에서 바로 보이게
            m = re.search(re.escape(n), flat)
            if m:
                detail["korea_ctx"][n] = ("…" if m.start() > 70 else "") + flat[max(0, m.start() - 70):m.end() + 70].strip() + "…"
    else:
        detail["news"] = news_titles(co, now)
    L = [f"[IPO 서류] {co['name']} — {FORM_KO.get(form, form)}",
         f"• 제출 {day} · 접수번호 {adsh}" + (f" · 주관사 {', '.join(detail['banks'][:3])} 등 {len(detail['banks'])}곳" if detail.get("banks") else "")]
    if kr:
        ctx = (detail.get("korea_ctx") or {}).get(kr[0]) if text else None
        L.append(f"• 🇰🇷 한국 기업 언급: {', '.join(kr)}" + (f" — 원문: “{ctx.strip()[:160]}”" if ctx else "(EDGAR 전문검색 — 문맥은 원문 확인)"))
    if gl:
        L.append(f"• 공급망 언급: {', '.join(gl[:6])}")
    if text:
        if detail.get("price_range") or detail.get("shares"):
            L.append(f"• 공모 조건: 가격 범위 {detail.get('price_range') or '미기재'} · 주식 수 {detail.get('shares') or '미기재'}")
        nums = detail.get("fin_new") or []
        L.append(f"• {'이전 판 대비 새 숫자' if form.endswith('/A') else '숫자'}: {nums[0][:150]}" if nums else "• 숫자 문장 없음(본문 확인 필요)")
    else:
        L.append(f"• {why}")
        if detail.get("news"):
            L.append(f"• 보도 기준(원문 미열람): {detail['news'][0][0]}")
    L.append(f"원문: {url or '미확인'}")
    return "\n".join(L[:6] + ([L[-1]] if len(L) > 6 else [])), detail


DETAIL_FORMS = ("S-1", "S-1/A", "F-1", "F-1/A", "424B4")   # FWP·DRS·RW는 첫 카드만(상세 풀이 모델 호출 없음)
DETAIL_PROMPT = """너는 반도체·AI 하드웨어 리서치 에이전트 Chiip이다. 아래는 {name}의 {form}({day}) 원문에서 결정론으로 뽑은 재료다(JSON).
한국어로 텔레그램 상세 풀이를 쓴다. 순서: ① 사업 개요 1줄 ② 매출·성장·손실·현금흐름(숫자 그대로, $B·$M 표기) ③ 컴퓨트 계약·CAPEX 약정
④ 한국 기업 언급(korea_ctx 문맥 그대로 — 공급사인지 위험 요인인지 구분, 없으면 '언급 없음') ⑤ 위험 요인 핵심 3개 ⑥ 지배구조(의결권 구조·지배 주주)
⑦ 주관사 ⑧ 공모 조건 ⑨ {diff_rule}. 재료에 없는 숫자·사실을 쓰지 않는다. 매수·매도 표현 금지. 각 항목 1~2줄, 머리에 '[IPO 상세] {name} {form}'.
재료:
{materials}
본문만 출력."""


def detail_message(co, detail, caller=None):
    """원문을 읽었으면 상세 풀이(소형 모델 1회). 못 읽었으면 None — 첫 카드에 사유가 이미 있다"""
    if not detail.get("read"):
        return None
    mats = {k: detail.get(k) for k in ("overview", "fin", "fin_new", "korea", "korea_ctx", "global", "risks", "dual_class", "banks", "price_range", "shares")}
    diff = "S-1/A이므로 fin_new(이전 판에 없던 숫자 문장)만 '바뀐 숫자'로" if detail["form"].endswith("/A") else "첫 서류이므로 '바뀐 숫자' 항목은 뺀다"
    prompt = DETAIL_PROMPT.format(name=co["name"], form=detail["form"], day=detail.get("day", ""), diff_rule=diff,
                                  materials=json.dumps(mats, ensure_ascii=False)[:9000])
    try:
        if caller:
            return (caller(prompt) or "").replace("**", "").strip() or None
        import run_triage
        if not run_triage.claude_exe():
            return None
        out = run_triage.run_claude(prompt, "sonnet", timeout=300)
        return str(out.get("result") or "").replace("**", "").strip() or None   # 텔레그램은 일반 글 — ** 가 그대로 보인다(2026-11-12)
    except Exception as exc:
        common.record_health(SOURCE_ID, False, f"상세 풀이: {type(exc).__name__}: {exc}"[:200])
        return None


def ua_notice(st, send):
    """SEC_USER_AGENT가 없으면 마스터에게 한 번 알린다(이메일을 대신 넣지 않는다)"""
    import fulltext
    if fulltext.sec_ua() or st.get("ua_notice"):
        return False
    msg = ("[Chiip 설정 필요] SEC 원문(www.sec.gov)이 403으로 막혀 IPO 서류·8-K 본문을 읽지 못합니다.\n"
           "D:\\local-only\\secrets\\.env에 한 줄을 넣어 주세요: SEC_USER_AGENT=<이름> <연락 이메일>\n"
           "(SEC 공정 접근 규칙 — 식별 가능한 User-Agent. Chiip은 이메일을 대신 넣지 않습니다.) 감지는 EDGAR 전문검색으로 계속 됩니다.")
    if send:
        import notify
        notify.send(msg, "P1")
    st["ua_notice"] = common.iso(common.now_kst())
    return True


def large_offering(cik, adsh):
    """감시 밖 첫 S-1·F-1의 최대 공모 총액($) — 원문(수수료 첨부)이 필요. 모르면 None"""
    import fulltext
    ua = fulltext.sec_ua()
    if not ua:
        return None
    try:
        idx = json.loads(common.http_get(f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{adsh.replace('-', '')}/index.json", headers={"User-Agent": ua}))
        fee = next((x["name"] for x in idx["directory"]["item"] if re.search(r"fee", x["name"], re.I)), None)
        if not fee:
            return None
        time.sleep(0.15)
        t = fulltext.clean_html(common.http_get(f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{adsh.replace('-', '')}/{fee}", headers={"User-Agent": ua}).decode("utf-8", "ignore"))
        vals = [float(x.replace(",", "")) for x in re.findall(r"\$\s?([\d,]{9,}(?:\.\d+)?)", t)]
        return max(vals) if vals else None
    except Exception:
        return None


def poll(env=None, send=True, now=None, filings=None):
    c = cfg()
    now = now or common.now_kst()
    st = common.load_state(STATE, {})
    seen = set(st.get("seen", []))
    cos = c.get("companies") or []
    items = []
    ua_notice(st, send)
    for adsh, s in (filings if filings is not None else recent_filings(c, today=now.date())):
        key = f"{adsh}:{s.get('form')}"
        if key in seen or s.get("file_type") not in (s.get("form"), None):   # 첨부(EX-…)는 본문 서류와 같은 접수번호 — 본문만
            continue
        seen.add(key)
        form = s.get("form", "")
        co = match(s, cos)
        disp = (s.get("display_names") or [""])[0]
        cik = (s.get("ciks") or [""])[0]
        if co:
            text, detail = card(co, form, adsh, s, now, st)
            item = common.make_item(SOURCE_ID, adsh.replace("-", "") + form.replace("/", ""), detail["url"], f"[SEC {form} IPO] {co['name']}",
                                    s.get("file_date"), "공시", "en", f"{co['name']} {FORM_KO.get(form, form)}",
                                    extra={"entities_matched": [co["id"]], "report_nm": form, "sec_always": True, "tier": "글로벌",
                                           "ipo": detail, "alert_hint": LEVEL.get(form, "P1")})
            items.append(item)
            fwp_dup = form == "FWP" and (st.get("fwp_day") or {}).get(co["id"]) == s.get("file_date")   # 로드쇼 자료는 하루 여러 건 — 회사당 하루 1통
            if form == "FWP":
                st.setdefault("fwp_day", {})[co["id"]] = s.get("file_date")
            if send and not fwp_dup:
                import notify
                ref = notify.remember_alert(item, LEVEL.get(form, "P1"), what=text.split("\n")[0], impact=" / ".join(detail.get("korea") or []))
                if notify.send(text, LEVEL.get(form, "P1"), ref=ref):
                    long = detail_message(co, detail) if form in DETAIL_FORMS else None   # 상세 풀이는 이어서 한 통(원문을 읽었을 때만, 등록 서류만)
                    if long:
                        notify.send(long, LEVEL.get(form, "P1"))
                    fs = common.load_state("rule_fast", {"ids": []})   # 판정 모델이 같은 건을 다시 보내지 않게(run_triage fast_sent)
                    fs["ids"] = (fs.get("ids") or [])[-2000:] + [item["item_id"], f"src-sec-filings:{adsh}"]   # sec_always 수집분(같은 서류)도 다시 보내지 않게
                    common.save_state("rule_fast", fs)
        elif form in ("S-1", "F-1") and "Acquisition" not in disp and cik:
            amt = large_offering(cik, adsh)
            if amt and amt >= float(c.get("large_offering_usd", 1e9)):
                items.append(common.make_item(SOURCE_ID, adsh.replace("-", "") + form.replace("/", ""), doc_url(cik, adsh, s.get("_doc", "")),
                                              f"[SEC {form} 대형 IPO] {disp.split('(CIK')[0].strip()}", s.get("file_date"), "공시", "en",
                                              f"최대 공모 총액 ${amt / 1e9:.1f}B · SIC {(s.get('sics') or [''])[0]}",
                                              extra={"sec_always": True, "report_nm": form, "tier": "글로벌", "offering_usd": amt}))
    st["seen"] = sorted(seen)[-5000:]
    common.save_state(STATE, st)
    common.record_health(SOURCE_ID, True, None)
    return items


def main(argv):
    sys.stdout.reconfigure(encoding="utf-8")
    if argv[:1] == ["--card"]:
        cik, adsh, form, day = argv[1:5]
        co = next((x for x in cfg().get("companies") or [] if x.get("cik") and int(x["cik"]) == int(cik)), {"id": f"cik{cik}", "name": f"CIK {cik}", "why": ""})
        d = efts({"ciks": str(cik).zfill(10), "forms": form, "dateRange": "custom", "startdt": day, "enddt": day})
        hit = next((h for h in d["hits"]["hits"] if h["_id"].startswith(adsh) and h["_source"].get("file_type") == form), None)
        s = {**(hit or {}).get("_source", {"ciks": [cik], "file_date": day}), "_doc": (hit or {}).get("_id", ":").split(":", 1)[-1]}
        text, detail = card(co, form, adsh, s, common.now_kst(), {})
        print(text)
        print(json.dumps({k: v for k, v in detail.items() if k not in ("overview",)}, ensure_ascii=False, indent=1))
        return 0
    items = poll(send=False) if "--dry" in argv else poll()
    for it in items:
        print(it["title"], it.get("alert_hint", ""))
    print(f"[IPO 서류] {len(items)}건")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
