"""어닝콜 인사이트 피드 계산기 — 마스터 지시 2026-10-30 "Fiscal.ai에 어닝콜 스크립트가 실적 지표 발표 이후 뒤늦게 올라오면
뉴팩트 정리와 함께 인사이트 피드도 함께 제공하라" (knowledge/methods/earnings_format.md ④, 지시서 docs/tasks/chiip-pulse.md 1-1)

전제: 콜은 발표 직후 생중계됐다 — 전문 게재 지연은 Fiscal.ai의 지연이지 시장의 지연이 아니다. 그래서 피드의 값은 '새 소식'이 아니라
  (가) 보도자료(①)에 없고 콜에서만 나온 것(가이던스 색채·수주·가격·캐파) (나) Q&A에서 드러난 것(답변 회피·질문 초점 이동 —
  Matsumoto, Pronk & Roelofsen 2011: Q&A가 발표문보다 정보가 많다 / Hollander, Pronk & Roelofsen 2010: 답하지 않음에 시장이 음(−)으로 반응)
  (다) 발표 반응 뒤 남은 표류(Bernard & Thomas 1989 PEAD, Price et al. 2012: 콜 Q&A 어조가 이후 60일 표류를 설명)를 숫자로 가르는 데 있다.
이 스크립트는 숫자만 계산한다(판단·문장은 모델). 결정론 스크립트는 Fiscal.ai를 직접 못 부르므로 '코드 → execute_code → 결과 넣기'(ADR-012).
사용: py scripts/insight/call_feed.py code <회사 키> <q분기-연도>       # call_feed.js 본문(이번·직전 이벤트 키 채움)
      py scripts/insight/call_feed.py calc <파일> <회사 키> <q분기-연도>  # 발표 반응 AR·β·게재까지 표류·Q&A 비교 → knowledge/models/earnings/call_feed/
      py scripts/insight/call_feed.py log <회사 키> <q분기-연도> --score 6 --view 상향|하향|중립 --conf 고|중|저 [--note …]  # 보낸 피드 기록(성적표용)
"""
import argparse
import csv
import json
import re
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "radar"))
TPL = ROOT / "scripts" / "fiscal" / "templates" / "call_feed.js"
OUT = ROOT / "knowledge" / "models" / "earnings" / "call_feed"
LOG = OUT / "log.csv"
CFG = ROOT / "config" / "insight" / "call_feed.yaml"   # 상수는 여기(등록부 prm-callfeed-*)


def params():
    import yaml
    return (yaml.safe_load(CFG.read_text(encoding="utf-8")) or {}).get("params") or {}


def prev_event(ev):
    """'q1-2027' → 'q4-2026'"""
    m = re.fullmatch(r"q([1-4])-(\d{4})", ev or "")
    if not m:
        return ""
    q, y = int(m.group(1)), int(m.group(2))
    return f"q{q - 1}-{y}" if q > 1 else f"q4-{y - 1}"


def _record(key, ev):
    from pollers import common
    st = common.load_state("transcripts", {})
    return (st.get("events") or {}).get(f"{key}|{ev}") or {}


# ── 거래소 현지 시각(tzdata가 없는 환경 — 서머타임은 규칙으로) ──
def _nth_sunday(y, m, n):
    d = date(y, m, 1)
    d += timedelta(days=(6 - d.weekday()) % 7)
    return d + timedelta(weeks=n - 1)


def _last_sunday(y, m):
    d = date(y, m + 1, 1) - timedelta(days=1) if m < 12 else date(y, 12, 31)
    return d - timedelta(days=(d.weekday() + 1) % 7)


