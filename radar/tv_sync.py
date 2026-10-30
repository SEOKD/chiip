"""TradingView 와치리스트 양방향 동기화 (마스터 지시 2026-10-31 "내 TradingView 와치리스트에 있는 종목들도 알파 종목 발굴 및 텐배거 발굴 레이더 망에
포함시켜주고 반대로 Chiip이 스스로 찾은 종목들이 와치리스트에 없다면 추가해줘. 폴더와 국가가 일치하게, 폴더 안 섹터별 Section에 맞게, 적절한 Section이 없으면 직접 만들어줘")

결정론 스크립트는 TradingView MCP를 직접 부를 수 없다 — Fiscal.ai처럼 '모델이 도구를 부르고 → 결과를 파일로 넣는다'.
  ① 와치리스트 → 레이더: --put <list-watchlists 출력> 이 config/discovery.yaml의 생성 구역(tradingview 표시 사이)을 다시 쓴다. 폴더·섹션이 테마가 되고 watch: true라
     레이더 종목 인식·SEC 공시·수집 관문·관심도·선별·구간 엔진·리포트 후보에 자동으로 들어간다. 이름 없는 종목은 unresolved로 돌려준다(--names로 넣는다).
  ② Chiip → 와치리스트: --plan 이 빠진 종목을 폴더·섹션에 배치한 호출 목록을 낸다. add-to-watchlist는 맨 뒤에만 붙고 이미 있는 항목은 맨 뒤로 옮기므로
     섹션 중간에 넣으려면 그 뒤 항목 전체를 순서대로 다시 넣는다(plan_order). 새 섹션은 ###NONE 앞에 만든다.
  지우지 않는다: Chiip은 와치리스트에서 종목을 빼지 않는다. 마스터가 지운 종목(added.csv에 있는데 목록에 없음)은 다시 넣지 않는다.
사용: py radar/tv_sync.py --put <파일> · --names <파일> · --plan · --done <파일(add 결과 전체 목록)>
"""
import csv
import json
import re
import sys
from datetime import date
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
CFG = ROOT / "config" / "tradingview.yaml"
DISC = ROOT / "config" / "discovery.yaml"
SYMS = ROOT / "config" / "tradingview_symbols.csv"
SNAP = ROOT / "radar" / "state" / "tv_watchlists.json"
ADDED = ROOT / "knowledge" / "models" / "tradingview" / "added.csv"
BEGIN = "  # >>> tradingview — radar/tv_sync.py가 만든다. 손으로 고치지 않는다(종목은 TradingView에서 고친다)\n"
END = "  # <<< tradingview\n"
SYM_COLS = ["tv_symbol", "exchange", "ticker", "entity_id", "name", "match_method", "confirmed"]
ADD_COLS = ["entity_id", "tv_symbol", "folder", "section", "added_on"]


def _y(p):
    return yaml.safe_load(Path(p).read_text(encoding="utf-8")) or {}


def cfg():
    return _y(CFG)


def is_equity(sym):
    """섹션 표시·환율로 나눈 값·선물·스프레드는 종목이 아니다"""
    return not (sym.startswith("###") or "/" in sym or sym.endswith("!") or "+" in sym or ":" not in sym)


def clean_section(s):
    return re.sub(r"[^\w &·/-]", "", s[3:], flags=re.U).strip()


def sections(symbols):
    """[(섹션 이름 또는 '', 종목…)] — 첫 표시 전 종목은 섹션 ''"""
    out, cur = [], ("", [])
    for s in symbols:
        if s.startswith("###"):
            out.append(cur)
            cur = (clean_section(s), [])
        elif is_equity(s):
            cur[1].append(s)
    out.append(cur)
    return [x for x in out if x[1]]


def market_of(sym, c=None):
    return ((c or cfg()).get("exchange_market") or {}).get(sym.split(":")[0], "eu")


def normalize(code):
    c = str(code or "").upper()
    return re.sub(r"\.(US|TSE|T|KO|KQ|TW|TWO|XETRA|DE|PA|MI|MC|AS|OL|LSE|L|ST|HE|SW|F|CO)$", "", c).rstrip(".").replace("_", "-")


SUFFIX_MARKET = {"US": "us", "KO": "kr", "KQ": "kr", "TSE": "jp", "T": "jp", "TW": "tw", "TWO": "tw", "HK": "hk"}


