"""한국 외 소비 트렌드 보드 — 공식 통계(무엇이 팔리나) + 상향식 발굴(무엇이 뜨나)을 한 장으로 (마스터 지시 2026-11-14)

결정론(모델 없음). 입력 knowledge/models/consumer_trends/macro_latest.json(radar/consumer_macro.py) · discovery_latest.json(radar/consumer_discovery.py).
출력 outputs/consumer/trends_<YYYY-MM-DD>.md(사람이 읽는 보드) · knowledge/models/consumer_trends/board.json(대시보드 자료 — heat·flags·rising·series).
해석·내러티브는 모델 몫(Weekly·Industry·Analysis가 이 보드를 읽는다). 보드는 숫자와 매핑만 고정한다.
금지표: 업종 판매 증가 → 특정 기업 매출 / 관심 증가 → 매출. 노출 종목은 가설.
출처 표기: 미국 Census·BLS(FRED 경유) · 総務省統計局 家計調査(e-Stat) · 日本政府観光局(JNTO) · Eurostat · ONS.
사용: py scripts/consumer/trends_board.py [--date YYYY-MM-DD]
"""
import csv
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "radar"))
from pollers import common  # noqa: E402

DIR = ROOT / "knowledge" / "models" / "consumer_trends"
MACRO, DISC, SERIES, BOARD = DIR / "macro_latest.json", DIR / "discovery_latest.json", DIR / "macro_series.csv", DIR / "board.json"
OUTDIR = ROOT / "outputs" / "consumer"
FAMILY = [("us", "미국 소매(Census, 명목·계절조정)"), ("jp", "일본 가계 지출(総務省 家計調査, 2인 이상 가구 명목)"), ("jp_inbound", "일본 방일객(JNTO)"),
          ("eu", "유럽 소매 판매량(Eurostat, 실질·계절조정)"), ("uk", "영국 소매(ONS)")]
SOURCES = "출처: 미국 Census·BLS(FRED 경유) · 総務省統計局 家計調査(e-Stat) · 日本政府観光局（JNTO） · Eurostat · ONS · 애플 앱 순위 RSS · 스팀 상점 · Wikimedia 조회수 · Google Trends 급상승"


def pct(x, nd=1):
    return "—" if x is None else f"{x * 100:+.{nd}f}%"


def pp(x):
    return "—" if x is None else f"{x:+.1f}%p"


def zz(x):
    return "—" if x is None else f"{x:+.1f}"


def ex_short(ex, n=4):
    return ", ".join(str(e) for e in (ex or [])[:n])


def heat(macro):
    """원천별 표 행 — 가격 시계열과 끊긴 시계열은 빼고, z 높은 순"""
    rows = {f: [] for f, _ in FAMILY}
    for sid, r in macro.get("series", {}).items():
        if r.get("cat") == "price" or r.get("stale") or r.get("yoy3") is None:
            continue
        rows.setdefault(r["family"], []).append({"id": sid, "name": r["name"], "region": r.get("region"), "month": r["month"], "yoy3": r["yoy3"],
                                                 "accel_pp": r.get("accel_pp"), "z": r.get("z"), "real_yoy3": r.get("real_yoy3"), "flag": r.get("flag"),
                                                 "noisy": r.get("noisy", False), "exposure": r.get("exposure") or []})
    for f in rows:
        rows[f].sort(key=lambda x: -(x["z"] if x["z"] is not None else -99))
    return rows


def prices(macro):
    return sorted([{"id": sid, "name": r["name"], "month": r["month"], "yoy3": r.get("yoy3"), "accel_pp": r.get("accel_pp"), "z": r.get("z")}
                   for sid, r in macro.get("series", {}).items() if r.get("cat") == "price" and r.get("yoy3") is not None], key=lambda x: -(x["z"] or -99))


