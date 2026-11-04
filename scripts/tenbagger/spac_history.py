"""SPAC 과거 표본 4단계 (마스터 지시 2026-11-04 "4단계 진행", 설계 knowledge/methods/spac_discovery_design.md 3절 기저율·6절)

2021~2025년 합병 종결(8-K Item 2.01 + 종결 상투 문구 'consummated the previously announced business combination') 스팩을 EDGAR 전문 검색으로 모아 종결 뒤 수익 분포(기저율)를 낸다.
  collect  종결 8-K 목록 → knowledge/models/spac/history.csv(cik, 이름, 티커, 종결일, 서류 폴더)
  theme    종결 서류로 테마 판정(radar/pollers/spac_theme.classify) → theme 칸
  returns  모델이 Fiscal.ai execute_code로 받은 종가 묶음(scripts/tenbagger/spac_history.js 출력 JSON)을 합친다 → r6m·r12m·r24m·max24m·현재 배수
  rates    기저율: 중앙값·하위/상위 분위·2배·3배·10배 도달 비율·−50% 이하 비율, 테마 일치/불일치·연도별 → knowledge/models/spac/base_rates.json
생존 편향: 상장폐지·티커 변경으로 시세를 못 받은 종목은 '시세 없음'으로 따로 센다(대부분 실패 종목이므로 기저율은 낙관 쪽으로 기운다 — 결과에 표시).
사용: py scripts/tenbagger/spac_history.py collect 2021 2025 | theme [--limit N] [--priced] | returns <json> | rates
"""
import csv
import json
import re
import statistics as st
import sys
import time
import urllib.parse
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "radar"))
from pollers import common, sec_filings, spac_theme  # noqa: E402

DIR = ROOT / "knowledge" / "models" / "spac"
HIST = DIR / "history.csv"
COLS = ["cik", "name", "tickers", "close_date", "url", "theme", "theme_hits", "key", "r6m", "r12m", "r24m", "max24m", "now_x", "px_status"]
EFTS = "https://efts.sec.gov/LATEST/search-index"
PHRASES = ['"consummated the previously announced business combination"', '"completed the previously announced business combination"',
           '"consummation of the business combination"']   # 종결 8-K 상투 문구(2026-11-04 표본 수집 — 한 문구로는 2021년 84건뿐)
NAME_RE = re.compile(r"^(.*?)\s*(?:\(([^)]*)\))?\s*\(CIK (\d+)\)")


def load():
    if not HIST.exists():
        return {}
    with HIST.open(encoding="utf-8", newline="") as f:
        return {r["cik"]: r for r in csv.DictReader(f)}


def save(rows):
    DIR.mkdir(parents=True, exist_ok=True)
    with HIST.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, COLS, restval="")
        w.writeheader()
        w.writerows(sorted(rows.values(), key=lambda r: r["close_date"]))


def collect(y0, y1):
    rows = load()
    for y in range(y0, y1 + 1):
        for q0, q1 in ((f"{y}-01-01", f"{y}-03-31"), (f"{y}-04-01", f"{y}-06-30"), (f"{y}-07-01", f"{y}-09-30"), (f"{y}-10-01", f"{y}-12-31")):   # 분기씩(페이지 상한·서버 오류 회피)
            for phrase in PHRASES:
                for page in range(10):
                    # 종결 8-K는 대개 SIC를 피인수 업종으로 바꾼 뒤 낸다(SIC 6770만 보면 2021~2025에 104건뿐, 2026-11-04 확인) — 종결 상투 문구로 찾는다
                    p = {"q": phrase, "forms": "8-K", "dateRange": "custom", "startdt": q0, "enddt": q1, "from": page * 100}
                    try:
                        d = json.loads(common.http_get(EFTS + "?" + urllib.parse.urlencode(p), headers={"User-Agent": sec_filings._ua()}, timeout=40))
                    except Exception as e:   # 깊은 페이지에서 500이 난다 — 그 창은 거기까지
                        print(f"{q0}~{q1} p{page}: {type(e).__name__}")
                        break
                    hs = d.get("hits", {}).get("hits", [])
                    for h in hs:
                        s = h["_source"]
                        if "2.01" not in (s.get("items") or []):
                            continue
                        m = NAME_RE.match((s.get("display_names") or [""])[0])
                        if not m:
                            continue
                        cik = str(int(m.group(3)))
                        if cik in rows and rows[cik]["close_date"] <= s.get("file_date", ""):
                            continue   # 같은 회사의 첫 2.01만(종결일)
                        adsh = s.get("adsh", "")
                        rows[cik] = {**rows.get(cik, {}), "cik": cik, "name": m.group(1).strip(), "tickers": (m.group(2) or "").replace(" ", ""),
                                     "close_date": s.get("file_date"), "url": f"https://www.sec.gov/Archives/edgar/data/{cik}/{adsh.replace('-', '')}/"}
                    if len(hs) < 100:
                        break
                    time.sleep(0.3)
    save(rows)
    return len(rows)