def _offset(prefix, utc):
    """거래소 접두어 → (UTC 시차, 장 시작, 장 마감) 시각(시 단위 소수)"""
    d = utc.date()
    us_dst = _nth_sunday(d.year, 3, 2) <= d < _nth_sunday(d.year, 11, 1)
    eu_dst = _last_sunday(d.year, 3) <= d < _last_sunday(d.year, 10)
    table = {"NASDAQ": (-4 if us_dst else -5, 9.5, 16), "NYSE": (-4 if us_dst else -5, 9.5, 16), "NYSEAMERICAN": (-4 if us_dst else -5, 9.5, 16),
             "TSE": (9, 9, 15.5), "TYO": (9, 9, 15.5), "TWSE": (8, 9, 13.5), "TPEX": (8, 9, 13.5), "KRX": (9, 9, 15.5), "KOSDAQ": (9, 9, 15.5),
             "LSE": (1 if eu_dst else 0, 8, 16.5), "XETRA": (2 if eu_dst else 1, 9, 17.5), "ENXTPA": (2 if eu_dst else 1, 9, 17.5),
             "ENXTAM": (2 if eu_dst else 1, 9, 17.5), "BIT": (2 if eu_dst else 1, 9, 17.5), "SIX": (2 if eu_dst else 1, 9, 17.5)}
    return table.get(prefix, table["NYSE"])


def reaction_day(key, release_utc, dates):
    """발표를 처음 반영한 거래일과 그 전 종가일. 장 마감 후 발표 → 다음 거래일, 장 전·장중 → 그날"""
    off, _open, close = _offset(key.split("_")[0], release_utc)
    local = release_utc + timedelta(hours=off)
    hour = local.hour + local.minute / 60
    d0 = local.date().isoformat()
    after = hour >= close
    cand = [d for d in dates if (d > d0 if after else d >= d0)]
    if not cand:
        return None, None, "after_close" if after else "pre_or_intraday"
    r = cand[0]
    i = dates.index(r)
    return r, (dates[i - 1] if i > 0 else None), "after_close" if after else ("pre_market" if hour < _open else "intraday")


def _returns(rows):
    return {rows[i][0]: rows[i][1] / rows[i - 1][1] - 1 for i in range(1, len(rows)) if rows[i - 1][1]}


def _basket(series, keys):
    """동일가중 일간 수익률(날짜별로 있는 종목만 평균)"""
    rets = [_returns(series[k]) for k in keys if series.get(k)]
    days = sorted({d for r in rets for d in r})
    out = {}
    for d in days:
        v = [r[d] for r in rets if d in r]
        if v:
            out[d] = sum(v) / len(v)
    return out


def _beta(stock, mkt, until, n=120, n_min=60):
    days = [d for d in sorted(stock) if d < until and d in mkt][-n:]
    if len(days) < n_min:
        return 1.0, len(days), "기본값 1.0(표본 부족)"
    x = [mkt[d] for d in days]
    y = [stock[d] for d in days]
    mx, my = sum(x) / len(x), sum(y) / len(y)
    vx = sum((a - mx) ** 2 for a in x)
    if not vx:
        return 1.0, len(days), "기본값 1.0(시장 분산 0)"
    b = sum((a - mx) * (c - my) for a, c in zip(x, y)) / vx
    return round(min(max(b, 0.3), 3.0), 2), len(days), "OLS(0.3~3 제한)"


def _window(rets, d_from, d_to):
    """d_from 다음 거래일부터 d_to까지 누적 수익률(%)"""
    v = 1.0
    n = 0
    for d in sorted(rets):
        if d_from < d <= d_to:
            v *= 1 + rets[d]
            n += 1
    return (round((v - 1) * 100, 2) if n else None), n