def render(macro, disc, day):
    h = heat(macro)
    flagged = [r for f in h.values() for r in f if r["flag"]]
    L = [f"# 한국 외 소비 트렌드 보드 — {day}", "",
         "공식 통계는 무엇이 실제로 팔리는지(월간, 늦지만 정직하다), 상향식 발굴은 무엇이 막 뜨는지(매일, 빠르지만 단서다)를 본다. "
         "노출 종목은 업종·브랜드로 연결한 가설이다(금지표: 업종 판매 증가 → 특정 기업 매출, 관심 증가 → 매출).", ""]
    L += ["## ■ 문턱을 넘은 업종", ""]
    if flagged:
        L += ["| 업종 | 기준 달 | 3개월 YoY | 가속 | 5년 z | 노출 종목(가설) |", "|---|---|---|---|---|---|"]
        for r in sorted(flagged, key=lambda x: -abs(x["accel_pp"] or 0)):
            L.append(f"| {'▲' if r['flag'] == 'up' else '▼'} {r['name']} | {r['month']} | {pct(r['yoy3'])} | {pp(r['accel_pp'])} | {zz(r['z'])} | {ex_short(r['exposure'])} |")
    else:
        L.append("이번에는 없다.")
    L += ["", f"문턱: 가속 ±{(macro.get('alert') or {}).get('accel_pp', 3)}%p와 5년 z ±1.5가 같은 방향(가계조사 품목은 ±8%p — 표본 잡음)."]
    for fam, title in FAMILY:
        rows = h.get(fam) or []
        if not rows:
            continue
        if fam == "eu":   # 나라 × 업종 격자(48줄 표는 휴대폰에서 못 읽는다) — 칸 = 3개월 YoY, ▲▼ = 문턱
            geos = list(dict.fromkeys(r["region"] for r in sorted(rows, key=lambda r: r["region"] != "EU27")))
            cats = {}
            for r in rows:
                cats.setdefault(r["name"].split(" ", 1)[1], {})[r["region"]] = r
            L += ["", f"## ■ {title}", "", "칸 = 3개월 YoY(▲▼ 문턱, 괄호 = 5년 z). 노출 종목은 업종 아래.", "",
                  "| 업종 | " + " | ".join(geos) + " |", "|---|" + "---|" * len(geos)]
            for cname, by in cats.items():
                cells = []
                for g in geos:
                    r = by.get(g)
                    cells.append("—" if not r else f"{'▲' if r['flag'] == 'up' else '▼' if r['flag'] == 'down' else ''}{pct(r['yoy3'])}({zz(r['z'])})")
                L.append(f"| {cname} | " + " | ".join(cells) + " |")
            ex = {cname: next((r["exposure"] for r in by.values() if r["exposure"]), []) for cname, by in cats.items()}
            L += [""] + [f"- {c}: {ex_short(e, 6)}" for c, e in ex.items() if e]
            continue
        L += ["", f"## ■ {title}", "", "| 업종 | 기준 달 | 3개월 YoY | 가속 | 5년 z | 실질 근사 | 노출 종목(가설) |", "|---|---|---|---|---|---|---|"]
        for r in rows:
            mark = "▲ " if r["flag"] == "up" else "▼ " if r["flag"] == "down" else ""
            L.append(f"| {mark}{r['name']}{' ·잡음' if r['noisy'] else ''} | {r['month']} | {pct(r['yoy3'])} | {pp(r['accel_pp'])} | {zz(r['z'])} | {pct(r['real_yoy3'])} | {ex_short(r['exposure'], 3)} |")
    pr = prices(macro)
    if pr:
        L += ["", "## ■ 미국 업종 물가(BLS CPI, 계절조정) — 가격 결정력·관세 전가", "", "| 품목 | 기준 달 | 3개월 YoY | 가속 | 5년 z |", "|---|---|---|---|---|"]
        L += [f"| {r['name'].replace('물가 ', '')} | {r['month']} | {pct(r['yoy3'])} | {pp(r['accel_pp'])} | {zz(r['z'])} |" for r in pr]
        L.append("실질 근사 = 판매 3개월 YoY − 짝지은 물가 3개월 YoY(같은 달끼리만).")
    rising = (disc or {}).get("rising") or {}
    L += ["", "## ■ 새로 뜨는 것(상향식 — 단서)", ""]
    al = (disc or {}).get("alerts") or []
    if al:
        L += [f"- {a['headline']}" for a in al]
    else:
        L.append("- 상장사에 매핑된 경보 없음.")
    w = rising.get("wiki") or []
    if w:
        L += ["", "| 위키 | 문서 | 7일 조회 | 평소 대비 | 연결 |", "|---|---|---|---|---|"]
        L += [f"| {r['project'].split('.')[0]} | {r['title'][:60]} | {r['views7']:,} | ×{r['accel']} | {(r.get('brand') or {}).get('company') or r.get('kind')} |" for r in w[:20]]
    for key, label in (("apple", "애플 앱 순위"), ("steam", "스팀 판매 순위")):
        rs = rising.get(key) or []
        base = ((disc or {}).get("baseline_from") or {}).get(key)
        if not base:
            L += ["", f"{label}: 기록을 쌓는 중(7일 기준선이 생기면 신규 진입·급상승을 판정한다 — 기록 {((disc or {}).get('baseline_days') or {}).get(key, 0)}일)."]
            continue
        L += ["", f"{label}(기준 {base} 대비):", ""]
        L += [f"- {r.get('country', '').upper()} {r.get('feed', '')} {r['rank']}위 {r['kind']} — {r['name'][:40]} ({(r.get('issuer') or {}).get('company') or r.get('artist') or r.get('publisher') or '미매핑'})" for r in rs[:15]] or ["- 없음."]
    t = rising.get("trends") or []
    if t:
        L += ["", "급상승 검색(브랜드 사전에 걸린 것만):", ""]
        L += [f"- {r['geo']} '{r['query']}' {r['traffic']:,}+ → {r['brand']['company']}" for r in t[:10]]
    if (macro.get("errors") or []) or ((disc or {}).get("errors") or []):
        L += ["", f"수집 오류: {'; '.join((macro.get('errors') or []) + ((disc or {}).get('errors') or []))}"]
    L += ["", SOURCES, ""]
    return "\n".join(L), h, flagged, pr


