"""대만·중국·홍콩 종목 발굴 스크리너 — 계량 스크린 → 테마 지도 → 발굴 선별 합류 (마스터 지시 2026-11-09, 설정 config/asia_discovery.yaml)

왜: 발굴 후보 529종목 중 대만 20·홍콩 2·중국 본토 0이었다. 펀더멘털 공급원 Fiscal.ai가 대만 15·중국 26·홍콩 21종목만 지원해 늘어날 수 없었다.
흐름(수집은 결정론, TradingView 호출만 모델):
  ① --specs  : 시장별 스크리너 호출 사양(JSON) — 모델이 mcp-tv-run-screener를 시장마다 한 번씩(병렬 금지) 부르고 응답을 파일로 저장
  ② --put <시장> <파일> : 응답 저장(knowledge/models/discovery/asia/<시장>.json)
  ③ 대만 월매출 전 종목(TWSE·TPEx 공개 데이터, 결정론) — 가속 = 당월 전년 대비 − 연누계 전년 대비(%p). tw_revenue()
  ④ --score  : 시가총액·거래대금 하한 → 시장 안 z점수(±3 절단) 가중합 + 테마·한국 연결 가점 → 시장별 상위 top_n
     출력 knowledge/models/discovery/asia_candidates.json(screen.py가 '아시아 스크리너' 테마로 합류)·outputs/discovery/asia_<날짜>.md
  ⑤ --pulse  : 대만 월매출 급증(새 달, 전자 업종, 전년 +50% 이상·가속 +20%p 이상·월 3억 대만달러 이상, 감시 밖 회사 포함) → inbox src-tw-revenue-surge
점수는 후보를 줄이는 보조이지 판단이 아니다 — 편입은 위원회 메모(사람 판단). 금지표: 매출 급증 → 이익 증가가 아니다(가격·믹스·원가).
"""
import csv
import io
import json
import math
import re
import sys
from datetime import date
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "radar"))
DIR = ROOT / "knowledge" / "models" / "discovery"
ASIA = DIR / "asia"
TW_ELEC = re.compile(r"半導體|電子|電腦|光電|通信網路|資訊服務|電機機械|電器電纜")


def cfg():
    return yaml.safe_load((ROOT / "config" / "asia_discovery.yaml").read_text(encoding="utf-8"))


def specs(c=None):
    c = c or cfg()
    out = []
    for m, v in c["markets"].items():
        lo, hi = c["mcap_usd"]
        fx = c["fx_to_usd"][v["currency"]]
        out.append({"market": m, "filters": {"sector": c["sectors"], "market_cap_basic": [round(lo / fx), round(hi / fx)]},
                    "columns": c["columns"], "sort_by": "total_revenue_yoy_growth_ttm", "sort_order": "desc", "limit": v["limit"]})
    return out


def put(market, path):
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    rows = (raw.get("data") or raw).get("rows") if isinstance(raw, dict) else raw
    ASIA.mkdir(parents=True, exist_ok=True)
    (ASIA / f"{market}.json").write_text(json.dumps({"as_of": date.today().isoformat(), "rows": rows}, ensure_ascii=False), encoding="utf-8")
    return len(rows or [])


def tw_revenue(fetch=True):
    """대만 상장·장외 전 종목 월매출(전자 업종) → {코드: {...}} — 같은 원천을 radar/reverse/collectors/twse_monthly.py가 감시 회사만 남겨 쓴다"""
    f = DIR / "tw_revenue_all.json"
    if not fetch and f.exists():
        return json.loads(f.read_text(encoding="utf-8"))
    from pollers import common
    sys.path.insert(0, str(ROOT / "radar" / "reverse" / "collectors"))
    import twse_monthly as T
    rows = list(csv.reader(io.StringIO(common.http_get(T.URL, timeout=60).decode("utf-8-sig"))))[1:]
    try:
        rows += T.tpex_rows()
    except Exception:
        pass
    num = lambda x: float(str(x).replace(",", "")) if str(x).strip() not in ("", "-") else None
    out = {}
    for r in rows:
        if len(r) < 13 or not TW_ELEC.search(r[4] or ""):
            continue
        yoy, ytd = num(r[9]), num(r[12])
        out[r[2]] = {"code": r[2], "name": r[3], "industry": r[4], "period": T.roc_to_period(r[1]), "rev_k": num(r[5]), "mom": num(r[8]), "yoy": yoy, "ytd_yoy": ytd,
                     "accel": round(yoy - ytd, 1) if yoy is not None and ytd is not None else None}
    DIR.mkdir(parents=True, exist_ok=True)
    f.write_text(json.dumps(out, ensure_ascii=False), encoding="utf-8")
    return out