def calc(data, key, ev, rec=None, now=None):
    now = now or datetime.now(timezone.utc)
    rec = rec if rec is not None else _record(key, ev)
    prm = params()
    rows = data.get("stock") or []
    if len(rows) < 3:
        return {"error": "종가 없음", "errors": data.get("errors")}
    us = key.split("_")[0] in ("NASDAQ", "NYSE", "NYSEAMERICAN")
    if "mkt_ret" in data:   # call_feed.js가 묶어 준 동일가중 수익률
        mkt, peer = (data.get("mkt_ret") or {}) if us else {}, data.get("peer_ret") or {}
    else:
        series = data.get("series") or {}
        mkt = _basket(series, data.get("market") or []) if us else {}
        peer = _basket(series, data.get("peers") or [])
    srets = _returns(rows)
    dates = [r[0] for r in rows]
    rel = datetime.fromisoformat(rec["utc"]) if rec.get("utc") else None
    out = {"key": key, "event": ev, "ticker": rec.get("ticker"), "release_utc": rec.get("utc"), "transcript_found_utc": rec.get("found_at"),
           "transcript_lag_h": rec.get("lag_h"), "market_heard_live": True,
           "market_proxy": "미국 대형주 6종 동일가중(Fiscal에 지수 없음 — 근사)" if us else "없음(비미국 — 원시 수익률·경쟁사 대비만)",
           "peers": data.get("peers") or []}
    if not rel:
        out["error"] = "발표 시각 없음(transcripts 상태에 없는 건)"
        return out
    r_day, base, when = reaction_day(key, rel, dates)
    if not r_day:   # 장 마감 후 발표에 전문이 그날 밤 올라오면 반응일 장이 아직 없다
        cand = [d for d in dates if d <= rel.date().isoformat()]
        base = cand[-1] if cand else None
    out.update({"release_session": when, "reaction_day": r_day, "base_day": base})
    beta, nb, how = _beta(srets, mkt, base, prm.get("beta_window", 120), prm.get("beta_min", 60)) if (mkt and base) else (1.0, 0, "시장 근사 없음")
    if base:   # 발표 전 runup_days 거래일 상승(기대 수준의 근사 — 많이 오른 채 발표를 맞으면 기준선이 높다)
        i = dates.index(base)
        start = dates[max(i - prm.get("runup_days", 20), 0)]
        s0, n0 = _window(srets, start, base)
        m0, _ = _window(mkt, start, base) if mkt else (None, 0)
        out["runup_20d"] = {"from": start, "to": base, "days": n0, "stock_pct": s0, "market_pct": m0,
                            "ar_pct": round(s0 - beta * m0, 2) if (s0 is not None and m0 is not None) else s0}
    if not r_day:
        out["reaction"] = None
        out["drift"] = {"days": 0, "note": "반응일 장이 아직 열리지 않았다 — 가격 줄은 ①의 장전·장후 등락(있으면)과 발표 전 20일 상승으로 쓴다"}
    if r_day and base:
        s, _ = _window(srets, base, r_day)
        m, _ = _window(mkt, base, r_day) if mkt else (None, 0)
        p, _ = _window(peer, base, r_day) if peer else (None, 0)
        ar = round(s - beta * m, 2) if m is not None else s
        out["reaction"] = {"stock_pct": s, "market_pct": m, "peers_pct": p, "beta": beta, "beta_n": nb, "beta_how": how, "ar_pct": ar,
                           "vs_peers_pct": round(s - p, 2) if p is not None else None}
        last = dates[-1]
        if last > r_day:
            s2, n2 = _window(srets, r_day, last)
            m2, _ = _window(mkt, r_day, last) if mkt else (None, 0)
            out["drift"] = {"from": r_day, "to": last, "days": n2, "stock_pct": s2, "market_pct": m2,
                            "ar_pct": round(s2 - beta * m2, 2) if m2 is not None else s2,
                            "same_sign_as_reaction": (s2 or 0) * (ar or 0) > 0}
        else:
            out["drift"] = {"from": r_day, "to": last, "days": 0, "note": "반응일 이후 거래일 없음 — 콜 게재 전후 반응을 가를 수 없다(발표·콜 반응이 한 날에 섞임)"}
    c, pc = data.get("call") or {}, data.get("prev_call") or {}
    out["qa"] = {"now": {k: c.get(k) for k in ("questions", "firms", "answer_words_avg", "prepared_words", "qa_found")},
                 "prev": {k: pc.get(k) for k in ("questions", "firms", "answer_words_avg", "prepared_words", "qa_found")} if pc else None,
                 "short_or_refuse": [{"firm": q.get("firm"), "words": q.get("words"), "refuse": q.get("refuse"), "q_head": (q.get("q") or "")[:120]}
                                     for q in (c.get("short_or_refuse") or [])],
                 "note": "짧은 답·회피 표현은 후보일 뿐 — 원문 맥락을 읽고 '답변 회피'인지 판정(같은 질문을 다른 경영진이 이어서 답했을 수 있다)"}
    if pc and c.get("answer_words_avg") and pc.get("answer_words_avg"):
        out["qa"]["answer_len_change_pct"] = round((c["answer_words_avg"] / pc["answer_words_avg"] - 1) * 100, 1)
    out["cif_hints"] = {
        "novelty": "0~2(3 없음 — 콜은 생중계로 이미 공개): 2 = 보도자료에 없던 콜 전용 숫자·가이던스 색채이고 영어권·국내 보도에 아직 없음 / 1 = 콜 전용이지만 이미 보도 또는 정성 변화 / 0 = 보도자료 반복",
        "priced": "reaction.ar_pct를 insight_calc.py priced --stock <ar> --market 0 --beta 1 --implied <밸류 다리 %>로 — 반응일은 보도자료와 콜이 섞인 값",
        "diffusion": "callqa(Q&A 변화·회피) + link·complex·smallcap 해당 시 insight_calc.py diffusion",
        "baserate": "earnings_drift · call_qa_content · call_nonanswer (config/insight/base_rates.yaml)",
    }
    out["computed_at"] = now.isoformat()
    return out


