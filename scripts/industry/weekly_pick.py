"""Chiip Industry Weekly 산업 선정 (마스터 지시 2026-11-08 — 매주 일요일 08:00, 월스트리트 시니어 애널리스트식 시의성 선정)

설계는 config/industry_weekly.yaml 맨 위. 결정론 축(①촉매·③뉴스 가속·④1차 사건·⑤알파 밀도·감점·가산)은 저장소 자료로 계산하고,
②가격 신호·⑥논쟁도는 모델이 TradingView·Fiscal로 받아 --put으로 넣는다(없으면 중립 5점).
사용:
  py scripts/industry/weekly_pick.py --plan            # 산업별 구성 종목·가격 바스켓(TradingView 심볼) — 모델이 2주 수익률을 받는다
  py scripts/industry/weekly_pick.py --put <json>      # {"price": {산업: 2주 초과수익(소수)}, "debate": {산업: 0~10}}
  py scripts/industry/weekly_pick.py --rank            # 점수표(상위 3 근거)
  py scripts/industry/weekly_pick.py --choose <산업> [--why "<1위가 아닐 때 이유>"]   # picks.csv에 기록
"""
import argparse
import csv
import json
import math
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
CFG = ROOT / "config" / "industry_weekly.yaml"
OUT = ROOT / "knowledge" / "models" / "industries" / "weekly"
INPUTS = OUT / "inputs.json"
PICKS = OUT / "picks.csv"
STATE = ROOT / "radar" / "state"


TAX = ROOT / "config" / "industry_taxonomy.yaml"


def cfg():
    """industries = 시장 세부 산업(GICS) 묶음 — config/industry_taxonomy.yaml, 마스터 지시 2026-11-08. 옛 분야 모듈 11개는 themes로 남아 큰 세부 산업을 나누는 데 쓴다."""
    c = yaml.safe_load(CFG.read_text(encoding="utf-8"))
    c["themes"] = c.pop("industries")
    c["industries"], c["_members"] = groups(c)
    return c


def slug(s):
    return "".join(ch if ch.isalnum() else "-" for ch in s.lower()).strip("-").replace("--", "-").replace("--", "-")


def classify(tax=None):
    """{유니버스 종목 id: 세부 산업} — 거래소 접미사가 붙은 항목(RR.LSE)은 정확히, 나머지는 접미사를 뗀 티커로 맞춘다"""
    tax = tax or yaml.safe_load(TAX.read_text(encoding="utf-8"))
    exact, base = {}, {}
    for sub, src in (tax.get("members") or {}).items():
        for kind in ("fiscal", "assigned"):
            for t in src.get(kind) or []:
                (exact if "." in str(t) else base)[str(t).upper()] = (sub, kind)
    out = {}
    for m in universe():
        tk = str(m["ticker"] or "").upper()
        hit = exact.get(tk) or (None if any(k.split(".")[0] == tk.split(".")[0] for k in exact) and tk not in exact else base.get(tk.split(".")[0]))
        if hit:
            out[m["id"]] = {**m, "sub": hit[0], "source": hit[1]}
    return out


