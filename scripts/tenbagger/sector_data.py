"""Analysis 섹터 데이터 원천 (마스터 지시 2026-11-13 종목 범위 확대 4단계, ADR-029) — scripts/tenbagger/gather.py가 원천 'sector_data'로 돌린다

AI 밸류체인 밖 종목이면 그 섹터 판단 틀(knowledge/methods/sector_lenses/)의 질문 7개와, 섹터별 공개 데이터를 출력한다.
모델은 이걸 보고 datapack "sector_kpis"를 쓴다(scripts/tenbagger/sector_view.py 맨 위) → 리포트 '섹터 핵심 지표' 절.
  헬스케어·바이오·의료기기: openFDA(공개 API, 키 없음 하루 1,000회) — 의약품 승인(drugsfda)·의료기기 510(k) 최근 결정
  금융·지역은행: FDIC BankFind(공개 API) — 지주회사 이름으로 자회사 은행의 자산·예금·ROA·ROE(분기 콜 리포트 기준)
  에너지·유틸리티: 기존 원천 eia 줄을 본다
  그 밖: 10-K·IR·생산자물가(trade_ppi 원천)
쓰지 않는 것: ClinicalTrials.gov API(robots.txt가 /api/ 금지 — 2026-11-13 확인). 회사 IR 파이프라인 표·10-K로 대신한다.
AI 밸류체인·미분류 종목은 '해당 없음'만 출력한다(병목 틀을 쓴다). 숫자는 원천 그대로 — 해석·점수는 모델이 판단 틀로.
사용: py scripts/tenbagger/sector_data.py <회사 id> <티커> <회사 이름>
"""
import json
import re
import sys
import urllib.parse
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "sectors"))
sys.path.insert(0, str(ROOT / "radar"))
LENSES = ROOT / "knowledge" / "methods" / "sector_lenses"
LENS_OF = {"health": "health", "biotech": "health", "medtech": "health", "life_tools": "industrials",   # 계측·연구 장비는 수주·소모품 반복 매출·가격 전가가 가른다(2026-11-13 MTD 시험)
          
           "financials": "financials", "regional_banks": "financials", "real_estate": "financials",
           "industrials": "industrials", "infra_build": "industrials", "airlines": "industrials", "shipping": "industrials", "robotics": "industrials",
           "shipbuild": "industrials", "trading_houses": "industrials", "autos": "industrials",
           "cons_disc": "consumer", "cons_staples": "consumer", "retail": "consumer", "homebuild": "consumer", "media_ent": "consumer", "luxury": "consumer",
           "energy": "energy", "utilities": "energy", "materials": "energy", "chemicals": "energy", "gold": "energy", "copper": "energy", "solar": "energy",
           "software": "software", "cyber": "software", "comm": "software", "info_tech": "software"}
SUFFIX = re.compile(r"[,.]|\b(inc|corp|corporation|holdings?|company|co|ltd|plc|group|the)\b", re.I)


def lens_for(cid, ticker):
    import sector_map
    g = sector_map.tag(cid, ticker)
    if not g:
        return None, None
    if sector_map.is_ai(g):
        return g, None
    return g, LENS_OF.get(g)


def questions(lens):
    f = LENSES / f"{lens}.md"
    return re.findall(r"(?m)^(\d+\. .+)$", f.read_text(encoding="utf-8")) if f.exists() else []


def _get(url):
    from pollers import common
    return json.loads(common.http_get(url, timeout=20))


def core_name(name):
    return " ".join(SUFFIX.sub(" ", name or "").split())


