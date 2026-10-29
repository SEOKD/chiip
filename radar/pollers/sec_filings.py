"""SEC 공시·실적 (BUILD_PROMPT §21.13) — 포커스 종목(미국 상장·ADR)의 새 EDGAR 제출 서류

data.sec.gov/submissions/CIK##########.json (키 불필요). 티커→CIK는 EDGAR 기업 검색으로 한 번 찾아 저장.
SEC 접속 규칙: 식별 가능한 User-Agent(SEC_USER_AGENT, .env), 초당 10회 이하.
실적 = 8-K Item 2.02(보도자료 Exhibit 99.1), 분기·연간 보고서 = 10-Q·10-K, 외국 발행사 = 6-K·20-F.
"""
import json
import time
from datetime import timedelta

from . import common, gate

SOURCE_ID = "src-sec-filings"
SUB = "https://data.sec.gov/submissions/CIK{cik:0>10}.json"
LOOKUP = "https://efts.sec.gov/LATEST/search-index"
FORMS = {"8-K", "8-K/A", "10-Q", "10-K", "6-K", "20-F", "S-1", "DEF 14A", "SC 13D", "425"}
ITEM_LABEL = {"2.02": "실적", "1.01": "중요 계약", "1.02": "계약 해지", "2.01": "인수·처분", "2.05": "구조조정",
              "2.06": "손상", "5.02": "임원 변동", "7.01": "IR 자료", "8.01": "기타 중요 사항", "3.02": "증권 발행"}
DOC_TYPE = {"8-K": "공시", "10-Q": "실적", "10-K": "실적", "6-K": "공시", "20-F": "실적"}


def _ua():
    return common.load_env().get("SEC_USER_AGENT") or common.UA


def ticker_of(u):
    code = u.get("code") or ""
    if code.endswith(".US"):
        return code[:-3]
    return u.get("sec_ticker")  # 해외 본주 + 미국 ADR(TSMC→TSM 등)


def cik_for(ticker, state, name=None):
    """티커 → CIK. 티커 검색이 비면(예: GEV — 0건) 회사명으로 다시 찾고 티커 일치를 확인한다(2026-10-28 GEV 누락 수정).
    실패(None)는 하루 뒤 다시 시도한다"""
    ciks = state.setdefault("ciks", {})
    tried = state.setdefault("cik_miss", {})
    if ciks.get(ticker):
        return ciks[ticker]
    today = common.now_kst().date().isoformat()
    if tried.get(ticker) == today:
        return None
    cik = None
    for q in [ticker] + ([name] if name else []):
        data = json.loads(common.http_get(LOOKUP, {"keysTyped": q}, {"User-Agent": _ua()}))
        for h in data.get("hits", {}).get("hits", []):
            if ticker.upper() in str(h["_source"].get("tickers", "")).upper().split(", "):
                cik = h["_id"]
                break
        if cik:
            break
    if cik:
        ciks[ticker] = cik
        tried.pop(ticker, None)
    else:
        tried[ticker] = today
    return cik


def poll(env=None, days=3):
    focus, _ = gate.focus_state()
    uni = list((common.load_yaml("config/valuation.yaml") or {}).get("universe", []))
    uni += (common.load_yaml("config/earnings_watch.yaml") or {}).get("extra") or []   # 어닝 감시 확장 종목도(2026-10-28 GEV 누락 수정)
    have = {str(u.get("code", "")).upper() for u in uni}
    uni += [u for u in common.edge_watch_entries() if u["code"].upper() not in have]   # 조용한 매집형 상승 watch·마스터 지정 관측(2026-10-29 Nova 등)
    watch = gate.watch_ids()
    state = common.load_state("sec_filings", {})
    since = (common.now_kst() - timedelta(days=days)).date().isoformat()
    items = []
    for u in uni:
        if focus is not None and u["id"] not in focus and u["id"] not in watch:
            continue
        tk = ticker_of(u)
        if not tk:
            continue
        cik = cik_for(tk, state, (u.get("aliases") or [u.get("name")])[0])
        time.sleep(0.15)
        if not cik:
            continue
        d = json.loads(common.http_get(SUB.format(cik=cik), headers={"User-Agent": _ua()}))
        time.sleep(0.15)
        r = d.get("filings", {}).get("recent", {})
        for i, form in enumerate(r.get("form", [])):
            if r["filingDate"][i] < since:
                break
            if form not in FORMS:
                continue
            items_s = r.get("items", [""] * len(r["form"]))[i] or ""
            labels = [ITEM_LABEL[x] for x in items_s.split(",") if x in ITEM_LABEL]
            if form.startswith("8-K") and not labels:
                continue  # 항목 없는 8-K(규정 공시 등)는 건너뜀
            acc = r["accessionNumber"][i]
            url = f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{acc.replace('-', '')}/{r['primaryDocument'][i]}"
            tag = "·".join(labels) if labels else form
            items.append(common.make_item(
                SOURCE_ID, acc, url, f"[SEC {form} {tag}] {d.get('name', u['name'])}",
                r.get("acceptanceDateTime", [""] * len(r["form"]))[i] or r["filingDate"][i],
                "실적" if "실적" in labels else DOC_TYPE.get(form.split("/")[0], "공시"), "en",
                f"{u['name']} {form} {items_s} {r.get('primaryDocDescription', [''] * len(r['form']))[i]}",
                extra={"entities_matched": [u["id"]], "report_nm": form, "sec_items": items_s, "tier": "글로벌"}))
    common.save_state("sec_filings", state)
    return items


if __name__ == "__main__":
    import sys
    sys.stdout.reconfigure(encoding="utf-8")
    its = poll(days=int(sys.argv[1]) if len(sys.argv) > 1 else 3)
    print(f"SEC 공시 {len(its)}건")
    for it in its[:20]:
        print("-", it["published_at"][:16], it["title"], it["url"])
