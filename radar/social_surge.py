"""커뮤니티 관심 급증 모델 (마스터 지시 2026-11-07 "Quantral로 Pulse에 X, 서브스택, 레딧, 유튜브, 의회 의원 매매, 내부자 매수가 급격히
늘어나는 종목을 관측 … 급격히 증가하는 정도는 고도화된 수학 모델로 체계적으로 설계 … 알파 점수에도 활용") — 설정 config/social_surge.yaml

수집은 모델이 Quantral MCP로 받아 파일로 넘기고(--due가 고른 종목만), 계산은 여기서 한다(결정론, 모델 없음).
저장은 집계만 — 종목·날짜·채널별 건수, 신뢰 가중 건수, 감성 합. 글 본문·작성자·링크는 버린다(CLAUDE.md 커뮤니티 경계, ADR-011).
중복은 링크 해시로 거르고 해시는 radar/state(git 제외)에만 둔다.

모델(채널 c, 종목 i):
  1. 신뢰 가중 건수  글 하나의 가중치 w = 작성자 적중률의 베타 사후평균 ÷ 사전평균 — 적중 기록이 적으면 1에 가깝다
  2. 기준 수준      최근 recent_days를 뺀 baseline_days의 일평균 μ, 분산으로 음이항 과산포 k(모멘트법, 하한 nb_k_floor).
                    일별 이력이 짧으면 월간 요약(recaps) 게시 수/30을 prior_days만큼의 가상 표본으로 섞는다(경험적 베이즈)
  3. 급증 Z         최근 창 합 R의 음이항 표준화 (R − mμ)/√(mμ + mμ²/k)
  4. 지속성         일별 표준화 잔차의 Page CUSUM S_t = max(0, S_{t−1} + z_t − k) — S ≥ h면 '지속 상승'
  5. 사건형 채널     내부자 매수·의회 매매: 최근 30일 건수 x, 기저율 λ(365일, 하한 event_floor_rate) → 포아송 P(X ≥ x) → z = Φ⁻¹(1 − p)
  6. 결합           스토퍼 Z = Σ wᶜ zᶜ / √Σ (wᶜ)² (자료가 있는 채널만)
  7. 급증 점수      10·(1 − e^(−max(0,Z)/scale))
  8. 알파 요소      attention = 5 + tilt·tanh(Z/3)·(0.5 + 0.5·s̄) − 과밀(Quantral 7일 점수 ≥ crowd_score이고 Z < 1) → 0~10
경보: Z ≥ alert.z_comb 이고 최근 신뢰 가중 건수 ≥ min_recent 이고 (CUSUM 경보 채널 ≥ 1), 또는 사건형 p ≤ event_p. 같은 종목은 cooldown_days.
급증은 관심의 변화이지 펀더멘털 변화가 아니다(금지표: 주가 급등 → 펀더멘털 변화). 커뮤니티 신호는 S1·S2 — 주장이 아니다.

사용: py radar/social_surge.py --due                 # 이번 회차에 Quantral로 받을 티커(없으면 '→ 종료')
      py radar/social_surge.py --put <파일>          # [{"ticker", "score": get_company_score 응답, "signals": get_company_signals 응답의 signals, "recaps": [...]}]
      py radar/social_surge.py --run                 # 계산 → knowledge/models/social/latest.json, 경보 줄 출력
      py radar/social_surge.py --show <id|티커>
"""
import csv
import hashlib
import json
import math
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
from pollers import common  # noqa: E402

ROOT = common.ROOT
CFG = ROOT / "config" / "social_surge.yaml"
DIR = ROOT / "knowledge" / "models" / "social"
DAILY = DIR / "daily.csv"
SCORES = DIR / "scores.csv"
RECAPS = DIR / "recaps.csv"
LATEST = DIR / "latest.json"
STATE = common.STATE / "social_surge.json"   # 본 링크 해시·조회 시각·경보 시각(git 제외)
KST = timezone(timedelta(hours=9))
DCOLS = ["date", "id", "ticker", "channel", "count", "wcount", "sent", "wsent"]
RCOLS = ["month", "id", "posts", "score", "partial"]


def cfg():
    return yaml.safe_load(CFG.read_text(encoding="utf-8"))


