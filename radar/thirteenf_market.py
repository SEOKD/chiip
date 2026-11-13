"""13F 시장 전체 — 종목별 매입·매도 기관 수 순위 (마스터 지시 2026-11-14 "13F는 내 와치리스트 종목 말고 주식시장 종목 전체를 범위로
잡고 13F 매수 및 매입 상위 순으로 랭킹업하라", ADR-034)

수집(결정론, 모델 없음 — run_hourly 원천 src-13f-market, 회차당 시간 예산):
  ① EDGAR 전문검색(efts)으로 분기 말 다음 날부터 오늘까지 제출된 13F-HR(정정본 13F-HR/A·13F-NT 제외)을 날짜별로 모은다.
  ② 기관(CIK)마다 정보표 XML(index.json에서 primary_doc.xml이 아닌 .xml)을 받아 CUSIP별 보유 주식 수(SH, 옵션 put/call 제외)를 합친다.
  ③ 같은 기관의 직전 분기 13F-HR(data.sec.gov 제출 목록의 reportDate)도 받아 둔다(다음 분기에는 캐시를 다시 쓴다).
  캐시: radar/state/inst13f/<분기>/<CIK>.json.gz(git 제외) — 기관 이름은 저장하지 않는다(CIK는 공개 식별번호, 순위에는 쓰지 않는다).
집계(--rank): 두 분기 다 제출한 기관만 증감을 센다 — 늘린(신규 포함)·줄인(전량 매도 포함). 직전 분기 제출이 없는 기관은 보유 수에만.
  주식 분할: 종목별로 두 분기 다 보유한 기관의 주식 수 비율 중앙값이 정수배(×2·×3…)나 그 역수에 가까우면 분할로 보고 직전 보유를 맞춘다.
  종목 이름: 상위 후보 CUSIP만 OpenFIGI(무료, 키 없음 25회/분)로 티커·증권 종류를 붙이고 ETF·펀드는 뺀다. 매핑은
  knowledge/models/inst13f/cusip_map.json에 쌓는다. 못 찾으면 정보표의 발행사 이름으로 쓴다.
SEC 접속 규칙: 식별 User-Agent(.env SEC_USER_AGENT), 초당 10회 이하(요청 간 0.11초 이상, 동시 6개).
사용: py radar/thirteenf_market.py --collect [--budget-min 30]   # 이번 시즌 분기 수집(이어서)
      py radar/thirteenf_market.py --rank                        # 순위 JSON
      py radar/thirteenf_market.py --status
"""
import gzip
import json
import re
import statistics
import sys
import threading
import time
import urllib.parse
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from pollers import common  # noqa: E402

ROOT = common.ROOT
CACHE = ROOT / "radar" / "state" / "inst13f"
OUT = ROOT / "knowledge" / "models" / "inst13f"
MAP = OUT / "cusip_map.json"
EFTS = "https://efts.sec.gov/LATEST/search-index"
SOURCE_ID = "src-13f-market"
MIN_GAP = 0.11
WORKERS = 6
EXCLUDE_TYPES = ("ETP", "Mutual Fund", "Closed-End Fund", "Open-End Fund", "Unit", "Right", "Warrant")
_lock = threading.Lock()
_last = [0.0]


def ua():
    import fulltext
    return fulltext.sec_ua()


def get(url, timeout=40):
    """SEC 요청 — 전역 간격(초당 10회 이하)"""
    with _lock:
        wait = MIN_GAP - (time.time() - _last[0])
        if wait > 0:
            time.sleep(wait)
        _last[0] = time.time()
    return common.http_get(url, headers={"User-Agent": ua() or common.UA}, timeout=timeout)


def q_end(y, q):
    return date(y, 3 * q, 30 if q in (2, 3) else 31)


def prev_q(y, q):
    return (y, q - 1) if q > 1 else (y - 1, 4)


def qname(y, q):
    return f"{y}Q{q}"


