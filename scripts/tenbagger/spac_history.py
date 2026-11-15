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
from datetime import date, timedelta
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "radar"))
from pollers import common, sec_filings, spac_theme  # noqa: E402

DIR = ROOT / "knowledge" / "models" / "spac"
HIST = DIR / "history.csv"
COLS = ["cik", "name", "tickers", "close_date", "url", "theme", "theme_hits",
        # 2026-11-15 재계산(ADR-044): 스팩 여부·이후 운명(EDGAR)·Fiscal 키·종결가(분할 전 원가)·마지막 시세일 — 생존 편향·진입가 기준을 다루려고 더했다
        "spac_like", "spac_marks", "doc_tickers", "exch", "fate", "fate_date", "fiscal_key",
        "key", "listing", "base_date", "base_px", "last_date", "term_r", "r6m", "r12m", "r24m", "max24m", "now_x", "px_status"]
SUB = "https://data.sec.gov/submissions/CIK{cik:0>10}.json"
SPAC_NAME_RE = re.compile(r"acqui|merger corp|\bspac\b|blank.?check", re.I)   # 옛 이름에 이것이 있으면 스팩 출신(이름에 없는 스팩도 많다 — 본문 표지로 보완)
MARKS = {"trust": r"trust account", "bc": r"blank[- ]check|special purpose acquisition", "red": r"redemption|redeem", "pub": r"public (?:shares|stockholders|shareholders)",
         "spon": r"Sponsor", "bca": r"Business Combination Agreement", "pipe": r"PIPE",
         "acq": r"Acquisition (?:Corp|Corporation|Company|Holdings|Ltd|Limited|Inc)"}   # 지주회사 구조 종결 8-K는 신탁 계좌를 안 쓰고 Sponsor·BCA·PIPE 정의어를 쓴다(D-Wave·KORE·Vacasa, 2026-11-15)
TICK_CTX_RE = re.compile(r"symbols?", re.I)
TICK_RE = re.compile(r"[“\"'‘]\s*([A-Z]{1,5}(?:[ .\-]?(?:WS|WT|W|U|UN|R|RT))?)\s*[”\"'’]")
NEW_CTX_RE = re.compile(r"began|begin|commenc|will trade|expected to trade|start(?:ed)? trading|is listed|are listed|now trad", re.I)
OLD_CTX_RE = re.compile(r"prior to|previously|formerly|ceased|were listed|was listed", re.I)
EXCH_RE = re.compile(r"NYSE American|NYSE MKT|Nasdaq|NASDAQ|New York Stock Exchange|NYSE")
MERGER_FORMS = {"DEFM14A", "PREM14A", "DEFM14C", "PREM14C", "SC 14D9", "SC 14D9/A", "SC TO-T", "SC TO-T/A", "SC 13E3", "SC 13E3/A", "SCHEDULE 13E-3"}
SETTLE_D = 60   # 종결 직후 이만큼 안의 25·15·5.01은 스팩 증권 정리(유닛·워런트 폐지, 지배권 변동 = 합병 자체)로 보고 운명 판정에서 뺀다
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


def sec_get(url):
    time.sleep(0.25)   # 초당 4회 이하(SEC 공정 접근 10회/초 — 프로젝트 규칙 5회/초)
    return common.http_get(url, headers={"User-Agent": sec_filings._ua()}, timeout=60)


def marks_of(text):
    return {k: len(re.findall(p, text, re.I)) for k, p in MARKS.items()}


def lifecycle(sub, close_date):
    """제출 목록에 스팩 생애가 보이나 — 젊은 등록자(첫 제출이 종결 4년 안)가 종결 전에 IPO 투자설명서(424B4)와 합병 서류(425·S-4·위임장)를 냈다"""
    rec = (sub.get("filings") or {}).get("recent") or {}
    fd = [(f, d) for f, d in zip(rec.get("form") or [], rec.get("filingDate") or []) if d < close_date]
    if not fd or (sub.get("filings") or {}).get("files"):
        return False   # 최근 1천 건 밖 이력이 있으면 오래된 회사 — 젊은 스팩이 아니다
    young = min(d for _, d in fd) >= (date.fromisoformat(close_date) - timedelta(days=4 * 365)).isoformat()
    ipo = any(f in ("424B4", "424B1", "S-1", "S-1/A") for f, _ in fd)   # 스팩 IPO 투자설명서가 424B4가 아닌 경우도 있다(Novus Capital: S-1만, 2026-11-15)
    deal = any(f in ("425", "S-4", "S-4/A", "F-4", "F-4/A", "PREM14A", "DEFM14A", "DEFA14A") for f, _ in fd)
    return young and ipo and deal


