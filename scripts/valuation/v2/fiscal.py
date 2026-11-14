"""회계연도 시점 — DCF 할인 시점을 평가일 기준으로 맞춘다(마스터 지시 2026-11-14 "Analysis의 Valuation Model을 점검하라 … 신뢰성을 높이기 위해 고도화", ADR-039)

문제(ADR-036 '남긴 것' 1번): 기준 매출 rev0가 진행 중인 회계연도 컨센서스여도 1년차를 0.5년 뒤(연중)로 할인했다. AMAT는 FY2026이 10/25에 끝나
rev0 = FY2027(11/14 기준 거의 1년이 남은 해)인데, 1년차 FY2028을 0.5년 뒤로 당겨 할인하고 FY2027 현금흐름은 통째로 건너뛰었다(약 7% 과대).
반대로 12월 결산 종목은 남은 1.5개월치를 버렸다.

해법: fy_offset = 평가일(시세 날짜)부터 rev0 회계연도가 끝나는 날까지의 거리(년). dcf.value가 연도별 몫·할인 시점을 이 값으로 잡는다
(0이면 지금과 똑같다). rev0 해가 아직 남았으면 남은 몫의 현금흐름을 더하고, 이미 끝났으면 1년차 중 지난 몫은 세지 않는다.

회계연도 끝(MM-DD) 우선순위: drivers fy_end → config/fiscal_year_end.yaml(SEC submissions fiscalYearEnd 등 캐시) →
SEC 펀더멘털(knowledge/models/fundamentals/us/<티커>.csv) 최근 FY 행 끝 날짜 → 지역 기본값(JP 03-31, 그 밖 12-31, '추정').
rev0 회계연도: provenance '컨센서스 FY2026' → 2026 · 회사 가이던스 → 컨센서스 첫 해 · TTM → 마지막 분기 끝 날짜.
라벨 = 회계연도가 끝나는 해(Fiscal.ai 관행: AMAT FY2027 = 2027년 10월 끝, NVDA FY2027 = 2027년 1월 끝).

사용: py scripts/valuation/v2/fiscal.py <entity>            # 그 종목의 시점 계산을 보여 준다
      py scripts/valuation/v2/fiscal.py --sync              # 미국 종목 회계연도 끝을 SEC submissions에서 받아 캐시(네트워크)
"""
import csv
import json
import re
import sys
from datetime import date
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[3]
CACHE = ROOT / "config" / "fiscal_year_end.yaml"
FUND = ROOT / "knowledge" / "models" / "fundamentals" / "us"
REGION_DEFAULT = {"JP": "03-31"}
CURRENCY_REGION = {"¥": "JP", "JPY": "JP", "₩": "KR", "KRW": "KR"}
OFFSET_RANGE = [-0.75, 1.0]   # rev0는 진행 중이거나 막 끝난 해 — 이 밖이면(아직 시작도 안 한 해 등) 라벨·날짜 해석이 틀렸을 가능성이 커서 보정하지 않는다


def _cache():
    try:
        return yaml.safe_load(CACHE.read_text(encoding="utf-8")) or {}
    except OSError:
        return {}


def _sec_md(ticker):
    """SEC 펀더멘털 CSV의 가장 최근 연간(FY) 행 끝 날짜 → 'MM-DD'"""
    p = FUND / f"{ticker}.csv"
    if not ticker or not p.exists():
        return None
    ends = []
    with p.open(encoding="utf-8", newline="") as fh:
        for r in csv.DictReader(fh):
            if r.get("fp") == "FY" and r.get("end"):
                try:
                    s, e = date.fromisoformat(r["start"]), date.fromisoformat(r["end"])
                except (KeyError, ValueError):
                    continue
                if (e - s).days >= 340:
                    ends.append(e)
    return max(ends).strftime("%m-%d") if ends else None


def _region(co, dp=None):
    """통화 기호(datapack currency_symbol·quarters_hist currency) → 지역, 없으면 region_mix 최대(TOWA region_mix 'ASIA' — 통화가 더 정확하다)"""
    for k in (str((dp or {}).get("currency_symbol") or "").strip(), str(((dp or {}).get("quarters_hist") or {}).get("currency") or "")):
        if k in CURRENCY_REGION:
            return CURRENCY_REGION[k]
    if str(co.get("id") or "").startswith("jp-"):
        return "JP"
    rm = co.get("region_mix") or {"US": 1.0}
    return max(rm, key=rm.get)


def fy_end(co, dp=None):
    """(MM-DD, 근거)"""
    if co.get("fy_end"):
        return str(co["fy_end"]), "동인 지정"
    tk = str(co.get("ticker") or "").split(":")[-1]
    c = (_cache().get(tk) or {}) if tk else {}
    if c.get("md"):
        return c["md"], c.get("source", "캐시")
    md = _sec_md(tk)
    if md:
        return md, "SEC 10-K 회계연도 끝"
    region = _region(co, dp)
    return REGION_DEFAULT.get(region, "12-31"), f"지역 기본값({region}, 추정)"


def _end_date(year, md):
    m, d = (int(x) for x in md.split("-"))
    try:
        return date(year, m, d)
    except ValueError:   # 2월 29일
        return date(year, m, 28)


