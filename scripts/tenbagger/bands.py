"""시가총액 구간 엔진 — Chiip Ten-bagger (마스터 지시 2026-10-29 "$1B 이상 $10B 미만 반도체, AI 밸류체인 및 소프트웨어, 방위 종목들도 다뤄라.
시가총액 $10B~$20B … $200B 이상 등 체계적으로 나눠 접근해야 텐배거 종목을 더욱 용이하게 찾을 수 있다. 이를 엔진에 담아라.")

왜 구간인가: 작은 회사와 큰 회사를 한 잣대로 줄 세우면 순위가 크기에 끌려간다. 같은 구간 안에서만 백분위로 비교하고(구간 상대 점수),
구간마다 10배의 산술이 다르다는 것(목표 시가총액 → 필요한 매출 → 필요한 성장률 → 참조 시장 대비 점유)을 숫자로 보여준다.

유니버스(시드): config/valuation.yaml universe · config/earnings_watch.yaml extra · config/discovery.yaml 후보 · config/coverage.yaml ·
  config/defense.yaml 상장 기업. EODHD_API_KEY가 있으면 EODHD 스크리너로 시총 $1B 이상 반도체·소프트웨어·방위를 자동으로 더한다.
시가총액·펀더멘털: knowledge/models/discovery/fundamentals.json — 일요일 Ten-bagger 회차의 모델이 Fiscal.ai fundamentals.js 출력을(scripts/fiscal/adapter.py --fund, 2026-10-30 ADR-012 — 옛 easyconomics 응답은 --put)
  `--put <id> <응답 JSON 파일>`로 넣는다(필드 추출·통화 환산은 이 스크립트가 한다, 환율은 ECB 기준환율).
점수: config/tenbagger.yaml factors(FCF 수익률·B/M·크기·질·성장·병목)를 구간 안 백분위로 → 0~10. 빠진 값은 중립(50%)이고 '빠진 자료'로 표시.
출력: outputs/tenbagger/bands/<YYYYMMDD>.md · 구간 이동 knowledge/models/tenbagger/bands_history.csv. 점수는 판단 보조 — 매수 권유 아님.

사용: py scripts/tenbagger/bands.py              # 구간 표·구간별 상위·10배 산술·구간 이동
      py scripts/tenbagger/bands.py --stale [N]  # 시총이 없거나 오래된 종목(Fiscal.ai 갱신 대상) 'id ticker market' 목록
      py scripts/tenbagger/bands.py --put <id|티커> <profile.json>   # (옛) easyconomics company_profile 응답 → fundamentals.json — 새 갱신은 scripts/fiscal/adapter.py --fund
      py scripts/tenbagger/bands.py --band <id|티커>             # 구간 이름(구간 내 순위·이동 기록용)
      py scripts/tenbagger/bands.py --cap <id|티커>              # 시가총액 '시총 $4.55B'(펄스 🚀 머리줄, 2026-10-30)
"""
import csv
import json
import re
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
FUND = ROOT / "knowledge" / "models" / "discovery" / "fundamentals.json"
HIST = ROOT / "knowledge" / "models" / "tenbagger" / "bands_history.csv"
OUTD = ROOT / "outputs" / "tenbagger" / "bands"
ECB = "https://www.ecb.europa.eu/stats/eurofxref/eurofxref-daily.xml"
EODHD = "https://eodhd.com/api/screener"
# 감시 목록 하위 섹터 → 구간 엔진 섹터
SUB_SECTOR = {"semicap": "semis", "accelerator": "semis", "memory": "semis", "foundry": "semis", "analog": "semis", "eda_ip": "semis",
              "semis": "semis", "materials": "semis", "software": "software", "hyperscaler": "software"}
THEME_SECTOR = {"targets_inp": "semis", "probe_test": "semis", "metrology_inspection": "semis", "munitions_energetics": "defense", "srm_missile": "defense",
                "gan_radar_ew": "defense", "cuas_unmanned": "defense", "naval_capacity": "defense", "space_isr": "defense",
                "nuclear_fuel": "nuclear", "nuclear_reactor": "nuclear", "satellite_launch": "space", "satellite_data": "space"}