def is_spac(marks, former_names, life=False):
    """스팩 종결인가 — 종결 8-K 본문의 신탁 계좌·환매 표지, 옛 이름(…Acquisition Corp), 제출 목록의 스팩 생애 중 하나.
    일반 인수합병 종결 8-K도 같은 상투 문구를 쓴다(2026-11-15 점검: Carlisle·First Busey 등)"""
    if life or any(SPAC_NAME_RE.search(n or "") for n in former_names):   # former_names = 종결 무렵(±400일)까지 쓰던 이름만(edgar가 거른다)
        return True
    if marks.get("red", 0) >= 1 and (marks.get("bca", 0) >= 1 or marks.get("acq", 0) >= 1 or marks.get("wt", 0) >= 1):
        return True   # 환매 + '합병 계약(BCA)'·'…Acquisition Corp' 이름·상장 워런트 티커 — 지주회사 구조 종결 8-K(KORE·Vacasa·D-Wave, 2026-11-15)
    if marks.get("spon", 0) >= 1 and (marks.get("bca", 0) >= 1 or marks.get("pipe", 0) >= 1):
        return True   # 대문자 정의어 'Sponsor'(스폰서) + 합병 계약·PIPE — 일반 인수합병은 'Sponsor'를 거의 정의어로 쓰지 않는다
    return marks.get("trust", 0) >= 1 and (marks.get("red", 0) >= 1 or marks.get("pub", 0) >= 1) or marks.get("bc", 0) >= 1


def tickers_in(text):
    """종결 서류 문장에서 새 티커 — '…began trading … under the symbols “CLOV” and “CLOVW”'. 옛 스팩 티커 문장(prior to·previously)은 뒤로 미룬다"""
    new, old = [], []
    for m in TICK_CTX_RE.finditer(text):
        ctx = text[max(0, m.start() - 220): m.start()]
        win = text[m.end(): m.end() + 160]
        toks = [t.replace(" ", "").replace(".", "-") for t in TICK_RE.findall(win)]
        if not toks:
            continue
        (old if OLD_CTX_RE.search(ctx) and not NEW_CTX_RE.search(ctx[-120:]) else new).extend(toks)
    out = []
    for t in new + old:
        if t not in out:
            out.append(t)
    base = [t for t in out if not re.search(r"(?:-?WS|-?WT|-U|-UN|-R|-RT)$", t) and not (len(t) >= 4 and t[-1] in "WUR" and t[:-1] in out)]
    return base[:4], (EXCH_RE.search(text).group(0) if EXCH_RE.search(text) else "")


def fate_of(sub, close_date, today=None):
    """종결 뒤 운명(EDGAR 제출 목록) — 파산(8-K 1.03) > 피인수(종결 60일 뒤 5.01 또는 합병 위임장·공개매수 + 25·15) > 상장폐지(25-NSE·25, 최근 정기보고서 없음) > 등록 말소(15) > 보고 중 > 미확인"""
    today = today or date.today().isoformat()
    rec = (sub.get("filings") or {}).get("recent") or {}
    forms, dates, items = rec.get("form") or [], rec.get("filingDate") or [], rec.get("items") or []
    cut = (date.fromisoformat(close_date) + timedelta(days=SETTLE_D)).isoformat()
    after = [(f, d, (items[i] if i < len(items) else "") or "") for i, (f, d) in enumerate(zip(forms, dates)) if d >= cut]
    first = lambda pred: min((d for f, d, it in after if pred(f, it)), default="")   # noqa: E731
    bk = first(lambda f, it: f.startswith("8-K") and "1.03" in it)
    ctrl = first(lambda f, it: f.startswith("8-K") and "5.01" in it)
    mform = first(lambda f, it: f in MERGER_FORMS)
    f25 = first(lambda f, it: f in ("25", "25-NSE"))
    f15 = first(lambda f, it: f.startswith("15"))
    periodic = max((d for f, d in zip(forms, dates) if f in ("10-K", "10-Q", "20-F", "40-F", "10-KT", "10-K/A", "10-Q/A")), default="")
    recent = periodic >= (date.fromisoformat(today) - timedelta(days=460)).isoformat()
    if bk:
        return "bankrupt", bk
    if (ctrl or mform) and (f25 or f15 or not recent):
        return "acquired", ctrl or f25 or f15 or mform
    if f25 and not recent:
        return "delisted", f25
    if f15:
        return "deregistered", f15
    if recent:
        return "reporting", periodic
    return "unknown", periodic


