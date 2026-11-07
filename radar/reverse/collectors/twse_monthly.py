"""L3/거울 매트릭스 — 대만 상장사 월매출 (TWSE 공개 데이터 t187ap05_L.csv)

config/mirror_matrix.yaml 의 tw_codes 기업만 추려 knowledge/models/mirror_monthly.csv 에 누적.
새 달 데이터가 들어오면 mirror-check 스킬 입력용 후보를 만든다.
단위: 천 대만달러(NT$1,000). 연월은 민국력(115 = 2026) → 서기로 변환.
장외(TPEx) 상장사는 TPEx OpenAPI mopsfin_t187ap05_O(JSON, 같은 열)로 받는다(2026-11-07). 대만 공시 재무 감시 목록
(pollers.tw_financials.universe — AI 밸류체인)도 같은 표에 쌓는다. 그 종목은 mirror_for가 비어 있어 거울 후보를 만들지 않는다.
"""
import csv
import io

from common_rev import common, save_candidates

SOURCE_ID = "src-twse-monthly"
URL = "https://mopsfin.twse.com.tw/opendata/t187ap05_L.csv"
TPEX_URL = "https://www.tpex.org.tw/openapi/v1/mopsfin_t187ap05_O"
TPEX_KEYS = ["出表日期", "資料年月", "公司代號", "公司名稱", "產業別", "營業收入-當月營收", "營業收入-上月營收", "營業收入-去年當月營收",
             "營業收入-上月比較增減(%)", "營業收入-去年同月增減(%)", "累計營業收入-當月累計營收", "累計營業收入-去年累計營收", "累計營業收入-前期比較增減(%)"]
OUT = common.ROOT / "knowledge" / "models" / "mirror_monthly.csv"
COLS = ["period", "tw_code", "name", "industry", "revenue_k_twd", "mom_pct", "yoy_pct", "ytd_k_twd", "ytd_yoy_pct",
        "mirror_for", "source_url", "retrieved"]


def roc_to_period(s):
    s = s.strip()
    return f"{int(s[:-2]) + 1911}-{s[-2:]}"


def tpex_rows():
    """TPEx JSON → TWSE CSV와 같은 열 순서의 행"""
    import json
    return [[str(r.get(k, "")) for k in TPEX_KEYS] for r in json.loads(common.http_get(TPEX_URL, timeout=60))]


def run():
    matrix = common.load_yaml("config/mirror_matrix.yaml") or {}
    wanted = {}
    for t0, groups in (matrix.get("mirrors") or {}).items():
        for g in groups:
            for code in g.get("tw_codes", []) or []:
                wanted.setdefault(str(code), set()).add(t0)
    from pollers import tw_financials
    for code in tw_financials.universe():
        wanted.setdefault(code, set())
    raw = common.http_get(URL, timeout=60).decode("utf-8-sig")
    rows = [(r, URL) for r in list(csv.reader(io.StringIO(raw)))[1:]]
    try:
        rows += [(r, TPEX_URL) for r in tpex_rows()]
    except Exception as e:   # TPEx가 막혀도 상장분은 쌓는다
        common.record_health(SOURCE_ID + "-tpex", False, f"{type(e).__name__}: {e}")
    existing = set()
    if OUT.exists():
        with OUT.open(encoding="utf-8", newline="") as f:
            existing = {(r["period"], r["tw_code"]) for r in csv.DictReader(f)}
    new_rows, cands, found = [], [], set()
    for r, src in rows:
        if len(r) < 13 or r[2] not in wanted:
            continue
        found.add(r[2])
        period = roc_to_period(r[1])
        if (period, r[2]) in existing:
            continue
        new_rows.append({"period": period, "tw_code": r[2], "name": r[3], "industry": r[4], "revenue_k_twd": r[5],
                         "mom_pct": r[8], "yoy_pct": r[9], "ytd_k_twd": r[10], "ytd_yoy_pct": r[12],
                         "mirror_for": ";".join(sorted(wanted[r[2]])), "source_url": src,
                         "retrieved": common.iso(common.now_kst())})
        for t0 in wanted[r[2]]:
            cands.append({"uid": f"{period}:{r[2]}", "mentioned_entity": t0, "match_text": r[3],
                          "counterparty": f"{r[3]}({r[2]})", "form": "월매출", "published_at": period,
                          "url": src, "language": "zh", "signal_type_hint": "무역거울",
                          "data": {"revenue_k_twd": r[5], "mom_pct": r[8], "yoy_pct": r[9]}})
    write_header = not OUT.exists()
    with OUT.open("a", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=COLS, lineterminator="\n")
        if write_header:
            w.writeheader()
        w.writerows(new_rows)
    missing = sorted(set(wanted) - found)
    n = save_candidates("L3", SOURCE_ID, cands)
    common.record_health(SOURCE_ID, True, None)
    return len(new_rows), n, missing


if __name__ == "__main__":
    rows, n, missing = run()
    print(f"대만 월매출: 새 행 {rows}, 후보 {n}, 파일에 없는 코드(장외 등) {missing}")
