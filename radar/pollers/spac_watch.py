"""SPAC 감지·생애 단계 장부 1단계 (마스터 지시 2026-11-04 "1단계부터 구현", 설계 knowledge/methods/spac_discovery_design.md 1·2절)

SEC EDGAR 전문 검색(efts, 키 불필요)에서 제출자 SIC 6770(백지수표 회사) 서류만 받아 스팩마다 생애 단계를 매긴다. 모델 없음.
  S0 상장        S-1·424B4
  S2 확정 계약   425, 또는 8-K 1.01 중 'business combination agreement' 문구가 있는 것
                 (스팩의 8-K 1.01은 시한 연장 대출·신탁 계약도 많아 1.01만으로는 올리지 않는다)
  S3 등록        S-4·F-4(정정 포함), EFFECT(효력 발생은 effective 표시)
  S4 주총        DEFM14A·PREM14A(합병 위임장) — DEF 14A·PRE 14A는 시한 연장 주총이라 단계 대신 연장 횟수로 센다
  S5 종결        8-K 2.01(자산 취득 완료)
후속 추적: 계약 뒤 SIC가 바뀌어 6770 검색에서 빠지는 S2~S4 스팩은 3시간마다 스팩 자신의 제출 목록을 본다(follow).
단계는 앞으로만 간다. 단계가 바뀌면 transitions.csv에 한 줄 — 2단계에서 Pulse 알림 재료가 된다.
장부: knowledge/models/spac/registry.csv(스팩별 현재 상태), transitions.csv(단계 전환 이력)
사용: py radar/pollers/spac_watch.py [--days 2] [--backfill 180]
SEC 접속 규칙: 프로젝트 User-Agent(sec_filings._ua), 페이지 사이 0.3초.
"""
import csv
import json
import re
import sys
import time
import urllib.parse
from datetime import timedelta
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from pollers import common, sec_filings   # noqa: E402
else:
    from . import common, sec_filings

EFTS = "https://efts.sec.gov/LATEST/search-index"
DIR = common.ROOT / "knowledge" / "models" / "spac"
REG = DIR / "registry.csv"
TRANS = DIR / "transitions.csv"
COLS = ["cik", "name", "tickers", "stage", "stage_date", "effective", "extensions", "last_form", "last_date", "url", "first_seen"]
ORDER = {"S0": 0, "S1": 1, "S2": 2, "S3": 3, "S4": 4, "S5": 5}
LABEL = {"S0": "상장", "S1": "단서", "S2": "확정 계약", "S3": "등록", "S4": "주총", "S5": "종결"}
# (검색 양식, 문구, 단계) — 문구가 있으면 전문 검색 q로 건다
QUERIES = [("S-1", None, "S0"), ("424B4", None, "S0"),
           ("425", None, "S2"), ("8-K", '"business combination agreement"', "S2"),
           ("S-4", None, "S3"), ("S-4/A", None, "S3"), ("F-4", None, "S3"), ("F-4/A", None, "S3"),
           ("EFFECT", None, "S3|S2"),       # 효력 발생 통지는 IPO S-1에도 나온다 — 확정 계약(S2) 뒤일 때만 등록 효력으로
           ("PREM14A", None, "S4"), ("DEFM14A", None, "S4"),
           ("424B3", None, "S4|S2"),        # 합병 최종 위임장(지주회사가 S-4를 낸 거래는 스팩 쪽에 424B3만 남는다) — S2 뒤일 때만
           ("8-K", '"Item 5.07"', "S4|S2"),   # 주총 결과 — 연장 주총도 5.07이라 S2 뒤일 때만 합병 주총으로
           ("DEF 14A", None, "EXT"), ("PRE 14A", None, "EXT"),
           ("8-K", '"Item 2.01"', "CLOSE?")]   # 'Item 2.01' 문구가 있는 8-K 중 항목에 2.01이 있는 것만 종결(전체 8-K는 페이지 상한에 걸린다)
FOLLOW_EVERY_H = 3
NAME_RE = re.compile(r"^(.*?)\s*(?:\(([^)]*)\))?\s*\(CIK (\d+)\)")