def save(res):
    OUT.mkdir(parents=True, exist_ok=True)
    d = (res.get("reaction_day") or (res.get("release_utc") or "")[:10] or datetime.now().strftime("%Y-%m-%d")).replace("-", "")
    p = OUT / f"{d}_{res.get('ticker') or res['key']}_{res['event']}.json"
    p.write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
    return p


def log(key, ev, score, view, conf, note=""):
    rec = _record(key, ev)
    OUT.mkdir(parents=True, exist_ok=True)
    new = not LOG.exists()
    calc_file = sorted(OUT.glob(f"*_{rec.get('ticker') or key}_{ev}.json"))
    r = json.loads(calc_file[-1].read_text(encoding="utf-8")) if calc_file else {}
    with LOG.open("a", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        if new:
            w.writerow(["logged_at", "key", "event", "ticker", "release_utc", "transcript_lag_h", "reaction_day", "reaction_ar_pct", "drift_ar_pct",
                        "score", "view", "confidence", "note"])
        w.writerow([datetime.now(timezone.utc).isoformat(timespec="seconds"), key, ev, rec.get("ticker"), rec.get("utc"), rec.get("lag_h"),
                    r.get("reaction_day"), (r.get("reaction") or {}).get("ar_pct"), (r.get("drift") or {}).get("ar_pct"), score, view, conf, note])
    return LOG


def main(argv):
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    sp = ap.add_subparsers(dest="cmd", required=True)
    c = sp.add_parser("code")
    c.add_argument("key")
    c.add_argument("event")
    k = sp.add_parser("calc")
    k.add_argument("file")
    k.add_argument("key")
    k.add_argument("event")
    g = sp.add_parser("log")
    g.add_argument("key")
    g.add_argument("event")
    g.add_argument("--score", type=float, required=True)
    g.add_argument("--view", required=True, choices=["상향", "하향", "중립"])
    g.add_argument("--conf", required=True, choices=["고", "중", "저"])
    g.add_argument("--note", default="")
    a = ap.parse_args(argv)
    if a.cmd == "code":
        prm = params()
        print(TPL.read_text(encoding="utf-8").replace("__KEY__", a.key).replace("__EVENT__", a.event).replace("__PREV__", prev_event(a.event))
              .replace("__SHORT__", str(prm.get("short_answer_words", 40))).replace("__QMIN__", str(prm.get("question_min_words", 25))))
        return 0
    if a.cmd == "calc":
        text = Path(a.file).read_text(encoding="utf-8")
        res = calc(json.loads(text[text.index("{"):text.rindex("}") + 1]), a.key, a.event)
        if "error" not in res:
            res["saved"] = save(res).relative_to(ROOT).as_posix()
        print(json.dumps(res, ensure_ascii=False, indent=1))
        return 0
    print(f"기록: {log(a.key, a.event, a.score, a.view, a.conf, a.note).relative_to(ROOT).as_posix()}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