SUFFIX_MARKET = {"US": "us", "KO": "kr", "KQ": "kr", "TSE": "jp", "T": "jp", "TW": "tw", "TWO": "tw",
                 "XETRA": "eu", "F": "eu", "DE": "eu", "PA": "eu", "MI": "eu", "MC": "eu", "AS": "eu", "SW": "eu", "CO": "eu", "HE": "eu", "ST": "eu",
                 "OL": "eu", "LSE": "eu", "L": "eu"}


def _y(p):
    f = ROOT / p
    return (yaml.safe_load(f.read_text(encoding="utf-8")) or {}) if f.exists() else {}


def cfg():
    return _y("config/tenbagger.yaml").get("bands") or {}


def load_fund():
    return json.loads(FUND.read_text(encoding="utf-8")) if FUND.exists() else {}


def save_fund(d):
    FUND.parent.mkdir(parents=True, exist_ok=True)
    FUND.write_text(json.dumps(d, ensure_ascii=False, indent=1, sort_keys=True), encoding="utf-8")


# ---------- 유니버스 ----------
def universe():
    """id → {id, name, code, market, sector, source}. 섹터는 방위 지도(본업·큰 비중) > 감시 목록 sub > 발굴 테마 순"""
    out = {}

    def add(cid, name, code, market, sector, src):
        r = out.setdefault(cid, {"id": cid, "name": name, "code": str(code or ""), "market": market, "sector": sector, "source": src})
        r["code"] = r["code"] or str(code or "")
        r["market"] = r["market"] or market
        return r

    for f in ("config/valuation.yaml", "config/earnings_watch.yaml"):
        d = _y(f)
        for u in (d.get("universe") or []) + (d.get("extra") or []):
            add(u["id"], u.get("name"), u.get("code"), market_of(u.get("code")), SUB_SECTOR.get(u.get("sub"), "ai_hw"), f)
    for t in _y("config/discovery.yaml").get("themes") or []:
        for c in t.get("candidates") or []:
            add(c["id"], c.get("name"), c.get("code"), c.get("market"), THEME_SECTOR.get(t["id"], "ai_hw"), "discovery")
    for c in _y("config/coverage.yaml").get("companies") or []:
        add(c["id"], c.get("name"), c.get("code"), c.get("market"), "ai_hw", "coverage")
    for sector, seeds in (_y("config/tenbagger_universe.yaml").get("seeds") or {}).items():   # 미국 중형 반도체·SW·AI 인프라 시드
        for s in seeds or []:
            if not any(r.get("code") == f"{s['ticker']}.US" for r in out.values()):
                add(f"us-{s['ticker'].lower()}", s["name"], f"{s['ticker']}.US", "us", sector, "seed")
    for c in _y("config/consumer.yaml").get("companies") or []:   # 소비재·게임·콘텐츠IP(Chiip Consumer, 2026-10-30) — 출구 배수는 sectors.consumer
        code = f"{c['code']}.US" if c.get("market") == "us" else c.get("code")
        add(c["id"], c.get("name"), code, c.get("market"), "consumer", "consumer")
    for c in _y("config/defense.yaml").get("companies") or []:
        if not c.get("listed"):
            continue
        r = add(c["id"], c.get("name"), c.get("code"), market_of(c.get("code")), "defense", "defense")
        if c.get("exposure") in ("core", "major") and r["sector"] != "software":
            r["sector"] = "defense"   # 방산이 본업이면 방위 잣대(출구 배수·참조 시장)로 본다
        r["defense"] = True
        if c.get("ec_ticker"):
            r["ec_ticker"] = c["ec_ticker"]   # 조회 인자가 거래소 코드와 다를 때(영국 BA.L 등) — Fiscal.ai 회사 키는 config/fiscal_keys.yaml
    return out


def market_of(code):
    m = re.search(r"\.([A-Z]+)$", str(code or ""))
    return SUFFIX_MARKET.get(m.group(1)) if m else None