def series_rows(ids):
    if not SERIES.exists():
        return []
    with SERIES.open(encoding="utf-8", newline="") as f:
        return [r for r in csv.DictReader(f) if r["id"] in ids]


def run(day=None):
    day = day or common.now_kst().date().isoformat()
    macro = json.loads(MACRO.read_text(encoding="utf-8")) if MACRO.exists() else {"series": {}}
    macro["alert"] = ((common.load_yaml("config/consumer_trends.yaml") or {}).get("macro") or {}).get("alert")
    disc = json.loads(DISC.read_text(encoding="utf-8")) if DISC.exists() else {}
    md, h, flagged, pr = render(macro, disc, day)
    OUTDIR.mkdir(parents=True, exist_ok=True)
    out = OUTDIR / f"trends_{day}.md"
    out.write_text(md, encoding="utf-8")
    # 시계열은 macro_series.csv(최근 72개월)에 있다 — 보드 파일에는 넣지 않는다(매일 다시 쓰는 파일이 무거워지지 않게)
    BOARD.write_text(json.dumps({"day": day, "macro_as_of": macro.get("as_of"), "discovery_as_of": disc.get("as_of"), "heat": h, "flags": flagged, "prices": pr,
                                 "alerts": disc.get("alerts") or [], "rising": disc.get("rising") or {}, "baseline_days": disc.get("baseline_days"),
                                 "series_file": "knowledge/models/consumer_trends/macro_series.csv", "sources": SOURCES}, ensure_ascii=False, indent=1), encoding="utf-8")
    return out, len(flagged)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    d = sys.argv[sys.argv.index("--date") + 1] if "--date" in sys.argv else None
    p, n = run(d)
    print(f"{p.relative_to(ROOT)} · 문턱 업종 {n}")
