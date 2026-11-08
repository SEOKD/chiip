"""Chiip Flow — 미국 장초·장마감 섹터 로테이션 관측 (마스터 지시 2026-11-08 "Chiip Midterm을 Chiip Flow로 바꾸고 미국 주식 시장의 장초, 장마감
섹터 로테이션 흐름을 관측") — 설정 config/chiip_flow.yaml, 계산은 결정론, 해석 2~3줄만 모델

회차: 장초(ET 09:45, 개장 15분 뒤)·장마감(ET 15:45, 조기 폐장일 12:45). 서머타임은 미국 규칙으로 계산해, NYSE 휴장일은 설정으로 거른다.
지표(모두 당일 등락 기준, %·%p):
  흐름 = (ETF 등락 − SPY 등락) × 상대 거래량(10일, rv_floor~rv_cap) — 섹터 11 + 세부 업종 19, 유입·유출 상위 3
  로테이션 축 = 왼쪽 묶음 평균 등락 − 오른쪽 묶음 평균 등락(경기민감↔방어, 성장↔가치, 소형↔대형, 고베타↔저변동, 반도체↔소프트웨어, 시장 폭, 신용)
  교차 자산 = 장기 국채·달러·금·VIX·하이일드 — 위험 선호와 같은 방향인지
  장마감 회차: 같은 날 장초 대비 지속(상위 유지)·반전(상위 → 하위)·새 진입 / 다일 로테이션(장마감 기준 연속 n일 상위)
단서이지 사실이 아니다: 등락·거래량만 본 흐름이고 원인(뉴스)은 1차 출처로 확인된 것만 모델이 덧붙인다(금지표: 주가 급등 → 펀더멘털 변화).
사용: py radar/markets/sector_flow.py --session            → '장초'·'장마감'·'장외'
      py radar/markets/sector_flow.py --symbols            → TradingView get-symbol-data-batch 심볼 목록(JSON)
      py radar/markets/sector_flow.py --tick <응답 파일> [--out <tg 파일>]  → 계산·기록·텔레그램 본문(해석 자리 '{해석}')
저장: knowledge/models/chiip_flow/log.csv(회차별), state.json(당일 장초·최근 장마감)
"""
import csv
import json
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from pollers import common  # noqa: E402

KST = timezone(timedelta(hours=9), "KST")


def et_tz(d):
    """미국 동부 시각대 — 서머타임(3월 둘째 일요일 ~ 11월 첫째 일요일)이면 UTC−4, 아니면 −5. Windows 파이썬에 tzdata가 없어 규칙으로 계산"""
    def sunday(y, m, nth):
        x = date(y, m, 1)
        return x + timedelta(days=(6 - x.weekday()) % 7 + 7 * (nth - 1))
    on = sunday(d.year, 3, 2) <= d < sunday(d.year, 11, 1)
    return timezone(timedelta(hours=-4 if on else -5), "EDT" if on else "EST")


def to_et(t):
    t = t.astimezone(timezone.utc)
    return t.astimezone(et_tz((t - timedelta(hours=5)).date()))
DIR = common.ROOT / "knowledge" / "models" / "chiip_flow"


def cfg():
    return common.load_yaml("config/chiip_flow.yaml")


def session(now=None, c=None):
    """지금이 장초·장마감 회차인지(체크포인트 ± tolerance). 주말·NYSE 휴장일은 장외"""
    c = c or cfg()
    now = to_et(now or common.now_kst())
    d = now.date().isoformat()
    if now.weekday() >= 5 or d in (c.get("holidays") or []):
        return "장외", now
    tol = timedelta(minutes=int(c.get("tolerance_min") or 40))
    close = "12:45" if d in (c.get("early_close") or []) else c["checkpoints"]["close"]
    for name, hm in (("장초", c["checkpoints"]["open"]), ("장마감", close)):
        h, m = map(int, hm.split(":"))
        if abs(now - now.replace(hour=h, minute=m, second=0, microsecond=0)) <= tol:
            return name, now
    return "장외", now


def symbols(c=None):
    c = c or cfg()
    s = [c["benchmark"]] + c["sectors"] + c["industries"] + c["cross"]
    for a in c["axes"]:
        s += a["left"] + a["right"]
    return list(dict.fromkeys(s))


