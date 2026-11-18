"""'핵심 솔루션 + 반복 매출' 발굴 채널 — NPKI 유형 (마스터 지시 2026-11-18, ADR-047, 설정 config/enabler_screen.yaml)

마스터: "밸류체인의 일부에 불과하지만 핵심 솔루션을 제공하고, 단순 소모품을 넘어 리스 구조로 반복 매출까지 내는 종목을 발굴하는 알고리즘"
NPKI(NPK International)를 분해하면: 송전 투자라는 큰 물결(①) 속에서 작업 현장 접근용 매트라는 작은 부품(②)인데, 없으면 공사를 못 하는 핵심이고(③),
목재를 대체하는 복합소재라 침투 여지가 있으며(④), 렌탈 함대로 반복 매출을 낸다(⑤). 회사는 이 구조를 10-K에 스스로 적는다 — 서류가 말보다 먼저다.
알고리즘(결정론):
  1. SEC EDGAR 전문 검색(efts, 10-K·10-Q, 최근 lookback_days)으로 '반복 매출 어구 × 투자 물결 어구' 질의를 모두 돈다 → 회사별로 맞춘 묶음을 모은다
  2. 대체·침투 어구, 핵심성 어구 질의도 돌려 겹치는 회사에 가점
  3. 단서 강도 = base + 반복 매출 종류 수(최대 2) + 물결 수(최대 2) + 대체 + 핵심성 → min_emit 이상만 발굴 단서 장부(scripts/discovery/leads.py, 채널 enabler)에
  4. 장부 → channels.py 겹침 선별 → 판단 카드(knowledge/methods/sector_lenses/enabler.md, 질문 7개) → 발굴 선별 edge
한계·금지 연결: 어구가 서류에 있다 → 경쟁우위·반복 매출 비중이 크다가 아니다. 임대 부동산·금융·스팩은 이름으로 뺀다. 시가총액은 장부·선별 단계에서 본다.
사용: py scripts/discovery/enabler_screen.py [--dry] [--days N]   # 주 1회(일요일 전체 선별 전)
      py scripts/discovery/enabler_screen.py --from-latest          # 저장 결과(enabler_latest.json)만 장부에
"""
import json
import re
import sys
import time
import urllib.parse
from datetime import date, timedelta
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "radar"))
sys.path.insert(0, str(ROOT / "scripts" / "discovery"))
EFTS = "https://efts.sec.gov/LATEST/search-index"
NAME_RE = re.compile(r"^(.*?)\s*(?:\(([^)]*)\))?\s*\(CIK (\d+)\)")
OUT = ROOT / "knowledge" / "models" / "discovery" / "enabler_latest.json"


def cfg():
    return yaml.safe_load((ROOT / "config" / "enabler_screen.yaml").read_text(encoding="utf-8"))


def _get(url):
    import discovery_filings
    return discovery_filings._get(url)   # 프로젝트 SEC User-Agent(sec_filings._ua)·재시도 공용


def search(q, start, end, forms, max_pages=3, get=None):
    """[(CIK, 이름, 티커, 서류 종류, 제출일, adsh, SIC)]"""
    get = get or _get
    out, seen = [], set()
    for page in range(max_pages):
        p = {"q": q, "forms": forms, "dateRange": "custom", "startdt": start.isoformat(), "enddt": end.isoformat(), "from": page * 100}
        try:
            d = json.loads(get(EFTS + "?" + urllib.parse.urlencode(p)))
        except Exception:  # noqa: BLE001 — 질의 하나가 막혀도 나머지는 돈다
            break
        hs = d.get("hits", {}).get("hits", [])
        for h in hs:
            s = h.get("_source") or {}
            m = NAME_RE.match((s.get("display_names") or [""])[0])
            if not m or s.get("adsh") in seen:
                continue
            seen.add(s.get("adsh"))
            tk = (m[2] or "").split(",")[0].strip()
            out.append((str(int(m[3])), m[1].strip(), tk, s.get("form") or s.get("root_forms", [""])[0], s.get("file_date"), s.get("adsh"), str((s.get("sics") or [""])[0] or "")))
        if len(hs) < 100:
            break
    return out


