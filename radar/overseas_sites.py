"""한국 전자기업 해외 생산 거점 — 그 나라 정부 자료와 수출입 거울 (마스터 지시 2026-11-08 "기사 소재 발굴 시 해외에 생산 거점을 두고 있는 한국 전자기업과
연관된 해당 국가의 정부기관 자료와 수출입, PPI 데이터도 참고") — 설정 config/korea_overseas_sites.yaml, 모델 없음

① 수출입 거울: 거점 나라 → 미국 품목 수입(Census, 나라 코드별) — radar/state/trade_hs.sqlite obs(reporter us, partner = 나라 ISO)에 쌓는다.
   일본 품목·국가별 수출입(e-Stat)은 trade_hs가 이미 쌓는다. 거점 품목의 최근 3개월 합 vs 전년 같은 기간이 ±30% 이상이면 신호.
② 정부 자료: robots 허용 목록 페이지(직접) + 막힌 곳은 Google News 색인 site: 검색 — 감시어(회사·전자·반도체·관세·FDI)가 든 새 제목만.
   처음 보는 페이지는 기준선만 기록한다. 새 항목은 radar inbox src-overseas-gov(정부)로 — Pulse와 기사 소재 후보 풀이 본다.
③ PPI: 거점 나라 PPI는 공식 자동 경로가 없어(2026-11-08 확인) 품목의 미국·일본·대만 PPI(config/trade_ppi.yaml)를 신호에 붙인다.
출력 knowledge/models/overseas_sites/latest.json {as_of, signals[], gov[], errors[]}. 단서이지 사실이 아니다(금지표: 수출입 급증 → 특정 기업 매출).
사용: py radar/overseas_sites.py [--status]
"""
import hashlib
import json
import re
import sys
import time
import urllib.parse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from pollers import common  # noqa: E402

CFG = "config/korea_overseas_sites.yaml"
OUT = common.ROOT / "knowledge" / "models" / "overseas_sites" / "latest.json"
GN = "https://news.google.com/rss/search?q={q}&hl=en-US&gl=US&ceid=US:en"


def cfg():
    return common.load_yaml(CFG)


def items_by_country(c):
    """{나라: {hs: [(회사 id, 회사 이름, 품목 이름, 거점, ppi 키)]}}"""
    out = {}
    for s in c["sites"]:
        for it in s["items"]:
            out.setdefault(s["country"], {}).setdefault(it["hs"], []).append((s["company"], s["name"], it["name"], s["place"], it.get("ppi")))
    return out


def census_mirror(c, db, key, today, errors):
    """거점 나라 → 미국 수입(품목·나라·월) — 이미 있는 달은 최근 2개월만 다시 받는다"""
    import trade_ppi as tp
    start = tp.start_month(today, c["months"])
    got = 0
    for ctry, hss in items_by_country(c).items():
        code = c["census_country"].get(ctry)
        for hs in hss:
            have = {r[0] for r in db.execute("SELECT period FROM obs WHERE reporter='us' AND flow='import' AND partner=? AND hs=?", (ctry, hs))}
            since = start if not have else sorted(have)[-2] if len(have) > 1 else start
            try:
                rows = json.loads(tp.get(f"https://api.census.gov/data/timeseries/intltrade/imports/hs?get=I_COMMODITY,GEN_VAL_MO,CTY_CODE&COMM_LVL=HS6"
                                         f"&I_COMMODITY={hs}&CTY_CODE={code}&time=from+{since}&key={key}", timeout=90) or "[]")
            except Exception as e:
                errors.append(f"census {ctry} {hs}: {type(e).__name__}")
                continue
            if rows:
                h = rows[0]
                v, t = h.index("GEN_VAL_MO"), h.index("time")
                data = [("us", "import", ctry, hs, r[t], float(r[v]), "USD") for r in rows[1:] if r[v] not in ("", None)]
                db.executemany("INSERT OR REPLACE INTO obs VALUES(?,?,?,?,?,?,?)", data)
                db.commit()
                got += len(data)
            time.sleep(0.4)
    return got


def series(db, reporter, flow, partner, hs):
    return dict(db.execute("SELECT period, value FROM obs WHERE reporter=? AND flow=? AND partner=? AND hs=? ORDER BY period", (reporter, flow, partner, hs)).fetchall())


def yoy3(s):
    """최근 3개월 합 vs 전년 같은 3개월 — (증가율, 최근 합, 마지막 달)"""
    ps = sorted(s)
    if len(ps) < 15:
        return None, None, None
    last3 = ps[-3:]
    prev = [f"{int(p[:4]) - 1}{p[4:]}" for p in last3]
    if not all(p in s and s[p] for p in prev):
        return None, None, ps[-1]
    now, before = sum(s[p] for p in last3), sum(s[p] for p in prev)
    return now / before - 1, now, ps[-1]