def list_filings(y, q, today=None):
    """[(cik, adsh, file_date)] — 분기 말 다음 날부터 today까지 13F-HR(정정본 제외), 보고 기간이 그 분기 말인 것"""
    today = today or date.today()
    end = q_end(y, q)
    d, out, seen = end + timedelta(days=1), [], set()
    while d <= today:
        for page in range(40):
            p = {"forms": "13F-HR", "dateRange": "custom", "startdt": d.isoformat(), "enddt": d.isoformat(), "from": page * 100}
            hits = json.loads(get(EFTS + "?" + urllib.parse.urlencode(p))).get("hits", {}).get("hits", [])
            for h in hits:
                s = h["_source"]
                adsh = s.get("adsh") or h["_id"].split(":")[0]
                if adsh in seen or s.get("form") != "13F-HR" or str(s.get("period_ending", "")) != end.isoformat():
                    continue
                seen.add(adsh)
                out.append((str(int((s.get("ciks") or ["0"])[0])), adsh, s.get("file_date")))
            if len(hits) < 100:
                break
        d += timedelta(days=1)
    return out


def info_table(cik, adsh):
    """{cusip: [shares, 발행사 이름]} — 정보표 XML(SH만, 옵션 제외)"""
    base = f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{adsh.replace('-', '')}"
    idx = json.loads(get(base + "/index.json"))
    xmls = [x["name"] for x in idx["directory"]["item"] if x["name"].lower().endswith(".xml") and x["name"].lower() != "primary_doc.xml"]
    if not xmls:
        return {}
    root = ET.fromstring(get(f"{base}/{xmls[0]}"))
    out = {}
    for it in root.iter():
        if not it.tag.endswith("infoTable"):
            continue
        f = {c.tag.split("}")[-1]: c for c in it.iter()}
        if f.get("putCall") is not None and (f["putCall"].text or "").strip():
            continue
        if (f.get("sshPrnamtType").text if f.get("sshPrnamtType") is not None else "SH").strip() != "SH":
            continue
        cus = (f["cusip"].text or "").strip().upper() if f.get("cusip") is not None else ""
        try:
            sh = float((f["sshPrnamt"].text or "0").replace(",", ""))
        except (KeyError, ValueError):
            continue
        if len(cus) != 9:
            continue
        cur = out.setdefault(cus, [0.0, (f["nameOfIssuer"].text or "").strip() if f.get("nameOfIssuer") is not None else ""])
        cur[0] += sh
    return out


def prev_filing(cik, y, q):
    """직전 분기 13F-HR 접수번호(같은 보고 기간 중 가장 늦은 원본) 또는 None"""
    py, pq = prev_q(y, q)
    sub = json.loads(get(f"https://data.sec.gov/submissions/CIK{str(cik).zfill(10)}.json"))
    r = sub.get("filings", {}).get("recent", {})
    hits = [(r["filingDate"][i], r["accessionNumber"][i]) for i in range(len(r.get("form", [])))
            if r["form"][i] == "13F-HR" and r["reportDate"][i] == q_end(py, pq).isoformat()]
    return max(hits)[1] if hits else None


def cpath(y, q, cik):
    return CACHE / qname(y, q) / f"{cik}.json.gz"


def save(y, q, cik, data):
    p = cpath(y, q, cik)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(gzip.compress(json.dumps(data, separators=(",", ":")).encode("utf-8")))


def load(y, q, cik):
    p = cpath(y, q, cik)
    return json.loads(gzip.decompress(p.read_bytes())) if p.exists() else None


def one(cik, adsh, y, q):
    """기관 하나 — 이번·직전 분기 정보표 캐시. 결과 문자열"""
    if load(y, q, cik) is None:
        save(y, q, cik, {"adsh": adsh, "h": info_table(cik, adsh)})
    py, pq = prev_q(y, q)
    if load(py, pq, cik) is None:
        pa = prev_filing(cik, y, q)
        save(py, pq, cik, {"adsh": pa, "h": info_table(cik, pa) if pa else None})
    return "ok"


