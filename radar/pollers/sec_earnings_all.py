"""전체 미국 상장사 실적 스캐너 (마스터 지시 2026-10-28 "이런 걸 자동으로") — Investing.com 어닝 캘린더 대체

SEC EDGAR 전문검색(efts.sec.gov/LATEST/search-index, 키 불필요·2026-10-28 응답 확인)에서 최근 이틀의 8-K 중
Item 2.02(실적)를 낸 모든 회사를 받는다. Investing.com·Yahoo·Finviz는 약관·robots로 자동 수집하지 않는다.
선별(결정론): 업종 코드(SIC)가 AI·반도체·하드웨어·데이터센터 전력·냉각·전력망 EPC이거나 감시 목록 티커.
  - 감시 목록 종목은 sec_filings가 이미 받으므로 건너뛴다(중복 방지).
  - 그 밖의 관련 종목: 공개 유통주식 가치(dei:EntityPublicFloat)가 1.5억 달러 미만인 초소형주는 제외
    (Hou·Xue·Zhang 2020: 미세주 신호는 거래비용 대비 착시가 많다), 나머지는 radar/state/v2_queue.json에 '알파 산정'으로 올린다.
    → 예약 작업 chiip-valuation-queue(모델)가 알파 4요소를 매기고, 5.0 이상이면 감시 목록에 추가·동인 작성·3요인 발송.
사용: py -m pollers.sec_earnings_all [--days 2]  (radar/에서)  /  run_hourly 60분
"""
import json
import re
import time
import urllib.parse
from datetime import timedelta

from . import common, sec_filings

SOURCE_ID = "src-sec-earnings-all"
EFTS = "https://efts.sec.gov/LATEST/search-index"
FACTS = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik:0>10}.json"
MIN_FLOAT = 150e6
# 관련 업종 코드(SIC) — 반도체·전자부품·장비·하드웨어·통신장비·광섬유/유리 / 발전·전력설비·전력사업자·전력망 시공·냉각·가스터빈 장비
SIC_AI = {"3674", "3672", "3679", "3678", "3677", "3559", "3825", "3826", "3827", "3571", "3572", "3576", "3577",
          "3661", "3663", "3669", "3357", "3229", "3670", "3690", "3699"}
SIC_POWER = {"3511", "3612", "3613", "3621", "3629", "3640", "3643", "3644", "4911", "4931", "4991", "1623", "1731",
             "1600", "3585", "3443", "3533", "3690", "8711"}
NAME_RE = re.compile(r"^(.*?)\s+\(([A-Z0-9.\-, ]+)\)\s+\(CIK (\d+)\)")


def parse_name(display):
    """'Jersey Mike's Subs Inc.  (JMKE)  (CIK 0002127043)' → (이름, 첫 티커, cik)"""
    m = NAME_RE.match(re.sub(r"\s+", " ", display or ""))
    if not m:
        return display, None, None
    return m.group(1).strip(), m.group(2).split(",")[0].strip(), m.group(3)


def fetch_hits(start, end, max_pages=8, forms="8-K"):
    """[(adsh, _source)] — 8-K 전부(페이지 100건), adsh 중복 제거"""
    seen, out = set(), []
    for page in range(max_pages):
        q = {"forms": forms, "dateRange": "custom", "startdt": start.isoformat(), "enddt": end.isoformat(), "from": page * 100}
        d = json.loads(common.http_get(EFTS + "?" + urllib.parse.urlencode(q), headers={"User-Agent": sec_filings._ua()}, timeout=40))
        hits = d.get("hits", {}).get("hits", [])
        for h in hits:
            s = h["_source"]
            if s.get("adsh") in seen:
                continue
            seen.add(s.get("adsh"))
            out.append((s.get("adsh"), s))
        if len(hits) < 100:
            break
        time.sleep(0.3)
    return out


def relevant(sic):
    return ("AI·반도체" if sic in SIC_AI else "") or ("전력·인프라" if sic in SIC_POWER else "")


