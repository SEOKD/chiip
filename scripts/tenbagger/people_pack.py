"""구루 '사람과 문화' 관점 재료 — 결정론 수집(마스터 지시 2026-11-27 "구루 평가 항목이 미실행되는 종목의 경우 이유를 분석하고 최대한 실행되도록 하라").

원인(2026-11-27 집계, 데이터팩 guru 27개): '미확인' 56건 중 사람과 문화 16건 — 대부분 "위임장·유가증권보고서로 대조하지 못했다".
모델이 매 회차 서류를 찾다 못 여는 대신, 여기서 1차 원천의 숫자를 먼저 모아 datapack "people_pack"에 쓴다.
  미국 상장(SEC 제출사): data.sec.gov submissions(키 불필요, User-Agent = sec_filings._ua — 마스터 이메일 금지)
    · 최신 위임장(DEF 14A)·연차보고서(10-K/20-F) 날짜·주소
    · 최근 12개월 Form 4 장내 매수(P)·매도(S) 건수와 금액, 그중 사전 계획(10b5-1) 매도 건수 — 최대 40건 본문 XML
  일본(EDINET): 키(EDINET_API_KEY)가 있으면 radar/edinet.py 목록으로 유가증권보고서 주소 — 없으면 '키 대기'
  그 밖: 경로 없음으로 적는다(모델이 연차보고서로 판정)
판정은 하지 않는다 — 숫자만. 매매·비중 지시가 아니다.
사용: py scripts/tenbagger/people_pack.py <회사 id> [--write]
"""
import json
import re
import sys
import time
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "radar"))
from pollers import common, sec_filings  # noqa: E402

CO = ROOT / "knowledge" / "models" / "companies"
SUB = "https://data.sec.gov/submissions/CIK{cik:0>10}.json"
ARCH = "https://www.sec.gov/Archives/edgar/data/{cik}/{acc}/{doc}"
MAX_F4 = 40


def _get(url):
    time.sleep(0.15)   # SEC 초당 10회 이하
    b = common.http_get(url, headers={"User-Agent": sec_filings._ua()}, timeout=30)
    return b.decode("utf-8", "replace") if isinstance(b, bytes) else b


def form4(xml):
    """Form 4 본문 → [(코드 P/S, 금액, 사전계획 여부)] — 비파생 거래만"""
    plan = bool(re.search(r"<aff10b5One>\s*(1|true)", xml, re.I)) or "10b5-1" in xml
    out = []
    for t in re.findall(r"<nonDerivativeTransaction>(.*?)</nonDerivativeTransaction>", xml, re.S):
        code = re.search(r"<transactionCode>\s*(\w)", t)
        sh = re.search(r"<transactionShares>\s*<value>\s*([\d.]+)", t)
        px = re.search(r"<transactionPricePerShare>\s*<value>\s*([\d.]+)", t)
        if code and code.group(1) in ("P", "S"):
            out.append((code.group(1), float(sh.group(1)) * float(px.group(1)) if sh and px else 0.0, plan))
    return out


def summarize(rows):
    b = [r for r in rows if r[0] == "P"]
    s = [r for r in rows if r[0] == "S"]
    return {"buy_n": len(b), "buy_usd": round(sum(r[1] for r in b)), "sell_n": len(s), "sell_usd": round(sum(r[1] for r in s)),
            "sell_planned_n": sum(1 for r in s if r[2])}


def sec(ticker, name=None, today=None):
    today = today or date.today()
    st = common.load_state("sec_filings", {}) or {}
    cik = sec_filings.cik_for(ticker, st, name)
    if not cik:
        return {"route": "sec", "note": f"CIK 못 찾음({ticker})"}
    d = json.loads(_get(SUB.format(cik=cik)))
    r = d.get("filings", {}).get("recent", {})
    rows = list(zip(r.get("form", []), r.get("filingDate", []), r.get("accessionNumber", []), r.get("primaryDocument", [])))
    out = {"route": "sec", "cik": str(cik), "as_of": today.isoformat()}

    def doc(f, dt, acc, pd):
        return {"form": f, "date": dt, "url": ARCH.format(cik=int(cik), acc=acc.replace("-", ""), doc=pd)}
    for key, forms in (("proxy", ("DEF 14A",)), ("annual", ("10-K", "20-F", "40-F"))):
        hit = next((x for x in rows if x[0] in forms), None)
        if hit:
            out[key] = doc(*hit)
    since = (today - timedelta(days=365)).isoformat()
    f4 = [x for x in rows if x[0] == "4" and x[1] >= since]
    tx = []
    for f, dt, acc, pd in f4[:MAX_F4]:
        try:
            tx += form4(_get(ARCH.format(cik=int(cik), acc=acc.replace("-", ""), doc=pd.split("/")[-1])))
        except Exception as e:   # 한 건 실패는 건너뛴다
            out.setdefault("errors", []).append(type(e).__name__)
    out["form4_12m"] = {"filings": len(f4), "read": min(len(f4), MAX_F4), **summarize(tx)}
    return out


def edinet(code):
    k = common.load_env().get("EDINET_API_KEY")
    if not k:
        return {"route": "edinet", "note": "키 대기(EDINET_API_KEY) — 유가증권보고서 '役員の状況'은 모델이 회사 IR 자료실로 본다"}
    return {"route": "edinet", "note": f"EDINET 키 있음 — 증권코드 {code} 유가증권보고서는 radar/edinet.py 목록에서 찾는다"}


def build(dp):
    t = str(dp.get("ticker") or "")
    if re.fullmatch(r"\d{4}", t) or t.endswith(".T"):
        return edinet(t[:4])
    # 미국 티커는 달러 단위 데이터팩만 — 유럽 상장(ENR=Siemens Energy, ASM=ASMI)이 미국 동명 티커(Energizer·Avino)로 잘못 가지 않게(2026-11-27)
    if re.fullmatch(r"[A-Z][A-Z.\-]{0,5}", t) and "$" in str(dp.get("unit") or ""):
        return sec(t, dp.get("name"))
    return {"route": "none", "note": f"자동 경로 없음({t}) — 연차보고서 경영진·보상 절로 판정"}


def line(pp):
    """guru 사람 관점 '계산한 숫자' 칸 한 줄"""
    if not pp:
        return "서류로 확인(people_pack 없음 — py scripts/tenbagger/people_pack.py <id> --write)"
    f = pp.get("form4_12m")
    bits = []
    if f:
        bits.append(f"최근 12개월 Form 4 {f['filings']}건 — 장내 매수 {f['buy_n']}건 ${f['buy_usd'] / 1e6:,.1f}M · 매도 {f['sell_n']}건 ${f['sell_usd'] / 1e6:,.1f}M"
                    + (f"(사전 계획 {f['sell_planned_n']}건)" if f.get("sell_n") else ""))
    for k, nm in (("proxy", "위임장"), ("annual", "연차보고서")):
        if pp.get(k):
            bits.append(f"{nm} {pp[k]['date']}")
    if pp.get("note"):
        bits.append(pp["note"])
    return " · ".join(bits) or "서류로 확인"


def main(argv):
    sys.stdout.reconfigure(encoding="utf-8")
    if not argv:
        print(__doc__)
        return 0
    p = CO / argv[0] / "datapack.json"
    dp = json.loads(p.read_text(encoding="utf-8"))
    pp = build(dp)
    print(json.dumps(pp, ensure_ascii=False, indent=1))
    print("한 줄:", line(pp))
    if "--write" in argv:
        dp["people_pack"] = pp
        p.write_text(json.dumps(dp, ensure_ascii=False, indent=1), encoding="utf-8")
        print("datapack people_pack 저장")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