def edgar(limit=None, redo=False):
    """스팩 여부·새 티커(종결 8-K 본문) + 이후 운명(제출 목록). 한 행에 SEC 요청 2~4회 — 509행이면 약 6~10분(백그라운드로)"""
    rows = load()
    weak = lambda r: r.get("spac_like") == "1" and "spon:" not in (r.get("spac_marks") or "") and not re.search(r"trust:[1-9]|bc:[1-9]|life:1", r.get("spac_marks") or "")   # noqa: E731
    todo = [r for r in rows.values() if (redo is True) or (redo == "0" and r.get("spac_like") == "0") or (redo == "weak" and weak(r)) or not r.get("spac_like")]
    done, errs = 0, []
    for r in todo[:limit]:
        try:
            sub = json.loads(sec_get(SUB.format(cik=r["cik"])))
            lo = (date.fromisoformat(r["close_date"]) - timedelta(days=400)).isoformat()
            hi = (date.fromisoformat(r["close_date"]) + timedelta(days=400)).isoformat()
            # 옛 스팩 이름은 종결 무렵에 바뀐 것만 — 몇 해 전 스팩 출신 회사의 일반 인수합병(Kinetik·IEA, 2026-11-15)을 거른다
            former = [x.get("name") for x in sub.get("formerNames") or [] if lo <= str(x.get("to") or "")[:10] <= hi] + [sub.get("name")]   # 지금 이름이 스팩 이름이면(지주회사 구조로 스팩 자신이 낸 종결 8-K) 그대로
            rec = (sub.get("filings") or {}).get("recent") or {}
            adsh = r["url"].rstrip("/").split("/")[-1]
            prim = next((p for a, p in zip(rec.get("accessionNumber") or [], rec.get("primaryDocument") or []) if a.replace("-", "") == adsh), None)
            urls = [r["url"] + prim] if prim else []
            if not urls:   # 제출 목록 최근 1천 건 밖 — 폴더 목록에서 본문 찾기
                d = json.loads(sec_get(r["url"].rstrip("/") + "/index.json"))
                items = [i for i in d.get("directory", {}).get("item", []) if i["name"].lower().endswith((".htm", ".html")) and "index" not in i["name"].lower()]
                body = sorted([i for i in items if not re.search(r"ex-?\d", i["name"], re.I)], key=lambda i: -int(i.get("size") or 0))
                urls = [r["url"] + i["name"] for i in body[:1]]
            text = ""
            for u in urls:
                text += " " + re.sub(r"\s+", " ", common.strip_tags(sec_get(u).decode("utf-8", "replace")))[:200000]
            mk = marks_of(text)
            ticks, ex = tickers_in(text)
            if not ticks:   # 본문에 티커 문장이 없으면 보도자료(EX-99.1)
                d = json.loads(sec_get(r["url"].rstrip("/") + "/index.json"))
                pr = [i["name"] for i in d.get("directory", {}).get("item", []) if re.search(r"ex-?99", i["name"], re.I) and i["name"].lower().endswith((".htm", ".html"))]
                if pr:
                    t2 = re.sub(r"\s+", " ", common.strip_tags(sec_get(r["url"] + pr[0]).decode("utf-8", "replace")))[:80000]
                    ticks, ex2 = tickers_in(t2)
                    ex = ex or ex2
                    mk = {k: mk[k] + v for k, v in marks_of(t2).items()}
            fate, fd = fate_of(sub, r["close_date"])
            life = lifecycle(sub, r["close_date"])
            alltk = [t for t in (r.get("tickers") or "").split(",") + list(sub.get("tickers") or []) if t]
            mk["wt"] = int(any(re.search(r"(?:-WT|-WS|\.WS)$", t) or (len(t) >= 4 and t.endswith("W") and t[:-1] in alltk) for t in alltk))   # 상장 워런트 = 스팩 출신 표지
            mk["life"] = int(life)
            r.update({"spac_like": "1" if is_spac(mk, former, life) else "0", "spac_marks": "|".join(f"{k}:{v}" for k, v in mk.items()),
                      "doc_tickers": ",".join(ticks), "exch": ex, "fate": fate, "fate_date": fd,
                      "tickers": r.get("tickers") or ",".join(sub.get("tickers") or [])})
            done += 1
        except Exception as e:
            errs.append(f"{r['cik']}: {type(e).__name__} {str(e)[:60]}")
        if done and done % 25 == 0:
            save(rows)
            print(f"… {done}/{len(todo[:limit])}", flush=True)
    save(rows)
    return {"done": done, "errors": errs[:10], "n_err": len(errs)}


