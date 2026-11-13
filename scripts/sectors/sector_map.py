"""공통 섹터 지도 — 모든 기능이 같은 섹터 이름을 쓴다 (마스터 지시 2026-11-13 종목 범위 확대 1단계, ADR-025)

섹터 분류 = config/sector_select.yaml groups(Portfolio 섹터 후보) + config/sector_map.yaml extra_groups(태그 전용).
종목 → 섹터 우선순위(처음 정해진 것을 쓴다):
  1. sector_select holding_group(내 종목)  2. sector_select 묶음 구성 종목(TradingView 기호)
  3. 발굴 테마(config/discovery.yaml) — 테마 이름 규칙(name_rules) → 테마 sector 칸(theme_sector)
  4. 감시 목록 sub(config/valuation.yaml·earnings_watch.yaml → watch_sub)
  5. 소비재 지도(config/consumer.yaml segment) · 방위 지도(config/defense.yaml) → defense
  6. 시가총액 구간 시드(config/tenbagger_universe.yaml)
할당량: diversify(rows, n) — 점수순으로 고르되 AI 밖 최소 비율·같은 섹터 상한을 지킨다(후보가 모자라면 그만큼 풀어 준다).
사용: py scripts/sectors/sector_map.py            # 지도 다시 만들기 + 섹터 분포
      py scripts/sectors/sector_map.py <id|티커> …  # 조회
"""
import json
import re
import sys
from collections import Counter
from functools import lru_cache
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "knowledge" / "models" / "sectors" / "tags.json"


def _y(p):
    f = ROOT / p
    try:
        return yaml.safe_load(f.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError):
        return {}


@lru_cache(maxsize=1)
def cfg():
    return _y("config/sector_map.yaml")


@lru_cache(maxsize=1)
def names():
    """{섹터 id: 한국어 이름}"""
    out = {g: v["name"] for g, v in (_y("config/sector_select.yaml").get("groups") or {}).items()}
    out.update(cfg().get("extra_groups") or {})
    return out


def is_ai(gid):
    return gid in set(cfg().get("ai_chain") or [])


def by_name(text, rules=None):
    """테마·섹션 이름 → 섹터(name_rules, 처음 맞는 규칙)"""
    for pat, gid in rules if rules is not None else (cfg().get("name_rules") or []):
        if re.search(pat, text or "", re.I):
            return gid
    return None


def build():
    """{"by_id": {id: 섹터}, "by_ticker": {티커: 섹터}, "src": {id: 근거}}"""
    c = cfg()
    by_id, by_t, src = {}, {}, {}

    def put(cid, ticker, gid, why):
        if not gid:
            return
        if cid and cid not in by_id:
            by_id[cid], src[cid] = gid, why
        if ticker:
            by_t.setdefault(str(ticker).split(":")[-1].upper(), gid)

    ss = _y("config/sector_select.yaml")
    for t, gid in (ss.get("holding_group") or {}).items():
        by_t.setdefault(t.upper(), gid)
    mw = _y("config/market_watch.yaml").get("sectors") or {}
    for gid, g in (ss.get("groups") or {}).items():
        mem = g.get("members") or [k.replace("_", ":", 1) for k in (mw.get(gid) or {}).get("keys", [])]
        for s in mem:
            by_t.setdefault(s.split(":")[-1].upper(), gid)
    for h in _y("config/portfolio.yaml").get("holdings") or []:
        if h.get("ticker") and h["ticker"].upper() in by_t:
            put(h["id"], h["ticker"], by_t[h["ticker"].upper()], "내 종목")
    ts = {("null" if k is None else str(k)): v for k, v in (c.get("theme_sector") or {}).items()}
    for t in _y("config/discovery.yaml").get("themes") or []:
        gid = by_name(t.get("name", "")) or ts.get("null" if t.get("sector") is None else str(t.get("sector")))
        for cand in t.get("candidates") or []:
            tk = cand.get("code") if cand.get("market") in ("us", None) else None
            pre = by_t.get(str(tk).upper()) if tk else None
            put(cand.get("id"), tk, pre or gid, f"테마 {t.get('name')}")
    ws = c.get("watch_sub") or {}
    for p in ("config/valuation.yaml", "config/earnings_watch.yaml"):
        d = _y(p)
        for u in (d.get("universe") or []) + (d.get("extra") or []):
            code = str(u.get("code") or "")
            tk = code[:-3] if code.endswith(".US") else None
            put(u.get("id"), tk, (by_t.get(tk.upper()) if tk else None) or ws.get(u.get("sub")), f"감시 목록 sub {u.get('sub')}")
    seg = c.get("consumer_segment") or {}
    for co in _y("config/consumer.yaml").get("companies") or []:
        put(co.get("id"), co.get("code") if co.get("market") == "us" else None, seg.get(co.get("segment"), seg.get("default", "cons_disc")), "소비재 지도")
    for co in _y("config/defense.yaml").get("companies") or []:
        put(co.get("id"), None, "defense", "방위 지도")
    rc = ROOT / "knowledge" / "models" / "discovery" / "rotation_candidates.json"   # 섹터 순환 스크린 후보(2026-11-13 2단계, ADR-027)
    if rc.exists():
        for v in (json.loads(rc.read_text(encoding="utf-8")).get("sectors") or {}).values():
            for r in v.get("rows") or []:
                t = str(r.get("ticker") or "").upper()
                put(f"us-{re.sub(r'[^a-z0-9]', '', t.lower())}", t, by_t.get(t) or r.get("group"), "섹터 순환 스크린")
    sd = c.get("seed_sector") or {}
    for grp, rows in (_y("config/tenbagger_universe.yaml").get("seeds") or {}).items():
        for r in rows or []:
            t = str(r.get("ticker") or "").upper()
            put(f"us-{t.lower()}", t, by_t.get(t) or sd.get(grp), f"구간 시드 {grp}")
    return {"by_id": by_id, "by_ticker": by_t, "src": src}