def signals(c, db, ppi_hist=None):
    """거점 품목 수출입 급변 — 미국 수입 거울(달러) + 일본 수출입(천 엔, 4자리 장 단위라 참고)"""
    out = []
    for ctry, hss in items_by_country(c).items():
        for hs, owners in hss.items():
            g, v, last = yoy3(series(db, "us", "import", ctry, hs))
            if g is None or v < c["min_usd_3m"] or abs(g) < c["surge_yoy"]:
                continue
            ppi = []
            for _, _, _, _, key in owners:
                if key and ppi_hist:
                    for k2, s2 in ((ppi_hist.get("inputs", {}).get(key) or {}).get("ppi") or {}).items():
                        if k2 in ("us", "jp", "tw") and s2:
                            ps = sorted(s2)
                            if len(ps) >= 13 and s2[ps[-13]]:
                                ppi.append(f"{k2.upper()} PPI {s2[ps[-1]] / s2[ps[-13]] - 1:+.1%}(전년, {ps[-1][:7]})")
            out.append({"country": ctry, "hs": hs, "flow": f"{ctry}→미국 수입", "yoy_3m": round(g, 3), "usd_3m": round(v), "last": last,
                        "companies": sorted({o[1] for o in owners}), "company_ids": sorted({o[0] for o in owners}), "items": sorted({o[2] for o in owners}),
                        "places": sorted({o[3] for o in owners}), "ppi": sorted(set(ppi)), "source": "U.S. Census Bureau 국가별 품목 수입"})
    return sorted(out, key=lambda x: -abs(x["yoy_3m"]))


def gov_pages(c, seen, errors):
    """정부 목록 페이지·색인에서 감시어가 든 새 제목"""
    from usgov import korea_watch as kw
    from pollers import rss
    terms = c["terms"]
    rows = []
    for p in c["gov"]["direct"]:
        try:
            first = p["id"] not in seen
            old = set(seen.get(p["id"], []))
            docs = kw.page_docs(kw.fetch(p["url"]), p["url"], terms, "news")
            if not first:
                rows += [{"id": p["id"], "country": p["country"], "juris": p["juris"], **d} for d in docs if d["url"] not in old]
            seen[p["id"]] = sorted(old | {d["url"] for d in docs})[-500:]
        except Exception as e:
            errors.append(f"{p['id']}: {type(e).__name__}")
    for p in c["gov"]["gn"]:
        try:
            first = p["id"] not in seen
            old = set(seen.get(p["id"], []))
            ents = rss.parse_feed(common.http_get(GN.format(q=urllib.parse.quote(p["q"] + " when:7d")), timeout=30))[:40]
            docs = [{"url": e["link"], "title": common.strip_tags(e["title"]), "pub": e.get("date")} for e in ents]
            if not first:
                rows += [{"id": p["id"], "country": p["country"], "juris": p["juris"], **d} for d in docs if d["url"] not in old]
            seen[p["id"]] = sorted(old | {d["url"] for d in docs})[-500:]
        except Exception as e:
            errors.append(f"{p['id']}: {type(e).__name__}")
    return rows


def to_items(rows):
    return [common.make_item("src-overseas-gov", hashlib.sha1(r["url"].encode()).hexdigest()[:16], r["url"], f"[{r['juris']}] {r['title']}",
                             common.iso(common.now_kst()), "정부", "ko" if re.search("[가-힣]", r["title"]) else "en", "",
                             extra={"country": r["country"], "published_estimated": True}) for r in rows]


def run(today=None):
    import sqlite3
    import trade_hs
    today = today or common.now_kst().date()
    c = cfg()
    errors = []
    db = trade_hs.connect()
    key = common.load_env().get("CENSUS_API_KEY")
    got = census_mirror(c, db, key, today, errors) if key else 0
    if not key:
        errors.append("CENSUS_API_KEY 없음 — 거울 수입 건너뜀")
    hist_p = common.ROOT / "knowledge" / "models" / "trade_ppi" / "history.json"
    hist = json.loads(hist_p.read_text(encoding="utf-8")) if hist_p.exists() else {}
    sig = signals(c, db, hist)
    seen = common.load_state("overseas_sites", {})
    first = seen.setdefault("_signals", {})   # 신호(나라·품목·마지막 달)를 처음 본 날 — 월간 통계라 기사 소재 후보에는 새 달이 나온 날만 올린다
    for x in sig:
        k = f"{x['country']}:{x['hs']}:{x['last']}"
        first.setdefault(k, today.isoformat())
        x["first_seen"] = first[k]
    gov = gov_pages(c, seen, errors)
    common.save_state("overseas_sites", seen)
    new = common.save_new_items(to_items(gov))
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({"as_of": today.isoformat(), "signals": sig, "gov": gov, "errors": errors}, ensure_ascii=False, indent=1), encoding="utf-8")
    return f"거울 {got}행 · 신호 {len(sig)} · 정부 새 항목 {len(gov)}(inbox {new})" + (f" · 오류 {len(errors)}" if errors else "")


def main(argv):
    sys.stdout.reconfigure(encoding="utf-8")
    if "--status" in argv:
        d = json.loads(OUT.read_text(encoding="utf-8")) if OUT.exists() else {}
        for s in d.get("signals") or []:
            print(f"{s['flow']} HS{s['hs']} {s['yoy_3m']:+.0%} (${s['usd_3m'] / 1e6:,.0f}M, ~{s['last']}) — {', '.join(s['companies'])} {', '.join(s['places'])} {'; '.join(s['ppi'])}")
        print(f"정부 새 항목 {len(d.get('gov') or [])} · 오류 {d.get('errors')}")
        return 0
    print(run())
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
