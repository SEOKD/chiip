"""발굴 후보 펀더멘털 일괄 채우기 (2026-11-14 Ten-bagger 점검, ADR-037)

왜: 발굴 선별(screen.py)의 '② 선별 통과'는 펀더멘털(knowledge/models/discovery/fundamentals.json)이 있어야 한다. 11/11 기준 후보 567개 중 73개(13%)만
    있었다 — fundamentals.js가 한 번에 한 종목이라 일요일 회차가 40개씩밖에 못 채웠다. 대부분 후보가 점수와 무관하게 '① 아이디어'에 묶였다.
무엇: 우선순위 높은 후보부터 Fiscal.ai 키를 찾아, fundamentals.js와 같은 계산을 여러 종목에 한 번에 돌리는 execute_code 본문을 만든다.
  우선순위: ① 섹터 판단 카드·edge 6 이상 ② 알파 5.0 이상 ③ 섹터 순환 후보 ④ 나머지 발굴 후보 — 펀더멘털이 없거나 stale_days보다 오래된 것만
  키: config/fiscal_keys.yaml → TradingView 기호('NASDAQ:XYZ' → 'NASDAQ_XYZ', config/tradingview_symbols.csv·Portfolio 섹터 묶음·순환 후보). 모르면 빼고 목록에 남긴다.
사용: py scripts/discovery/fund_fill.py --code [N]      # execute_code 본문(기본 12종목 — 샌드박스 60초·동시 6호출) — 출력 → 파일, 여러 번 돌려 채운다
      py scripts/discovery/fund_fill.py --put <파일>      # {id: fundamentals.js 출력} → fundamentals.json(adapter.put_fund)
      py scripts/discovery/fund_fill.py --status          # 채움 비율
"""
import csv
import json
import re
import sys
from datetime import date, timedelta
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
DISC = ROOT / "knowledge" / "models" / "discovery"
FUND = DISC / "fundamentals.json"
TPL = ROOT / "scripts" / "fiscal" / "templates" / "fundamentals.js"
STALE_DAYS = 14
RETRY_DAYS = 7    # 실패(시총 없음·오류)한 종목은 1주 뒤에 다시 시도 — 같은 종목이 매 회차 자리를 먹지 않게
TRIED = ROOT / "radar" / "state" / "fund_fill.json"
sys.path.insert(0, str(ROOT / "scripts" / "discovery"))
sys.path.insert(0, str(ROOT / "scripts" / "fiscal"))