def openfda(name, get=_get):
    """[(종류, 날짜, 내용)] — 최근 의약품 승인·510(k) 결정. 결과가 없으면 빈 목록"""
    words = core_name(name).upper().split()
    if not words:
        return []
    q = words[0]   # 신청인 이름은 회사 이름과 꼬리가 다르다(XERIS BIOPHARMA HOLDINGS ↔ XERIS PHARMACEUTICALS) — 첫 낱말 토큰으로 찾는다
    out = []
    try:
        d = get("https://api.fda.gov/drug/drugsfda.json?" + urllib.parse.urlencode({"search": f"sponsor_name:{q}", "limit": 5}))
        for r in d.get("results") or []:
            if q not in str(r.get("sponsor_name") or "").upper():
                continue
            subs = sorted(r.get("submissions") or [], key=lambda s: s.get("submission_status_date") or "", reverse=True)[:2]
            prod = ", ".join(sorted({p.get("brand_name", "") for p in r.get("products") or []} - {""}))[:60]
            for s in subs:
                out.append(("의약품", s.get("submission_status_date"), f"{r.get('application_number')} {prod} — {s.get('submission_type')} {s.get('submission_status')}"))
    except Exception:  # noqa: BLE001 — 404는 '결과 없음'
        pass
    try:
        d = get("https://api.fda.gov/device/510k.json?" + urllib.parse.urlencode({"search": f"applicant:{q}", "limit": 5, "sort": "decision_date:desc"}))
        for r in d.get("results") or []:
            if q not in str(r.get("applicant") or "").upper():
                continue
            out.append(("의료기기 510(k)", r.get("decision_date"), f"{r.get('k_number')} {r.get('device_name', '')[:60]} — {r.get('decision_description', '')}"))
    except Exception:  # noqa: BLE001
        pass
    return sorted(out, key=lambda x: x[1] or "", reverse=True)


def fdic(name, get=_get):
    """[{은행 행}] — 지주회사 이름(NAMEHCR)으로 활동 중인 자회사 은행. 첫 낱말*로도 찾되 꼬리를 뗀 이름이 정확히 같은 것만"""
    words = core_name(name).upper().split()
    if not words:
        return []
    fields = "NAME,NAMEHCR,CERT,ASSET,DEP,ROA,ROE,REPDTE"
    for f in (f'NAMEHCR:"{" ".join(words)}"', f"NAMEHCR:{words[0]}*"):
        try:
            d = get("https://api.fdic.gov/banks/institutions?" + urllib.parse.urlencode({"filters": f + " AND ACTIVE:1", "fields": fields, "limit": 10}))
        except Exception:  # noqa: BLE001
            continue
        want = " ".join(words)   # 지주회사 이름이 꼬리(Inc·Holdings)를 뺀 뒤 정확히 같아야 — PALOMAR ↔ PALOMAR ENTERPRISES 같은 오탐 방지(2026-11-13 시험)
        rows = [x["data"] for x in d.get("data") or [] if core_name(str(x["data"].get("NAMEHCR") or "")).upper() == want]
        if rows:
            return rows
    return []


def run(cid, ticker, name, get=_get):
    g, lens = lens_for(cid, ticker)
    if lens is None:
        return [f"해당 없음({'AI 밸류체인 — 병목 틀' if g else '섹터 미분류'})"]
    import sector_map
    out = [f"섹터: {sector_map.names().get(g, g)} → 판단 틀 {lens} (knowledge/methods/sector_lenses/{lens}.md)", "질문(datapack sector_kpis에 번호대로 숫자를 채운다 — 모르면 미확인):"]
    out += ["  " + q for q in questions(lens)]
    if lens == "health":
        rows = openfda(name, get)
        out.append(f"openFDA 최근 결정 {len(rows)}건(출처 https://open.fda.gov — 미검증 데이터, 회사 공시와 대조):" if rows else "openFDA: 일치 없음(회사 이름이 FDA 신청인 이름과 다를 수 있다 — 10-K·IR로)")
        out += [f"  {k} {d} {t}" for k, d, t in rows[:8]]
    elif g in ("financials", "regional_banks"):
        rows = fdic(name, get)
        out.append(f"FDIC 자회사 은행 {len(rows)}곳(출처 https://banks.data.fdic.gov, 금액 $천):" if rows else "FDIC: 지주회사 일치 없음(보험·자산운용이면 해당 없음 — 10-K로)")
        out += [f"  {r.get('NAME')}(CERT {r.get('CERT')}) {r.get('REPDTE')} 자산 {r.get('ASSET')} · 예금 {r.get('DEP')} · ROA {r.get('ROA')} · ROE {r.get('ROE')}" for r in rows[:5]]
    elif lens == "energy":
        out.append("에너지·유틸리티: 같은 장부의 eia 원천 출력과 10-K 매장량·원가를 본다")
    else:
        out.append("섹터 공개 데이터 원천 미연결 — 10-K·IR·trade_ppi 원천으로 숫자를 채운다")
    return out


def main(argv):
    sys.stdout.reconfigure(encoding="utf-8")
    if len(argv) < 2:
        print(__doc__)
        return
    print("\n".join(run(argv[0], argv[1], " ".join(argv[2:]) or argv[1])))


if __name__ == "__main__":
    main(sys.argv[1:])
