"""TradingView 와치리스트 섹션 재분배 (마스터 지시 2026-11-04 "Watchlist의 Section을 정해 종목들을 분류할 때 Section에 포함되지 않거나 잘못된 Section에
들어간 종목은 적합한 Section에 재분배하라")

TradingView MCP는 항목을 옮기는 도구가 없다 — add-to-watchlist가 이미 있는 항목을 맨 뒤로 옮기므로, 원하는 순서 전체(섹션 머리 '###이름' 포함)를 한 번에
다시 넣으면 그 순서가 된다. 이 스크립트는 지금 목록 + config/tv_sections.yaml(옮길 종목·합칠 섹션·새 섹션 순서) → 다시 넣을 전체 순서를 낸다.
  지우지 않는다: 목록에 있는 종목은 모두 남는다(옮기기만). 빈 옛 섹션 머리(예: ###ALL)는 맨 앞에 남는다 — 지우는 것은 마스터 몫.
  분류 근거: TradingView 업종(sector·industry)을 기본으로, Chiip 테마 섹션(반도체·전력·원자력 등)이 맞으면 그쪽(config의 moves에 이유와 함께).
사용: py radar/tv_sections.py <목록 JSON(get-watchlist 또는 list-watchlists 출력)> <watchlist 이름>   → {"watchlist_id", "symbols": [...], "moved": n}
      py radar/tv_sections.py --taxonomy <list-watchlists 출력>   → 시장 세부 산업 섹션으로 옮기고 빠진 유니버스 종목을 더한 순서(와치리스트마다, 2026-11-08)
"""
import json
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
CFG = ROOT / "config" / "tv_sections.yaml"


def parse(symbols):
    """[(섹션 또는 None, 종목)] — 섹션 머리 앞의 종목은 None"""
    sec, out, heads = None, [], []
    for s in symbols:
        if s.startswith("###"):
            sec = s[3:].strip()
            heads.append(sec)
        else:
            out.append((sec, s))
    return out, heads


def plan(symbols, rule):
    items, heads = parse(symbols)
    merge = rule.get("merge") or {}
    moves = {k: v for k, v in (rule.get("moves") or {}).items()}
    order = []
    for h in heads + list(rule.get("new_sections") or []):
        h2 = merge.get(h, h)
        if h2 not in order and h2 not in (rule.get("drop_empty") or []):
            order.append(h2)
    groups = {h: [] for h in order}
    loose, moved = [], 0
    for sec, s in items:
        tgt = moves.get(s) or merge.get(sec, sec)
        if tgt != sec:
            moved += 1
        if tgt in groups:
            groups[tgt].append(s)
        else:
            loose.append(s)   # 섹션이 정해지지 않은 종목 — 맨 앞(머리 없는 자리)에 둔다
    out = list(loose)
    for h in order:
        if groups[h]:
            out.append("###" + h)
            out += groups[h]
    return out, moved, [s for s in loose]


FOLDER = {"US": "1_US", "KR": "2_Korea", "JP": "3_Japan", "TW": "6_Taiwan", "HK": "5_HK"}   # 그 밖(유럽·영국·스위스·북유럽) → 4_EU & UK


def taxonomy_sections():
    """{TradingView 심볼: (폴더, 섹션)} — 시장 세부 산업 묶음(scripts/industry/weekly_pick.groups)을 와치리스트 섹션으로(마스터 지시 2026-11-08
    "세부 섹터가 정해지면 이를 와치리스트 섹션에 넣고 추가하거나 업데이트하라"). 섹션 이름: 한국 폴더는 한국어 산업명, 나머지는 GICS 영문(테마로 나눈 묶음은 '· 테마')"""
    import csv
    sys.path.insert(0, str(ROOT / "scripts" / "industry"))
    import taxonomy_refresh as TR
    import weekly_pick as W
    c = W.cfg()
    sym = {r["entity_id"]: r["tv_symbol"] for r in csv.DictReader((ROOT / "config" / "tradingview_symbols.csv").open(encoding="utf-8")) if r.get("tv_symbol")}
    out = {}
    for gid, ms in c["_members"].items():
        info = c["industries"][gid]
        en = str(info["sub"]).split(" / ")[0].upper() if " / " not in str(info["sub"]) else str(info["industry"]).upper()
        if "." in gid:
            en += " · " + gid.split(".", 1)[1].replace("-", " ").upper()
        for m in ms:
            s_ = sym.get(m["id"]) or (m["ticker"] if m.get("peer") else None)
            if not s_:
                continue
            ctry = TR.country(m)
            folder = FOLDER.get(ctry, "4_EU & UK")
            out[s_] = (folder, info["name"] if folder == "2_Korea" else en)
    return out


def taxonomy_plan(wl, tax=None, everywhere=None):
    """한 와치리스트의 새 순서 — 이미 있는 종목은 산업 섹션으로 옮기고, 이 폴더 나라인데 어느 와치리스트에도 없는 유니버스 종목은 더한다. 지우지 않는다"""
    tax = tax if tax is not None else taxonomy_sections()
    everywhere = everywhere or set()
    syms = list(wl["symbols"])
    moves = {s_: sec for s_, (f, sec) in tax.items() if f == wl["name"] and (s_ in syms or s_ not in everywhere)}
    add = [s_ for s_ in moves if s_ not in syms]
    rule = {"moves": moves, "new_sections": sorted(set(moves.values()))}
    out, moved, loose = plan(syms + add, rule)
    return out, moved, add


def main(argv):
    sys.stdout.reconfigure(encoding="utf-8")
    if argv and argv[0] == "--taxonomy":   # py radar/tv_sections.py --taxonomy <list-watchlists 출력> → 와치리스트마다 다시 넣을 순서
        data = json.loads(Path(argv[1]).read_text(encoding="utf-8"))
        wls = data.get("watchlists") or [data]
        tax = taxonomy_sections()
        every = {x for w in wls for x in w.get("symbols") or []}
        res = []
        for wl in wls:
            if wl.get("name") not in set(FOLDER.values()) | {"4_EU & UK"}:
                continue
            out, moved, add = taxonomy_plan(wl, tax, every)
            assert set(out) - {x for x in out if x.startswith("###")} >= {x for x in wl["symbols"] if not x.startswith("###")}, "종목이 빠졌다"
            res.append({"watchlist_id": str(wl["id"]), "name": wl["name"], "symbols": out, "moved": moved, "added": add})
        print(json.dumps(res, ensure_ascii=False))
        return
    data = json.loads(Path(argv[0]).read_text(encoding="utf-8"))
    name = argv[1]
    wls = data.get("watchlists") or [data]
    wl = next(w for w in wls if w.get("name") == name)
    rule = (yaml.safe_load(CFG.read_text(encoding="utf-8")) or {}).get(name) or {}
    out, moved, loose = plan(wl["symbols"], rule)
    assert sorted(x for x in out if not x.startswith("###")) == sorted(x for x in wl["symbols"] if not x.startswith("###")), "종목이 빠지거나 늘었다"
    print(json.dumps({"watchlist_id": str(wl["id"]), "symbols": out, "moved": moved, "unsectioned": loose}, ensure_ascii=False))


if __name__ == "__main__":
    main(sys.argv[1:])
