"""USITC DataWeb API 보조 경로 — 키 대기 (마스터 지시 2026-11-21, 연결 방법 knowledge/methods/usitc_dataweb.md)

주 경로는 radar/trade_share.py(Census API, 키 있음)다. DataWeb은 Census에 없는 칸(관세액·통관 항구·특혜 프로그램·소비용 수입)이 필요할 때만 쓴다.
공식 안내(usitc.gov/applications/dataweb/api/dataweb_query_api.html, 2026-11-21 확인): 무료 계정(Login.gov 연결) → DataWeb 'API' 탭에서 토큰 발급(6개월 유효, 자동 갱신 없음)
→ Authorization: Bearer <토큰>, 기준 주소 https://datawebws.usitc.gov/dataweb. 권장 방식은 DataWeb 화면에서 '저장한 질의(Saved Query)'를 만들고 이름으로 불러 실행하는 것.
  GET  /api/v2/savedQuery/getAllSavedQueries   → 저장한 질의 목록
  POST /api/v2/report2/runReport               → 질의 실행(본문 = 저장한 질의 JSON)
토큰은 D:/local-only/secrets/.env의 USITC_DATAWEB_TOKEN(load_env로만 읽는다). 없으면 아무것도 하지 않는다. 토큰 발급 전이라 실제 호출은 아직 시험하지 못했다.
사용: py radar/usitc_dataweb.py --list · --run <저장한 질의 이름>   → knowledge/models/consumer/dataweb/<이름>.json
"""
import argparse
import json
import sys
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from pollers import common  # noqa: E402

SOURCE_ID = "src-usitc-dataweb"
BASE = "https://datawebws.usitc.gov/dataweb"
OUT = common.ROOT / "knowledge" / "models" / "consumer" / "dataweb"


def call(path, token, body=None):
    req = urllib.request.Request(BASE + path, data=None if body is None else json.dumps(body).encode("utf-8"),
                                 headers={"Content-Type": "application/json; charset=utf-8", "Authorization": "Bearer " + token, "User-Agent": common.contact_ua()},
                                 method="GET" if body is None else "POST")
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.loads(r.read().decode("utf-8"))


def columns(groups, out=None):
    out = [] if out is None else out
    for g in groups:
        if isinstance(g, dict) and "columns" in g:
            columns(g["columns"], out)
        elif isinstance(g, dict) and "label" in g:
            out.append(g["label"])
        elif isinstance(g, list):
            columns(g, out)
    return out


def tables(resp):
    """runReport 응답 → [{columns, rows}] (측정값마다 표 하나 — 공식 안내의 getColumns·getData와 같은 위치)"""
    out = []
    for t in (resp.get("dto") or {}).get("tables") or []:
        rows = [[f.get("value") for f in r.get("rowEntries") or []] for r in ((t.get("row_groups") or [{}])[0].get("rowsNew") or [])]
        out.append({"columns": columns(t.get("column_groups") or []), "rows": rows})
    return out


def saved(token):
    return call("/api/v2/savedQuery/getAllSavedQueries", token).get("list") or []


def run(name, token=None):
    token = token or common.load_env().get("USITC_DATAWEB_TOKEN")
    if not token:
        return {"skipped": "USITC_DATAWEB_TOKEN 없음(키 대기 — knowledge/methods/usitc_dataweb.md)"}
    try:
        q = next((x for x in saved(token) if x.get("savedQueryName") == name), None)
        if q is None:
            return {"error": f"저장한 질의 '{name}' 없음"}
        tb = tables(call("/api/v2/report2/runReport", token, q))
    except Exception as e:
        common.record_health(SOURCE_ID, False, f"{type(e).__name__}: {str(e)[:80]}")
        return {"error": type(e).__name__}
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / f"{name}.json").write_text(json.dumps({"query": name, "at": common.iso(common.now_kst()), "tables": tb}, ensure_ascii=False, indent=1), encoding="utf-8")
    common.record_health(SOURCE_ID, True, None)
    return {"query": name, "tables": len(tb), "rows": sum(len(t["rows"]) for t in tb)}


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--run")
    a = ap.parse_args()
    token = common.load_env().get("USITC_DATAWEB_TOKEN")
    if a.list:
        print(json.dumps([x.get("savedQueryName") for x in saved(token)] if token else {"skipped": "USITC_DATAWEB_TOKEN 없음"}, ensure_ascii=False))
    if a.run:
        print(json.dumps(run(a.run, token), ensure_ascii=False))


if __name__ == "__main__":
    main()