def fiscal_map(path):
    """Fiscal.ai companies_list를 CIK로 맞춘 결과('cik 키' 줄) → fiscal_key. 티커가 바뀌었거나 지주회사 구조여도 CIK로 잡는다(2026-11-15: 509건 중 259건)"""
    rows = load()
    n = 0
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        p = line.split()
        if len(p) >= 2 and p[0] in rows:
            rows[p[0]]["fiscal_key"] = p[1]
            n += 1
    save(rows)
    return n


def price_keys(r):
    """시세 키 후보 — Fiscal CIK 일치 → 서류·EDGAR 티커 × 거래소. 옛 스팩 티커가 섞여도 JS가 '종결 뒤 20거래일 이상 시세'로 거른다"""
    out = [r["fiscal_key"]] if r.get("fiscal_key") else []
    ticks = [t for t in (r.get("doc_tickers") or "").split(",") + (r.get("tickers") or "").split(",") if t]
    ticks = [t for t in ticks if not re.search(r"(?:-?WS|-?WT|-U|-UN|-R|-RT)$", t) and not (len(t) >= 4 and t[-1] in "WUR" and t[:-1] in ticks)]
    ex = (r.get("exch") or "").upper()
    order = ["NYSEAM", "NYSE", "NASDAQ"] if "AMERICAN" in ex or "MKT" in ex else (["NYSE", "NASDAQ", "NYSEAM"] if "NYSE" in ex or "NEW YORK" in ex else ["NASDAQ", "NYSE", "NYSEAM"])
    for t in ticks:
        for e in order:
            k = f"{e}_{t.replace('.', '-')}"
            if k not in out:
                out.append(k)
    return out[:7]


PX_FIELDS = ("key", "listing", "base_date", "base_px", "last_date", "term_r", "r6m", "r12m", "r24m", "max24m", "now_x", "px_status")


def merge_returns(path):
    """spac_history.js 출력 합치기. 새 형식 {"out": [[cik, key, listing, base_date, base_px, last_date, term_r, r6m, r12m, r24m, max24m, now_x, n_splits] | [cik]], "pending": […]}
    옛 압축 형식 [cik, r6m, r12m, r24m, max24m, now_x]도 받는다. 이미 'ok'인 행을 '시세 없음'으로 덮지 않는다(다른 키로 다시 찾은 결과가 뒤에 올 수 있다)"""
    rows = load()
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if isinstance(data, dict) and "out" in data:
        data = data["out"]
    if isinstance(data, list):
        conv = {}
        for x in data:
            cik = str(x[0])
            if len(x) >= 12:
                conv[cik] = dict(zip(PX_FIELDS, list(x[1:12]) + ["ok"]))
            elif len(x) > 1:   # 옛 형식
                conv[cik] = {"r6m": x[1], "r12m": x[2], "r24m": x[3], "max24m": x[4], "now_x": x[5], "px_status": "ok"}
            else:
                conv[cik] = {"px_status": "시세 없음"}
        data = conv
    n = 0
    for cik, v in data.items():
        if cik in rows and not (v.get("px_status") != "ok" and rows[cik].get("px_status") == "ok"):
            rows[cik].update({k: ("" if v.get(k) is None else v[k]) for k in PX_FIELDS if k in v})
            n += 1
    save(rows)
    return n


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


