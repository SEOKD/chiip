"""시장 세부 산업 분류표 자동 갱신 (마스터 지시 2026-11-08 "32개 기준으로 고정하지 말고 세부 산업이 지속 업데이트해라. 분류가 애매한 것들은 시장이 일반적으로
많이 분류하는 곳에 넣어 함께 분석하도록 해라. 산업 리포트에서 다루는 섹터는 한 국가를 특정하지 말아라. 트레이딩뷰와도 연동해 … 와치리스트 섹션에 넣고 추가하거나 업데이트하라")

분류표 config/industry_taxonomy.yaml의 members를 유니버스(감시 목록·알파 유니버스·실적 감시)와 맞춘다. 산업 묶음 수는 고정이 아니다 — weekly_pick.groups()가 매번 다시 센다.
  ① 미분류 종목 → Fiscal.ai companies_list(GICS 세부 산업)·TradingView(sector·industry) 결과를 --put-fiscal / --put-tv로 넣는다(결정론 스크립트는 MCP를 못 부른다 — 모델이 받아 파일로).
  ② 원천이 엇갈리면 '시장이 가장 많이 쓰는 분류' 순서로 고른다: GICS(Fiscal — S&P·MSCI 지수와 대부분 ETF가 쓰는 표준) > TradingView 업종(tv_map으로 GICS 변환) > Chiip 배정.
     다른 원천 값은 alt로 남긴다(conflicts 장부).
  ③ 나라: 산업 묶음은 나라를 가르지 않는다(같은 세부 산업이면 미국·한국·일본·대만·유럽을 한 묶음). countries()가 묶음별 나라 분포를 낸다.
사용:
  py scripts/industry/taxonomy_refresh.py --plan              # 미분류 종목 + Fiscal 조회 본문 + TradingView 심볼
  py scripts/industry/taxonomy_refresh.py --put-fiscal <json> # [{ticker, countryCode, sector, industryGroup, industry, subIndustry}]
  py scripts/industry/taxonomy_refresh.py --put-tv <json>     # [{ticker, sector, industry}]
  py scripts/industry/taxonomy_refresh.py --learn-tv          # knowledge/models/industries/tv_industry.json으로 TV 업종 → GICS 변환표 학습 + 미분류 배치
  py scripts/industry/taxonomy_refresh.py --status            # 묶음 수·나라 분포·미분류
"""
import argparse
import csv
import json
import sys
from datetime import date
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))
import weekly_pick as W  # noqa: E402

TAX = W.TAX
CONFLICTS = ROOT / "knowledge" / "models" / "industries" / "taxonomy_conflicts.csv"
SUFFIX_COUNTRY = {"KO": "KR", "KQ": "KR", "T": "JP", "TSE": "JP", "TW": "TW", "TWO": "TW", "HK": "HK", "SW": "CH", "AS": "NL", "XETRA": "DE", "PA": "FR", "MI": "IT",
                  "ST": "SE", "HE": "FI", "CO": "DK", "LSE": "GB", "L": "GB", "US": "US"}
PRIORITY = {"fiscal": 3, "tv": 2, "assigned": 1}


def country(m):
    """종목 나라 — 유니버스 region이 있으면 그것, 없으면 티커 접미사, 그래도 모르면 '?'(4자리 숫자는 일본·대만이 겹쳐 추측하지 않는다)"""
    if isinstance(m, dict):
        if m.get("region"):
            return {"UK": "GB", "EU": "EU"}.get(m["region"], m["region"])
        m = m.get("ticker")
    t = str(m or "")
    if "." in t:
        return SUFFIX_COUNTRY.get(t.rsplit(".", 1)[1].upper(), "?")
    if t.isdigit():
        return "KR" if len(t) == 6 else "?"
    return "US" if t else "?"


def load():
    return yaml.safe_load(TAX.read_text(encoding="utf-8"))


def save(tax):
    head = "".join(l for l in TAX.read_text(encoding="utf-8").splitlines(keepends=True) if l.startswith("#"))   # 맨 위 설명 주석은 그대로
    body = yaml.safe_dump(tax, allow_unicode=True, sort_keys=False, width=200)
    TAX.write_text(head + body, encoding="utf-8")