def collect(y, q, budget_min=30, today=None, log=print):
    """시간 예산 안에서 이어서 수집. (처리, 남음, 전체)"""
    t0 = time.time()
    st = common.load_state("thirteenf_market", {})
    key = qname(y, q)
    if st.get("listed_on", {}).get(key) != (today or date.today()).isoformat():
        rows = list_filings(y, q, today)
        st.setdefault("filings", {})[key] = rows
        st.setdefault("listed_on", {})[key] = (today or date.today()).isoformat()
        common.save_state("thirteenf_market", st)
    rows = st["filings"][key]
    todo = [r for r in rows if load(y, q, r[0]) is None or not cpath(*prev_q(y, q), r[0]).exists()]
    done = errs = 0
    with ThreadPoolExecutor(WORKERS) as ex:
        futs = []
        for cik, adsh, _ in todo:
            futs.append(ex.submit(one, cik, adsh, y, q))
        for f in futs:
            if time.time() - t0 > budget_min * 60:
                ex.shutdown(wait=False, cancel_futures=True)
                break
            try:
                f.result()
                done += 1
            except Exception as exc:
                errs += 1
                if errs <= 5 or errs % 200 == 0:
                    log(f"[13F 시장] 오류 {errs}: {type(exc).__name__} {getattr(exc, 'code', '')} {str(exc)[:120]}")
            if (done + errs) % 500 == 0:
                log(f"[13F 시장] {done + errs}/{len(todo)} (오류 {errs})")
    left = len([r for r in rows if load(y, q, r[0]) is None])
    st = common.load_state("thirteenf_market", {})
    st.setdefault("progress", {})[key] = {"filers": len(rows), "cached": len(rows) - left, "errors": errs, "at": common.iso(common.now_kst())}
    common.save_state("thirteenf_market", st)
    return done, left, len(rows)


def _split(ratios):
    """두 분기 다 보유한 기관의 비율 중앙값이 정수배·역수에 가까우면 그 배수, 아니면 1"""
    if len(ratios) < 5:
        return 1.0
    m = statistics.median(ratios)
    for k in (2, 3, 4, 5, 10, 20):
        if abs(m - k) / k < 0.06:
            return float(k)
        if abs(m - 1 / k) * k < 0.06:
            return 1 / k
    return 1.0


def aggregate(y, q, ciks):
    """{cusip: {holders, increased, decreased, new, sold_out, name}} + 기관 수 통계"""
    py, pq = prev_q(y, q)
    pairs, names, holders, newf = {}, {}, {}, 0
    both = 0
    for cik in ciks:
        cur = load(y, q, cik)
        if not cur:
            continue
        prev = load(py, pq, cik)
        ph = (prev or {}).get("h")
        for cus, (sh, nm) in cur["h"].items():
            holders[cus] = holders.get(cus, 0) + 1
            names.setdefault(cus, nm)
        if ph is None:
            newf += 1
            continue
        both += 1
        for cus in set(cur["h"]) | set(ph):
            pairs.setdefault(cus, []).append((ph.get(cus, [0])[0], cur["h"].get(cus, [0])[0]))
            if cus in ph:
                names.setdefault(cus, ph[cus][1])
    out = {}
    for cus, ps in pairs.items():
        k = _split([b / a for a, b in ps if a > 0 and b > 0])
        inc = sum(1 for a, b in ps if b > a * k * 1.0001)
        dec = sum(1 for a, b in ps if b < a * k * 0.9999)
        out[cus] = {"holders": holders.get(cus, 0), "increased": inc, "decreased": dec, "new": sum(1 for a, b in ps if a == 0 and b > 0),
                    "sold_out": sum(1 for a, b in ps if a > 0 and b == 0), "split": k if k != 1 else None, "name": names.get(cus, "")}
    return out, {"filers": len(ciks), "both": both, "new_filers": newf}