def groups(c, tax=None):
    """세부 산업 → 산업 묶음. min_members 미만은 상위 '산업'으로, 그래도 미만이면 뺀다. split_over를 넘으면 테마로 한 번 더 나눈다."""
    tax = tax or yaml.safe_load(TAX.read_text(encoding="utf-8"))
    meta, etf, n = tax["sub"], tax.get("etf") or {}, c["min_members"]
    cls = classify(tax)
    by = {}
    for m in cls.values():
        by.setdefault(m["sub"], []).append(m)
    theme_of = {}
    for t, ms in theme_members(c).items():
        for m in ms:
            theme_of.setdefault(m["id"], t)
    inds, mem, up = {}, {}, {}
    def put(gid, name, ms, info):
        inds[gid] = {"name": name, "etf": etf.get(info[2]) or etf.get(info[3]) or "AMEX:SPY", "sub": info[0], "industry": info[1], "sector": info[3]}
        mem[gid] = ms
    for sub, ms in sorted(by.items(), key=lambda x: -len(x[1])):
        ko, ind, grp, sec = meta[sub]
        if len(ms) < n:
            up.setdefault(ind, {"ms": [], "info": (sub, ind, grp, sec)})["ms"] += ms
            continue
        split = {}
        for m in ms:
            split.setdefault(theme_of.get(m["id"]), []).append(m)
        kids = {t: tm for t, tm in split.items() if t and len(tm) >= n}
        if len(ms) <= tax.get("split_over", 15) or len(kids) < 2:   # 테마 둘 이상으로 갈릴 때만 나눈다
            put(slug(sub), ko, ms, (sub, ind, grp, sec))
            continue
        rest = [m for t, tm in split.items() if t not in kids for m in tm]
        for t, tm in kids.items():
            put(f"{slug(sub)}.{t}", f"{ko} — {c['themes'][t]['name']}", tm, (sub, ind, grp, sec))
        if len(rest) >= n:
            put(slug(sub), f"{ko} — 기타", rest, (sub, ind, grp, sec))
        else:   # 남은 종목이 대표성 미달이면 가장 큰 테마 묶음에 붙인다(빠뜨리지 않는다)
            mem[f"{slug(sub)}.{max(kids, key=lambda t: len(kids[t]))}"] += rest
    for ind, v in up.items():
        same = [g for g, i in inds.items() if i["industry"] == ind]
        if len(v["ms"]) >= n:
            subs = sorted({m["sub"] for m in v["ms"]})
            put(slug(ind), " · ".join(meta[s][0] for s in subs), v["ms"], (" / ".join(subs),) + v["info"][1:])
        elif same:   # 같은 '산업'의 묶음이 있으면 거기에 붙인다(재생에너지 → IPP, 건설기계 → 산업 기계)
            g = max(same, key=lambda x: len(mem[x]))
            mem[g] += v["ms"]
            inds[g]["sub"] += " / " + v["info"][0]
    return inds, mem


def universe():
    """감시 목록 + 알파 유니버스 + 실적 감시 추가 종목 [{id, name, ticker, korea}]"""
    seen, out = set(), []
    with (ROOT / "config" / "watchlist.csv").open(encoding="utf-8", newline="") as f:
        for r in csv.DictReader(f):
            if r["entity_id"] not in seen:
                seen.add(r["entity_id"])
                out.append({"id": r["entity_id"], "name": r["name"], "ticker": r.get("ticker"), "korea": _kr(r.get("ticker"))})
    for f, key in (("valuation.yaml", "universe"), ("earnings_watch.yaml", "extra")):
        for u in (yaml.safe_load((ROOT / "config" / f).read_text(encoding="utf-8")) or {}).get(key) or []:
            if u["id"] not in seen:
                seen.add(u["id"])
                tk = u.get("code") or u.get("jp_code") or u.get("ticker")
                out.append({"id": u["id"], "name": u.get("name"), "ticker": tk, "korea": u.get("region") == "KR" or _kr(tk)})
    return out


def _kr(tk):
    t = str(tk or "").split(".")[0]
    return t.isdigit() and len(t) == 6


def members(c=None):
    """{산업(시장 세부 산업 묶음): [{id, name, ticker, korea, sub, source}]}"""
    return (c or cfg())["_members"]


