"""SEC 일괄 재무(companyfacts.zip) → 미국 전 상장사 연간 매출 이력 — 기저율 표본 확대 (무료, 키 불필요)

생존 종목·AI 대형주만 있는 지금 표본(39종목)의 편향을 줄인다. SEC는 일괄 파일 접속에 연락처가 든
User-Agent를 요구한다(일반 UA는 403 확인, 2026-10-28) → .env SEC_USER_AGENT가 없으면 실행하지 않는다.
처리: zip을 받아 회사별 JSON에서 연간(10-K·20-F, 12개월) 매출만 뽑아
knowledge/models/baserates/us_revenue_annual.csv(cik,entity,year,revenue)에 저장하고 zip은 지운다(--keep이면 보존).
월 1회면 충분(기저율은 천천히 변한다). 사용: py scripts/valuation/v2/sec_bulk.py [--keep]
"""
import argparse
import csv
import json
import sys
import urllib.request
import zipfile
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "radar"))
sys.path.insert(0, str(ROOT / "radar" / "markets"))
from pollers import common  # noqa: E402
import sec_xbrl  # noqa: E402

URL = "https://www.sec.gov/Archives/edgar/daily-index/xbrl/companyfacts.zip"
TMP = ROOT / "knowledge" / "models" / "fundamentals" / "bulk"
OUT = ROOT / "knowledge" / "models" / "baserates" / "us_revenue_annual.csv"


def annual_revenue(facts):
    """[(연도, 매출)] — 회계연도(FY) 12개월(±20일) 값, 같은 연도는 늦게 제출된 값"""
    out = {}
    for r in sec_xbrl.extract({"facts": facts.get("facts", {})}):
        if r["metric"] != "revenue" or r["fp"] != "FY" or not r["start"] or r["unit"] != "USD":
            continue
        d0, d1 = date.fromisoformat(r["start"]), date.fromisoformat(r["end"])
        if 345 <= (d1 - d0).days <= 385 and r["value"] and r["value"] > 0:
            out[d1.year] = r["value"]
    return sorted(out.items())


def download(ua):
    TMP.mkdir(parents=True, exist_ok=True)
    dest = TMP / "companyfacts.zip"
    req = urllib.request.Request(URL, headers={"User-Agent": ua})
    with urllib.request.urlopen(req, timeout=120) as r, dest.open("wb") as f:
        while True:
            chunk = r.read(1 << 20)
            if not chunk:
                break
            f.write(chunk)
    return dest


def build(zpath):
    OUT.parent.mkdir(parents=True, exist_ok=True)
    n_co, n_rows = 0, 0
    with zipfile.ZipFile(zpath) as z, OUT.open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["cik", "entity", "year", "revenue"])
        for name in z.namelist():
            if not name.endswith(".json"):
                continue
            try:
                facts = json.loads(z.read(name))
            except (ValueError, KeyError):
                continue
            rows = annual_revenue(facts)
            if len(rows) < 2:
                continue
            n_co += 1
            for y, v in rows:
                w.writerow([facts.get("cik"), facts.get("entityName", ""), y, v])
                n_rows += 1
    return n_co, n_rows


def run(keep=False):
    ua = common.load_env().get("SEC_USER_AGENT")
    if not ua:
        raise RuntimeError("SEC_USER_AGENT 없음(.env) — SEC 일괄 파일은 연락처가 든 User-Agent 필요")
    z = download(ua)
    n_co, n_rows = build(z)
    if not keep:
        z.unlink(missing_ok=True)
    common.record_health("src-sec-bulk", n_co > 0, None)
    return n_co, n_rows


def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument("--keep", action="store_true")
    a = ap.parse_args(argv)
    n_co, n_rows = run(a.keep)
    print(f"[SEC 일괄] {n_co:,}개 회사, 연간 매출 {n_rows:,}행 → {OUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