def watch_tickers():
    ids = {}
    for path in ("config/valuation.yaml", "config/earnings_watch.yaml"):
        y = common.load_yaml(path) or {}
        for u in (y.get("universe") or []) + (y.get("extra") or []):
            code = u.get("code") or ""
            tk = code[:-3] if code.endswith(".US") else u.get("sec_ticker")
            if tk:
                ids[tk.upper()] = u["id"]
    return ids


def public_float(cik):
    try:
        f = json.loads(common.http_get(FACTS.format(cik=cik), headers={"User-Agent": sec_filings._ua()}, timeout=40))
    except Exception:
        return None
    vals = (((f.get("facts") or {}).get("dei") or {}).get("EntityPublicFloat") or {}).get("units", {}).get("USD", [])
    vals = sorted(vals, key=lambda v: v.get("end", ""))
    return vals[-1]["val"] if vals else None


def scan(days=2):
    today = common.now_kst().date()
    hits = fetch_hits(today - timedelta(days=days), today)
    watch = watch_tickers()
    st = common.load_state("sec_earnings_all", {"done": []})
    done = set(st["done"])
    found, queued, skipped_small = [], 0, 0
    for adsh, s in hits:
        if "2.02" not in (s.get("items") or []) or adsh in done:
            continue
        done.add(adsh)
        sic = (s.get("sics") or [""])[0]
        name, ticker, cik = parse_name((s.get("display_names") or [""])[0])
        if not ticker or ticker.upper() in watch:
            continue           # 감시 목록은 sec_filings 담당
        seg = relevant(sic)
        if not seg:
            continue
        fl = public_float(cik)
        time.sleep(0.15)
        if fl is not None and fl < MIN_FLOAT:
            skipped_small += 1
            continue
        cik_i = int(cik)
        url = f"https://www.sec.gov/Archives/edgar/data/{cik_i}/{adsh.replace('-', '')}/"
        eid = "us-" + re.sub(r"[^a-z0-9]", "", ticker.lower())
        found.append({"id": eid, "name": name, "ticker": ticker, "cik": cik_i, "sic": sic, "segment": seg,
                      "float": fl, "file_date": s.get("file_date"), "url": url})
        queued += enqueue(eid, f"{name} ({ticker})", f"실적 8-K {s.get('file_date')} · SIC {sic} {seg} · 유통주식 가치 {('%.1f억$' % (fl / 1e8)) if fl else '미상'} · {url}")
    st["done"] = sorted(done)[-5000:]
    common.save_state("sec_earnings_all", st)
    return found, queued, skipped_small


def enqueue(eid, name, reason):
    q_path = common.STATE / "v2_queue.json"
    q = json.loads(q_path.read_text(encoding="utf-8")) if q_path.exists() else []
    if any(x["id"] == eid and x["kind"] == "알파 산정" for x in q):
        return 0
    q.append({"id": eid, "name": name, "kind": "알파 산정", "reason": reason, "added": common.iso(common.now_kst()), "source": SOURCE_ID})
    q_path.write_text(json.dumps(q, ensure_ascii=False, indent=1), encoding="utf-8")
    return 1


def run():
    """run_hourly용 — (관련 실적 발표 수, 대기열 추가, 초소형 제외)"""
    found, queued, small = scan()
    common.record_health(SOURCE_ID, True, None)
    return len(found), queued, small


if __name__ == "__main__":
    import sys
    days = int(sys.argv[sys.argv.index("--days") + 1]) if "--days" in sys.argv else 2
    f, q, s = scan(days)
    print(f"[전체 실적 스캐너] 관련 {len(f)} · 대기열 추가 {q} · 초소형 제외 {s}")
    for x in f:
        print(f"- {x['file_date']} {x['ticker']:6} {x['name'][:40]:40} SIC {x['sic']} {x['segment']} 유통 {x['float'] / 1e9 if x['float'] else 0:.2f}B$")