FRAMES = "https://data.sec.gov/api/xbrl/frames"


def _frame(path, get):
    try:
        return json.loads((get or _get)(f"{FRAMES}/{path}.json")).get("data") or []
    except Exception:  # noqa: BLE001
        return []


def public_float(c, get=None):
    """{CIK: 공시 유통 시가총액 $} — dei:EntityPublicFloat 프레임(한 번 호출에 전 제출사). 최근 프레임 먼저"""
    out = {}
    for fr in c["size"]["frames"]:
        for r in _frame(f"dei/EntityPublicFloat/USD/{fr}I" if not fr.endswith("I") else f"dei/EntityPublicFloat/USD/{fr}", get):
            out.setdefault(str(r["cik"]), r.get("val"))
    return out


def lease_share(c, get=None):
    """{CIK: 리스·렌탈 수익 ÷ 매출} — us-gaap OperatingLeaseLeaseIncome(임대인) 연간 프레임 ÷ 매출 프레임"""
    out = {}
    for yr in c["lease_share"]["years"]:
        lease = {str(r["cik"]): r.get("val") for r in _frame(f"us-gaap/OperatingLeaseLeaseIncome/USD/{yr}", get)}
        rev = {}
        for tag in ("Revenues", "RevenueFromContractWithCustomerExcludingAssessedTax"):
            for r in _frame(f"us-gaap/{tag}/USD/{yr}", get):
                rev.setdefault(str(r["cik"]), r.get("val"))
        for k, v in lease.items():
            if k not in out and rev.get(k) and v:
                out[k] = round(v / rev[k], 3)
    return out


def run(today=None, days=None, dry=False, get=None, sleep=time.sleep):
    c = cfg()
    today = today or date.today()
    start = today - timedelta(days=days or c["lookback_days"])
    co = {}

    def hit(rows, fam, key):
        for cik, name, tk, form, fd, adsh, sic in rows:
            if re.search(c["exclude_names"], name.upper()) or (sic and sic.startswith(tuple(c.get("exclude_sic") or []))):
                continue
            x = co.setdefault(cik, {"cik": cik, "name": name, "ticker": tk, "sic": sic, "recurring": {}, "waves": {}, "substitute": 0, "critical": 0, "last": fd, "adsh": adsh})
            x["ticker"] = x["ticker"] or tk
            if fd and (not x["last"] or fd > x["last"]):
                x["last"], x["adsh"] = fd, adsh
            if fam == "pair":
                kind, wave = key
                x["recurring"][kind] = x["recurring"].get(kind, 0) + 1
                x["waves"][wave] = x["waves"].get(wave, 0) + 1
            else:
                x[fam] += 1

    for kind, rps in c["recurring"].items():
        for wave, wps in c["waves"].items():
            for rp in rps:
                for wp in wps:
                    hit(search(f"{rp} {wp}", start, today, c["forms"], c["max_pages"], get), "pair", (kind, wave))
                    sleep(c["pause_s"])
    pair_ciks = set(co)
    for fam in ("substitute", "critical"):
        for ph in c[fam]:
            rows = [r for r in search(ph, start, today, c["forms"], c["max_pages"], get) if r[0] in pair_ciks]   # 반복×물결을 맞춘 회사에만 가점
            hit(rows, fam, None)
            sleep(c["pause_s"])
    s = c["strength"]
    floats = public_float(c, get)
    share = lease_share(c, get)
    leads, cut = [], {"size": 0, "no_float": 0}
    for x in co.values():
        f = floats.get(x["cik"])
        x["float_usd"] = f
        if f is None:
            cut["no_float"] += 1   # 공시 유통 시가총액이 없다 = 10-K 표지 미제출(외국 사업자·신생) — 규모를 모르면 넣지 않는다
            continue
        if not c["size"]["min_usd"] <= f <= c["size"]["max_usd"]:
            cut["size"] += 1
            continue
        x["lease_share"] = share.get(x["cik"])
        nr, nw = len(x["recurring"]), len(x["waves"])
        top = max(x["waves"].values()) if x["waves"] else 0
        x["focus"] = top >= s["focus_hits"]
        st = s["base"] + (s["first_recurring"] if nr else 0) + (s["extra_recurring"] if nr >= 2 else 0) \
            + (s["first_wave"] if nw else 0) + (s["extra_wave"] if nw >= 2 else 0) + (s["focus"] if x["focus"] else 0) \
            + (s["substitute"] if x["substitute"] else 0) + (s["critical"] if x["critical"] else 0) \
            + (s["lease_share"] if (x["lease_share"] or 0) >= c["lease_share"]["min"] else 0)
        x["strength"] = round(min(10.0, st), 1)
        if x["strength"] >= s["min_emit"] and x["ticker"]:
            leads.append(x)
    leads.sort(key=lambda x: (-x["strength"], -sum(x["recurring"].values())))
    out = {"as_of": today.isoformat(), "since": start.isoformat(), "companies": len(co), "cut": cut, "leads": leads}
    if get is None:   # 실제 SEC 호출일 때만 결과 파일을 쓴다(단위 시험이 가짜 응답으로 덮어쓰던 문제, 2026-11-18). --dry도 결과는 남기고 장부에만 안 넣는다
        OUT.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    if not dry:
        out["added"] = emit(out, today)
    return out


