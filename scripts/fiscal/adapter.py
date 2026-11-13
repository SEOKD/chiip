"""Fiscal.ai 본보기 출력 → 엔진 파일 (마스터 지시 2026-10-30 "easyconomics를 쓰지 말고 Fiscal.ai만 MCP로", knowledge/methods/data_fiscal.md)

모델이 scripts/fiscal/templates/*.js를 execute_code로 돌려 받은 출력을 파일로 저장하면, 이 스크립트가 결정론으로 엔진 파일에 넣는다.
  --fund <id> <출력 json>   fundamentals.js → knowledge/models/discovery/fundamentals.json 한 행(bands.ingest_profile과 같은 스키마 + 추세 재료)
  --ohlcv <id> <출력 txt>   prices.js → knowledge/models/companies/<id>/ohlcv.csv(일봉 260) + ohlcv_m.csv(월봉 120)
                            Fiscal.ai 일봉에는 고가·저가가 없어 max/min(시가·종가) 근사 — 파일 첫 줄 주석에 남기고 levels·flow가 '근사'로 표기한다
  --ohlcv-tv <id> <TradingView json> [심볼]   mcp-tv-get-ohlcv(1D, format=columns 또는 rows) 응답 → ohlcv.csv 일봉을 실제 고가·저가로 바꾼다(마스터 지시 2026-11-08
                            "일봉 그래프 데이터를 제대로 못 가져온다" — Fiscal.ai 근사 봉은 리포트 일봉에 쓰지 않는다). 월봉(ohlcv_m.csv)은 그대로
  --key <id> <companyKey> [terminalUrl]   config/fiscal_keys.yaml 캐시(감시 목록 id → Fiscal.ai 회사 키)
사용 예: py scripts/fiscal/adapter.py --fund co-quanta-services out.json
"""
import json
import sys
from datetime import date
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
FUND = ROOT / "knowledge" / "models" / "discovery" / "fundamentals.json"
KEYS = ROOT / "config" / "fiscal_keys.yaml"
APPROX = "# source: Fiscal.ai company_stock_prices — 고가·저가 없음, max/min(시가·종가) 근사"


def fund_row(out, today=None):
    """fundamentals.js 출력 → fundamentals.json 행. 통화가 USD가 아니면 mcap_usd는 비운다(환산은 bands --put이 ECB 환율로)"""
    usd = (out.get("currency") or "USD") == "USD"
    return {"as_of": out.get("as_of") or (today or date.today()).isoformat(), "source": f"Fiscal.ai {out.get('key', '')}",
            "currency": out.get("currency") or "USD", "mcap_usd": out.get("mcap") if usd else None, "mcap_local": out.get("mcap"),
            "rev_ttm_usd": out.get("rev_ttm") if usd else None, "rev_growth": out.get("rev_growth"), "op_margin": out.get("op_margin"),
            "ev_sales": out.get("ev_sales"), "pb": out.get("pb"), "n_analysts": out.get("n_analysts"), "fcf_yield": out.get("fcf_yield"),
            "sector_src": out.get("sector"), "industry": out.get("industry"), "price": out.get("price"), "ma50": out.get("ma50"), "ma200": out.get("ma200"),
            "high_52w": out.get("high_52w"), "low_52w": out.get("low_52w"), "inst_own": out.get("inst_own"), "short_pct": out.get("short_pct"),
            "eps_fwd": out.get("eps_fwd"), "eps_ttm": out.get("eps_ttm"), "surprises": out.get("surprises") or [],
            "target_mean": out.get("target_mean"), "terminal_url": out.get("terminalUrl"),
            "note": "애널리스트 수·목표가·서프라이즈 기준 추정은 Zacks — 표시할 때 'Data provided by Zacks Investment Research' 표기"}


def put_fund(cid, out):
    d = json.loads(FUND.read_text(encoding="utf-8")) if FUND.exists() else {}
    d[cid] = fund_row(out)
    FUND.parent.mkdir(parents=True, exist_ok=True)
    FUND.write_text(json.dumps(d, ensure_ascii=False, indent=1, sort_keys=True), encoding="utf-8")
    return d[cid]


def split_prices(text):
    """prices.js 출력 → (일봉 줄, 월봉 줄) — 각각 머리행 포함"""
    blocks, cur = {}, None
    for line in (text or "").splitlines():
        line = line.strip()
        if line in ("#daily", "#monthly"):
            cur = line[1:]
            blocks[cur] = []
        elif line and cur:
            blocks[cur].append(line)
    return blocks.get("daily", []), blocks.get("monthly", [])


