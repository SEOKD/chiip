"""소비 트렌드 보드 → 대시보드 자료 파일(JSON {rows, meta}) 내보내기 (2026-11-14 마스터 지시 '한국 외 소비 트렌드')

결정론. 입력 knowledge/models/consumer_trends/board.json · macro_series.csv(scripts/consumer/trends_board.py 뒤에 돈다).
출력(<폴더>):
  heat.json       업종·지역별 최근 지표 행(3개월 YoY·가속·5년 z·실질 근사·문턱·노출 종목) — 가격 시계열은 family us_price
  series.json     업종별 3개월 YoY 월 추이(최근 36개월) — radar/consumer_macro.metrics와 같은 식
  discovery.json  상향식 발굴 행(위키·급상승 검색·애플·스팀)과 Pulse 경보 여부
meta에는 이 파일과 계산 원천 코드의 원문을 넣는다(읽는 사람이 다시 계산할 수 있게).
사용: py scripts/consumer/board_export.py <출력 폴더>
"""
import csv
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "radar"))
import consumer_macro as cm  # noqa: E402

DIR = ROOT / "knowledge" / "models" / "consumer_trends"
FAMILY = {"us": "미국 소매", "jp": "일본 가계 지출", "jp_inbound": "일본 방일객", "eu": "유럽 소매 판매량", "uk": "영국 소매", "us_price": "미국 업종 물가"}
SRC = {"us": "FRED 경유 U.S. Census Bureau 월간 소매(계절조정·명목)", "us_price": "FRED 경유 BLS CPI(계절조정)", "jp": "総務省統計局 家計調査 2인 이상 가구(e-Stat 0004023601)",
       "jp_inbound": "日本政府観光局（JNTO） 訪日外客数", "eu": "Eurostat sts_trtu_m 소매 판매량(VOL_SLS·SCA)", "uk": "ONS 소매판매지수(DRSI)"}


def pc(v):
    """비율 → % 숫자(소수 둘째 자리) — 화면 숫자와 자료 칸이 같게"""
    return None if v is None else round(v * 100, 2)


def heat_rows(board, macro):
    rows = []
    for fam, rs in (board.get("heat") or {}).items():
        for r in rs:
            rows.append({"id": r["id"], "family": fam, "family_name": FAMILY.get(fam, fam), "region": r.get("region") or "", "name": r["name"], "month": r["month"],
                         "yoy3": r["yoy3"], "accel_pp": r.get("accel_pp"), "z": r.get("z"), "real_yoy3": r.get("real_yoy3"), "flag": r.get("flag") or "",
                         "noisy": bool(r.get("noisy")), "exposure": " · ".join(str(e) for e in r.get("exposure") or []), "source": SRC.get(fam, ""),
                         "yoy3_pct": pc(r["yoy3"]), "real_pct": pc(r.get("real_yoy3"))})
    for r in board.get("prices") or []:
        rows.append({"id": r["id"], "family": "us_price", "family_name": FAMILY["us_price"], "region": "미국", "name": r["name"].replace("물가 ", ""), "month": r["month"],
                     "yoy3": r["yoy3"], "accel_pp": r.get("accel_pp"), "z": r.get("z"), "real_yoy3": None, "flag": "", "noisy": False, "exposure": "", "source": SRC["us_price"],
                     "yoy3_pct": pc(r["yoy3"]), "real_pct": None})
    return rows


def series_rows(ids, months=36):
    data = {}
    with (DIR / "macro_series.csv").open(encoding="utf-8", newline="") as f:
        for r in csv.DictReader(f):
            if r["id"] in ids:
                data.setdefault(r["id"], {})[r["month"]] = float(r["value"])
    out = []
    for sid, s in data.items():
        kind = "yoy" if sid in YOY_IDS else "level"
        last = max(s)
        for k in range(months - 1, -1, -1):
            m = cm.shift(last, -k)
            sub = {x: v for x, v in s.items() if x <= m}
            if m not in sub:
                continue
            r = cm.metrics(sub, kind)
            if r and r["month"] == m and r.get("yoy3") is not None:
                out.append({"id": sid, "month": m, "yoy3": r["yoy3"], "yoy3_pct": pc(r["yoy3"])})
    return out