def rev0_end(co, dp=None):
    """rev0 회계연도가 끝나는 날(date)과 근거. 모르면 (None, 이유)"""
    prov = str((co.get("provenance") or {}).get("rev0") or "")
    cons = sorted((((dp or {}).get("consensus") or {}).get("rev") or {}))
    if "TTM" in prov:
        q = (((dp or {}).get("quarters_hist") or {}).get("q") or [])
        if q and q[-1].get("period"):
            return date.fromisoformat(str(q[-1]["period"])[:10]), "TTM — 마지막 분기 끝"
        return None, "TTM인데 마지막 분기 날짜 없음"
    m = re.search(r"FY(\d{4})", prov)
    year = int(m.group(1)) if m else None
    if year is None and "가이던스" in prov and cons:
        m2 = re.search(r"(\d{4})", cons[0])
        year = int(m2.group(1)) if m2 else None
    if year is None and co.get("rev0"):   # 손으로 만든 동인(provenance 없음, AMAT) — 컨센서스 해 매출과 2% 안으로 맞는 해
        revs = ((dp or {}).get("consensus") or {}).get("rev") or {}
        near = [(abs(v / co["rev0"] - 1), k) for k, v in revs.items() if v]
        near = sorted(x for x in near if x[0] <= 0.02)
        m3 = re.search(r"(\d{4})", near[0][1]) if near else None
        year = int(m3.group(1)) if m3 else None
    if year is None:
        return None, f"rev0 회계연도를 못 찾음(provenance '{prov[:30]}', 컨센서스와 2% 안 일치 없음)"
    md, src = fy_end(co, dp)
    return _end_date(year, md), f"FY{year} 끝 {md}({src})"


def offset(co, dp=None, today=None):
    """{'offset': 년 또는 None, 'end', 'val_date', 'why'} — offset None이면 보정하지 않는다(기존 연중 할인)"""
    end, why = rev0_end(co, dp)
    vd = str(((co.get("market") or {}).get("date")) or "")[:10]
    try:
        v = date.fromisoformat(vd) if vd else (today or date.today())
    except ValueError:
        v = today or date.today()
    if end is None:
        return {"offset": None, "end": None, "val_date": v.isoformat(), "why": why}
    off = (end - v).days / 365.25
    if not OFFSET_RANGE[0] < off < OFFSET_RANGE[1]:
        return {"offset": None, "end": end.isoformat(), "val_date": v.isoformat(), "why": f"{why} — 평가일과 {off:+.2f}년 떨어져 해석 의심, 보정 안 함"}
    return {"offset": round(off, 4), "end": end.isoformat(), "val_date": v.isoformat(), "why": why}


def apply(co, dp=None):
    """co에 fy_offset·fy_timing을 붙인다(제자리). scenarios.drivers가 dcf로 넘긴다"""
    t = offset(co, dp)
    co["fy_timing"] = t
    if t["offset"] is not None:
        co["fy_offset"] = t["offset"]
    return t


def line(t):
    if not t:
        return ""
    if t.get("offset") is None:
        return f"할인 시점: 기본 연중 할인({t.get('why')})"
    off = t["offset"]
    part = f"rev0 해가 {off:.2f}년 남아 남은 몫 현금흐름을 더함" if off > 0 else f"rev0 해가 {-off:.2f}년 전에 끝나 1년차 중 지난 몫은 뺌"
    return f"할인 시점: 평가일 {t['val_date']} → {t['why']} — {part}"


def sync(entities=None):
    """미국 종목 회계연도 끝을 SEC submissions(fiscalYearEnd)에서 받아 캐시. User-Agent는 프로젝트 값(sec_filings._ua) — 개인 정보 금지"""
    sys.path.insert(0, str(ROOT / "radar"))
    from pollers import common, sec_filings
    ciks = {str(k).upper(): str(v) for k, v in (common.load_state("sec_filings", {}).get("ciks") or {}).items()}
    cache = _cache()
    got = 0
    for p in sorted((ROOT / "knowledge" / "models" / "companies").glob("*/drivers.yaml")):
        if entities and p.parent.name not in entities:
            continue
        co = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
        tk = str(co.get("ticker") or "").split(":")[-1].upper()
        if not tk or tk in cache or not tk.isalpha():
            continue
        cik = ciks.get(tk)
        if not cik:
            continue
        try:
            js = json.loads(common.http_get(f"https://data.sec.gov/submissions/CIK{int(cik):010d}.json", headers={"User-Agent": sec_filings._ua()}))
        except Exception as exc:   # 네트워크·차단 — 다음 회차
            print(f"[회계연도] {tk} 실패 {type(exc).__name__}")
            continue
        fye = str(js.get("fiscalYearEnd") or "")
        if re.fullmatch(r"\d{4}", fye):
            cache[tk] = {"md": f"{fye[:2]}-{fye[2:]}", "source": f"SEC submissions fiscalYearEnd {fye}({date.today().isoformat()})"}
            got += 1
    if got:
        CACHE.write_text("# 회계연도 끝(MM-DD) 캐시 — scripts/valuation/v2/fiscal.py --sync(SEC submissions fiscalYearEnd). 손으로 고칠 땐 source에 근거\n"
                         + yaml.safe_dump(cache, allow_unicode=True, sort_keys=True), encoding="utf-8")
    return got


def main(argv):
    sys.stdout.reconfigure(encoding="utf-8")
    if "--sync" in argv:
        print(f"[회계연도] 새로 캐시 {sync()}곳")
        return 0
    ent = argv[0]
    folder = ROOT / "knowledge" / "models" / "companies" / ent
    co = yaml.safe_load((folder / "drivers.yaml").read_text(encoding="utf-8"))
    dp = json.loads((folder / "datapack.json").read_text(encoding="utf-8")) if (folder / "datapack.json").exists() else {}
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import run
    co["market"] = run.resolve_market(co)
    print(json.dumps(offset(co, dp), ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
