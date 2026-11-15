"""SEC SPAC Inline XBRL(spac 택소노미) 추출 시험 (2026-11-15, ADR-044 — 조사 D §3.5)

2024-07-01 SEC 스팩 규칙(규정 S-K 1600절)의 공시는 2025-06-30부터 Inline XBRL 태그가 의무다(Item 1610). 태그가 있으면 datapack의
희석 표(환매 수준별 순유형자산·주식 수)·스폰서 보상·신탁 비율을 서류를 읽지 않고 뽑을 수 있다. 이 스크립트는 그 숫자를 초안으로 뽑기만 하고
datapack을 고치지 않는다(모델이 서류와 대조해 옮긴다 — 모르는 칸은 비운다).
  2026-11-15 시험: 최근 S-4 3건(SVAQ·TONT·IPFX)과 S-1 2건은 spac 태그 44~375개, HCAC S-4/A·DEFM14A 2건은 태그 없음(위임장은 아직 드묾).
사용: py scripts/tenbagger/spac_xbrl.py <서류 폴더 URL>   (예: https://www.sec.gov/Archives/edgar/data/2145371/000121390026112739/)
SEC 접속 규칙: 프로젝트 User-Agent(sec_filings._ua), 요청 사이 0.3초.
"""
import json
import re
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "radar"))
from pollers import common, sec_filings  # noqa: E402

CTX_RE = re.compile(r"<(?:xbrli:)?context\b[^>]*\bid=\"([^\"]+)\"[^>]*>(.*?)</(?:xbrli:)?context>", re.S)
MEM_RE = re.compile(r"<(?:xbrldi:)?explicitMember\b[^>]*dimension=\"([^\"]+)\"[^>]*>\s*([^<\s]+)\s*<")
FACT_RE = re.compile(r"<(spac:[A-Za-z0-9]+)\b([^>]*)>([^<]{0,80})</\1>")
KEEP = ("NetTangibleBookValue", "NumberOfSharesUsed", "Difference", "Dilution", "Trust", "SponsorCompensation", "Redemption", "Projection", "Percent")


def get(url):
    time.sleep(0.3)
    return common.http_get(url, headers={"User-Agent": sec_filings._ua()}, timeout=90)


def instance_url(folder):
    """폴더의 XBRL 인스턴스(*_htm.xml — SEC가 Inline XBRL에서 뽑아 둔 것). 서식 수수료 첨부(ex107)는 뺀다"""
    folder = folder.rstrip("/") + "/"
    d = json.loads(get(folder + "index.json"))
    names = [i["name"] for i in d.get("directory", {}).get("item", []) if i["name"].endswith("_htm.xml") and "ex107" not in i["name"].lower()]
    return folder + names[0] if names else None


def parse(xml):
    """spac:* 수치·표지 → [{name, value, members}] (텍스트 블록은 뺀다)"""
    ctx = {m.group(1): [(a.split(":")[-1], b.split(":")[-1]) for a, b in MEM_RE.findall(m.group(2))] for m in CTX_RE.finditer(xml)}
    out = []
    for name, attrs, val in FACT_RE.findall(xml):
        if "TextBlock" in name or not any(k in name for k in KEEP):
            continue
        c = re.search(r'contextRef="([^"]+)"', attrs)
        out.append({"name": name.split(":")[1], "value": val.strip(), "members": ctx.get(c.group(1), []) if c else []})
    return out


def dilution_table(facts):
    """환매 수준별 '조정 순유형자산 / 주식 수'(Item 1604(c) 희석 표) — 같은 차원 조합끼리 짝짓는다. 합병 뒤 주당 가치의 서류상 근사(피인수 순자산 포함, KOR 주당 순현금과 다르다)"""
    nt = {}
    for f in facts:
        key = tuple(sorted(m for _, m in f["members"]))
        if f["name"] == "DeSpacNetTangibleBookValueAdjusted":
            nt.setdefault(key, {})["ntbv"] = f["value"]
        elif f["name"] == "DeSpacNumberOfSharesUsedToDetermineNetTangibleBookValueAdjusted":
            nt.setdefault(key, {})["shares"] = f["value"]
    rows = []
    for key, v in nt.items():
        try:
            per = float(v["ntbv"].replace(",", "")) * 1000 / float(v["shares"].replace(",", ""))   # 금액은 보통 천 달러 단위 — 원 서류 표로 확인
        except (KeyError, ValueError, ZeroDivisionError):
            continue
        rows.append({"members": list(key), "ntbv_k": v["ntbv"], "shares": v["shares"], "per_share_if_thousands": round(per, 2)})
    return rows


def run(folder):
    u = instance_url(folder)
    if not u:
        return {"folder": folder, "tagged": False, "note": "XBRL 인스턴스 없음 — 서류를 읽어 채운다"}
    facts = parse(get(u).decode("utf-8", "replace"))
    return {"folder": folder, "instance": u, "tagged": bool(facts), "n_facts": len(facts), "dilution_table": dilution_table(facts),
            "facts": facts[:200], "note": "초안 — datapack에 옮기기 전에 서류 표와 대조(단위·환매 수준 이름)"}


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    print(json.dumps(run(sys.argv[1]), ensure_ascii=False, indent=1))