def code_market(code, market=None):
    """코드 꼬리표·지도의 market → 시장. 꼬리표가 다른 유럽 거래소면 eu, 알 수 없으면 None"""
    tail = str(code or "").upper().rsplit(".", 1)
    if len(tail) == 2 and tail[1]:
        return SUFFIX_MARKET.get(tail[1], "eu")
    return {"KRX": "kr", "KOSDAQ": "kr", "KOSPI": "kr", "NASDAQ": "us", "NYSE": "us", "TSE": "jp"}.get(str(market or "").upper(), market)


def known_entities():
    """(코드 → {시장: 엔티티 id}, id → 이름·코드). 저장소 지도 전체(생성 구역 제외).
    같은 코드가 시장마다 다른 회사일 수 있어 시장까지 본다 — NYSE:BA(보잉)와 LSE:BA.(BAE)"""
    out, idx = {}, {}

    def add(cid, name, code, market=None):
        n = normalize(code)
        if n and n != "NONE":
            out.setdefault(n, {}).setdefault(code_market(code, market), cid)
        idx.setdefault(cid, {"name": name, "code": n})
    val, ew = _y(ROOT / "config" / "valuation.yaml"), _y(ROOT / "config" / "earnings_watch.yaml")
    for u in (val.get("universe") or []) + (ew.get("extra") or []):
        add(u["id"], u.get("name"), u.get("code") or u.get("jp_code"))
    for t in _y(DISC).get("themes") or []:
        if t.get("source") != "tradingview":
            for c in t.get("candidates") or []:
                add(c["id"], c.get("name"), c.get("code"), c.get("market"))
    for c in _y(ROOT / "config" / "defense.yaml").get("companies") or []:
        add(c["id"], c.get("name"), c.get("code"))
    for c in _y(ROOT / "config" / "consumer.yaml").get("companies") or []:
        add(c["id"], c.get("name"), c.get("code"), c.get("market"))
    for seeds in (_y(ROOT / "config" / "tenbagger_universe.yaml").get("seeds") or {}).values():
        for s in seeds or []:
            add(f"us-{s['ticker'].lower()}", s.get("name"), s["ticker"], "us")
    with (ROOT / "config" / "watchlist.csv").open(encoding="utf-8", newline="") as f:
        for r in csv.DictReader(f):
            add(r["entity_id"], r.get("name"), r.get("ticker"), r.get("market"))
    return out, idx


def lookup(code_id, sym, c=None):
    """TradingView 종목 → 엔티티 id. 시장이 맞아야 같은 회사로 본다. 제3시장 상장(BCBA·TSX 등)만 미국 상장과 잇는다"""
    d = code_id.get(normalize(sym.split(":", 1)[1])) or {}
    m = market_of(sym, c)
    return d.get(m) or d.get(None) or (d.get("us") if m == "other" else None)


def new_id(sym, c=None):
    ex, tk = sym.split(":", 1)
    return f"{market_of(sym, c)}-{re.sub(r'[^a-z0-9]', '', tk.lower())}"


def load_symbols():
    if not SYMS.exists():
        return {}
    with SYMS.open(encoding="utf-8", newline="") as f:
        return {r["tv_symbol"]: r for r in csv.DictReader(f)}


def write_symbols(rows):
    SYMS.parent.mkdir(parents=True, exist_ok=True)
    with SYMS.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=SYM_COLS, lineterminator="\n")
        w.writeheader()
        for k in sorted(rows):
            w.writerow(rows[k])


def resolve(snapshot):
    """와치리스트 → 종목 매핑. 코드가 저장소 지도에 있으면 그 id, 없으면 새 id. 이름 없는 종목은 unresolved"""
    c = cfg()
    code_id, idx = known_entities()
    rows, unresolved = load_symbols(), []
    skip = c.get("skip_symbols") or {}
    for s in skip:
        rows.pop(s, None)
    for w in snapshot["watchlists"]:
        if w["name"] not in (c.get("folders") or {}):
            continue
        for s in w["symbols"]:
            if not is_equity(s) or s in skip:
                continue
            ex, tk = s.split(":", 1)
            cid = lookup(code_id, s, c)
            old = rows.get(s) or {}
            name = (idx.get(cid) or {}).get("name") or old.get("name") or ""
            rows[s] = {"tv_symbol": s, "exchange": ex, "ticker": tk, "entity_id": cid or old.get("entity_id") or new_id(s, c), "name": name,
                       "match_method": "ticker" if cid else old.get("match_method") or "new", "confirmed": "true" if cid else old.get("confirmed") or "false"}
            if not name:
                unresolved.append(s)
    return rows, unresolved


