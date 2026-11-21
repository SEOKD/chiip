"""발굴 단서 장부 — 모든 발굴 채널의 단서를 한 장부에 쌓고, 선별·Pulse·성적표가 같은 장부를 본다
(마스터 지시 2026-11-15 "AI 밸류체인에 국한하지 말고 산업·섹터 전반에서 알파가 높은 종목을 찾는 프로세스 … 다양한 종목 발굴 채널",
설계 knowledge/methods/discovery_engine.md, 채널 등록부 config/discovery_channels.yaml).

왜: 채널마다 결과 파일이 따로라 ① 같은 종목에 여러 채널 신호가 겹쳐도 몰랐고 ② 채널별 적중률을 잴 수 없었다(성적표·피팅 재료 없음).
장부(덧붙이기만 — 사후 수정 금지, 상태 변화는 새 행):
  knowledge/models/discovery/leads.csv         lead_id,date,channel,kind,market,ticker,tv,name,signal,strength,url,price,ccy,mcap_usd,extra
  knowledge/models/discovery/leads_events.csv  date,lead_id,event,note        (선별·카드·기각 등 상태 변화)
  knowledge/models/discovery/lead_prices.csv   date,tv,close,source           (성적표용 시세 — 모델이 TradingView로 받아 --put-prices)
흐름: 수집기(결정론)·스크린(모델 TradingView → 각 스크립트 --put)이 add()로 단서를 넣는다 → scripts/discovery/channels.py가 겹침·관문으로
      선별하고 screen.py에 합류 → Pulse는 channels.py 경보만 → 주 1회 --price-specs → 모델 get-symbol-data-batch → --put-prices → --scorecard.
단서는 주장(claim)이 아니다. 채널 신호 → 경쟁우위·매출이 아니다(금지표). 성적표는 채널을 고르는 재료이지 종목 추천이 아니다.
사용: py scripts/discovery/leads.py --status | --recent [일수] | --price-specs [n] | --put-prices <파일> | --scorecard | --event <lead_id> <event> [메모]
      (event 'void' = 무효 — 장부에서 지우지 않고 선별·성적표·경보에서 뺀다)
"""
import csv
import hashlib
import json
import os
import statistics
import sys
import time
from contextlib import contextmanager
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
DISC = ROOT / "knowledge" / "models" / "discovery"
LEADS = DISC / "leads.csv"
EVENTS = DISC / "leads_events.csv"
PRICES = DISC / "lead_prices.csv"
SCORECARD = DISC / "channel_scorecard.json"
CFG = ROOT / "config" / "discovery_channels.yaml"
OUTD = ROOT / "outputs" / "discovery"
KST = timezone(timedelta(hours=9))
FIELDS = ["lead_id", "date", "channel", "kind", "market", "ticker", "tv", "name", "signal", "strength", "url", "price", "ccy", "mcap_usd", "extra"]
EV_FIELDS = ["date", "lead_id", "event", "note"]
PX_FIELDS = ["date", "tv", "close", "source"]
REGIONS = ("us", "jp", "kr", "tw", "hk", "uk", "eu")
HORIZONS = (30, 91, 182, 365, 730, 1095)   # 달력 일 — 성적표 평가 시점(주 1회 시세라 ±7일 오차). 730·1095 = 텐배거는 3~5년 복리라 긴 기간도 잰다(2026-11-21)
TAIL_X = 1.0                    # 오른쪽 꼬리 — 수익률 +100%(2배) 이상 비율. 멱법칙 채널은 중앙값이 아니라 평균과 꼬리로 본다(Bessembinder 2018·2024)
PX_TOL = 10                     # 평가 시점 뒤 이 일수 안의 첫 시세를 쓴다(없으면 그 시점은 아직 '미측정')
STALE_D = 3                     # 공개일이 탐지일보다 이만큼 넘게 앞서면 탐지일을 성적표 기준일로(extra.detected)
MIN_N = 30                      # 채널별 결과 30건 전에는 다시 맞추지 않는다(등록부 prm-dch-min-n, 조사 A — Beta 축소·30건 뒤 재피팅)
BETA_PRIOR = 10                 # 적중률 Beta(10,10) 축소 — 표본이 적을 때 50% 쪽으로(prm-dch-beta-prior)


def cfg():
    return yaml.safe_load(CFG.read_text(encoding="utf-8")) if CFG.exists() else {"channels": {}}


def today_kst():
    return datetime.now(KST).date()