def put_ohlcv(cid, text):
    daily, monthly = split_prices(text)
    if len(daily) < 2:
        raise SystemExit("일봉 없음 — prices.js 출력을 확인")
    d = ROOT / "knowledge" / "models" / "companies" / cid
    d.mkdir(parents=True, exist_ok=True)
    (d / "ohlcv.csv").write_text(APPROX + "\n" + "\n".join(daily) + "\n", encoding="utf-8")
    if len(monthly) > 1:
        (d / "ohlcv_m.csv").write_text(APPROX + "\n" + "\n".join(monthly) + "\n", encoding="utf-8")
    return len(daily) - 1, max(0, len(monthly) - 1)


def put_ohlcv_tv(cid, resp, symbol=None):
    """TradingView 일봉(정규장·분할 보정) → ohlcv.csv. t는 UTC 초 — 미국·아시아 정규장 봉은 UTC 날짜가 거래일과 같다"""
    from datetime import datetime, timezone
    b = resp.get("bars", resp)
    rows = [dict(zip("tohlcv", x)) for x in zip(*(b[k] for k in "tohlcv"))] if isinstance(b, dict) else list(b)
    rows = [r for r in rows if None not in (r.get(k) for k in "ohlc") and r["h"] >= max(r["o"], r["c"]) - 1e-9 and r["l"] <= min(r["o"], r["c"]) + 1e-9]
    if len(rows) < 60:
        raise SystemExit(f"TradingView 일봉 {len(rows)}개 — 60개 이상 필요")
    sym = symbol or resp.get("symbol") or ""
    head = f"# source: TradingView {sym} 1D(정규장, 실제 고가·저가, 분할 보정) 조회 {datetime.now().strftime('%Y-%m-%d %H:%M')} KST"
    out = [head, "date,o,h,l,c,v"] + [f"{datetime.fromtimestamp(r['t'], timezone.utc):%Y-%m-%d},{r['o']},{r['h']},{r['l']},{r['c']},{int(r.get('v') or 0)}" for r in sorted(rows, key=lambda r: r["t"])]
    d = ROOT / "knowledge" / "models" / "companies" / cid
    d.mkdir(parents=True, exist_ok=True)
    (d / "ohlcv.csv").write_text("\n".join(out) + "\n", encoding="utf-8")
    return len(rows)


def put_eps_history(cid, out):
    """eps_history.js 출력 → datapack consensus.eps_history (그림 5·8 재료, 2026-10-30)"""
    p = ROOT / "knowledge" / "models" / "companies" / cid / "datapack.json"
    dp = json.loads(p.read_text(encoding="utf-8"))
    dp.setdefault("consensus", {})["eps_history"] = {"basis": out.get("basis"), "updated_at": out.get("updatedAt"), "source": out.get("source"), "rows": out.get("rows") or []}
    if out.get("breadth_rows") is not None:   # 추정치 수정 폭 재료(2026-11-14, scripts/tenbagger/breadth.py)
        dp["consensus"]["revision_breadth"] = {"as_of": out.get("asOf"), "source": out.get("source"), "rows": out["breadth_rows"]}
    p.write_text(json.dumps(dp, ensure_ascii=False, indent=1), encoding="utf-8")
    return len(out.get("rows") or [])


def later_multiples(row, ntm, horizons):
    """Fwd 2Y·3Y 배수 = Fwd 1Y 배수 × 다음 4개 분기 이익 ÷ 그 해 이익 — 같은 가격·EV로 분모만 바꾼다. 이익이 0 이하면 비움"""
    out = {}
    for h in (2, 3):
        later = (horizons or {}).get(str(h)) or {}
        for key, field in (("pe_fwd", "eps"), ("ev_ebitda_fwd", "ebitda")):
            mult, base, x = row.get(key), (ntm or {}).get(field), later.get(field)
            out[f"{key}{h}"] = round(mult * base / x, 2) if mult and base and base > 0 and x and x > 0 else None
    return out