def figi(cusips, cmap):
    """CUSIP → {ticker, type, name} (OpenFIGI, 10개씩, 키 없이 25회/분) — 이미 아는 것은 건너뜀"""
    todo = [c for c in cusips if c not in cmap]
    for i in range(0, len(todo), 10):
        chunk = todo[i:i + 10]
        body = json.dumps([{"idType": "ID_CUSIP", "idValue": c, "exchCode": "US"} for c in chunk]).encode()
        import urllib.request
        try:
            req = urllib.request.Request("https://api.openfigi.com/v3/mapping", data=body, headers={"Content-Type": "application/json", "User-Agent": common.UA})
            res = json.loads(urllib.request.urlopen(req, timeout=30).read())
        except Exception:
            break
        for c, r in zip(chunk, res):
            d = (r.get("data") or [{}])[0]
            cmap[c] = {"ticker": d.get("ticker"), "type": d.get("securityType") or d.get("securityType2"), "name": d.get("name")} if d else {"ticker": None}
        time.sleep(2.5)
    return cmap


def rank(y, q, top=10, min_holders=30, map_fn=None):
    st = common.load_state("thirteenf_market", {})
    rows = st.get("filings", {}).get(qname(y, q), [])
    agg, stat = aggregate(y, q, [r[0] for r in rows])
    cands = [(c, v) for c, v in agg.items() if v["holders"] >= min_holders]
    pick = {c for c, _ in sorted(cands, key=lambda x: -x[1]["increased"])[:top * 4]} | {c for c, _ in sorted(cands, key=lambda x: -x[1]["decreased"])[:top * 4]}
    cmap = json.loads(MAP.read_text(encoding="utf-8")) if MAP.exists() else {}
    cmap = (map_fn or figi)(sorted(pick), cmap)
    OUT.mkdir(parents=True, exist_ok=True)
    MAP.write_text(json.dumps(cmap, ensure_ascii=False, indent=0, sort_keys=True), encoding="utf-8")

    def row(c, v):
        m = cmap.get(c) or {}
        return {**v, "cusip": c, "ticker": m.get("ticker") or "", "name": m.get("name") or v["name"], "type": m.get("type") or "",
                "net": v["increased"] - v["decreased"]}
    ok = [row(c, v) for c, v in cands if c in pick and not str((cmap.get(c) or {}).get("type") or "").startswith(EXCLUDE_TYPES)]
    res = {"quarter": qname(y, q), "stat": stat, "n": len(cands),
           "buy": sorted(ok, key=lambda r: -r["increased"])[:top], "sell": sorted(ok, key=lambda r: -r["decreased"])[:top],
           "at": common.iso(common.now_kst())}
    (OUT / f"{qname(y, q)}_market.json").write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
    return res


def season(today=None):
    """지금 다룰 분기 — thirteenf.season을 그대로 쓴다"""
    import thirteenf
    s = thirteenf.season(today or date.today())
    return (s[0], s[1]) if s else None


def run():
    """run_hourly용 — 시즌 창이면 15분 예산으로 이어서 수집"""
    s = season()
    if not s or not ua():
        return "시즌 아님 또는 SEC_USER_AGENT 없음", 0
    done, left, total = collect(*s, budget_min=15, log=lambda m: None)
    common.record_health(SOURCE_ID, True, None)
    return f"{qname(*s)} 처리 {done} · 남음 {left}/{total}", 0


def main(argv):
    sys.stdout.reconfigure(encoding="utf-8")
    s = season()
    if "--quarter" in argv:
        v = argv[argv.index("--quarter") + 1]
        s = (int(v[:4]), int(v[-1]))
    if not s:
        print("[13F 시장] 시즌 창이 아니다")
        return 0
    if "--collect" in argv:
        b = float(argv[argv.index("--budget-min") + 1]) if "--budget-min" in argv else 30
        print("[13F 시장] 처리 %d · 남음 %d / 전체 %d" % collect(*s, budget_min=b))
    elif "--rank" in argv:
        print(json.dumps(rank(*s), ensure_ascii=False, indent=1))
    else:
        print(json.dumps(common.load_state("thirteenf_market", {}).get("progress", {}), ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