def theme_members(c):
    """{테마(옛 분야 모듈): [{id, name, ticker}]} — config/watchlist.csv keywords_ref + 유니버스 sub 라벨"""
    out = {k: [] for k in c["themes"]}
    with (ROOT / "config" / "watchlist.csv").open(encoding="utf-8", newline="") as f:
        for r in csv.DictReader(f):
            for tag in (r.get("keywords_ref") or "").split(";"):
                if tag.strip() in out:
                    out[tag.strip()].append({"id": r["entity_id"], "name": r["name"], "ticker": r.get("ticker"), "korea": str(r.get("ticker") or "").isdigit() and len(str(r.get("ticker"))) == 6})
    seen = {m["id"] for v in out.values() for m in v}
    sm = c.get("sub_map") or {}
    for f, key in (("valuation.yaml", "universe"), ("earnings_watch.yaml", "extra")):   # 알파 유니버스 종목(sub 라벨)도 구성에
        for u in (yaml.safe_load((ROOT / "config" / f).read_text(encoding="utf-8")) or {}).get(key) or []:
            k = sm.get(u.get("sub"))
            if k in out and u["id"] not in seen:
                tk = u.get("code") or u.get("jp_code") or u.get("ticker")
                out[k].append({"id": u["id"], "name": u.get("name"), "ticker": tk, "korea": (u.get("region") == "KR") or (str(tk or "").isdigit() and len(str(tk)) == 6)})
                seen.add(u["id"])
    return out