def where(tax, base):
    """종목(접미사 뗀 티커)이 지금 어디에 있나 → (세부 산업, 원천)"""
    for sub, src in (tax.get("members") or {}).items():
        for kind, ts in src.items():
            if base in [str(x).split(".")[0].upper() for x in ts or []]:
                return sub, kind
    return None, None


def unclassified():
    cls = W.classify()
    return [m for m in W.universe() if m["id"] not in cls and m.get("ticker")]


def put(rows, kind, today=None):
    """원천 결과를 분류표에 넣는다. 이미 있는 종목은 원천 우선순위가 높을 때만 옮기고, 다르면 conflicts에 남긴다"""
    tax = load()
    tvmap = tax.get("tv_map") or {}
    meta = tax.setdefault("sub", {})
    uni = {str(m["ticker"]).split(".")[0].upper(): m for m in W.universe() if m.get("ticker")}
    moved, added, conflicts, skipped = 0, 0, [], []
    for r in rows:
        base = str(r["ticker"]).split(".")[0].upper()
        m = uni.get(base)
        if not m:
            skipped.append(base)
            continue
        if kind == "fiscal":
            if r.get("countryCode") and country(m) not in ("?", "EU", r["countryCode"]):   # 동명 티커(다른 거래소) 거름
                skipped.append(base)
                continue
            sub = r["subIndustry"]
            if sub not in meta:
                meta[sub] = [sub, r["industry"], r["industryGroup"], r["sector"]]   # 한국어 이름은 모델이 나중에 고친다(영문 그대로도 동작)
        else:
            sub = tvmap.get(r.get("industry"))
            if not sub:
                skipped.append(f"{base}(TV 업종 '{r.get('industry')}' 변환표 없음)")
                continue
        cur, ck = where(tax, base)
        if cur == sub:
            continue
        if cur and PRIORITY[ck] >= PRIORITY[kind]:
            conflicts.append({"date": (today or date.today()).isoformat(), "ticker": base, "kept": cur, "kept_src": ck, "alt": sub, "alt_src": kind})
            continue
        if cur:   # 낮은 원천 분류를 높은 원천으로 바꾼다
            tax["members"][cur][ck] = [x for x in tax["members"][cur][ck] if str(x).split(".")[0].upper() != base]
            conflicts.append({"date": (today or date.today()).isoformat(), "ticker": base, "kept": sub, "kept_src": kind, "alt": cur, "alt_src": ck})
            moved += 1
        else:
            added += 1
        tax.setdefault("members", {}).setdefault(sub, {}).setdefault(kind if kind != "tv" else "tv", []).append(base)
    save(tax)
    if conflicts:
        new = not CONFLICTS.exists()
        CONFLICTS.parent.mkdir(parents=True, exist_ok=True)
        with CONFLICTS.open("a", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, ["date", "ticker", "kept", "kept_src", "alt", "alt_src"])
            if new:
                w.writeheader()
            w.writerows(conflicts)
    return {"added": added, "moved": moved, "conflicts": len(conflicts), "skipped": skipped}


def countries(c=None):
    """묶음별 나라 분포 — 산업은 나라를 가르지 않는다(한 나라 묶음이면 경고)"""
    c = c or W.cfg()
    return {k: sorted({country(m) for m in ms} - {"?"}) for k, ms in c["_members"].items()}


TV_IND = ROOT / "knowledge" / "models" / "industries" / "tv_industry.json"