def put_forward(cid, out):
    """forward_multiples.js 출력 → datapack multiples_now·forward·peers·history (Fwd 1Y·2Y·3Y 멀티플, 2026-10-30 마스터 지시). 반환: (대상 배수, 채운 동종 수, 과거 점 수)"""
    p = ROOT / "knowledge" / "models" / "companies" / cid / "datapack.json"
    dp = json.loads(p.read_text(encoding="utf-8"))
    t = out.get("target") or {}
    now = dp.setdefault("multiples_now", {})
    for k in ("pe_fwd", "ev_ebitda_fwd"):
        now[k] = t.get(k)
    now.update(later_multiples(t, out.get("ntm"), out.get("horizons")))
    dp["forward"] = {"as_of": out.get("as_of"), "ntm": out.get("ntm") or {}, "horizons": out.get("horizons") or {}, "guided": out.get("guided") or {}, "src": t.get("src") or {}, "source": out.get("source")}
    by_ticker = {k.split("_", 1)[-1]: v for k, v in (out.get("peers") or {}).items()}
    n = 0
    for row in dp.get("peers") or []:
        v = by_ticker.get(row.get("ticker"))
        if v:
            row.update({"pe_fwd": v.get("pe_fwd"), "ev_ebitda_fwd": v.get("ev_ebitda_fwd")})
            if v.get("hist_q"):   # 최근 4개 분기말 배수 — 멀티플 프리미엄 추이(2026-11-06)
                row["hist_q"] = v["hist_q"]
            row.update(later_multiples(v, v.get("ntm"), v.get("horizons")))
            q = v.get("ntm") or {}
            if q.get("revenue") and q.get("ebit") is not None:
                row["ntm_ebit_margin"] = round(q["ebit"] / q["revenue"], 4)
                if q.get("rev_ttm"):
                    row["ntm_growth"] = round(q["revenue"] / q["rev_ttm"] - 1, 4)
            n += 1
    hist = dp.setdefault("history", {})
    for k in ("pe_fwd", "ev_ebitda_fwd"):
        hist[k] = [{"date": r["date"], "value": r[k]} for r in out.get("history") or [] if r.get(k)]
    p.write_text(json.dumps(dp, ensure_ascii=False, indent=1), encoding="utf-8")
    return {k: now.get(k) for k in ("pe_fwd", "pe_fwd2", "pe_fwd3", "ev_ebitda_fwd", "ev_ebitda_fwd2", "ev_ebitda_fwd3")}, n, len(out.get("history") or [])


def put_key(cid, key, url=None):
    d = (yaml.safe_load(KEYS.read_text(encoding="utf-8")) if KEYS.exists() else None) or {}
    head = "".join(l + "\n" for l in KEYS.read_text(encoding="utf-8").splitlines() if l.startswith("#")) if KEYS.exists() else ""
    keys = d.get("keys") or {}
    keys[cid] = {"key": key, **({"terminal_url": url} if url else {}), "checked": date.today().isoformat()}
    KEYS.write_text(head + yaml.safe_dump({"keys": keys}, allow_unicode=True, sort_keys=True), encoding="utf-8")


def key_of(cid):
    """config/fiscal_keys.yaml 캐시 — 없으면 None(모델이 company_profile로 확인해 --key로 넣는다)"""
    d = (yaml.safe_load(KEYS.read_text(encoding="utf-8")) if KEYS.exists() else None) or {}
    return ((d.get("keys") or {}).get(cid) or {}).get("key")


def main(argv):
    sys.stdout.reconfigure(encoding="utf-8")
    if len(argv) >= 3 and argv[0] == "--fund":
        r = put_fund(argv[1], json.loads(Path(argv[2]).read_text(encoding="utf-8")))
        print(f"[Fiscal.ai→펀더멘털] {argv[1]} 시총 {r['mcap_usd']} · 가격 {r['price']} · 200일선 {r['ma200']}")
        return 0
    if len(argv) >= 3 and argv[0] == "--ohlcv":
        n, m = put_ohlcv(argv[1], Path(argv[2]).read_text(encoding="utf-8"))
        print(f"[Fiscal.ai→일봉] {argv[1]} 일봉 {n} · 월봉 {m}(고저 근사)")
        return 0
    if len(argv) >= 3 and argv[0] == "--ohlcv-tv":
        n = put_ohlcv_tv(argv[1], json.loads(Path(argv[2]).read_text(encoding="utf-8")), argv[3] if len(argv) > 3 else None)
        print(f"[TradingView→일봉] {argv[1]} 일봉 {n}(실제 고가·저가)")
        return 0
    if len(argv) >= 3 and argv[0] == "--eps-history":
        n = put_eps_history(argv[1], json.loads(Path(argv[2]).read_text(encoding="utf-8")))
        print(f"[Fiscal.ai→EPS 이력] {argv[1]} {n}행 → datapack consensus.eps_history")
        return 0
    if len(argv) >= 3 and argv[0] == "--forward-multiples":
        now, n, h = put_forward(argv[1], json.loads(Path(argv[2]).read_text(encoding="utf-8")))
        print(f"[Fiscal.ai→Fwd 1Y·2Y·3Y 멀티플] {argv[1]} {now} · 동종 {n}곳 · 과거 {h}개월")
        return 0
    if len(argv) >= 3 and argv[0] == "--key":
        put_key(argv[1], argv[2], argv[3] if len(argv) > 3 else None)
        print(f"[Fiscal.ai 키] {argv[1]} → {argv[2]}")
        return 0
    print(__doc__)
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