@lru_cache(maxsize=1)
def index():
    return build()


def tag(cid=None, ticker=None):
    """섹터 id 또는 None(미분류)"""
    ix = index()
    if cid and cid in ix["by_id"]:
        return ix["by_id"][cid]
    if ticker:
        return ix["by_ticker"].get(str(ticker).split(":")[-1].upper())
    if cid and cid.startswith("us-"):
        return ix["by_ticker"].get(cid[3:].upper())
    return None


def diversify(rows, n, key=None, non_ai_min=None, per_sector_max=None):
    """점수순 rows에서 n개 — 같은 섹터 상한, AI 밖 최소 비율. 섹터를 모르는 행은 AI 밖으로 세지 않는다(모르면 미확인)"""
    q = cfg().get("quota") or {}
    non_ai_min = q.get("non_ai_min", 0.4) if non_ai_min is None else non_ai_min
    per = q.get("per_sector_max", 2) if per_sector_max is None else per_sector_max
    key = key or (lambda r: tag(r.get("id"), r.get("ticker")))
    need_non = int(-(-n * non_ai_min // 1))     # 올림
    secs = [key(r) for r in rows]
    picked, cnt = [], Counter()

    def ok(i):
        s = secs[i]
        return s is None or cnt[s] < per

    non_ai = [i for i, s in enumerate(secs) if s and not is_ai(s)]
    for i in non_ai:                              # ① AI 밖 최소 몫을 먼저(점수순)
        if sum(1 for j in picked if secs[j] and not is_ai(secs[j])) >= need_non or len(picked) >= n:
            break
        if ok(i):
            picked.append(i)
            cnt[secs[i]] += 1
    for i in range(len(rows)):                    # ② 나머지는 점수순(섹터 상한 지킴)
        if len(picked) >= n:
            break
        if i not in picked and ok(i):
            picked.append(i)
            if secs[i]:
                cnt[secs[i]] += 1
    for i in range(len(rows)):                    # ③ 그래도 모자라면 상한을 풀어 채운다
        if len(picked) >= n:
            break
        if i not in picked:
            picked.append(i)
    return [rows[i] for i in sorted(picked)]


def write():
    ix = build()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({"names": names(), "ai_chain": cfg().get("ai_chain"), **ix}, ensure_ascii=False, indent=1), encoding="utf-8")
    return ix


def main(argv):
    sys.stdout.reconfigure(encoding="utf-8")
    if argv:
        for a in argv:
            g = tag(a, a)
            print(f"{a}: {g or '미분류'} {names().get(g, '')}{' (AI 밸류체인)' if g and is_ai(g) else ''}")
        return
    ix = write()
    alpha = json.loads((ROOT / "knowledge" / "models" / "alpha" / "latest.json").read_text(encoding="utf-8")).get("rows") or {}
    c = Counter(ix["by_id"].values())
    print(f"섹터 지도 — 종목 {len(ix['by_id'])} · 티커 {len(ix['by_ticker'])} · 섹터 {len(c)} → {OUT.relative_to(ROOT).as_posix()}")
    a = Counter("AI 밸류체인" if (tag(k) and is_ai(tag(k))) else ("미분류" if not tag(k) else "AI 밖") for k in alpha)
    print("알파 산정 종목:", dict(a))
    for g, k in c.most_common():
        print(f"  {names().get(g, g)}{' *' if is_ai(g) else ''}: {k}")


if __name__ == "__main__":
    main(sys.argv[1:])