def rates_v1():
    """2026-11-04 4단계 방식(시세 받은 행만, 스팩 여부·상장폐지 보정 없음) — 비교용으로 남긴다. 결과를 파일에 쓰지 않는다"""
    rows = list(load().values())
    priced = [r for r in rows if r.get("px_status") == "ok"]
    res = {"as_of": date.today().isoformat(), "collected": len(rows), "priced": len(priced),
           "no_price": sum(1 for r in rows if r.get("px_status") and r["px_status"] != "ok"),
           "survivorship_note": "시세를 못 받은 종목(상장폐지·티커 변경)은 빠져 있다 — 실패 종목이 많아 기저율은 낙관 쪽으로 기운다",
           "all": summarize(priced), "theme_match": summarize([r for r in priced if r.get("theme")]), "theme_none": summarize([r for r in priced if not r.get("theme")]),
           "by_year": {y: summarize([r for r in priced if r["close_date"][:4] == y]) for y in sorted({r["close_date"][:4] for r in priced})},
           "by_theme": {t: summarize([r for r in priced if r.get("theme") == t]) for t in sorted({r["theme"] for r in priced if r.get("theme")})}}
    return res


# ── 2026-11-15 재계산(ADR-044): 스팩만·생존 편향 보정·종결가/$10 두 기준 ──
def hcfg():
    return (yaml.safe_load((ROOT / "config" / "spac.yaml").read_text(encoding="utf-8")) or {})["history"]


def _f(v):
    return None if v in ("", None) else float(v)


def exch_of(r):
    k = (r.get("key") or "").split("_")[0]
    if k:
        return k
    e = (r.get("exch") or "").upper()
    return "NYSEAM" if "AMERICAN" in e or "MKT" in e else ("NYSE" if "NYSE" in e or "NEW YORK" in e else "NASDAQ")


def usable(r, c):
    """기저율에 쓸 시세인가 → (참/거짓, 이유). 시세 시작이 종결보다 한참 늦으면(티커 변경 뒤 이력만, 파산 뒤 재상장 등) 같은 주식의 종결 뒤 수익이 아니다"""
    if r.get("px_status") != "ok" or not r.get("base_date"):
        return False, "시세 없음"
    lag = (date.fromisoformat(r["base_date"]) - date.fromisoformat(r["close_date"])).days
    if lag > c["lag_max_d"]:
        return False, "기준일 지연"
    if r.get("listing") == "suspended" and _f(r.get("max24m")) == 1 and abs(_f(r.get("term_r")) or 0) < 1e-9:
        return False, "시세 정지"
    return True, ""


def horizon(r, h, c, today):
    """h(r6m·r12m·r24m) 수익(종결가 기준) → (값, 종류). 창 안에서 상장폐지돼 시세가 끝났으면 마지막 값 × 상장폐지 보정
    (Shumway 1997 NYSE·AMEX −30%, Shumway & Warther 1999 나스닥 −55% — 피인수는 0). 창이 아직 안 찼으면 (None, 'early')"""
    v = _f(r.get(h))
    if v is not None:
        return v, "obs"
    end = date.fromisoformat(r["base_date"]) + timedelta(days=c["h_days"][h])
    if end > today:
        return None, "early"   # 창이 덜 찼으면 끝난 종목(상장폐지)만 넣으면 실패 쪽으로 기운다 — 살아 있는 종목과 똑같이 뺀다
    last = date.fromisoformat(r["last_date"]) if r.get("last_date") else None
    if r.get("listing") in ("delisted", "suspended") and last and last < end and _f(r.get("term_r")) is not None:
        d = 0.0 if r.get("fate") == "acquired" else c["delist_ret"].get(exch_of(r), c["delist_ret"]["default"])
        return (1 + _f(r["term_r"])) * (1 + d) - 1, "term"
    return None, ("early" if end > today else "gap")