def ticker_of(row):
    """조회 인자(ticker, market — Fiscal.ai 키 확인의 출발점) — RHM.XETRA → (RHM, eu), 7011.TSE → (7011, jp)"""
    code = str(row.get("code") or "")
    return row.get("ec_ticker") or re.sub(r"\.[A-Z]+$", "", code), row.get("market") or market_of(code) or "us"


# ---------- 환율·EODHD ----------
def ecb_rates(xml=None):
    """통화 → USD 환산 배수(1 통화 = x USD). ECB 기준환율(EUR 기준, 공식 일일 XML)에서 계산"""
    if xml is None:
        sys.path.insert(0, str(ROOT / "radar"))
        from pollers import common
        xml = common.http_get(ECB, timeout=20).decode("utf-8", "replace")
    eur = {m.group(1): float(m.group(2)) for m in re.finditer(r"currency='([A-Z]{3})' rate='([\d.]+)'", xml)}
    if "USD" not in eur:
        return {}
    usd_per_eur = eur["USD"]
    out = {"EUR": usd_per_eur, "USD": 1.0}
    for cur, rate in eur.items():
        out[cur] = usd_per_eur / rate
    return out


def to_usd(amount, currency, fx):
    if amount is None:
        return None
    cur = (currency or "USD").upper()
    rate = fx.get(cur) if fx else None
    if rate is None:
        rate = (cfg().get("fx_fallback") or {}).get(cur)
    return amount * rate if rate else None


def eodhd_rows(key, http_get, fx):
    """EODHD 스크리너(공식 문서 2026-10-29 확인: filters JSON 3원소 배열, limit ≤500, offset ≤999, 요청 1건 = API 5콜)"""
    c = cfg().get("eodhd") or {}
    out = []
    for ex in c.get("exchanges") or []:
        for flt in c.get("filters") or []:
            for ind in flt.get("industries") or []:
                for off in (0, 500):
                    q = {"api_token": key, "sort": "market_capitalization.desc", "limit": 500, "offset": off,
                         "filters": json.dumps([["exchange", "=", ex], ["sector", "=", flt["sector"]], ["industry", "=", ind]])}
                    try:
                        data = json.loads(http_get(EODHD, q, timeout=40)).get("data") or []
                    except Exception:
                        break
                    for r in data:
                        usd = to_usd(r.get("market_capitalization"), r.get("currency_symbol"), fx)
                        if usd and usd >= float(c.get("min_usd", 1e9)):
                            out.append({"code": f"{r['code']}.{r.get('exchange') or ex}", "name": r.get("name"), "mcap_usd": usd,
                                        "sector": "defense" if flt["sector"] == "Industrials" else ("software" if "Software" in ind else "semis")})
                    if len(data) < 500:
                        break
    return out


# ---------- 개요 응답 넣기(옛 easyconomics 형식 — Fiscal.ai는 scripts/fiscal/adapter.py) ----------
def ingest_profile(cid, prof, fx, today=None):
    """company_profile 응답(data) → fundamentals.json 한 행. 금액은 USD로(통화 = currency)"""
    p = prof.get("data", prof)
    cur = p.get("currency") or "USD"
    mcap = to_usd(p.get("market_cap"), cur, fx)
    rev = to_usd(p.get("revenue"), cur, fx)
    fcf = p.get("free_cash_flow")
    rec = {"as_of": (today or date.today()).isoformat(), "source": f"easyconomics company_profile ({p.get('profile_source', '')}) {p.get('ticker', '')}",
           "currency": cur, "mcap_usd": mcap, "rev_ttm_usd": rev, "rev_growth": p.get("revenue_growth"), "op_margin": p.get("operating_margin"),
           "ev_sales": p.get("ev_sales"), "pb": p.get("pb_ratio"), "n_analysts": p.get("analyst_total"),
           "fcf_yield": (fcf / p["market_cap"]) if fcf is not None and p.get("market_cap") else None,
           "sector_src": p.get("sector"), "industry": p.get("industry"),
           # 조용한 매집형 상승 재료(scripts/discovery/quiet.py, 마스터 지시 2026-10-29) — 추세·관심·실적 확인
           "price": p.get("price"), "ma50": p.get("fifty_day_avg"), "ma200": p.get("two_hundred_day_avg"),
           "high_52w": p.get("high_52w"), "low_52w": p.get("low_52w"), "inst_own": p.get("institution_ownership"),
           "short_pct": p.get("short_pct_float"), "eps_fwd": p.get("eps_forward"), "eps_ttm": p.get("eps_trailing"),
           "surprises": [h.get("eps_surprise_pct") for h in (p.get("earnings_history") or [])[:4]]}
    if mcap is None:
        rec["note"] = f"환율 없음({cur}) — USD 환산 불가"
    return rec