def emit(out, today=None):
    """결과 → 발굴 단서 장부(채널 enabler). --from-latest로 검색 없이 저장 결과만 넣을 수도 있다"""
    import leads as L
    rows = []
    for x in out["leads"]:
        kind = max(x["recurring"], key=x["recurring"].get)
        sig = (f"반복 매출({', '.join(x['recurring'])}) × 투자 물결({', '.join(x['waves'])})"
               + (" · 주력 물결 반복" if x.get("focus") else "") + (" · 기존 방식 대체" if x["substitute"] else "") + (" · 핵심성 어구" if x["critical"] else ""))
        rows.append({"channel": "enabler", "kind": kind, "market": "us", "ticker": x["ticker"], "name": x["name"], "signal": sig,
                     "strength": x["strength"], "date": x["last"],
                     "url": f"https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK={x['cik']}&type=10-K",
                     "mcap_usd": x.get("float_usd"),
                     "extra": {"cik": x["cik"], "sic": x.get("sic"), "waves": x["waves"], "recurring": x["recurring"], "adsh": x["adsh"],
                               "lease_share": x.get("lease_share"), "float_basis": "공시 유통 시가총액(10-K 표지)"}})
    return len(L.add(rows, today))


def main(argv):
    sys.stdout.reconfigure(encoding="utf-8")
    days = int(argv[argv.index("--days") + 1]) if "--days" in argv else None
    if "--from-latest" in argv:
        out = json.loads(OUT.read_text(encoding="utf-8"))
        out["added"] = emit(out)
    else:
        out = run(days=days, dry="--dry" in argv)
    print(f"[핵심 솔루션·반복 매출] {out['since']}~{out['as_of']} · 회사 {out['companies']} · 단서 {len(out['leads'])}" + (f" · 장부 신규 {out['added']}" if "added" in out else ""))
    for x in out["leads"][:25]:
        print(f"  {x['ticker']:6} {x['name'][:34]:34} 강도 {x['strength']} · 반복 {','.join(x['recurring'])} · 물결 {','.join(x['waves'])}"
              + (" · 대체" if x["substitute"] else "") + (" · 핵심" if x["critical"] else ""))


if __name__ == "__main__":
    main(sys.argv[1:])
