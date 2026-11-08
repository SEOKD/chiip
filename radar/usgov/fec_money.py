"""규제산업 기업 PAC의 정당별 기부 집계 — FEC 공개 API (마스터 지시 2026-11-08 Industry Report "민주당도 규제산업에 속한 민간기업으로부터 상당한 로비를 받았다(데이터 확인 필수)")

api.open.fec.gov(미국 연방 선거위원회 공식 API, 연방 정부 공공 저작물). 키는 .env FEC_API_KEY 또는 DATA_GOV_API_KEY(api.data.gov 공용 키, 무료),
없으면 DEMO_KEY(시간당 약 30회). config/fec_pacs.yaml의 PAC마다 그 사이클 기부(후보·정당 위원회로 간 돈)를 받아 받는 쪽 위원회의 정당으로 나눈다.
한 PAC에서 금액 큰 순으로 max_rows건까지만 본다 — 합계는 '상위 n건 기준'이고, 전체 건수·전체 지출은 함께 남긴다.
결과: knowledge/models/fec/<cycle>.json. 로비(LD) 지출과 다르다 — 이것은 선거 기부다. 모델 없음.
사용: py radar/usgov/fec_money.py [--max-rows 100]
"""
import argparse
import json
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from pollers import common  # noqa: E402

API = "https://api.open.fec.gov/v1"
OUT = common.ROOT / "knowledge" / "models" / "fec"
PARTY = {"DEM": "민주", "REP": "공화"}


def key():
    env = common.load_env()
    return next((env[k] for k in ("FEC_API_KEY", "DATA_GOV_API_KEY") if env.get(k)), "DEMO_KEY")


def get(path, params, fetch=None):
    q = urllib.parse.urlencode({**params, "api_key": key()})
    if fetch:
        return fetch(f"{API}{path}?{q}")
    req = urllib.request.Request(f"{API}{path}?{q}", headers={"User-Agent": common.UA})
    with urllib.request.urlopen(req, timeout=40) as r:
        return json.loads(r.read().decode("utf-8"))


def resolve(p, fetch=None):
    """위원회 번호 — 설정에 있으면 그것, 없으면 이름 검색 첫 결과(활성 위원회 우선)"""
    if p.get("id"):
        return p["id"], None
    rows = get("/names/committees/", {"q": p["query"]}, fetch).get("results") or []
    rows = sorted(rows, key=lambda r: not r.get("is_active"))
    return (rows[0]["id"], rows[0]["name"]) if rows else (None, None)


def split(rows):
    """기부 행 → 정당별 합계. 받는 쪽이 후보·정당 위원회가 아니면(무소속·다른 PAC) '기타'"""
    out = {"민주": 0.0, "공화": 0.0, "기타": 0.0}
    for r in rows:
        party = ((r.get("recipient_committee") or {}).get("party") or "").upper()
        out[PARTY.get(party, "기타")] += float(r.get("disbursement_amount") or 0)
    return out


def collect(cfg, max_rows=100, fetch=None, pause=1.0, keep=None):
    """keep = 이전 결과 {회사: 행} — 'ok'인 PAC은 다시 부르지 않는다(DEMO_KEY 한도 아끼기)"""
    res = []
    for p in cfg["pacs"]:
        row = {"group": p["group"], "company": p["company"]}
        if (keep or {}).get(p["company"], {}).get("status") == "ok":
            res.append(keep[p["company"]])
            continue
        try:
            cid, name = resolve(p, fetch)
            if not cid:
                res.append({**row, "status": "위원회 없음"})
                continue
            d = get("/schedules/schedule_b/", {"committee_id": cid, "two_year_transaction_period": cfg["cycle"], "disbursement_purpose_categories": "CONTRIBUTIONS",
                                                  "per_page": max_rows, "sort": "-disbursement_amount"}, fetch)
            rows = d.get("results") or []
            row.update({"status": "ok", "committee_id": cid, "committee": name, "n_total": (d.get("pagination") or {}).get("count"), "n_used": len(rows), "by_party": split(rows)})
        except Exception as e:  # noqa: BLE001 — 한 PAC 실패가 나머지를 막지 않게
            row["status"] = f"실패: {type(e).__name__} {str(e)[:120]}"
        res.append(row)
        time.sleep(pause)
    return res


def summarize(res):
    groups = {}
    for r in res:
        if r.get("status") != "ok":
            continue
        g = groups.setdefault(r["group"], {"민주": 0.0, "공화": 0.0, "기타": 0.0})
        for k, v in r["by_party"].items():
            g[k] += v
    for g in groups.values():
        two = g["민주"] + g["공화"]
        g["민주_몫"] = g["민주"] / two if two else None
    return groups


def main(argv):
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("--max-rows", type=int, default=100)
    a = ap.parse_args(argv)
    cfg = common.load_yaml("config/fec_pacs.yaml")
    prev = OUT / f"{cfg['cycle']}.json"
    keep = {r["company"]: r for r in json.loads(prev.read_text(encoding="utf-8")).get("pacs", [])} if prev.exists() else {}
    res = collect(cfg, a.max_rows, keep=keep)
    doc = {"as_of": datetime.now(common.KST).isoformat(timespec="seconds"), "cycle": cfg["cycle"], "source": "FEC api.open.fec.gov schedule_b(기부, 금액 큰 순)",
           "key": "DEMO_KEY" if key() == "DEMO_KEY" else "등록 키", "pacs": res, "groups": summarize(res)}
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / f"{cfg['cycle']}.json").write_text(json.dumps(doc, ensure_ascii=False, indent=1), encoding="utf-8")
    for r in res:
        bp = r.get("by_party") or {}
        print(f"{r['group']} {r['company']}: {r['status']}" + (f" · 민주 ${bp['민주']:,.0f} 공화 ${bp['공화']:,.0f} (상위 {r['n_used']}/{r['n_total']}건)" if bp else ""))
    for g, v in doc["groups"].items():
        print(f"[{g}] 민주 몫 {v['민주_몫']:.0%}" if v["민주_몫"] is not None else f"[{g}] 정당 기부 없음")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