def hits(form, q, start, end, max_pages=5):
    out, seen = [], set()
    for page in range(max_pages):
        p = {"forms": form, "sics": "6770", "dateRange": "custom", "startdt": start.isoformat(), "enddt": end.isoformat(), "from": page * 100}
        if q:
            p["q"] = q
        d = json.loads(common.http_get(EFTS + "?" + urllib.parse.urlencode(p), headers={"User-Agent": sec_filings._ua()}, timeout=40))
        hs = d.get("hits", {}).get("hits", [])
        for h in hs:
            s = h["_source"]
            if s.get("adsh") not in seen:
                seen.add(s.get("adsh"))
                out.append(s)
        if len(hs) < 100:
            break
        time.sleep(0.3)
    return out


def parse(s):
    m = NAME_RE.match((s.get("display_names") or [""])[0])
    if not m:
        return None
    name, tick, cik = m.group(1).strip(), (m.group(2) or "").replace(" ", ""), str(int(m.group(3)))
    adsh = s.get("adsh", "")
    return {"cik": cik, "name": name, "tickers": tick, "form": s.get("form") or s.get("file_type"), "date": s.get("file_date"), "items": s.get("items") or [],
            "url": f"https://www.sec.gov/Archives/edgar/data/{cik}/{adsh.replace('-', '')}/"}


def stage_of(kind, f, reg=None):
    """조건부 단계 'S4|S2' = 장부에서 이미 S2 이상일 때만 S4"""
    if kind == "CLOSE?":
        return "S5" if "2.01" in f["items"] else None
    if kind == "S4|S2" and "5.07" not in f["items"] and f["form"] == "8-K":
        return None
    if "|" in kind:
        st, need = kind.split("|")
        cur = ((reg or {}).get(f["cik"]) or {}).get("stage", "")
        return st if ORDER.get(cur, -1) >= ORDER[need] else None
    return kind


def load():
    if not REG.exists():
        return {}
    with REG.open(encoding="utf-8", newline="") as fh:
        return {r["cik"]: r for r in csv.DictReader(fh)}


def save(reg):
    DIR.mkdir(parents=True, exist_ok=True)
    with REG.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, COLS)
        w.writeheader()
        w.writerows(sorted(reg.values(), key=lambda r: (-ORDER.get(r["stage"], -1), r["name"])))


def apply(reg, f, stage, today):
    """한 서류를 장부에 반영. 단계 전환이면 전환 행을 돌려준다"""
    r = reg.get(f["cik"])
    if r is None:
        r = reg[f["cik"]] = {"cik": f["cik"], "name": f["name"], "tickers": f["tickers"], "stage": "", "stage_date": "", "effective": "",
                             "extensions": "0", "last_form": "", "last_date": "", "url": "", "first_seen": today}
    if f["tickers"] and not r["tickers"]:
        r["tickers"] = f["tickers"]
    if (f["date"] or "") >= (r["last_date"] or ""):
        r.update({"last_form": f["form"], "last_date": f["date"], "url": f["url"], "name": f["name"]})
    if stage == "EXT":
        r["extensions"] = str(int(r["extensions"] or 0) + 1)
        return None
    if f["form"] == "EFFECT" and stage == "S3":
        r["effective"] = f["date"]
    if ORDER[stage] > ORDER.get(r["stage"], -1):
        prev = r["stage"]
        r.update({"stage": stage, "stage_date": f["date"]})
        return [today, f["cik"], f["name"], r["tickers"], prev, stage, f["form"], f["date"], f["url"]]
    return None


FOLLOW = {"S-4": "S3", "S-4/A": "S3", "F-4": "S3", "F-4/A": "S3", "EFFECT": "S3|S2", "PREM14A": "S4", "DEFM14A": "S4", "424B3": "S4|S2", "DEF 14A": "EXT", "PRE 14A": "EXT"}