# ---------- 구간·점수·10배 산술 ----------
def band_of(mcap, bands):
    if mcap is None:
        return None
    for b in bands:
        if mcap >= b["min_usd"] and (b.get("max_usd") is None or mcap < b["max_usd"]):
            return b
    return None


def factor_values(f, edge=None):
    pb = f.get("pb")
    return {"fcf_yield": f.get("fcf_yield"), "book_to_market": (1 / pb) if pb and pb > 0 else None, "size": f.get("mcap_usd"),
            "quality": f.get("op_margin"), "growth_accel": f.get("rev_growth"), "bottleneck": edge}


def pctile(vals, v, direction="high"):
    """구간 안 백분위(0~1). 같은 값은 중간 순위"""
    below = sum(1 for x in vals if x < v)
    eq = sum(1 for x in vals if x == v)
    p = (below + 0.5 * eq) / len(vals)
    return p if direction == "high" else 1 - p


def score_band(rows, factors):
    """rows: [{id, fv: factor_values}] → id → (점수 0~10, 빠진 요인)"""
    out = {}
    pools = {k: [r["fv"][k] for r in rows if r["fv"].get(k) is not None] for k in factors}
    for r in rows:
        tot, wsum, missing = 0.0, 0.0, []
        for k, spec in factors.items():
            w = float(spec.get("weight", 0))
            v = r["fv"].get(k)
            if v is None or len(pools[k]) < 2:
                missing.append(k)
                p = 0.5   # 자료 없음 또는 비교 대상 1개뿐 → 중립
            else:
                p = pctile(pools[k], v, spec.get("direction", "high"))
            tot += w * p
            wsum += w
        out[r["id"]] = (round(10 * tot / wsum, 2) if wsum else None, missing)
    return out


def tenx(f, sector, horizons=(5, 10), max_cap=None):
    """10배 산술: 목표 시총 = 10 × 현재 / 필요 매출 = 목표 ÷ 출구 EV/매출(순현금 무시 근사) / 필요 매출 성장률 / 참조 시장 대비 점유 / 유니버스 최대 대비"""
    sc = (cfg().get("sectors") or {}).get(sector) or {}
    m = f.get("mcap_usd")
    if not m:
        return None
    target = 10 * m
    out = {"target_usd": target, "exit_ev_sales": sc.get("exit_ev_sales"), "price_cagr": {n: 10 ** (1 / n) - 1 for n in horizons}}
    if sc.get("exit_ev_sales"):
        need = target / sc["exit_ev_sales"]
        out["need_rev_usd"] = need
        rev = f.get("rev_ttm_usd")
        if rev and rev > 0:
            out["rev_multiple"] = need / rev
            out["rev_cagr"] = {n: (need / rev) ** (1 / n) - 1 for n in horizons}
        if sc.get("tam_usd"):
            out["tam_share"] = need / sc["tam_usd"]
    if max_cap:
        out["vs_max"] = target / max_cap
    share, vs = out.get("tam_share"), out.get("vs_max")
    v = {"share_hard": 0.3, "share_stretch": 0.1, "vs_max_hard": 2.0, "vs_max_stretch": 1.0, **(cfg().get("verdict") or {})}
    if (share is not None and share > v["share_hard"]) or (vs is not None and vs > v["vs_max_hard"]):
        out["verdict"] = "산술적으로 어려움"
    elif (share is not None and share > v["share_stretch"]) or (vs is not None and vs > v["vs_max_stretch"]):
        out["verdict"] = "도전적"
    else:
        out["verdict"] = "산술상 가능 영역"
    return out