def failed_within(r, h, c, today=None):
    """시세 없는 스팩이 h 창 안에 파산·상장폐지됐으면 실패값(기본 −100%) — 중앙값·−50% 이하 비율은 '그보다 나쁘다'만 맞으면 정확하다.
    창이 아직 덜 찬 종결은 넣지 않는다(살아 있는 종목도 빠지므로)"""
    if r.get("fate") not in c["fail_fates"] or not r.get("fate_date"):
        return None
    end = date.fromisoformat(r["close_date"]) + timedelta(days=c["h_days"][h])
    if end > (today or date.today()):
        return None
    return c["fail_value"] if r["fate_date"] <= end.isoformat() else None


def dist(v):
    v = sorted(v)
    n = len(v)
    return {"n": n, "median": q(v, 0.5), "p10": q(v, 0.1), "p90": q(v, 0.9),
            "lt_minus50": round(sum(x <= -0.5 for x in v) / n, 3) if n else None, "lt_minus90": round(sum(x <= -0.9 for x in v) / n, 3) if n else None}


def tails(m):
    n = len(m)
    return {"n": n, **{f"ge{k}x": (round(sum(x >= k for x in m) / n, 4) if n else None) for k in (2, 3, 10)}}


def block(rs, fails, c, today, ten=False):
    """한 묶음의 기저율. rs = 쓸 수 있는 시세 행, fails = 시세 없는 실패 행(보정값에만). ten=True면 $10(스팩 IPO가) 기준"""
    out = {}
    lo, hi = c["px_band"]
    for h in ("r6m", "r12m", "r24m"):
        vals, kinds = [], {"obs": 0, "term": 0, "fail": 0}
        for r in rs:
            v, k = horizon(r, h, c, today)
            if v is None:
                continue
            if ten:
                bp = _f(r.get("base_px"))
                if bp is None or not (lo <= bp <= hi):
                    continue
                v = (1 + v) * bp / 10 - 1
            vals.append(v)
            kinds[k] += 1
        for r in fails:
            v = failed_within(r, h, c, today)
            if v is not None:
                vals.append(v)
                kinds["fail"] += 1
        out[h] = {**dist(vals), **{f"n_{k}": n for k, n in kinds.items()}}
    m = []
    for r in rs:
        mx = _f(r.get("max24m"))
        end24 = (date.fromisoformat(r["base_date"]) + timedelta(days=c["h_days"]["r24m"])).isoformat()
        full = end24 <= today.isoformat()
        if ten:
            bp = _f(r.get("base_px"))
            if bp is None or not (lo <= bp <= hi):
                continue
            mx = None if mx is None else mx * bp / 10
        if mx is None or not full:
            continue   # 24개월 창이 다 차지 않은 행은 꼬리 비율에서 뺀다(아직 못 오른 것과 안 오른 것을 가를 수 없다 — 창 안 상장폐지도 같은 규칙)
        m.append(mx)
    nf = sum(1 for r in fails if failed_within(r, "r24m", c, today) is not None)
    m += [0.0] * nf
    out["max24m"] = {**tails(m), "n_fail": nf}
    return out