def follow(reg, today, since_days=200):
    """확정 계약(S2)~주총(S4) 스팩은 계약 뒤 SIC를 피인수 업종으로 바꾼다(CCXI 6770 → 3569, 2026-11-04 확인) — SIC 6770 검색에서 빠지므로
    스팩 자신의 제출 목록(data.sec.gov submissions)을 직접 본다. 반환: (서류 수, 전환 행들)"""
    n, trans = 0, []
    cut = (today - timedelta(days=since_days)).isoformat()
    for cik, r in list(reg.items()):
        if r["stage"] not in ("S2", "S3", "S4"):
            continue
        try:
            d = json.loads(common.http_get(f"https://data.sec.gov/submissions/CIK{int(cik):010d}.json", headers={"User-Agent": sec_filings._ua()}, timeout=30))
        except Exception:
            continue
        rec = d.get("filings", {}).get("recent", {})
        rows = sorted(zip(rec.get("form", []), rec.get("filingDate", []), rec.get("items", []), rec.get("accessionNumber", [])), key=lambda x: x[1])
        for form, dt, items, acc in rows:
            if dt < cut or dt < (r["stage_date"] or ""):
                continue
            kind = FOLLOW.get(form) or ("S5" if form == "8-K" and "2.01" in items else "S4|S2" if form == "8-K" and "5.07" in items else None)
            if not kind:
                continue
            f = {"cik": cik, "name": d.get("name") or r["name"], "tickers": ",".join(d.get("tickers") or []) or r["tickers"], "form": form, "date": dt,
                 "items": items.split(","), "url": f"https://www.sec.gov/Archives/edgar/data/{cik}/{acc.replace('-', '')}/"}
            st = stage_of(kind, f, reg)
            if not st:
                continue
            n += 1
            t = apply(reg, f, st, today.isoformat())
            if t:
                trans.append(t)
        time.sleep(0.15)   # SEC 초당 10회 이하
    return n, trans


def run(days=2, today=None):
    today = today or common.now_kst().date()
    start = today - timedelta(days=days)
    reg, seen = load(), set(common.load_state("spac_watch", {}).get("adsh", []))
    trans, errors, n = [], [], 0
    batch = []
    for form, q, kind in QUERIES:
        try:
            batch += [(kind, d) for d in hits(form, q, start, today)]
        except Exception as e:
            errors.append(f"{form}: {type(e).__name__}")
        time.sleep(0.3)
    for kind, s in sorted(batch, key=lambda x: (x[1].get("file_date") or "", "|" in x[0])):   # 날짜순, 같은 날은 조건부 단계를 뒤에
        key = f"{kind}:{s.get('adsh')}"
        if key in seen:
            continue
        f = parse(s)
        st = f and stage_of(kind, f, reg)
        if not st:
            if not (f and "|" in kind):   # 조건부 단계가 조건 미달이면 '본 것'으로 치지 않는다 — 다음 회차에 선행 서류가 들어오면 다시 판정
                seen.add(key)
            continue
        seen.add(key)
        n += 1
        t = apply(reg, f, st, today.isoformat())
        if t:
            trans.append(t)
    st_follow = common.load_state("spac_watch_follow", {})
    if not st_follow.get("last") or st_follow["last"] < (common.now_kst() - timedelta(hours=FOLLOW_EVERY_H)).isoformat():   # 스팩 수만큼 요청 — 3시간마다
        k, tr = follow(reg, today)
        n += k
        trans += tr
        common.save_state("spac_watch_follow", {"last": common.iso(common.now_kst())})
    save(reg)
    if trans:
        new = not TRANS.exists()
        with TRANS.open("a", encoding="utf-8", newline="") as fh:
            w = csv.writer(fh)
            if new:
                w.writerow(["seen", "cik", "name", "tickers", "from", "to", "form", "filed", "url"])
            w.writerows(trans)
    common.save_state("spac_watch", {"adsh": sorted(seen)[-20000:]})
    common.record_health("src-spac-watch", len(errors) < len(QUERIES), "; ".join(errors) or None)
    return {"filings": n, "transitions": len(trans), "spacs": len(reg), "errors": errors,
            "by_stage": {LABEL[k]: sum(1 for r in reg.values() if r["stage"] == k) for k in ("S0", "S2", "S3", "S4", "S5")}}


def main(argv):
    sys.stdout.reconfigure(encoding="utf-8")
    days = int(argv[argv.index("--backfill") + 1]) if "--backfill" in argv else int(argv[argv.index("--days") + 1]) if "--days" in argv else 2
    print(json.dumps(run(days), ensure_ascii=False))


if __name__ == "__main__":
    main(sys.argv[1:])