def _j(p, default=None):
    try:
        return json.loads(Path(p).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {} if default is None else default


def _y(p):
    try:
        return yaml.safe_load((ROOT / p).read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError):
        return {}


def candidates():
    """[{id, name, code, market, edge}] — 발굴 지도 + 섹터 순환 후보"""
    out = {}
    for t in _y("config/discovery.yaml").get("themes") or []:
        for c in t.get("candidates") or []:
            out.setdefault(c["id"], {"id": c["id"], "name": c.get("name"), "code": str(c.get("code") or ""), "market": c.get("market"), "edge": c.get("edge")})
    for v in (_j(DISC / "rotation_candidates.json").get("sectors") or {}).values():
        for r in v.get("rows") or []:
            cid = "us-" + re.sub(r"[^a-z0-9]", "", str(r.get("ticker", "")).lower())
            out.setdefault(cid, {"id": cid, "name": r.get("name"), "code": r.get("ticker"), "market": "us", "edge": None, "symbol": r.get("symbol"), "rotation": True})
    return list(out.values())


def key_map():
    """{티커: 'EXCH_TKR'} — TradingView 기호에서"""
    tv = {}
    f = ROOT / "config" / "tradingview_symbols.csv"
    if f.exists():
        with f.open(encoding="utf-8", newline="") as fh:
            for r in csv.DictReader(fh):
                if r.get("tv_symbol") and r.get("ticker") and r.get("exchange") in ("NASDAQ", "NYSE", "AMEX"):
                    tv[r["ticker"].upper()] = r["tv_symbol"].replace(":", "_")
    for g in (_y("config/sector_select.yaml").get("groups") or {}).values():
        for s in (g.get("members") or []):
            tv.setdefault(s.split(":")[-1].upper(), s.replace(":", "_"))
    for g in (_y("config/market_watch.yaml").get("sectors") or {}).values():
        for k in g.get("keys") or []:
            tv.setdefault(k.split("_", 1)[-1].upper(), k)
    for v in (_j(DISC / "rotation_candidates.json").get("sectors") or {}).values():
        for r in v.get("rows") or []:
            if r.get("symbol") and r.get("ticker"):
                tv.setdefault(r["ticker"].upper(), r["symbol"].replace(":", "_"))
    return tv


def fiscal_key(c, fk, tv):
    k = (fk.get(c["id"]) or {}).get("key")
    if k:
        return k
    if c.get("symbol"):
        return c["symbol"].replace(":", "_")
    code = str(c.get("code") or "").upper()
    if c.get("market") in ("us", None) and re.fullmatch(r"[A-Z][A-Z.\-]{0,5}", code):
        return tv.get(code)
    return None


def priority(c, alpha, cards):
    """작을수록 먼저"""
    e = cards.get(c["id"], c.get("edge"))
    a = (alpha.get(c["id"]) or {}).get("total")
    if e is not None and e >= 6:
        return (0, -(a or 0))
    if a is not None and a >= 5:
        return (1, -a)
    if c.get("rotation"):
        return (2, 0)
    return (3, -(a or 0))


def todo(n=12, today=None):
    """(채울 [(id, 키)], 키 없음 [id])"""
    today = today or date.today()
    fund = _j(FUND)
    fk = _y("config/fiscal_keys.yaml").get("keys") or {}
    tv = key_map()
    alpha = _j(ROOT / "knowledge" / "models" / "alpha" / "latest.json").get("rows") or {}
    try:
        import sector_rotation
        cards = sector_rotation.cards()
    except Exception:  # noqa: BLE001
        cards = {}
    tried = _j(TRIED)
    rows, nokey = [], []
    for c in sorted(candidates(), key=lambda c: priority(c, alpha, cards)):
        f = fund.get(c["id"]) or {}
        try:
            have = f.get("mcap_usd") is not None or f.get("mcap_local") is not None   # 외화 상장은 원화폐 시총만 있어도 받은 것
            fresh = have and today - date.fromisoformat(str(f.get("as_of"))[:10]) <= timedelta(days=STALE_DAYS)
        except ValueError:
            fresh = False
        if fresh:
            continue
        t = tried.get(c["id"])
        if t and today - date.fromisoformat(t) <= timedelta(days=RETRY_DAYS):
            continue
        k = fiscal_key(c, fk, tv)
        if k:
            rows.append((c["id"], k))
        elif c.get("market") in ("us", None):
            nokey.append(c["id"])
        if len(rows) >= n:
            break
    return rows, nokey


def code(n=12):
    """fundamentals.js 계산을 그대로 함수로 감싸 여러 키에 돌린다(한 곳에서만 고치게 — 템플릿을 실행 때 변환)"""
    t = TPL.read_text(encoding="utf-8")
    body = t[t.index("{") + 1:t.rindex("}")]
    body = re.sub(r'const k = "__KEY__";', "", body)
    body = body.replace("console.log(JSON.stringify({", "return ({").replace("}));", "});")
    rows, nokey = todo(n)
    ids = {cid: k for cid, k in rows}
    return ("async () => {\n"
            "  // 발굴 후보 펀더멘털 일괄(scripts/discovery/fund_fill.py --code) — 출력 → 파일 → py scripts/discovery/fund_fill.py --put <파일>\n"
            f"  // 키 없음(빼 둠, company_profile로 확인해 adapter.py --key로 넣는다): {', '.join(nokey[:30]) or '없음'}\n"
            "  const one = async k => {" + body + "  };\n"
            f"  const ids = {json.dumps(ids)}, out = {{}}, errors = [];\n"
            "  const ks = Object.keys(ids);\n"
            "  for (let i = 0; i < ks.length; i += 1) {   // 종목당 호출 6개 = 샌드박스 동시 6개 상한\n"
            "    await Promise.all(ks.slice(i, i + 1).map(async id => {\n"
            "      try { const r = await one(ids[id]); if (r && r.mcap != null) out[id] = r; else errors.push(id + \": 시총 없음\"); }\n"
            "      catch (e) { errors.push(id + \": \" + String(e && e.message || e).slice(0, 60)); }\n"
            "    }));\n"
            "  }\n"
            "  console.log(JSON.stringify({ rows: out, errors }));\n"
            "}\n")


def put(path):
    import adapter
    d = json.loads(Path(path).read_text(encoding="utf-8"))
    rows = d.get("rows", d)
    done = []
    fx = {}
    if any((o.get("currency") or "USD") != "USD" for o in rows.values()):
        try:
            sys.path.insert(0, str(ROOT / "scripts" / "tenbagger"))
            import bands
            fx = bands.ecb_rates()
        except Exception:  # noqa: BLE001 — 환율을 못 받으면 원화폐 시총만 남긴다(bands --put이 나중에 환산)
            fx = {}
    for cid, out in rows.items():
        r = adapter.put_fund(cid, out)
        if r.get("mcap_usd") is None and fx and out.get("mcap") is not None:   # 외화 상장 — ECB 기준환율로 USD 시총(2026-11-14 점검: Kongsberg NOK)
            import bands
            full = _j(FUND)
            full[cid]["mcap_usd"] = bands.to_usd(out["mcap"], out.get("currency"), fx)
            FUND.write_text(json.dumps(full, ensure_ascii=False, indent=1, sort_keys=True), encoding="utf-8")
        done.append(cid)
    errs = d.get("errors") or []
    tried = _j(TRIED)
    today = date.today().isoformat()
    for e in errs:
        tried[e.split(":")[0].strip()] = today
    TRIED.parent.mkdir(parents=True, exist_ok=True)
    TRIED.write_text(json.dumps(tried, ensure_ascii=False, indent=1), encoding="utf-8")
    return done, errs


def status():
    c = candidates()
    fund = _j(FUND)
    have = sum(1 for x in c if (fund.get(x["id"]) or {}).get("mcap_usd") is not None)
    return {"candidates": len(c), "with_fundamentals": have, "share": round(have / len(c), 3) if c else None}


def main(argv):
    sys.stdout.reconfigure(encoding="utf-8")
    if "--code" in argv:
        i = argv.index("--code")
        n = int(argv[i + 1]) if len(argv) > i + 1 and argv[i + 1].isdigit() else 12
        print(code(n))
    elif "--put" in argv:
        done, errs = put(argv[argv.index("--put") + 1])
        print(f"펀더멘털 {len(done)}종목 저장" + (f" · 실패 {len(errs)}: {'; '.join(errs[:5])}" if errs else ""))
        print(json.dumps(status(), ensure_ascii=False))
    else:
        print(json.dumps(status(), ensure_ascii=False))


if __name__ == "__main__":
    main(sys.argv[1:])