def compute(quotes, c=None):
    c = c or cfg()
    ch = lambda s: (quotes.get(s) or {}).get("change")
    spy = ch(c["benchmark"]) or 0.0
    flow, thin = {}, []
    for s in c["sectors"] + c["industries"]:
        q = quotes.get(s) or {}
        if q.get("change") is None:
            continue
        rv = q.get("relative_volume_10d_calc") or 1.0
        flow[s] = round((q["change"] - spy) * min(max(rv, c["rv_floor"]), c["rv_cap"]), 2)
        if q["change"] - spy > 0.3 and rv < c["thin_rv"]:
            thin.append(s)
    rank = sorted(flow, key=lambda k: -flow[k])
    sec = sorted((s for s in c["sectors"] if s in flow), key=lambda k: -flow[k])
    axes = []
    for a in c["axes"]:
        L = [ch(s) for s in a["left"] if ch(s) is not None]
        R = [ch(s) for s in a["right"] if ch(s) is not None]
        if L and R:
            v = round(sum(L) / len(L) - sum(R) / len(R), 2)
            left, right = [x.strip() for x in a["name"].split("↔")[0:2]]
            right = right.split("(")[0].strip()
            lean = "중립" if abs(v) < c["axis_dead"] else (left if v > 0 else right)
            axes.append({"name": a["name"], "value": v, "lean": lean})
    cross = {s: ch(s) for s in c["cross"] if ch(s) is not None}
    return {"spy": round(spy, 2), "top": rank[:3], "bottom": rank[-3:][::-1], "sector_top": sec[:3], "sector_bottom": sec[-3:][::-1],
            "flow": flow, "axes": axes, "cross": cross, "thin": thin,
            "change": {s: ch(s) for s in flow}, "rv": {s: (quotes.get(s) or {}).get("relative_volume_10d_calc") for s in flow}}


def name(s, c):
    return f"{c['names'].get(s, s.split(':')[-1])}({s.split(':')[-1]})"


def compare(open_, cur):
    """장마감 vs 같은 날 장초 — 지속·반전·새 진입"""
    if not open_:
        return None
    held = [s for s in cur["top"] if s in open_["top"]]
    flipped = [s for s in open_["top"] if s in cur["bottom"]] + [s for s in open_["bottom"] if s in cur["top"]]
    new = [s for s in cur["top"] if s not in open_["top"]]
    turned = [a["name"] for a, b in ((a, next((x for x in open_["axes"] if x["name"] == a["name"]), None)) for a in cur["axes"])
              if b and a["lean"] != b["lean"] and "중립" not in (a["lean"], b["lean"])]
    return {"held": held, "flipped": flipped, "new": new, "axes_turned": turned}


def streaks(log, cur_top, n):
    """장마감 기준 연속 상위 일수(오늘 포함)"""
    closes = [r for r in log if r.get("session") == "장마감"]
    out = {}
    for s in cur_top:
        k = 1
        for r in reversed(closes):
            if s in (r.get("top") or "").split("|"):
                k += 1
            else:
                break
        if k >= n:
            out[s] = k
    return out