def _z(vals, sign=1):
    xs = [v for v in vals if v is not None and math.isfinite(v)]
    if len(xs) < 3:
        return [0.0 for _ in vals]
    m = sum(xs) / len(xs)
    sd = (sum((x - m) ** 2 for x in xs) / (len(xs) - 1)) ** 0.5 or 1.0
    return [0.0 if v is None or not math.isfinite(v) else max(-3.0, min(3.0, sign * (v - m) / sd)) for v in vals]


def korea_links():
    """대만 코드·회사 이름 → 한국 기업(월매출 거울 mirror_for + 공급망 상대방 목록)"""
    sys.path.insert(0, str(ROOT / "scripts" / "article"))
    import pitch_pool as P
    codes, _ = P.tw_mirror()
    names = (yaml.safe_load((ROOT / "config" / "korea_counterparties.yaml").read_text(encoding="utf-8")) or {}).get("counterparties") or []
    return codes, names


def score(c=None, tw=None):
    c = c or cfg()
    tw = tw if tw is not None else tw_revenue(fetch=False)
    codes, cps = korea_links()
    theme_rx = {k: re.compile(v, re.I) for k, v in c["themes"].items()}
    w, b = c["weights"], c["bonus"]
    result = {}
    for m, mv in c["markets"].items():
        f = ASIA / f"{m}.json"
        if not f.exists():
            continue
        fx = c["fx_to_usd"][mv["currency"]]
        rows = []
        for r in json.loads(f.read_text(encoding="utf-8"))["rows"] or []:
            vt = (r.get("average_volume_30d_calc") or 0) * (r.get("close") or 0) * fx
            mc = (r.get("market_cap_basic") or 0) * fx
            if vt < c["min_value_traded_usd"] or not (c["mcap_usd"][0] <= mc <= c["mcap_usd"][1]):
                continue
            if c.get("exclude_industries") and re.search(c["exclude_industries"], r.get("industry") or "", re.I):
                continue
            code = str(r.get("name"))
            t = tw.get(code) if m == "taiwan" else None
            rows.append({**r, "mcap_usd": mc, "value_traded_usd": vt, "accel": (t or {}).get("accel"), "tw_yoy": (t or {}).get("yoy"), "tw_period": (t or {}).get("period")})
        if not rows:
            continue
        cap = c.get("growth_outlier") or 1e9
        g = _z([None if (r.get("total_revenue_yoy_growth_ttm") or 0) > cap else r.get("total_revenue_yoy_growth_ttm") for r in rows])   # 이상치는 성장 z 0(합병·기저 효과 의심)
        a = _z([r.get("accel") for r in rows]) if m == "taiwan" else [0.0] * len(rows)
        q = _z([r.get("operating_margin_ttm") for r in rows])
        mo = _z([r.get("Perf.6M") for r in rows])
        va = _z([r.get("enterprise_value_to_revenue_ttm") for r in rows], -1)
        sz = _z([math.log(r["mcap_usd"]) for r in rows], -1)
        wg = w["growth"] + (0 if m == "taiwan" else w["accel"])   # 월매출이 없는 시장은 가속 가중을 성장에 더한다
        out = []
        for i, r in enumerate(rows):
            hay = f"{r.get('description', '')} {r.get('industry', '')}"
            themes = [k for k, rx in theme_rx.items() if rx.search(hay)]
            link = None
            if m == "taiwan" and str(r.get("name")) in codes:
                link = codes[str(r["name"])][1]
            else:
                for x in cps:
                    if any(re.search(r"(?<![A-Za-z])" + re.escape(n) + r"(?![A-Za-z])", r.get("description") or "") for n in x["names"]):
                        link = x["korea"]
                        break
            s = (wg * g[i] + (w["accel"] * a[i] if m == "taiwan" else 0) + w["quality"] * q[i] + w["momentum"] * mo[i] + w["value"] * va[i] + w["size"] * sz[i]
                 + (b["theme"] if themes else 0) + (b["korea_link"] if link else 0))
            out.append({"symbol": r.get("symbol"), "code": str(r.get("name")), "name": r.get("description"), "market": mv["region"], "industry": r.get("industry"),
                        "themes": themes, "korea_link": link, "score": round(s, 2), "mcap_usd": round(r["mcap_usd"]), "rev_growth": r.get("total_revenue_yoy_growth_ttm"),
                        "op_margin": r.get("operating_margin_ttm"), "ev_sales": r.get("enterprise_value_to_revenue_ttm"), "perf_6m": r.get("Perf.6M"),
                        "tw_accel": r.get("accel"), "tw_yoy": r.get("tw_yoy"), "tw_period": r.get("tw_period"),
                        "outlier": (r.get("total_revenue_yoy_growth_ttm") or 0) > cap})
        out.sort(key=lambda x: -x["score"])
        if m == "hongkong" and "china" in result:   # A+H 동시 상장은 본토(A주)만 남긴다(2026-11-09 시험: 기가디바이스·간펑리튬·Robotechnik 중복)
            stem = lambda x: re.sub(r"[^a-z]", "", re.sub(r"(co\.?,? ?ltd\.?|inc\.?|corp\.?|group|class [ah]).*$", "", (x or "").lower()))
            a_names = {stem(r["name"]) for r in result["china"]} | {stem(r.get("description")) for r in json.loads((ASIA / "china.json").read_text(encoding="utf-8"))["rows"] or []}
            out = [r for r in out if stem(r["name"]) not in a_names]
        result[m] = out[:c["top_n"]]
    (DIR / "asia_candidates.json").write_text(json.dumps({"as_of": date.today().isoformat(), "markets": result}, ensure_ascii=False, indent=1), encoding="utf-8")
    md = [f"# 대만·중국·홍콩 발굴 스크리너 {date.today().isoformat()}", "", "시장 안 z점수 합성(성장·가속·수익성·모멘텀·밸류·규모) + 테마·한국 연결 가점. 판단 보조이지 매수 권유가 아니다.", ""]
    for m, rows in result.items():
        md += [f"## {m}", "| 순위 | 종목 | 업종 | 점수 | 매출 YoY | 영업이익률 | 6개월 | 테마 | 한국 연결 |", "|---|---|---|---|---|---|---|---|---|"]
        for i, r in enumerate(rows, 1):
            f1 = lambda v: "-" if v is None else f"{v:+.0f}%"
            md.append(f"| {i} | {r['name']}({r['symbol']}) | {r['industry']} | {r['score']} | {f1(r['rev_growth'])}{' (이상치)' if r.get('outlier') else ''} | {f1(r['op_margin'])} | {f1(r['perf_6m'])} | {', '.join(r['themes']) or '-'} | {', '.join(r['korea_link'] or []) or '-'} |")
        md.append("")
    (ROOT / "outputs" / "discovery").mkdir(parents=True, exist_ok=True)
    (ROOT / "outputs" / "discovery" / f"asia_{date.today():%Y%m%d}.md").write_text("\n".join(md), encoding="utf-8")
    return result