def _json(p, default):
    try:
        return json.loads(Path(p).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def news_accel(ids, today, c):
    """7일 언급 수 ÷ 직전 4주 주평균 → 0~10(1배 = 5)"""
    days = (_json(STATE / "mentions.json", {}).get("days") or {})
    def tot(a, b):
        return sum(days.get((today - timedelta(days=i)).strftime("%Y%m%d"), {}).get(e, 0) for i in range(a, b) for e in ids)
    n = c["news_days"]
    prior = [i for i in range(n, n * 5) if (today - timedelta(days=i)).strftime("%Y%m%d") in days]   # 기록이 있는 날만(수집 시작 직후 과대 방지)
    now = tot(0, n)
    base = (sum(days.get((today - timedelta(days=i)).strftime("%Y%m%d"), {}).get(e, 0) for i in prior for e in ids) / len(prior) * n) if len(prior) >= 3 else 0
    if not base:
        return (7.0 if now else 5.0), now, base
    r = now / base
    return max(0.0, min(10.0, 5 + 2.5 * math.log2(max(r, 1e-3)))), now, round(base, 1)


def events(ids, today, c):
    """7일 P0·P1 알림 수 → 0~10"""
    since = (today - timedelta(days=c["news_days"])).isoformat()
    n = 0
    for a in (_json(STATE / "alerts.json", {}) or {}).values():
        if a.get("level") in ("P0", "P1") and str(a.get("sent_at") or "")[:10] >= since and set(a.get("entities") or []) & set(ids):
            n += 1
    return min(10.0, 2.0 * n), n


def catalysts(ids, today, c):
    """다음 14일 calendar.csv 일정 → 0~10"""
    end = (today + timedelta(days=c["catalyst_days"])).isoformat()
    n = 0
    p = ROOT / "knowledge" / "calendar.csv"
    if p.exists():
        with p.open(encoding="utf-8", newline="") as f:
            for r in csv.DictReader(f):
                if r.get("entity_or_event") in ids and today.isoformat() <= (r.get("date") or "") <= end:
                    n += 1
    return min(10.0, 2.5 * n), n


def alpha_density(ids):
    rows = (_json(ROOT / "knowledge" / "models" / "alpha" / "latest.json", {}).get("rows") or {})
    hit = [i for i in ids if (rows.get(i) or {}).get("total") is not None and rows[i]["total"] >= 5.0]
    return min(10.0, 10 * len(hit) / max(len(ids), 1)), len(hit)


def recent(today, c):
    if not PICKS.exists():
        return set()
    lim = (today - timedelta(weeks=c["recency_weeks"])).isoformat()
    with PICKS.open(encoding="utf-8", newline="") as f:
        return {r["industry"] for r in csv.DictReader(f) if r["date"] >= lim}


def rank(today=None, c=None):
    c = c or cfg()
    today = today or date.today()
    inp = _json(INPUTS, {})
    price, debate = inp.get("price") or {}, inp.get("debate") or {}
    w = c["weights"]
    mem = members(c)
    done = recent(today, c)
    out = []
    for k, meta in c["industries"].items():
        ms = mem.get(k) or []
        ids = [m["id"] for m in ms]
        cat, n_cat = catalysts(ids, today, c)
        nws, n_now, n_base = news_accel(ids, today, c)
        ev, n_ev = events(ids, today, c)
        al, n_al = alpha_density(ids)
        pr = 5.0 if k not in price else max(0.0, min(10.0, abs(float(price[k])) * 100 / 2))   # 2주 초과수익 ±10%p = 5점 가산
        db = 5.0 if k not in debate else max(0.0, min(10.0, float(debate[k])))
        s = w["catalyst"] * cat + w["price"] * pr + w["news"] * nws + w["events"] * ev + w["alpha"] * al + w["debate"] * db
        notes = []
        if any(m["korea"] for m in ms):
            s += c["korea_edge_bonus"]
            notes.append("한국 공급망")
        if k in done:
            s -= c["recency_penalty"]
            notes.append(f"최근 {c['recency_weeks']}주 안에 씀")
        if len(ms) < c["min_members"]:
            s -= 2
            notes.append(f"구성 {len(ms)}종목")
        out.append({"industry": k, "name": meta["name"], "score": round(s, 2), "members": len(ms),
                    "parts": {"촉매": [round(cat, 1), n_cat], "가격": [round(pr, 1), price.get(k)], "뉴스 가속": [round(nws, 1), f"{n_now}/{n_base}"],
                              "1차 사건": [round(ev, 1), n_ev], "알파": [round(al, 1), n_al], "논쟁": [round(db, 1), debate.get(k)]}, "notes": notes})
    return sorted(out, key=lambda x: -x["score"])


def choose(industry, why="", today=None):
    today = today or date.today()
    r = rank(today)
    top = [x["industry"] for x in r[:3]]
    if industry not in top:
        raise SystemExit(f"상위 3({', '.join(top)}) 밖은 고를 수 없다 — 점수 체계를 고치거나 입력을 다시 넣는다")
    if industry != top[0] and not why:
        raise SystemExit("1위가 아닌 산업을 고르면 --why로 이유를 적는다")
    OUT.mkdir(parents=True, exist_ok=True)
    new = not PICKS.exists()
    with PICKS.open("a", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        if new:
            w.writerow(["date", "industry", "score", "rank", "top3", "why"])
        x = next(i for i in r if i["industry"] == industry)
        w.writerow([today.isoformat(), industry, x["score"], top.index(industry) + 1, "|".join(top), why or "점수 1위"])
    return x


def main(argv):
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("--plan", action="store_true")
    ap.add_argument("--put")
    ap.add_argument("--rank", action="store_true")
    ap.add_argument("--choose")
    ap.add_argument("--why", default="")
    a = ap.parse_args(argv)
    c = cfg()
    if a.plan:
        mem = members(c)
        for k, meta in c["industries"].items():
            print(json.dumps({"industry": k, "name": meta["name"], "benchmark": "AMEX:SPY", "etf": meta.get("etf"),
                              "members": [m["ticker"] for m in mem.get(k) or []][:12]}, ensure_ascii=False))
        return 0
    if a.put:
        OUT.mkdir(parents=True, exist_ok=True)
        d = json.loads(Path(a.put).read_text(encoding="utf-8"))
        d["at"] = datetime.now().isoformat(timespec="minutes")
        INPUTS.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
        print("[선정 입력] 저장")
        return 0
    if a.choose:
        print(json.dumps(choose(a.choose, a.why), ensure_ascii=False))
        return 0
    for i, x in enumerate(rank(), 1):
        print(f"{i:2d}. {x['name']:<22} {x['score']:5.2f}  " + " · ".join(f"{k} {v[0]}({v[1]})" for k, v in x["parts"].items()) + (f"  [{', '.join(x['notes'])}]" if x["notes"] else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