def alias_names(name):
    """뉴스에서 찾을 이름 — 원래 이름 + 법인 꼬리를 뗀 이름(짧으면 오탐이라 뺀다: Visa·Linde)"""
    short = re.sub(r"[,\s]+(Inc\.?|Incorporated|Corp\.?|Corporation|Co\.?,?\s*Ltd\.?|Co\.|Ltd\.?|Limited|LLC|LP|PLC|plc|Plc|SA|S\.A\.|S\.p\.A\.|SpA|NV|SE|AG|SCA)$", "", name).strip()
    return [name] + ([short] if short != name and len(short) >= 6 else [])


def sector_of(section, c=None):
    sec = section.upper()
    for rx, name in ((c or cfg()).get("section_sector") or {}).items():
        if re.search(rx, sec):
            return name
    return "other"


def slug(s):
    return re.sub(r"_+", "_", re.sub(r"[^a-z0-9가-힣]+", "_", s.lower())).strip("_") or "main"


def block(snapshot, rows):
    """discovery.yaml 생성 구역 텍스트 — 손으로 만든 테마에 이미 있는 종목은 빼서 중복을 막는다"""
    c = cfg()
    d = _y(DISC)
    hand = [x for t in d.get("themes") or [] if t.get("source") != "tradingview" for x in t.get("candidates") or []]
    seen = {x["id"] for x in hand}
    codes = {(normalize(x.get("code")), code_market(x.get("code"), x.get("market"))) for x in hand}      # 같은 회사가 다른 id로 있는 경우(지도 간 id 차이)도 코드로 거른다
    L = [BEGIN]
    for w in snapshot["watchlists"]:
        if w["name"] not in (c.get("folders") or {}):
            continue
        for sec, syms in sections(w["symbols"]):
            items = []
            for s in syms:
                r = rows.get(s) or {}
                cid = r.get("entity_id")
                if cid and cid not in seen and (normalize(r.get("ticker")), market_of(s, c)) not in codes:
                    seen.add(cid)
                    items.append((cid, r, s))
            if not items:
                continue
            label = f"{w['name']} {sec or '미분류'}"
            L.append(f"  - id: {json.dumps('tv_' + slug(label), ensure_ascii=False)}\n    name: {json.dumps('TradingView ' + label, ensure_ascii=False)}\n"
                     f"    source: tradingview\n    watch: true\n    sector: {sector_of(sec, c)}\n"
                     f"    bottleneck: \"마스터 와치리스트 섹션 — 병목 미판정\"\n    driver: \"미판정\"\n    evidence: [\"공시·실적 자료\"]\n    candidates:\n")
            for cid, r, s in items:
                name = r.get("name") or r["ticker"]
                row = {"id": cid, "name": name, "aliases": alias_names(name), "market": market_of(s, c), "code": r["ticker"], "why": f"마스터 TradingView 와치리스트({label}) — edge 미판정"}
                L.append("      - " + json.dumps(row, ensure_ascii=False) + "\n")
    L.append(END)
    return "".join(L)


def write_block(text):
    s = DISC.read_bytes().decode("utf-8")
    crlf = "\r\n" in s
    s = s.replace("\r\n", "\n")
    if BEGIN in s:
        s = s[:s.index(BEGIN)] + text + s[s.index(END) + len(END):]
    else:
        a = "\ncode_verified: false\n"
        i = s.index(a)
        s = s[:i].rstrip("\n") + "\n" + text + s[i:]
    DISC.write_bytes((s.replace("\n", "\r\n") if crlf else s).encode("utf-8"))


def put(snapshot):
    SNAP.parent.mkdir(parents=True, exist_ok=True)
    SNAP.write_text(json.dumps(snapshot, ensure_ascii=False, indent=0), encoding="utf-8")
    rows, unresolved = resolve(snapshot)
    write_symbols(rows)
    write_block(block(snapshot, rows))
    return {"symbols": len(rows), "unresolved": unresolved}


def put_names(names):
    """{tv_symbol: 회사 이름} — symbol-data-batch description"""
    rows = load_symbols()
    for s, n in names.items():
        if s in rows and n:
            rows[s]["name"] = n
    write_symbols(rows)
    snap = json.loads(SNAP.read_text(encoding="utf-8"))
    write_block(block(snap, rows))
    return len(names)