def pulse(c=None):
    """대만 월매출 급증(새 달) → inbox — 감시 밖 전자 업종 회사까지(2026-11-09)"""
    from pollers import common
    prev = tw_revenue(fetch=False) if (DIR / "tw_revenue_all.json").exists() else {}
    cur = tw_revenue(fetch=True)
    st = common.load_state("tw_revenue_surge", {})
    hits = []
    for code, r in cur.items():
        p = prev.get(code) or {}
        if not prev or p.get("period") == r["period"] or st.get(code) == r["period"]:
            continue
        if (r["yoy"] or 0) >= 50 and (r["accel"] or 0) >= 20 and (r["rev_k"] or 0) >= 300000:
            hits.append(r)
    hits.sort(key=lambda r: -(r["accel"] or 0))
    items = []
    for r in hits[:15]:
        st[r["code"]] = r["period"]
        items.append(common.make_item("src-tw-revenue-surge", f"{r['code']}-{r['period']}", "https://mopsov.twse.com.tw/mops/web/t05st10_ifrs",
                                      f"[Taiwan monthly revenue] {r['name']}({r['code']}) {r['period']} YoY {r['yoy']:+.0f}%, accel {r['accel']:+.0f}pp vs YTD",
                                      common.iso(common.now_kst()), "공시", "en", f"{r['industry']} · 월매출 {r['rev_k'] / 1e5:,.1f}억 대만달러 · 전월 {r['mom']:+.0f}%",
                                      extra={"source_class": "공시", "tw_code": r["code"]}))
    common.save_state("tw_revenue_surge", st)
    n = len(common.save_new_items(items) or []) if items else 0
    return f"대만 월매출 전 종목 {len(cur)} · 급증 {len(hits)} · inbox {n}" + (" (첫 실행 — 기준선)" if not prev else "")


def run():
    """run_hourly 진입점 — 대만 월매출 전 종목 갱신·급증 알림(결정론)"""
    return pulse()


def main(argv):
    sys.stdout.reconfigure(encoding="utf-8")
    if argv[:1] == ["--specs"]:
        print(json.dumps(specs(), ensure_ascii=False, indent=1))
    elif argv[:1] == ["--put"]:
        print(put(argv[1], argv[2]), "행")
    elif argv[:1] == ["--score"]:
        r = score()
        for m, rows in r.items():
            print(m, [f"{x['name']}({x['score']})" for x in rows[:5]])
    elif argv[:1] == ["--pulse"]:
        print(pulse())
    else:
        print(__doc__)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