def theme(limit=None, priced_only=False):
    """priced_only: 시세를 받은 표본만(기저율에 쓰이는 행) — 전체 509건은 SEC 요청이 1천 건을 넘는다"""
    rows = load()
    c = spac_theme.cfg()
    todo = [r for r in rows.values() if not r.get("theme_hits") and (not priced_only or r.get("px_status") == "ok")]
    for r in todo[:limit]:
        try:
            res = spac_theme.classify(r["url"], c)
            r["theme"], r["theme_hits"] = res["theme"], str(res["hits"])
        except Exception as e:
            r["theme_hits"] = f"오류 {type(e).__name__}"
    save(rows)
    return sum(1 for r in rows.values() if r.get("theme")), len(todo)


def merge_returns(path):
    rows = load()
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if isinstance(data, list):   # 압축 형식 [cik, r6m, r12m, r24m, max24m, now_x] — 시세 없음은 [cik]
        data = {str(x[0]): ({"r6m": x[1], "r12m": x[2], "r24m": x[3], "max24m": x[4], "now_x": x[5], "px_status": "ok"} if len(x) > 1 else {"px_status": "시세 없음"}) for x in data}
    for cik, v in data.items():
        if cik in rows:
            rows[cik].update({k: ("" if v.get(k) is None else v[k]) for k in ("key", "r6m", "r12m", "r24m", "max24m", "now_x", "px_status")})
    save(rows)
    return len(data)


def q(v, p):
    v = sorted(v)
    return round(v[min(len(v) - 1, max(0, int(p * (len(v) - 1))))], 3) if v else None


def summarize(rs):
    out = {"n": len(rs)}
    for h in ("r6m", "r12m", "r24m"):
        v = [float(r[h]) for r in rs if r.get(h) not in ("", None)]
        out[h] = {"n": len(v), "median": q(v, 0.5), "p10": q(v, 0.1), "p90": q(v, 0.9), "lt_minus50": round(sum(x <= -0.5 for x in v) / len(v), 3) if v else None}
    m = [float(r["max24m"]) for r in rs if r.get("max24m") not in ("", None)]
    out["max24m"] = {"n": len(m), "ge2x": round(sum(x >= 2 for x in m) / len(m), 3) if m else None, "ge3x": round(sum(x >= 3 for x in m) / len(m), 3) if m else None,
                     "ge10x": round(sum(x >= 10 for x in m) / len(m), 4) if m else None}
    return out


def rates():
    rows = list(load().values())
    priced = [r for r in rows if r.get("px_status") == "ok"]
    res = {"as_of": date.today().isoformat(), "collected": len(rows), "priced": len(priced),
           "no_price": sum(1 for r in rows if r.get("px_status") and r["px_status"] != "ok"),
           "survivorship_note": "시세를 못 받은 종목(상장폐지·티커 변경)은 빠져 있다 — 실패 종목이 많아 기저율은 낙관 쪽으로 기운다",
           "all": summarize(priced), "theme_match": summarize([r for r in priced if r.get("theme")]), "theme_none": summarize([r for r in priced if not r.get("theme")]),
           "by_year": {y: summarize([r for r in priced if r["close_date"][:4] == y]) for y in sorted({r["close_date"][:4] for r in priced})},
           "by_theme": {t: summarize([r for r in priced if r.get("theme") == t]) for t in sorted({r["theme"] for r in priced if r.get("theme")})}}
    (DIR / "base_rates.json").write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
    return res


def main(argv):
    sys.stdout.reconfigure(encoding="utf-8")
    cmd = argv[0]
    if cmd == "collect":
        print(collect(int(argv[1]), int(argv[2])))
    elif cmd == "theme":
        print(theme(int(argv[argv.index("--limit") + 1]) if "--limit" in argv else None, priced_only="--priced" in argv))
    elif cmd == "returns":
        print(merge_returns(argv[1]))
    elif cmd == "keys":   # 시세를 받을 목록(모델이 execute_code에 넣는다)
        print(json.dumps([[r["cik"], r["tickers"], r["close_date"]] for r in load().values() if not r.get("px_status")], ensure_ascii=False))
    else:
        print(json.dumps(rates(), ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main(sys.argv[1:])