def added_ledger():
    if not ADDED.exists():
        return []
    with ADDED.open(encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def record_added(rows):
    ADDED.parent.mkdir(parents=True, exist_ok=True)
    new = not ADDED.exists()
    with ADDED.open("a", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=ADD_COLS, lineterminator="\n")
        if new:
            w.writeheader()
        w.writerows(rows)


def chiip_picks():
    """Chiip이 찾은 종목 = 발굴 테마(손으로 만든 것) + 알파 통과 + 조용한 상승 watch·always_watch + 텐배거 추적. [(id, 테마 또는 '')]"""
    d = _y(DISC)
    out = {}
    for t in d.get("themes") or []:
        if t.get("source") != "tradingview":
            for c in t.get("candidates") or []:
                out.setdefault(c["id"], t["id"])
    for p, key in ((ROOT / "knowledge" / "models" / "alpha" / "latest.json", "pass"), (ROOT / "knowledge" / "models" / "discovery" / "quiet_latest.json", "watch")):
        if p.exists():
            for cid in json.loads(p.read_text(encoding="utf-8")).get(key) or []:
                out.setdefault(cid, "")
    for cid in (d.get("quiet") or {}).get("always_watch") or []:
        out.setdefault(cid, "")
    return out


def plan_order(symbols, inserts):
    """맨 뒤로만 붙는 API로 섹션 위치에 넣는 호출 내용. inserts = [(섹션 표시, [종목…])], 표시가 목록에 없으면 ###NONE 앞(없으면 맨 뒤)에 새 섹션으로 만든다.
    반환 = add-to-watchlist에 넘길 목록(첫 삽입 지점 뒤 항목 전체 포함). 결과 목록은 (원래 + 삽입)"""
    full, first = list(symbols), None
    for mark, items in inserts:
        if mark in full:
            i = full.index(mark) + 1
            while i < len(full) and not full[i].startswith("###"):
                i += 1
            full[i:i] = items
            ins = i
        else:
            i = full.index("###NONE") if "###NONE" in full else len(full)
            full[i:i] = [mark] + items
            ins = i
        first = ins if first is None else min(first, ins)
    return ([] if first is None else full[first:]), full


def plan():
    """빠진 종목 → 폴더별 호출 목록. 심볼을 모르는 종목은 need_symbol로 돌려준다(search-symbols로 찾아 tradingview_symbols.csv에 넣는다)"""
    c = cfg()
    snap = json.loads(SNAP.read_text(encoding="utf-8"))
    present = {s for w in snap["watchlists"] for s in w["symbols"]}
    rows = load_symbols()
    code_of = {r["entity_id"]: s for s, r in rows.items()}
    in_lists = {rows[s]["entity_id"] for s in present if s in rows}
    held_codes = {(normalize(rows[s]["ticker"]), market_of(s, c)) for s in present if s in rows and rows[s].get("ticker")}
    hand_market = {x["id"]: code_market(x.get("code"), x.get("market")) for t in _y(DISC).get("themes") or [] for x in t.get("candidates") or []}
    gone = {r["entity_id"] for r in added_ledger()} - in_lists     # 넣었는데 없다 = 마스터가 지웠다
    by_list, need, skipped = {}, [], sorted(gone)
    theme_sec = c.get("theme_sections") or {}
    folders = {v["market"]: k for k, v in (c.get("folders") or {}).items() if v.get("market")}
    _, idx = known_entities()
    for cid, theme in chiip_picks().items():
        if cid in in_lists or cid in gone or ((idx.get(cid) or {}).get("code"), hand_market.get(cid)) in held_codes:
            continue
        sym = code_of.get(cid)
        if not sym:
            need.append({"id": cid, "name": (idx.get(cid) or {}).get("name"), "theme": theme})
            continue
        folder = folders.get(market_of(sym, c))
        if folder:
            by_list.setdefault(folder, {}).setdefault(theme_sec.get(theme) or c.get("default_section", "###CHIIP PICKS"), []).append(sym)
    calls = []
    for folder, secs in by_list.items():
        w = next(x for x in snap["watchlists"] if x["name"] == folder)
        order, _full = plan_order(w["symbols"], list(secs.items()))
        calls.append({"folder": folder, "watchlist_id": str(w["id"]), "symbols": order, "new": sum(len(v) for v in secs.values())})
    return {"calls": calls, "need_symbol": need, "removed_by_master": skipped}


def main(argv):
    sys.stdout.reconfigure(encoding="utf-8")
    if argv[:1] == ["--put"]:
        print(json.dumps(put(json.loads(Path(argv[1]).read_text(encoding="utf-8"))), ensure_ascii=False))
    elif argv[:1] == ["--names"]:
        print(put_names(json.loads(Path(argv[1]).read_text(encoding="utf-8"))), "건")
    elif argv[:1] == ["--plan"]:
        print(json.dumps(plan(), ensure_ascii=False, indent=1))
    else:
        print(__doc__)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