def edges():
    return {c["id"]: c.get("edge") for t in _y("config/discovery.yaml").get("themes") or [] for c in t.get("candidates") or []}


def stale(n=None, today=None):
    """시총이 없거나 stale_days보다 오래된 상장 종목 — 방위·발굴·커버리지 먼저"""
    today = today or date.today()
    c, fund = cfg(), load_fund()
    lim = timedelta(days=int(c.get("stale_days", 7)))
    pri = {"coverage": 0, "discovery": 1, "defense": 2}
    rows = []
    for r in universe().values():
        if not r.get("code"):
            continue
        f = fund.get(r["id"]) or {}
        try:
            old = f.get("mcap_usd") is None or today - date.fromisoformat(f.get("as_of", "1900-01-01")) > lim
        except ValueError:
            old = True
        if old:
            rows.append((pri.get(r["source"], 3), f.get("as_of") or "", r))
    rows.sort(key=lambda x: (x[0], x[1]))
    return [r for _, _, r in rows][: n or int(c.get("refresh_per_run", 40))]


def run(today=None, fund=None, uni=None, write=True):
    today = today or date.today()
    c = cfg()
    bands = c.get("list") or []
    fund = load_fund() if fund is None else fund
    uni = universe() if uni is None else uni
    factors = _y("config/tenbagger.yaml").get("factors") or {}
    ed = edges()
    rows = []
    for cid, u in uni.items():
        f = fund.get(cid) or {}
        b = band_of(f.get("mcap_usd"), bands)
        rows.append({**u, "f": f, "band": b["id"] if b else None, "fv": factor_values(f, ed.get(cid))})
    max_cap = max((r["f"].get("mcap_usd") or 0 for r in rows), default=0) or None
    by_band = {b["id"]: [r for r in rows if r["band"] == b["id"]] for b in bands}
    scores = {}
    for bid, rs in by_band.items():
        scores.update(score_band(rs, factors))
    for r in rows:
        r["score"], r["missing"] = scores.get(r["id"], (None, []))
        r["tenx"] = tenx(r["f"], r["sector"], tuple(c.get("horizons_years") or (5, 10)), max_cap) if r["band"] else None
    migrations = band_moves(rows, today) if write else []
    top_n = int(c.get("per_band_top", 3))
    top = {bid: sorted(rs, key=lambda r: -(r["score"] or 0))[:top_n] for bid, rs in by_band.items()}
    path = write_report(today, bands, by_band, top, rows, migrations) if write else None
    return {"rows": rows, "top": top, "migrations": migrations, "path": path}