def _read_log():
    f = DIR / "log.csv"
    if not f.exists():
        return []
    with f.open(encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


def render(sess, et, r, cmp_, stk, c):
    pc = lambda v: f"{v:+.2f}%"
    kst = et.astimezone(KST)
    L = [f"[Chiip Flow] 미국 {sess} 섹터 로테이션 · {kst:%m/%d %H:%M} KST(ET {et:%H:%M})", ""]
    L.append(f"결론: {{해석}}")
    L.append("")
    L.append(f"시장: S&P500(SPY) {pc(r['spy'])}" + (f" · 나스닥100 {pc(r['cross']['NASDAQ:QQQ'])}" if "NASDAQ:QQQ" in r["cross"] else "")
             + (f" · 동일가중 {pc(r['cross']['AMEX:RSP'])}" if "AMEX:RSP" in r["cross"] else ""))
    L.append("")
    L.append("돈이 들어간 곳(SPY 대비 초과 × 거래량)")
    L += [f"• {name(s, c)} {pc(r['change'][s])} · 거래량 {r['rv'][s] or 1:.1f}배" for s in r["top"]]
    L.append("돈이 빠진 곳")
    L += [f"• {name(s, c)} {pc(r['change'][s])} · 거래량 {r['rv'][s] or 1:.1f}배" for s in r["bottom"]]
    L.append("")
    L.append("로테이션 축(왼쪽 − 오른쪽, %p)")
    L += [f"• {a['name']}: {a['value']:+.2f} → {a['lean']}" for a in r["axes"]]
    x = r["cross"]
    parts = [f"{c['names'].get(s, s)} {pc(x[s])}" for s in ("NASDAQ:TLT", "AMEX:UUP", "AMEX:GLD", "CBOE:VIX", "AMEX:HYG") if s in x]
    if parts:
        L += ["", "교차 자산: " + " · ".join(parts)]
    if r["thin"]:
        L.append("얇은 상승(거래량 평소 아래): " + ", ".join(name(s, c) for s in r["thin"][:4]))
    if cmp_:
        L += ["", "장초 대비"]
        if cmp_["held"]:
            L.append("• 유지: " + ", ".join(name(s, c) for s in cmp_["held"]))
        if cmp_["flipped"]:
            L.append("• 반전: " + ", ".join(name(s, c) for s in cmp_["flipped"]))
        if cmp_["new"]:
            L.append("• 새 유입: " + ", ".join(name(s, c) for s in cmp_["new"]))
        if cmp_["axes_turned"]:
            L.append("• 방향이 바뀐 축: " + ", ".join(cmp_["axes_turned"]))
    if stk:
        L.append("다일 로테이션: " + ", ".join(f"{name(s, c)} {k}거래일 연속 유입 상위" for s, k in stk.items()))
    L += ["", "1차 판정·미검증 · 등락·거래량만 본 흐름이며 원인은 확인된 것만 적는다 · 공개 자료 기반 분석이며 투자 권유가 아님"]
    return "\n".join(L)


def tick(path, out=None, now=None):
    c = cfg()
    sess, et = session(now, c)
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    data = raw.get("data", raw)
    if isinstance(data, list):   # get-symbol-data-batch rows → {심볼: 값}
        data = {d.get("symbol"): d.get("values", d) for d in data}
    r = compute(data, c)
    DIR.mkdir(parents=True, exist_ok=True)
    sf = DIR / "state.json"
    st = json.loads(sf.read_text(encoding="utf-8")) if sf.exists() else {}
    day = et.date().isoformat()
    open_ = st.get("open") if (st.get("open") or {}).get("day") == day else None
    cmp_ = compare(open_, r) if sess == "장마감" else None
    log = _read_log()
    stk = streaks(log, r["top"], int(c["streak_days"])) if sess == "장마감" else {}
    if sess in ("장초", "장마감"):
        st["open" if sess == "장초" else "close"] = {**r, "day": day}
        sf.write_text(json.dumps(st, ensure_ascii=False), encoding="utf-8")
        f = DIR / "log.csv"
        new = not f.exists()
        with f.open("a", encoding="utf-8", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=["at_et", "day", "session", "spy", "top", "bottom", "axes"])
            if new:
                w.writeheader()
            w.writerow({"at_et": et.isoformat(timespec="minutes"), "day": day, "session": sess, "spy": r["spy"], "top": "|".join(r["top"]),
                        "bottom": "|".join(r["bottom"]), "axes": "; ".join(f"{a['name']} {a['value']:+.2f}" for a in r["axes"])})
    text = render(sess, et, r, cmp_, stk, c)
    if out:
        Path(out).write_text(text, encoding="utf-8")
    return {"session": sess, "result": r, "vs_open": cmp_, "streaks": stk, "text": text}


def main(argv):
    sys.stdout.reconfigure(encoding="utf-8")
    if "--session" in argv:
        print(session()[0])
    elif "--symbols" in argv:
        print(json.dumps(symbols()))
    elif "--tick" in argv:
        out = argv[argv.index("--out") + 1] if "--out" in argv else None
        res = tick(argv[argv.index("--tick") + 1], out)
        print(res["text"])
    else:
        raise SystemExit(__doc__)


if __name__ == "__main__":
    main(sys.argv[1:])