@contextmanager
def _lock(path, wait=30.0):
    """여러 프로세스(run_hourly 수집기·예약 작업 모델)가 같은 장부에 덧붙일 때 줄이 섞이지 않게 — 120초 지난 잠금은 버려진 것으로 본다"""
    lk = Path(str(path) + ".lock")
    t0 = time.time()
    while True:
        try:
            fd = os.open(str(lk), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.close(fd)
            break
        except FileExistsError:
            try:
                if time.time() - lk.stat().st_mtime > 120:
                    lk.unlink()
                    continue
            except OSError:
                pass
            if time.time() - t0 > wait:
                raise TimeoutError(f"잠금 대기 초과: {lk.name}")
            time.sleep(0.2)
    try:
        yield
    finally:
        try:
            lk.unlink()
        except OSError:
            pass


def read(path=None):
    path = path or LEADS   # 기본값을 호출 때 읽는다(시험이 LEADS를 바꿔도 따라가게)
    if not Path(path).exists():
        return []
    with Path(path).open(encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def _append(path, fields, rows):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with _lock(path):
        new = not path.exists() or path.stat().st_size == 0
        with path.open("a", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
            if new:
                w.writeheader()
            w.writerows(rows)


def key(r):
    who = (r.get("ticker") or r.get("name") or "").strip().upper()
    return f"{r['channel']}|{r['kind']}|{r['market']}|{who}"


def _num(v):
    try:
        return None if v in (None, "") else float(v)
    except (TypeError, ValueError):
        return None


def add(rows, today=None):
    """새 단서만 넣는다. 같은 채널·종류·시장·종목이 dedupe_days(채널 설정, 기본 30일) 안에 있으면 건너뛴다.
    행: {channel, kind, market, ticker|name, signal, strength(0~10), [date, tv, url, price, ccy, mcap_usd, extra]} → 돌려주는 값 = 새로 넣은 행"""
    chans = cfg().get("channels") or {}
    today = today or today_kst()
    have = {}
    for r in active():   # 무효(void) 단서는 같은 키의 바로잡은 단서를 막지 않는다
        have.setdefault(key(r), []).append(r["date"])
    out = []
    for r in rows:
        ch = chans.get(r.get("channel"))
        if not ch:
            raise ValueError(f"등록부(config/discovery_channels.yaml)에 없는 채널: {r.get('channel')}")
        if r.get("kind") not in (ch.get("kinds") or {}):
            raise ValueError(f"채널 {r['channel']}에 없는 종류: {r.get('kind')}")
        if r.get("market") not in REGIONS:
            raise ValueError(f"시장 코드는 {REGIONS} 중 하나: {r.get('market')}")
        if not (r.get("ticker") or r.get("name")):
            raise ValueError("ticker나 name이 있어야 한다")
        s = _num(r.get("strength"))
        if s is None or not 0 <= s <= 10:
            raise ValueError(f"strength는 0~10: {r.get('strength')}")
        d = str(r.get("date") or today)
        k = key(r)
        dd = int(ch.get("dedupe_days", 30))
        if any(0 <= (date.fromisoformat(d) - date.fromisoformat(x)).days < dd for x in have.get(k, [])):
            continue
        row = {f: "" for f in FIELDS}
        row.update({f: r.get(f, "") if r.get(f) is not None else "" for f in FIELDS if f not in ("extra", "strength")})
        ex = dict(r.get("extra") or {})
        if (today - date.fromisoformat(d)).days > STALE_D:   # 공개는 오래전(예: 지난 분기 13F)인데 지금 찾았다 — 성적표는 탐지일 시세부터 잰다
            ex.setdefault("detected", today.isoformat())
        r = {**r, "extra": ex}
        row.update({"date": d, "strength": f"{s:.1f}", "lead_id": "L-" + d.replace("-", "") + "-" + hashlib.sha1(f"{k}|{d}".encode()).hexdigest()[:8],
                    "extra": json.dumps(r.get("extra") or {}, ensure_ascii=False, separators=(",", ":"))})
        out.append(row)
        have.setdefault(k, []).append(d)
    if out:
        _append(LEADS, FIELDS, out)
    return out


def event(lead_id, ev, note="", today=None):
    _append(EVENTS, EV_FIELDS, [{"date": str(today or today_kst()), "lead_id": lead_id, "event": ev, "note": note}])


def voided():
    """무효 처리된 단서 — 덧붙이기 장부라 지우지 않고 'void' 사건을 남긴다(개발 중 산출물·잘못 만든 단서)"""
    return {e["lead_id"] for e in read(EVENTS) if e.get("event") == "void"}


def active():
    v = voided()
    return [r for r in read() if r["lead_id"] not in v]


def recent(days=30, channels=None, today=None):
    today = today or today_kst()
    lo = (today - timedelta(days=days)).isoformat()
    return [r for r in active() if r["date"] >= lo and (not channels or r["channel"] in channels)]


def extra(r):
    try:
        return json.loads(r.get("extra") or "{}")
    except ValueError:
        return {}


# ---------- 성적표 ----------
def bench_of(r, c=None):
    """단서의 비교 지수 — 시장별, 미국 $10B 미만은 러셀 2000(IWM), 한국 코스닥 종목은 코스닥(설정 benchmarks)"""
    b = (c or cfg()).get("benchmarks") or {}
    m = r["market"]
    mc = _num(r.get("mcap_usd"))
    if m == "us" and mc is not None and mc < 10e9 and b.get("us_small"):
        return b["us_small"]
    if m == "kr" and (extra(r).get("board") or "").upper() == "KOSDAQ" and b.get("kr_kosdaq"):
        return b["kr_kosdaq"]
    return b.get(m)


def prices():
    """{tv: [(date, close)]} 날짜순"""
    out = {}
    for r in read(PRICES):
        v = _num(r.get("close"))
        if v and v > 0:
            out.setdefault(r["tv"], []).append((r["date"], v))
    for v in out.values():
        v.sort()
    return out


def _px_on(series, d, tol=PX_TOL):
    """d 당일 또는 뒤 tol일 안의 첫 시세(없으면 None)"""
    hi = (date.fromisoformat(d) + timedelta(days=tol)).isoformat()
    for dt, v in series or []:
        if d <= dt <= hi:
            return v
    return None


_DETECTED = {}


def detected_events():
    """{lead_id: 탐지일} — 'detected' 사건(이 칸이 생기기 전에 들어간 단서의 탐지일을 장부를 고치지 않고 덧붙인다)"""
    _DETECTED.clear()
    _DETECTED.update({e["lead_id"]: e["note"] for e in read(EVENTS) if e.get("event") == "detected" and e.get("note")})
    return _DETECTED


def base_date(r):
    """성적표 기준일 — 공개일이 오래된 단서는 탐지일(extra.detected 또는 'detected' 사건)"""
    return extra(r).get("detected") or _DETECTED.get(r.get("lead_id")) or r["date"]


def entry_price(r, px):
    p = _num(r.get("price"))
    if p and p > 0:
        return p
    return _px_on(px.get(r.get("tv")), base_date(r))


def price_specs(n=50, today=None):
    """시세가 필요한 TradingView 기호 — ① 진입가 없는 단서 ② 평가 시점(30·91·182·365일)이 지났는데 그 시세가 없는 단서 ③ 그 비교 지수. 우선순위 순 n개"""
    today = today or today_kst()
    c, px = cfg(), prices()
    detected_events()
    need, bench = [], set()
    for r in active():
        tv = r.get("tv")
        if not tv:
            continue
        d0 = date.fromisoformat(base_date(r))
        if entry_price(r, px) is None and (today - d0).days <= PX_TOL:
            need.append((0, tv))
            bench.add(bench_of(r, c))
            continue
        for h in HORIZONS:
            t = d0 + timedelta(days=h)
            if t <= today <= t + timedelta(days=PX_TOL) and _px_on(px.get(tv), t.isoformat()) is None:
                need.append((1, tv))
                bench.add(bench_of(r, c))
    seen, out = set(), []
    for b in sorted(x for x in bench if x):
        if b not in seen:
            seen.add(b)
            out.append(b)
    for _, tv in sorted(need):
        if tv not in seen:
            seen.add(tv)
            out.append(tv)
    return out[:n]


def put_prices(path, today=None, source="TradingView get-symbol-data-batch"):
    """get-symbol-data-batch 응답(JSON: {"data": {sym: {close,…}}} 또는 그 data) → lead_prices.csv. 같은 날 같은 기호는 한 번만"""
    today = str(today or today_kst())
    d = json.loads(Path(path).read_text(encoding="utf-8"))
    data = d.get("data", d) if isinstance(d, dict) else {}
    if isinstance(data, dict) and "data" in data and isinstance(data["data"], dict):
        data = data["data"]
    have = {(r["date"], r["tv"]) for r in read(PRICES)}
    rows = []
    for sym, v in (data or {}).items():
        cl = _num((v or {}).get("close")) if isinstance(v, dict) else None
        if cl and cl > 0 and (today, sym) not in have:
            rows.append({"date": today, "tv": sym, "close": f"{cl:.6g}", "source": source})
    if rows:
        _append(PRICES, PX_FIELDS, rows)
    return len(rows)


def forward(r, px, c=None):
    """{h: {"ret", "bench", "excess"}} — 진입가·평가 시세·지수가 모두 있는 시점만"""
    p0 = entry_price(r, px)
    b = bench_of(r, c)
    if not p0 or not b:
        return {}
    b0 = _px_on(px.get(b), base_date(r))
    out = {}
    d0 = date.fromisoformat(base_date(r))
    for h in HORIZONS:
        t = (d0 + timedelta(days=h)).isoformat()
        p1, b1 = _px_on(px.get(r.get("tv")), t), _px_on(px.get(b), t)
        if p1 and b0 and b1:
            ret, br = p1 / p0 - 1, b1 / b0 - 1
            out[h] = {"ret": ret, "bench": br, "excess": ret - br}
    return out


def tail(excess, rets):
    """오른쪽 꼬리 지표 — 90분위 초과, 2배 이상 비율, 상위 10%가 전체 양(+)의 초과에서 차지하는 몫"""
    if not excess:
        return {}
    xs = sorted(excess)
    p90 = xs[min(len(xs) - 1, int(0.9 * (len(xs) - 1) + 0.5))]
    pos = sum(x for x in xs if x > 0)
    k = max(1, round(len(xs) * 0.1))
    return {"p90_excess": round(p90, 4), "tail_2x": round(sum(1 for r in rets if r >= TAIL_X) / len(rets), 3) if rets else None,
            "top10_share": round(sum(x for x in xs[-k:] if x > 0) / pos, 3) if pos > 0 else None}


def scorecard(today=None, write=True):
    """채널·종류별 n·측정 수·적중률(시장 대비 초과 > 0)·초과수익 중앙값 — 사전값(prior.excess)과 나란히. 표본 30 미만은 '표본 부족'"""
    today = today or today_kst()
    c, px = cfg(), prices()
    detected_events()
    chans = c.get("channels") or {}
    agg = {}
    passed = {e["lead_id"] for e in read(EVENTS) if e.get("event") == "triage_pass"}
    for r in active():
        g = agg.setdefault(r["channel"], {"n": 0, "kinds": {}, "h": {h: [] for h in HORIZONS}, "r": {h: [] for h in HORIZONS},
                                          "pass": {h: [] for h in HORIZONS}, "reject": {h: [] for h in HORIZONS}})
        g["n"] += 1
        g["kinds"][r["kind"]] = g["kinds"].get(r["kind"], 0) + 1
        for h, v in forward(r, px, c).items():
            g["h"][h].append(v["excess"])
            g["r"][h].append(v["ret"])
            g["pass" if r["lead_id"] in passed else "reject"][h].append(v["excess"])
    out = {"as_of": today.isoformat(), "min_n": MIN_N, "beta_prior": BETA_PRIOR, "channels": {}}
    for ch, g in sorted(agg.items()):
        pr = (chans.get(ch) or {}).get("prior") or {}
        row = {"name": (chans.get(ch) or {}).get("name", ch), "leads": g["n"], "kinds": g["kinds"], "prior": pr, "horizons": {}}
        for h, xs in g["h"].items():
            if xs:
                hits = sum(1 for x in xs if x > 0)
                row["horizons"][str(h)] = {"n": len(xs), "hit": round(hits / len(xs), 3), "hit_shrunk": round((hits + BETA_PRIOR) / (len(xs) + 2 * BETA_PRIOR), 3),
                                           "median_excess": round(statistics.median(xs), 4), "mean_excess": round(sum(xs) / len(xs), 4), "enough": len(xs) >= MIN_N,
                                           "pass_median": round(statistics.median(g["pass"][h]), 4) if g["pass"][h] else None, "pass_n": len(g["pass"][h]),
                                           "reject_median": round(statistics.median(g["reject"][h]), 4) if g["reject"][h] else None, "reject_n": len(g["reject"][h]),
                                           **tail(xs, g["r"][h])}
        out["channels"][ch] = row
    if write:
        SCORECARD.parent.mkdir(parents=True, exist_ok=True)
        SCORECARD.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
        OUTD.mkdir(parents=True, exist_ok=True)
        L = [f"# 발굴 채널 성적표 {today.isoformat()}", "",
             "시장 대비 초과수익(같은 시장 지수, 미국 $10B 미만은 러셀 2000) · 적중 = 초과 > 0 · 표본 30 미만은 판단에 쓰지 않는다.", "",
             "적중(축소) = Beta(10,10) — 표본이 적을수록 50%로 당긴다. 통과/기각 = 채널 선별을 통과한 단서와 못 한 단서의 91일 초과 중앙(기각의 후회 측정).", "",
             "| 채널 | 단서 | 91일 n | 91일 적중(축소) | 91일 초과 중앙 | 통과/기각 91일 | 365일 n | 365일 초과 중앙 | 사전값(초과·기간) |", "|---|---|---|---|---|---|---|---|---|"]
        for ch, row in out["channels"].items():
            h3, h12 = row["horizons"].get("91") or {}, row["horizons"].get("365") or {}
            fm = lambda v, pct=True: "—" if v is None else (f"{v * 100:+.1f}%" if pct else f"{v:.0%}")
            pr = row["prior"]
            L.append(f"| {row['name']} | {row['leads']} | {h3.get('n', 0)} | {fm(h3.get('hit'), False)}({fm(h3.get('hit_shrunk'), False)}) | {fm(h3.get('median_excess'))} | "
                     f"{fm(h3.get('pass_median'))}/{fm(h3.get('reject_median'))} | {h12.get('n', 0)} | {fm(h12.get('median_excess'))} | {fm(pr.get('excess'))}·{pr.get('horizon_d', '—')}일 |")
        tl = []
        for ch, row in out["channels"].items():
            for hh in ("365", "730", "1095"):
                t = row["horizons"].get(hh) or {}
                if t.get("n"):
                    tl.append(f"- {row['name']} {hh}일(n={t['n']}): 평균 초과 {t['mean_excess'] * 100:+.1f}% vs 중앙 {t['median_excess'] * 100:+.1f}% · 2배 이상 {t['tail_2x'] * 100:.0f}% · "
                              f"상위 10%가 이익의 {t['top10_share'] * 100:.0f}%" if t.get("top10_share") is not None else
                              f"- {row['name']} {hh}일(n={t['n']}): 평균 초과 {t['mean_excess'] * 100:+.1f}% vs 중앙 {t['median_excess'] * 100:+.1f}% · 2배 이상 {t['tail_2x'] * 100:.0f}%")
        if tl:
            L += ["", "## 오른쪽 꼬리(1년 이상) — 텐배거형 채널은 중앙값이 아니라 평균과 꼬리로 본다", "대부분 종목은 지고 소수가 전체 이익을 만든다(Bessembinder 2018·2024). "
                  "중앙값이 음수여도 평균이 양수이고 2배 이상 비율이 사전 기저율(5년 3배 6.8%·10배 0.69%)을 넘으면 그 채널은 제 몫을 한다."] + tl
        L += ["", "성적표는 채널 가중을 고르는 재료이지 종목 추천이 아니다. 피팅은 표본 외 검정(scripts/fit/stepwise.py)을 통과할 때만."]
        (OUTD / f"scorecard_{today.strftime('%Y%m%d')}.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    return out


def status(today=None):
    today = today or today_kst()
    rs = active()
    by = {}
    for r in rs:
        by.setdefault(r["channel"], [0, 0])
        by[r["channel"]][0] += 1
        if r["date"] >= (today - timedelta(days=7)).isoformat():
            by[r["channel"]][1] += 1
    return {"leads": len(rs), "by_channel": {k: {"total": a, "last7": b} for k, (a, b) in sorted(by.items())}, "prices": len(read(PRICES))}


def main(argv):
    sys.stdout.reconfigure(encoding="utf-8")
    if not argv or argv[0] == "--status":
        print(json.dumps(status(), ensure_ascii=False, indent=1))
    elif argv[0] == "--recent":
        for r in recent(int(argv[1]) if len(argv) > 1 else 7):
            print(f"{r['date']} {r['channel']}/{r['kind']} {r['market']} {r['ticker'] or r['name']} {r['strength']} — {r['signal']}")
    elif argv[0] == "--price-specs":
        print(json.dumps(price_specs(int(argv[1]) if len(argv) > 1 else 50), ensure_ascii=False))
    elif argv[0] == "--put-prices":
        print(f"시세 {put_prices(argv[1])}건")
    elif argv[0] == "--scorecard":
        print(json.dumps(scorecard(), ensure_ascii=False, indent=1)[:4000])
    elif argv[0] == "--event" and len(argv) >= 3:
        event(argv[1], argv[2], " ".join(argv[3:]))
        print("기록")
    else:
        print(__doc__)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