def learn_tv(min_votes=2, min_lead=2):
    """TradingView 업종 → GICS 세부 산업 변환표를 데이터로 배운다 — 이미 GICS(Fiscal)로 분류된 종목들이 그 TV 업종에서 가장 많이 속한 세부 산업
    (= '시장이 일반적으로 많이 분류하는 곳', 최다 득표). 1·2위 표 차이가 min_lead 미만이면 갈린 것으로 보고 변환하지 않는다. 그 표로 미분류 종목을 넣는다"""
    from collections import Counter
    tvi = json.loads(TV_IND.read_text(encoding="utf-8"))["industry"]
    sym = {r["entity_id"]: r["tv_symbol"] for r in csv.DictReader((ROOT / "config" / "tradingview_symbols.csv").open(encoding="utf-8")) if r.get("tv_symbol")}
    cls = W.classify()
    votes = {}
    for eid, m in cls.items():
        ind = tvi.get(sym.get(eid))
        if ind and m["source"] == "fiscal":
            votes.setdefault(ind, Counter())[m["sub"]] += 1
    tvmap, split = {}, {}
    for ind, c in votes.items():
        top = c.most_common(2)
        sub, n = top[0]
        second = top[1][1] if len(top) > 1 else 0
        if n >= min_votes and n - second >= min_lead:
            tvmap[ind] = sub
        else:
            split[ind] = dict(c)
    tax = load()
    tax["tv_map"] = dict(sorted(tvmap.items()))
    save(tax)
    def guess(m):   # 심볼표에 없으면 거래소를 추정(한국 6자리 → KRX, 그 밖 → NASDAQ·NYSE)
        b = str(m["ticker"]).split(".")[0]
        cands = [sym.get(m["id"])] + ([f"KRX:{b}"] if b.isdigit() and len(b) == 6 else [f"NASDAQ:{b}", f"NYSE:{b}"])
        return next((tvi[x] for x in cands if x and x in tvi), None)
    rows = [{"ticker": str(m["ticker"]), "industry": guess(m)} for m in unclassified()]
    res = put([r for r in rows if r["industry"]], "tv")
    return {"tv_map": len(tvmap), "split": split, **res}


def fiscal_body(tickers):
    return ("async () => { const want = new Set(" + json.dumps(sorted(tickers)) + "); const out = [];"
            " for (let p = 1; p <= 40; p++) { const r = await codemode.companies_list({ pageNumber: p, pageSize: 1000 });"
            " for (const c of r.data) { const t = String(c.ticker || '').toUpperCase(); if (c.tradingStatus === 'Active' && want.has(t))"
            " out.push({ticker: t, countryCode: c.countryCode, sector: c.sector, industryGroup: c.industryGroup, industry: c.industry, subIndustry: c.subIndustry}); }"
            " if (!r.pagination.hasNextPage) break; } console.log(JSON.stringify(out)); }")


def main(argv):
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("--plan", action="store_true")
    ap.add_argument("--put-fiscal")
    ap.add_argument("--put-tv")
    ap.add_argument("--status", action="store_true")
    ap.add_argument("--learn-tv", action="store_true")
    a = ap.parse_args(argv)
    if a.plan:
        un = unclassified()
        tv = {r["entity_id"]: r["tv_symbol"] for r in csv.DictReader((ROOT / "config" / "tradingview_symbols.csv").open(encoding="utf-8")) if r.get("tv_symbol")}
        print(json.dumps({"unclassified": [[m["id"], m["ticker"]] for m in un], "fiscal_code": fiscal_body({str(m["ticker"]).split(".")[0].upper() for m in un}),
                          "tv_symbols": [tv[m["id"]] for m in un if m["id"] in tv]}, ensure_ascii=False))
    elif a.learn_tv:
        print(json.dumps(learn_tv(), ensure_ascii=False))
    elif a.put_fiscal or a.put_tv:
        f = a.put_fiscal or a.put_tv
        print(json.dumps(put(json.loads(Path(f).read_text(encoding="utf-8")), "fiscal" if a.put_fiscal else "tv"), ensure_ascii=False))
    else:
        c = W.cfg()
        cs = countries(c)
        print(f"[분류표] 산업 묶음 {len(c['industries'])}개 · 분류 종목 {len(W.classify())}/{len(W.universe())} · 미분류 {len(unclassified())}")
        for k, v in cs.items():
            print(f"  {c['industries'][k]['name']}: {len(c['_members'][k])}종목 · {'/'.join(v)}" + ("  ⚠ 한 나라" if len(v) < 2 else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