def jload(p, default):
    try:
        return json.loads(Path(p).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def universe():
    """[(id, 티커)] — 알파 5점 이상 + Portfolio(보유·관심). 알파 높은 순"""
    sys.path.insert(0, str(ROOT / "scripts" / "discovery"))
    import alpha_gate
    t = alpha_gate.table()
    ids = {}
    for tick, a in t.items():
        if a is not None and a >= alpha_gate.MIN and tick.isalpha():
            ids.setdefault(tick, a)
    try:
        for h in yaml.safe_load((ROOT / "config" / "portfolio.yaml").read_text(encoding="utf-8")).get("holdings") or []:
            if h.get("status") in ("보유", "관심") and str(h.get("ticker", "")).isalpha():
                ids.setdefault(str(h["ticker"]).upper(), 9.9)
    except (OSError, AttributeError):
        pass
    for t, pri in extra_tickers().items():   # Valuation Queue 대기열·최근 Analysis 종목(2026-11-14 마스터 지시 "비어 있는 곳도 메워", ADR-032)
        ids.setdefault(t, pri)
    tid = id_map()
    return [(tid.get(k, f"us-{k.lower()}"), k) for k, _ in sorted(ids.items(), key=lambda kv: -kv[1])]


def _ticker_of(eid, inv):
    if eid in inv:
        return inv[eid]
    try:
        t = json.loads((ROOT / "knowledge" / "models" / "companies" / eid / "datapack.json").read_text(encoding="utf-8")).get("ticker")
    except (OSError, ValueError):
        t = None
    if not t and eid.startswith("us-"):
        t = eid[3:]
    return str(t or "").upper()


def extra_tickers(days=14):
    """{티커: 우선순위} — 대기열 종목 9.8, 최근 days일 Analysis 리포트 종목 9.7. 미국 알파벳 티커만(Quantral 범위)"""
    inv = {}
    for t, i in id_map().items():
        inv.setdefault(i, t)
    out = {}
    try:
        for q in json.loads((common.STATE / "v2_queue.json").read_text(encoding="utf-8")) or []:
            t = _ticker_of(q.get("id", ""), inv)
            if t.isalpha():
                out.setdefault(t, 9.8)
    except (OSError, ValueError, AttributeError):
        pass
    cut = (datetime.now(KST) - timedelta(days=days)).strftime("%Y%m%d")
    for f in (ROOT / "outputs" / "tenbagger" / "reports").glob("2*_*.json"):
        if f.name[:8] >= cut:
            t = f.stem.split("_", 1)[1].upper()
            if t.isalpha():
                out.setdefault(t, 9.7)
    return out


def id_map():
    """{티커: 감시 id}"""
    out = {}
    f = ROOT / "config" / "tradingview_symbols.csv"
    if f.exists():
        with f.open(encoding="utf-8", newline="") as fh:
            out.update({r["ticker"].upper(): r["entity_id"] for r in csv.DictReader(fh) if r.get("entity_id") and r.get("ticker")})
    try:
        for h in yaml.safe_load((ROOT / "config" / "portfolio.yaml").read_text(encoding="utf-8")).get("holdings") or []:
            if h.get("ticker"):
                out[str(h["ticker"]).upper()] = h["id"]
    except (OSError, AttributeError):
        pass
    return out


def due(now=None, c=None):
    c = c or cfg()
    now = now or datetime.now(KST)
    st = jload(STATE, {})
    last = st.get("fetched", {})
    fresh = lambda t: t in last and (now - datetime.fromisoformat(last[t])).total_seconds() < c["fetch"]["refresh_hours"] * 3600
    todo = [t for _, t in universe() if not fresh(t)]
    todo.sort(key=lambda t: last.get(t, ""))   # 오래 안 본 것부터
    return todo[: c["fetch"]["per_run"]]


def status(now=None):
    """Pulse 관문(radar/pulse.py)이 부른다 — 받을 종목이 있고 직전 회차에서 min_gap_minutes가 지났을 때만 회차를 연다"""
    c = cfg()
    now = now or datetime.now(KST)
    st = jload(STATE, {})
    last = st.get("opened")
    if last and (now - datetime.fromisoformat(last)).total_seconds() < c["fetch"]["min_gap_minutes"] * 60:
        return {"due": False}
    t = due(now, c)
    return {"due": bool(t), "tickers": t}


def offered(now=None):
    st = jload(STATE, {})
    st["opened"] = (now or datetime.now(KST)).isoformat(timespec="minutes")
    STATE.parent.mkdir(parents=True, exist_ok=True)
    STATE.write_text(json.dumps(st, ensure_ascii=False), encoding="utf-8")


def _kst_day(iso):
    return datetime.fromisoformat(str(iso).replace("Z", "+00:00")).astimezone(KST).date().isoformat()


def _weight(sig, prior):
    n, h = sig.get("authorEvaluatedCalls"), sig.get("authorHitRate")
    if not n or h is None:
        return 1.0
    a, b = prior["a"], prior["b"]
    return ((h * n + a) / (n + a + b)) / (a / (a + b))


def _sent(sig):
    if sig.get("sentimentScore") is not None:
        return float(sig["sentimentScore"])
    xs = [x.get("sentimentScore") for x in sig.get("comments") or [] if x.get("sentimentScore") is not None]
    return sum(xs) / len(xs) if xs else 0.0


def _read(path, cols):
    if not path.exists():
        return []
    with path.open(encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def _write(path, cols, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, cols)
        w.writeheader()
        w.writerows(rows)


def put(raw, now=None, c=None):
    """Quantral 응답 묶음 → 집계 행. 본문·작성자·링크는 여기서 버린다"""
    c = c or cfg()
    now = now or datetime.now(KST)
    st = jload(STATE, {})
    seen = set(st.get("seen", []))
    tid = id_map()
    book = {(r["date"], r["id"], r["channel"]): r for r in _read(DAILY, DCOLS)}
    added = 0
    for item in raw:
        tick = str(item.get("ticker", "")).upper()
        if not tick:
            continue
        iid = tid.get(tick, f"us-{tick.lower()}")
        sigs = item.get("signals") or []
        for s in sigs:
            ch = c["channels"].get(str(s.get("sourceType", "")).lower())
            if not ch or not s.get("detectedAt"):
                continue
            key = hashlib.sha1(f"{tick}|{s.get('url') or ''}|{s.get('detectedAt')}".encode("utf-8")).hexdigest()[:16]
            if key in seen:
                continue
            seen.add(key)
            day, w, se = _kst_day(s["detectedAt"]), _weight(s, c["credibility_prior"]), _sent(s)
            r = book.setdefault((day, iid, ch), {"date": day, "id": iid, "ticker": tick, "channel": ch, "count": 0, "wcount": 0, "sent": 0, "wsent": 0})
            r["count"] = int(float(r["count"])) + 1
            r["wcount"] = round(float(r["wcount"]) + w, 3)
            r["sent"] = round(float(r["sent"]) + se, 3)
            r["wsent"] = round(float(r["wsent"]) + w * se, 3)
            added += 1
        st.setdefault("since", {}).setdefault(iid, min([_kst_day(s["detectedAt"]) for s in sigs if s.get("detectedAt")] or [now.date().isoformat()]))
        if len(sigs) >= 50:   # 50건 상한에 닿으면 가장 오래된 날은 잘렸을 수 있다 — 그날부터를 관측 시작으로 본다(검열)
            st["since"][iid] = max(st["since"][iid], _kst_day(min(s["detectedAt"] for s in sigs if s.get("detectedAt"))))
        sc = item.get("score") or {}
        if sc:
            rows = _read(SCORES, ["ts", "id", "ticker", "score24h", "score7d"])
            rows.append({"ts": now.isoformat(timespec="minutes"), "id": iid, "ticker": tick, "score24h": sc.get("score24h"), "score7d": sc.get("score7d")})
            _write(SCORES, ["ts", "id", "ticker", "score24h", "score7d"], rows[-20000:])
        if item.get("recaps"):
            rec = {(r["month"], r["id"]): r for r in _read(RECAPS, RCOLS)}
            for x in item["recaps"]:   # Quantral get_company_recaps: monthStart·postCount·score·isPartial
                m = str(x.get("monthStart") or x.get("month") or "")[:7]
                if m:
                    rec[(m, iid)] = {"month": m, "id": iid, "posts": x.get("postCount"), "score": x.get("score"), "partial": int(bool(x.get("isPartial")))}
            _write(RECAPS, RCOLS, sorted(rec.values(), key=lambda r: (r["id"], r["month"])))
        st.setdefault("fetched", {})[tick] = now.isoformat(timespec="minutes")
    _write(DAILY, DCOLS, sorted(book.values(), key=lambda r: (r["id"], r["date"], r["channel"])))
    st["seen"] = sorted(seen)[-50000:]
    STATE.parent.mkdir(parents=True, exist_ok=True)
    STATE.write_text(json.dumps(st, ensure_ascii=False), encoding="utf-8")
    return added


def strip(raw):
    """Quantral 응답 묶음에서 글 단위 필드는 sourceType·detectedAt만 — 작성자 통계·감성·링크·본문은 집계(put) 뒤 버린다(마스터 지시 2026-11-14, ADR-032)"""
    out = []
    for item in raw or []:
        sc = item.get("score") or {}
        out.append({"ticker": item.get("ticker"),
                    "score": {k: sc.get(k) for k in ("score24h", "score7d") if k in sc},
                    "signals": [{"sourceType": s.get("sourceType"), "detectedAt": s.get("detectedAt")} for s in item.get("signals") or []],
                    "recaps": [{k: x.get(k) for k in ("monthStart", "postCount", "score", "isPartial") if k in x} for x in item.get("recaps") or []]})
    return out


def nb_z(total, m, mu, k):
    """m일 합 total의 음이항 표준화"""
    mean = m * mu
    var = mean + m * mu * mu / k
    return (total - mean) / math.sqrt(var) if var > 0 else 0.0


def pois_sf(x, lam):
    """P(X ≥ x), X ~ Poisson(lam)"""
    if x <= 0:
        return 1.0
    term, cdf = math.exp(-lam), 0.0
    for i in range(int(x)):
        cdf += term
        term *= lam / (i + 1)
    return max(0.0, 1.0 - cdf)


def norm_ppf(p):
    """표준정규 분위수(Acklam 근사, 상대오차 < 1.2e-9)"""
    p = min(max(p, 1e-12), 1 - 1e-12)
    a = [-3.969683028665376e+01, 2.209460984245205e+02, -2.759285104469687e+02, 1.383577518672690e+02, -3.066479806614716e+01, 2.506628277459239e+00]
    b = [-5.447609879822406e+01, 1.615858368580409e+02, -1.556989798598866e+02, 6.680131188771201e+01, -1.328068155288572e+01]
    cc = [-7.784894002430293e-03, -3.223964580411365e-01, -2.400758277161838e+00, -2.549732539343734e+00, 4.374664141464968e+00, 2.938163982698783e+00]
    d = [7.784695709041462e-03, 3.224671290700398e-01, 2.445134137142996e+00, 3.754408661907416e+00]
    if p < 0.02425:
        q = math.sqrt(-2 * math.log(p))
        return (((((cc[0] * q + cc[1]) * q + cc[2]) * q + cc[3]) * q + cc[4]) * q + cc[5]) / ((((d[0] * q + d[1]) * q + d[2]) * q + d[3]) * q + 1)
    if p > 1 - 0.02425:
        return -norm_ppf(1 - p)
    q = p - 0.5
    r = q * q
    return (((((a[0] * r + a[1]) * r + a[2]) * r + a[3]) * r + a[4]) * r + a[5]) * q / (((((b[0] * r + b[1]) * r + b[2]) * r + b[3]) * r + b[4]) * r + 1)


def channel_stats(series, days, c, prior_rate=None):
    """series {날짜: (건수, 신뢰 가중)}, days = 관측 날짜 목록(오래된 → 최근). 반환 dict 또는 None"""
    m, B = c["recent_days"], c["baseline_days"]
    if len(days) < m + 3:
        return None
    base_days, rec_days = days[-(m + B):-m], days[-m:]
    vals = [series.get(d, (0, 0))[1] for d in base_days]
    n = len(vals)
    mean = sum(vals) / n if n else 0.0
    var = sum((v - mean) ** 2 for v in vals) / (n - 1) if n > 1 else mean
    if prior_rate is not None:
        kp = c["prior_days"]
        mean = (n * mean + kp * prior_rate) / (n + kp)
    mu = max(mean, 0.05)   # 0 기준선에서 첫 언급이 무한대 Z가 되지 않게
    k = max(c["nb_k_floor"], mu * mu / max(var - mu, 1e-6)) if var > mu else 1e6   # 과산포가 없으면 포아송
    R = sum(series.get(d, (0, 0))[1] for d in rec_days)
    z = nb_z(R, m, mu, k)
    S, alarm, sd = 0.0, False, math.sqrt(mu + mu * mu / k)
    for d in days[-(m + B):]:
        S = max(0.0, S + (series.get(d, (0, 0))[1] - mu) / sd - c["cusum"]["k"])
        alarm = alarm or (d in rec_days and S >= c["cusum"]["h"])
    return {"recent": round(R, 2), "recent_n": sum(series.get(d, (0, 0))[0] for d in rec_days), "base": round(mu, 3), "k": round(min(k, 999), 2),
            "z": round(z, 2), "cusum": round(S, 2), "alarm": alarm, "obs_days": len(days)}


def compute(c=None, today=None):
    c = c or cfg()
    today = today or datetime.now(KST).date()
    st = jload(STATE, {})
    rows = _read(DAILY, DCOLS)
    rec = {}
    for r in _read(RECAPS, RCOLS):
        if r.get("posts") not in (None, "", "None") and r.get("partial") not in ("1",):   # 진행 중인 달은 기준으로 쓰지 않는다
            rec.setdefault(r["id"], []).append((r["month"], float(r["posts"])))
    sc = {}
    for r in _read(SCORES, ["ts", "id", "ticker", "score24h", "score7d"]):
        sc[r["id"]] = r
    by = {}
    for r in rows:
        by.setdefault(r["id"], []).append(r)
    out = {}
    for iid, rs in by.items():
        since = st.get("since", {}).get(iid) or min(r["date"] for r in rs)
        d0 = datetime.fromisoformat(since).date()
        days = [(d0 + timedelta(days=i)).isoformat() for i in range((today - d0).days + 1)]
        tick = rs[-1]["ticker"]
        chans, zs = {}, []
        total = {}
        for r in rs:
            t = total.setdefault(r["date"], [0, 0])
            if r["channel"] in c["attention"]:
                t[0] += int(float(r["count"]))
                t[1] += float(r["wcount"])
        months = sorted(rec.get(iid, []))
        prior = months[-1][1] / 30 if months else None
        for ch in c["attention"]:
            s = {r["date"]: (int(float(r["count"])), float(r["wcount"])) for r in rs if r["channel"] == ch}
            if not s:
                continue
            x = channel_stats(s, days, c)
            if x:
                chans[ch] = x
                zs.append((c["weights"][ch], x["z"]))
        tot = channel_stats({d: tuple(v) for d, v in total.items()}, days, c, prior)
        for ch in c["events"]:
            ev = [r for r in rs if r["channel"] == ch]
            if not ev:
                continue
            last30 = sum(int(float(r["count"])) for r in ev if (today - datetime.fromisoformat(r["date"]).date()).days < 30)
            span = max(30, min(c["event_lookback_days"], (today - d0).days))
            before = sum(int(float(r["count"])) for r in ev if 30 <= (today - datetime.fromisoformat(r["date"]).date()).days < span)
            lam = max(c["event_floor_rate"], before / max(1, (span - 30) / 30)) if span > 30 else c["event_floor_rate"]
            p = pois_sf(last30, lam)
            z = norm_ppf(1 - p)
            chans[ch] = {"recent": last30, "base": round(lam, 2), "p": round(p, 4), "z": round(z, 2)}
            zs.append((c["weights"][ch], z))
        Z = sum(w * z for w, z in zs) / math.sqrt(sum(w * w for w, _ in zs)) if zs else None
        ws = [(float(r["wsent"]), float(r["wcount"]), r["date"]) for r in rs if r["channel"] in c["attention"]]
        cut7 = (today - timedelta(days=7)).isoformat()
        s7 = [x for x in ws if x[2] >= cut7]
        sbar = sum(a for a, _, _ in s7) / sum(b for _, b, _ in s7) if s7 and sum(b for _, b, _ in s7) else None
        sall = sum(a for a, _, _ in ws) / sum(b for _, b, _ in ws) if ws and sum(b for _, b, _ in ws) else None
        q = sc.get(iid, {})
        q7 = float(q["score7d"]) if q.get("score7d") not in (None, "", "None") else None
        score = round(10 * (1 - math.exp(-max(0.0, Z) / c["score"]["scale"])), 1) if Z is not None else None
        ev_hit = [ch for ch in c["events"] if chans.get(ch, {}).get("p", 1) <= c["alert"]["event_p"]]
        alert = bool(Z is not None and Z >= c["alert"]["z_comb"] and (tot or {}).get("recent", 0) >= c["alert"]["min_recent"]
                     and any(chans[ch].get("alarm") for ch in c["attention"] if ch in chans)) or bool(ev_hit)
        out[iid] = {"ticker": tick, "Z": None if Z is None else round(Z, 2), "score": score, "total": tot, "channels": chans,
                    "sent7": None if sbar is None else round(sbar, 2), "sent_all": None if sall is None else round(sall, 2),
                    "q24": q.get("score24h"), "q7": q7, "alert": alert, "events_hit": ev_hit, "since": since}
    return out


def attention(row, c=None):
    """알파 요소 attention(0~10) — scripts/alpha/score.py가 부른다. 자료가 없으면 None"""
    c = c or cfg()
    a = c["alpha"]
    if not row or row.get("Z") is None:
        return None
    s = row.get("sent7") if row.get("sent7") is not None else (row.get("sent_all") or 0.0)
    v = 5 + a["tilt"] * math.tanh(row["Z"] / 3) * (0.5 + 0.5 * max(-1.0, min(1.0, s)))
    if (row.get("q7") or 0) >= a["crowd_score"] and row["Z"] < 1:
        v -= a["crowd_penalty"]
    return round(max(0.0, min(10.0, v)), 2)


def why(r):
    ch = {"x": "X", "reddit": "레딧", "youtube": "유튜브", "substack": "서브스택", "insider": "내부자 매수", "congress": "의회 매매"}
    parts = []
    for k, x in sorted(r["channels"].items(), key=lambda kv: -kv[1].get("z", 0)):
        if "p" in x:
            parts.append(f"{ch[k]} 30일 {x['recent']}건(평소 {x['base']}건, p {x['p']:.3f})")
        elif x["z"] >= 1:
            parts.append(f"{ch[k]} 최근 3일 {x['recent_n']}건(평소 하루 {x['base']:.1f}, Z {x['z']:+.1f}{', 지속 상승' if x['alarm'] else ''})")
    return " · ".join(parts[:4])


def run(today=None):
    c = cfg()
    res = compute(c, today)
    now = datetime.now(KST)
    DIR.mkdir(parents=True, exist_ok=True)
    LATEST.write_text(json.dumps({"as_of": now.isoformat(timespec="minutes"), "rows": {k: {**v, "attention": attention(v, c)} for k, v in res.items()}},
                                 ensure_ascii=False, indent=1), encoding="utf-8")
    st = jload(STATE, {})
    sent = st.setdefault("alerted", {})
    lines = []
    for iid, r in sorted(res.items(), key=lambda kv: -(kv[1]["Z"] or 0)):
        last = sent.get(iid)
        if not r["alert"] or (last and (now - datetime.fromisoformat(last)).days < c["alert"]["cooldown_days"]):
            continue
        sent[iid] = now.isoformat(timespec="minutes")
        tone = "" if r["sent7"] is None else f" · 감성 {r['sent7']:+.2f}(전체 {r['sent_all']:+.2f})"
        lines.append(f"{r['ticker']} 관심 급증 {r['score']}/10(Z {r['Z']:+.1f}){tone} — {why(r)}")
    STATE.write_text(json.dumps(st, ensure_ascii=False), encoding="utf-8")
    return lines


def main(argv):
    sys.stdout.reconfigure(encoding="utf-8")
    if argv[:1] == ["--due"]:
        t = due()
        print(json.dumps(t) if t else "→ 종료")
    elif argv[:1] == ["--put"]:
        src = Path(argv[1])
        raw = json.loads(src.read_text(encoding="utf-8"))
        n = put(raw)
        src.write_text(json.dumps(strip(raw), ensure_ascii=False), encoding="utf-8")   # 받은 파일엔 sourceType·detectedAt만 남긴다(ADR-032)
        print(json.dumps({"added": n}))
    elif argv[:1] == ["--run"]:
        lines = run()
        print("\n".join(lines) if lines else "급증 없음")
    elif argv[:1] == ["--show"]:
        key = argv[1]
        rows = jload(LATEST, {}).get("rows", {})
        print(json.dumps(rows.get(key) or next((v for v in rows.values() if v["ticker"] == key.upper()), None), ensure_ascii=False, indent=1))
    else:
        print(__doc__)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