def rates(today=None):
    """기저율 = 스팩 종결만(spac_like), 쓸 수 있는 시세 + (보정값) 시세 없는 파산·상장폐지. 종결가 기준과 $10 기준을 따로 낸다(Gahng·Ritter·Zhang 2023 표 8 — 진입가에 따라 답이 바뀐다).
    재현: py scripts/tenbagger/spac_history.py rates (history.csv만 읽는다)"""
    c = hcfg()
    today = today or date.today()
    rows = list(load().values())
    spac, seen, dup = [], set(), 0
    for r in sorted((r for r in rows if r.get("spac_like") == "1"), key=lambda r: (r["close_date"], -len(r.get("px_status") or ""))):
        tk = ((r.get("doc_tickers") or r.get("tickers") or "").split(",") or [""])[0]
        k = r.get("key") if r.get("px_status") == "ok" and r.get("key") else (f"T:{tk}" if tk else f"C:{r['cik']}")
        if k in seen:   # 같은 거래가 스팩 CIK와 지주회사 CIK로 두 번 잡힌 것(D-Wave·Selexis 등, 2026-11-15)
            dup += 1
            continue
        seen.add(k)
        spac.append(r)
    use, why = [], {"중복 거래": dup} if dup else {}
    for r in spac:
        ok, reason = usable(r, c)
        if ok:
            use.append(r)
        else:
            why[reason] = why.get(reason, 0) + 1
    unpriced = [r for r in spac if not usable(r, c)[0]]
    fails = [r for r in unpriced if r.get("fate") in c["fail_fates"]]
    fates = {}
    for r in unpriced:
        fates[r.get("fate") or "미확인"] = fates.get(r.get("fate") or "미확인", 0) + 1

    def both(rs, fs):
        return {"close": {"priced": block(rs, [], c, today), "adjusted": block(rs, fs, c, today)},
                "ten": {"priced": block(rs, [], c, today, ten=True), "adjusted": block(rs, fs, c, today, ten=True)}}

    years = sorted({r["close_date"][:4] for r in spac})
    res = {"as_of": today.isoformat(),
           "method": "ADR-044 — 스팩만(종결 8-K 신탁 계좌·환매 표지·옛 이름·스팩 생애), 종결 8-K 날짜 뒤 첫 종가 기준(분할 조정), "
                     "창 안 상장폐지는 마지막 값 × Shumway 보정, 'adjusted'는 시세 없는 파산·상장폐지(EDGAR)를 실패(−100%)로 더한 값, "
                     "$10 기준 = (1 + 종결가 기준 수익) × 분할 전 원래 종결가 / $10 − 1",
           "collected": len(rows), "spac_like": len(spac), "non_spac": sum(1 for r in rows if r.get("spac_like") == "0"),
           "spac_unknown": sum(1 for r in rows if r.get("spac_like") not in ("0", "1")),
           "priced": len(use), "excluded": why, "unpriced_fates": fates,
           **both(use, fails),
           "by_year": {y: {"n_priced": sum(1 for r in use if r["close_date"][:4] == y),
                           **both([r for r in use if r["close_date"][:4] == y], [r for r in fails if r["close_date"][:4] == y])} for y in years},
           "theme_match": both([r for r in use if r.get("theme")], [r for r in fails if r.get("theme")]),
           "theme_none": both([r for r in use if not r.get("theme")], [r for r in fails if not r.get("theme")]),
           "survivorship_note": "priced = 시세가 남은 종목만(낙관 쪽). adjusted = 시세 없는 파산·상장폐지를 실패로 더한 값(그래도 등록 말소·미확인 운명은 빠진다). "
                                "꼬리 비율(2·3·10배)은 24개월 창이 다 찬 행만 — adjusted의 꼬리는 실패 행을 '도달 못 함'으로 센 하한이다."}
    a, t = res["close"]["adjusted"], res["ten"]["adjusted"]
    res["headline"] = {"n": len(use), "n_fail": len(fails), "r12m_median": a["r12m"]["median"], "r24m_median": a["r24m"]["median"],
                       "lt_minus50_24m": a["r24m"]["lt_minus50"], "lt_minus90_24m": a["r24m"]["lt_minus90"],
                       "ge2x_24m": a["max24m"]["ge2x"], "ge3x_24m": a["max24m"]["ge3x"], "ge10x_24m": a["max24m"]["ge10x"], "n_tail": a["max24m"]["n"],
                       "r12m_median_10": t["r12m"]["median"], "r24m_median_10": t["r24m"]["median"], "ge3x_24m_10": t["max24m"]["ge3x"]}
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
    elif cmd == "keys":   # 시세를 받을 목록(모델이 execute_code에 넣는다) — [cik, 종결일, [키 후보…]] (spac_history.js LIST)
        rs = [r for r in load().values() if not r.get("px_status") and (r.get("spac_like") != "0" or "--all" in argv)]
        lim = int(argv[argv.index("--limit") + 1]) if "--limit" in argv else len(rs)
        off = int(argv[argv.index("--offset") + 1]) if "--offset" in argv else 0
        print(json.dumps([[r["cik"], r["close_date"], price_keys(r)] for r in rs[off:off + lim]], ensure_ascii=False, separators=(",", ":")))
    elif cmd == "edgar":
        print(json.dumps(edgar(int(argv[argv.index("--limit") + 1]) if "--limit" in argv else None, redo=("0" if "--redo0" in argv else ("weak" if "--redo-weak" in argv else "--redo" in argv))), ensure_ascii=False))
    elif cmd == "fiscal-map":
        print(fiscal_map(argv[1]))
    else:
        print(json.dumps(rates(), ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main(sys.argv[1:])