YOY_IDS = set()


def discovery_rows(board):
    alerted_titles = {(a.get("source"), a.get("title") or a.get("query") or a.get("name")) for a in board.get("alerts") or []}
    out = []
    rising = board.get("rising") or {}
    for r in rising.get("wiki") or []:
        b = r.get("brand") or {}
        out.append({"source": "위키 조회", "where": r["project"].split(".")[0], "item": r["title"], "metric": r["views7"], "metric_label": "7일 조회",
                    "accel": r["accel"], "company": b.get("company") or "", "ticker": b.get("ticker") or "", "kind": r.get("kind") or "",
                    "alert": ("wiki", r["title"]) in alerted_titles})
    for r in rising.get("trends") or []:
        b = r.get("brand") or {}
        out.append({"source": "급상승 검색", "where": r["geo"], "item": r["query"], "metric": r["traffic"], "metric_label": "검색량(+)", "accel": None,
                    "company": b.get("company") or "", "ticker": b.get("ticker") or "", "kind": "브랜드", "alert": ("trends", r["query"]) in alerted_titles})
    for key, label in (("apple", "애플 앱 순위"), ("steam", "스팀 판매 순위")):
        for r in rising.get(key) or []:
            i = r.get("issuer") or {}
            out.append({"source": label, "where": (r.get("country") or "").upper(), "item": r["name"], "metric": r["rank"], "metric_label": "순위", "accel": None,
                        "company": i.get("company") or "", "ticker": i.get("ticker") or "", "kind": r.get("kind") or "", "alert": (key, r["name"]) in alerted_titles})
    for i, r in enumerate(out):
        r["key"] = f"{r['source']}|{r['where']}|{r['item']}"[:200]
    return out


def code_meta(*paths):
    return [{"label": p.name, "value": p.read_text(encoding="utf-8"), "type": "code", "lang": "python"} for p in paths]


def main(outdir):
    out = Path(outdir)
    out.mkdir(parents=True, exist_ok=True)
    board = json.loads((DIR / "board.json").read_text(encoding="utf-8"))
    macro = json.loads((DIR / "macro_latest.json").read_text(encoding="utf-8"))
    YOY_IDS.update(sid for sid, r in macro.get("series", {}).items() if r.get("kind") == "yoy")
    heat = heat_rows(board, macro)
    me = Path(__file__)
    base = [{"label": "기준", "value": f"공식 통계 {board.get('macro_as_of')} · 발굴 {board.get('discovery_as_of')}"}]
    (out / "heat.json").write_text(json.dumps({"rows": heat, "meta": base + [{"label": "원천", "value": " · ".join(sorted(set(SRC.values())))}]
                                               + code_meta(me, ROOT / "radar" / "consumer_macro.py")}, ensure_ascii=False), encoding="utf-8")
    ser = series_rows({r["id"] for r in heat})
    (out / "series.json").write_text(json.dumps({"rows": ser, "meta": base + [{"label": "입력", "value": "knowledge/models/consumer_trends/macro_series.csv(최근 72개월)"}]
                                                 + code_meta(me)}, ensure_ascii=False), encoding="utf-8")
    disc = discovery_rows(board)
    (out / "discovery.json").write_text(json.dumps({"rows": disc, "meta": base + [{"label": "원천", "value": "애플 앱 순위 RSS · 스팀 상점 판매 상위 · Wikimedia 일별 상위 1,000 문서 · Google Trends 급상승 RSS"}]
                                                    + code_meta(me, ROOT / "radar" / "consumer_discovery.py")}, ensure_ascii=False), encoding="utf-8")
    return len(heat), len(ser), len(disc)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    print(main(sys.argv[1]))