def band_moves(rows, today):
    """직전 기록 대비 구간이 바뀐 종목(위로 = 시총이 한 단계 커짐). 오늘 구간을 기록에 덧붙인다"""
    prev = {}
    if HIST.exists():
        with HIST.open(encoding="utf-8", newline="") as f:
            for h in csv.DictReader(f):
                if h["date"] < today.isoformat():
                    prev[h["id"]] = h["band"]
    order = {f"B{i}": i for i in range(12)}
    moves = []
    for r in rows:
        if r["band"] and prev.get(r["id"]) and prev[r["id"]] != r["band"]:
            moves.append((r, prev[r["id"]], "↑" if order.get(r["band"], 0) > order.get(prev[r["id"]], 0) else "↓"))
    HIST.parent.mkdir(parents=True, exist_ok=True)
    new = not HIST.exists()
    with HIST.open("a", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        if new:
            w.writerow(["date", "id", "band", "mcap_usd"])
        for r in rows:
            if r["band"]:
                w.writerow([today.isoformat(), r["id"], r["band"], round(r["f"]["mcap_usd"])])
    return moves


def _usd(x):
    if x is None:
        return "-"
    return f"${x / 1e12:.2f}T" if x >= 1e12 else f"${x / 1e9:.1f}B" if x >= 1e9 else f"${x / 1e6:.0f}M"


def write_report(today, bands, by_band, top, rows, migrations):
    OUTD.mkdir(parents=True, exist_ok=True)
    have = sum(1 for r in rows if r["band"])
    sec = {"semis": "반도체", "ai_hw": "AI HW", "software": "SW", "defense": "방위", "nuclear": "원자력", "space": "위성"}
    L = [f"# Chiip Ten-bagger 시가총액 구간 {today.isoformat()}", "",
         f"유니버스 {len(rows)} · 시총 확보 {have} · 갱신 대상(없음·{cfg().get('stale_days', 7)}일 초과) {len(stale(10 ** 6, today))}", "",
         "| 구간 | 종목 수 | 반도체 | AI HW | SW | 방위 | 10배 = 목표 시총 |", "|---|---|---|---|---|---|---|"]
    for b in bands:
        rs = by_band[b["id"]]
        cnt = {s: sum(1 for r in rs if r["sector"] == s) for s in sec}
        lo = _usd(10 * b["min_usd"])
        hi = _usd(10 * b["max_usd"]) if b.get("max_usd") else "그 이상"
        L.append(f"| {b['id']} {b['label']} | {len(rs)} | {cnt['semis']} | {cnt['ai_hw']} | {cnt['software']} | {cnt['defense']} | {lo}~{hi} |")
    L += ["", "## 구간별 상위(구간 안 백분위 점수)", ""]
    for b in bands:
        if not top[b["id"]]:
            continue
        L.append(f"### {b['id']} {b['label']}")
        L.append("| 종목 | 섹터 | 시총 | 점수 | 10배 목표 | 필요 매출(출구 EV/매출) | 필요 매출 성장 10년 | 참조 시장 점유 | 판정 | 빠진 자료 |")
        L.append("|" + "---|" * 10)
        for r in top[b["id"]]:
            t = r["tenx"] or {}
            rc = (t.get("rev_cagr") or {}).get(10)
            rc_s = "-" if rc is None else f"{rc:.0%}"
            sh_s = "-" if t.get("tam_share") is None else f"{t['tam_share']:.1%}"
            L.append(f"| {r['name']}({ticker_of(r)[0]}) | {sec.get(r['sector'], r['sector'])} | {_usd(r['f'].get('mcap_usd'))} | **{r['score']}** | "
                     f"{_usd(t.get('target_usd'))} | {_usd(t.get('need_rev_usd'))}({t.get('exit_ev_sales')}배) | "
                     f"{rc_s} | {sh_s} | {t.get('verdict', '-')} | {', '.join(r['missing']) or '-'} |")
        L.append("")
    if migrations:
        L += ["## 구간 이동(직전 기록 대비)", ""] + [f"- {d} {r['name']}: {p} → {r['band']} ({_usd(r['f'].get('mcap_usd'))})" for r, p, d in migrations] + [""]
    L += ["읽는 법: 점수는 같은 구간 안에서만 비교한 백분위(FCF 수익률·B/M·크기·이익률·성장·병목, 가중치 config/tenbagger.yaml factors). "
          "10배 산술은 출구 EV/매출 사전값(config/tenbagger.yaml bands.sectors, 미검증)으로 '10배가 되려면 매출이 얼마여야 하나'를 보는 점검이지 예측이 아니다. "
          "참조 시장 점유는 현재 시장 규모 대비(성장 미반영).", "", "연구 후보이지 매수 권유 아님."]
    path = OUTD / f"{today.strftime('%Y%m%d')}.md"
    path.write_text("\n".join(L), encoding="utf-8")
    return path


def resolve_id(arg, uni=None):
    """id 또는 티커(KTOS·7012·RHM·BA.L) → 유니버스 id. 같은 회사가 여러 목록에 있으면 먼저 등록된 id(감시 목록 우선).
    맨 티커가 여러 시장에 겹치면(BA = Boeing·BAE) 미국 상장을 먼저 — 다른 시장은 BA.L처럼 easyconomics 티커로"""
    uni = universe() if uni is None else uni
    if arg in uni:
        return arg
    a = arg.upper()
    exact = [cid for cid, r in uni.items() if str(r.get("ec_ticker") or "").upper() == a or str(r.get("code") or "").upper() == a]
    if exact:
        return exact[0]
    hits = [cid for cid, r in uni.items() if re.sub(r"\.[A-Z]+$", "", str(r.get("code") or "")).upper() == a]
    hits.sort(key=lambda cid: uni[cid].get("market") != "us")
    return hits[0] if hits else None


def band_label(cid):
    """펄스 🚀 머리줄용 — fundamentals.json 시총으로 구간 이름(없으면 None)"""
    b = band_of((load_fund().get(cid) or {}).get("mcap_usd"), cfg().get("list") or [])
    return b["label"] if b else None


def cap_text(usd):
    """$4.55B·$812M·$1.21T — 유효숫자 3자리(마스터 지시 2026-10-30 "범위 대신 시가총액을 명시하라")"""
    if not usd or usd <= 0:
        return None
    for unit, div in (("T", 1e12), ("B", 1e9), ("M", 1e6)):
        if usd >= div:
            v = usd / div
            return f"${v:.3g}{unit}" if v < 100 else f"${v:.0f}{unit}"
    return f"${usd:,.0f}"


def cap_label(cid):
    """펄스 🚀 머리줄용 — fundamentals.json 시총(달러 환산). 없으면 None"""
    return cap_text((load_fund().get(cid) or {}).get("mcap_usd"))


def main(argv):
    sys.stdout.reconfigure(encoding="utf-8")
    if argv and argv[0] == "--stale":
        for r in stale(int(argv[1]) if len(argv) > 1 else None):
            tk, mk = ticker_of(r)
            print(f"{r['id']} {tk} {mk}")
        return 0
    if argv and argv[0] == "--cap":    # 펄스 🚀 머리줄용: py scripts/tenbagger/bands.py --cap SEI → '시총 $4.55B'(없으면 '시총 미확인')
        cid = resolve_id(argv[1])
        cap = cap_label(cid) if cid else None
        print(f"시총 {cap}" if cap else "시총 미확인")
        return 0
    if argv and argv[0] == "--band":   # 구간 이름: py scripts/tenbagger/bands.py --band KTOS → '$1–10B'(시총 없으면 '구간 미확인')
        cid = resolve_id(argv[1])
        print((band_label(cid) if cid else None) or "구간 미확인")
        return 0
    if argv and argv[0] == "--put":
        cid = resolve_id(argv[1])
        if not cid:
            print(f"유니버스에 없음: {argv[1]} — config/tenbagger_universe.yaml seeds에 먼저 추가")
            return 1
        prof = json.loads(Path(argv[2]).read_text(encoding="utf-8"))
        fund = load_fund()
        fund[cid] = ingest_profile(cid, prof, ecb_rates())
        save_fund(fund)
        print(f"{cid} 시총 {_usd(fund[cid].get('mcap_usd'))} 저장")
        return 0
    sys.path.insert(0, str(ROOT / "radar"))
    from pollers import common
    key = common.load_env().get("EODHD_API_KEY")
    uni = universe()
    if key:   # EODHD 자동 유니버스 — 시드에 없는 시총 $1B 이상 종목을 더한다(시총도 함께)
        fx = ecb_rates()
        fund = load_fund()
        for r in eodhd_rows(key, common.http_get, fx):
            cid = "eod-" + re.sub(r"[^a-z0-9]+", "-", r["code"].lower()).strip("-")
            if not any(u.get("code") == r["code"] for u in uni.values()):
                uni[cid] = {"id": cid, "name": r["name"], "code": r["code"], "market": market_of(r["code"]), "sector": r["sector"], "source": "eodhd"}
                fund.setdefault(cid, {})
                fund[cid].update({"as_of": date.today().isoformat(), "mcap_usd": r["mcap_usd"], "source": "EODHD screener"})
        save_fund(fund)
    res = run(uni=uni)
    tops = [f"{b}: " + ", ".join(f"{r['name']} {r['score']}" for r in rs) for b, rs in res["top"].items() if rs]
    print(f"[구간] {res['path'].relative_to(ROOT).as_posix()} · " + " | ".join(tops[:6]))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
