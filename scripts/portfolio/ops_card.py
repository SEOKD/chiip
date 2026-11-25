"""Portfolio 운용 카드 — 종목별 투자 논리·지표·킬 조건·다음 사건·위치, 주간 집중도 (마스터 지시 2026-11-25
"Portfolio의 종목 업데이트 회전율이 낮은 것 같다. 실제 포지션인 EROC과 INIO를 제외하고 나머지를 모두 리셋하고 본격적으로 포트폴리오 매니지먼트를 제공하라")

결정론 — 숫자와 상태는 여기서, 문장은 모델 몫. config/portfolio.yaml을 고치지 않는다.
  카드(보유·관심 전부)
    투자 논리     portfolio.yaml thesis → 없으면 tenbagger watch.csv thesis_1line → 리포트 verdict.view 첫 문장
    지표·킬 조건  portfolio.yaml kpis·kills → 없으면 datapack guru.hold.kpis · watch.csv kill_conditions
    리포트        buy_call_latest(규칙 등급·목표주가·현재가 기준 업사이드·약세·강세·판단이 바뀌는 조건)
    다음 사건     portfolio.yaml events + Fiscal 실적 일정(가장 가까운 것 둘)
    위치          현재가가 약세 시나리오 아래인가, 목표주가 대비 몇 %인가, 기간 고점 대비 낙폭(tenbagger/playbook.drawdown)
  상태(투자 논리 지표 — 가격이 아니라 지표로)
    훼손  킬 조건 발동(composite 킬) 또는 장부 판정 '제외'
    경고  현재가 < 약세 시나리오 · 장부 '재점검'(보유 알파 미달) · 유지 심사 경고 · 리포트 90일 넘음 · 지표 없음
    유지  그 밖
  주간(--table)   전 종목 카드 표 + 섹터 집중도(같은 섹터 몇 개·가장 큰 섹터 몫) + 상태 요약
출력 knowledge/models/portfolio/ops_latest.json. 지표·점검 틀이며 매매·비중·금액 지시가 아니다.
사용: py scripts/portfolio/ops_card.py            # 카드 계산·저장 + 요약
      py scripts/portfolio/ops_card.py --daily    # Daily '내 종목' 종목마다 붙일 상태 한 줄
      py scripts/portfolio/ops_card.py --table    # 주간 점검 표(마크다운)
"""
import csv
import json
import re
import sys
from collections import Counter
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
M = ROOT / "knowledge" / "models"
PORT = ROOT / "config" / "portfolio.yaml"
OUT = M / "portfolio" / "ops_latest.json"
KST = timezone(timedelta(hours=9))
REPORT_STALE = 90
UNK = "미확인"


def _j(p, default=None):
    try:
        return json.loads(Path(p).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {} if default is None else default


def _first_sentence(s):
    s = re.sub(r"\*\*|__|==", "", str(s or "")).strip()
    m = re.match(r"(.+?[다요]\.)(\s|$)", s)
    return (m.group(1) if m else s)[:160]


def _split(s):
    return [x.strip() for x in re.split(r"[;\n]|(?<=\S) · (?=\S)", str(s or "")) if x.strip()]


def load():
    port = yaml.safe_load(PORT.read_text(encoding="utf-8")) or {}
    seen, hs = set(), []
    for h in port.get("holdings") or []:   # 같은 id 블록이 여럿이면 살아 있는 블록 하나만
        if h.get("status") in ("보유", "관심") and h["id"] not in seen:
            seen.add(h["id"])
            hs.append(h)
    wl = {}
    p = M / "tenbagger" / "watch.csv"
    if p.exists():
        for r in csv.DictReader(p.open(encoding="utf-8", newline="")):
            if r.get("status") != "종료" and r.get("ticker"):
                wl[r["ticker"].upper()] = r
    book = {r["id"]: r for r in _j(M / "portfolio" / "book_latest.json").get("rows") or []}
    review = {r["id"]: r for r in _j(M / "portfolio" / "watch_review_latest.json").get("rows") or []}
    killed = {r["id"] for r in (_j(M / "portfolio" / "composite_latest.json").get("rows") or []) if r.get("id") and "킬" in " ".join(r.get("why") or [])}
    return {"holdings": hs, "events": port.get("events") or [], "watch": wl, "calls": _j(M / "portfolio" / "buy_call_latest.json").get("calls") or {},
            "book": book, "review": review, "killed": killed, "earn": _j(M / "earnings" / "fiscal_calendar.json").get("events") or []}


def next_events(ticker, events, earn, today, n=2):
    t = str(ticker or "").upper()
    xs = [(str(e.get("date")), str(e.get("what") or "")) for e in events if str(e.get("ticker") or "").upper() == t and str(e.get("date")) >= today.isoformat()]
    xs += [(e["date"], "실적 발표" + ("" if e.get("confirmed", True) else "(미확정)")) for e in earn
           if str(e.get("ticker") or "").upper() == t and e.get("date") and e["date"] >= today.isoformat()]
    out, dates = [], set()
    for d, w in sorted(xs):
        if d in dates and w.startswith("실적"):
            continue
        dates.add(d)
        out.append({"date": d, "what": re.split(r"[(—]", w)[0].strip()[:40]})
    return out[:n]


def _datapack(cid):
    return _j(M / "companies" / cid / "datapack.json")


def card(h, ctx, today, dd=None):
    t = str(h.get("ticker") or "").upper()
    wl, call = ctx["watch"].get(t) or {}, ctx["calls"].get(h["id"]) or {}
    dp = _datapack(h["id"])
    thesis = h.get("thesis") or wl.get("thesis_1line") or (_first_sentence(call.get("view")) if call.get("view") else None)
    kpis = [str(x) for x in h.get("kpis") or ((dp.get("guru") or {}).get("hold") or {}).get("kpis") or []]
    kills = [str(x) for x in h.get("kills") or _split(wl.get("kill_conditions"))]
    if not kills and call.get("swing"):
        kills = [call["swing"]]
    price, bear, tgt = call.get("price_now"), call.get("bear"), call.get("target")
    rep_date = call.get("date")
    try:
        rep_age = (today - date.fromisoformat(str(rep_date)[:10])).days
    except ValueError:
        rep_age = None
    if dd is None:
        try:
            sys.path.insert(0, str(ROOT / "scripts" / "tenbagger"))
            import playbook
            dd = playbook.drawdown
        except ImportError:
            dd = lambda e: (None, None, 0)   # noqa: E731
    from_peak = dd(h["id"])[0]
    bk, rv = ctx["book"].get(h["id"]) or {}, ctx["review"].get(h["id"]) or {}
    why = []
    if h["id"] in ctx["killed"]:
        why.append(("훼손", "킬 조건 발동"))
    if bk.get("verdict") == "제외":
        why.append(("훼손", f"장부 판정 제외 — {bk.get('reason')}"))
    if isinstance(price, (int, float)) and isinstance(bear, (int, float)) and price < bear:
        why.append(("경고", f"현재가 {price:,.2f} < 약세 시나리오 {bear:,.2f}"))
    if bk.get("verdict") == "재점검":
        why.append(("경고", bk.get("reason") or "장부 재점검"))
    for w in rv.get("warnings") or []:
        why.append(("경고", f"유지 심사 — {w}"))
    if rep_age is None:
        why.append(("경고", "리포트 없음 — 목표주가·셀온 조건 미확인"))
    elif rep_age > REPORT_STALE:
        why.append(("경고", f"리포트 {rep_age}일 전 — 다시 쓸 때"))
    if not kpis:
        why.append(("경고", "투자 논리 지표 없음 — 운용 카드에 적는다"))
    state = "훼손" if any(s == "훼손" for s, _ in why) else ("경고" if why else "유지")
    return {"id": h["id"], "ticker": t, "name": h.get("name"), "status": h["status"], "pin": bool(h.get("pin")), "added_by": h.get("added_by") or "master",
            "sector": _sector(h["id"], t), "thesis": thesis or UNK, "kpis": kpis, "kills": kills,
            "rating": call.get("grade_now") or call.get("grade"), "target": tgt, "price": price, "bear": bear, "bull": call.get("bull"),
            "to_target": (tgt / price - 1) if isinstance(tgt, (int, float)) and isinstance(price, (int, float)) and price else None,
            "from_peak": from_peak, "report": rep_date, "report_age": rep_age,
            "next": next_events(t, ctx["events"], ctx["earn"], today), "state": state, "why": [w for _, w in why]}


def _sector(cid, ticker):
    try:
        sys.path.insert(0, str(ROOT / "scripts" / "sectors"))
        import sector_map
        return sector_map.tag(cid, ticker) or UNK
    except Exception:
        return UNK


def concentration(cards):
    held = [c for c in cards]
    n = len(held)
    by = Counter(c["sector"] for c in held)
    top, k = (by.most_common(1)[0] if by else (None, 0))
    return {"n": n, "by_sector": dict(by.most_common()), "top": top, "top_share": (k / n) if n else None,
            "held_sectors": sorted({c["sector"] for c in held if c["status"] == "보유"})}


def run(today=None, ctx=None, dd=None, write=True):
    today = today or datetime.now(KST).date()
    ctx = ctx or load()
    cards = [card(h, ctx, today, dd) for h in ctx["holdings"]]
    order = {"훼손": 0, "경고": 1, "유지": 2}
    cards.sort(key=lambda c: (c["status"] != "보유", order[c["state"]], c["ticker"]))
    w = yaml.safe_load((ROOT / "config" / "watchlist.yaml").read_text(encoding="utf-8")) or {}
    cap = w.get("cap") or {}
    watch_n = sum(1 for c in cards if c["status"] == "관심")
    out = {"as_of": today.isoformat(), "cards": cards, "concentration": concentration(cards),
           "count": {s: sum(1 for c in cards if c["state"] == s) for s in ("유지", "경고", "훼손")},
           "watch": {"n": watch_n, "min_target": cap.get("min_target"), "max": cap.get("max_auto"),
                     "short": bool(cap.get("min_target")) and watch_n < cap["min_target"]}}
    if write:
        OUT.parent.mkdir(parents=True, exist_ok=True)
        OUT.write_text(json.dumps(out, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    return out


def _pct(x):
    return UNK if x is None else f"{x * 100:+.0f}%"


def daily(out):
    """Daily '내 종목' — 종목마다 상태 한 줄(모델이 그 종목 문단 끝에 그대로 붙인다)"""
    L = []
    for c in out["cards"]:
        s = f"{c['ticker']} 투자 논리 {c['state']}"
        if c["why"]:
            s += " — " + c["why"][0]
        elif c["kpis"]:
            s += f" — 볼 지표: {c['kpis'][0]}"
        if c["next"]:
            s += f" · 다음 {c['next'][0]['date'][5:].replace('-', '/')} {c['next'][0]['what']}"
        L.append(s)
    w = out["watch"]
    if w["short"]:
        L.append(f"관심 종목 {w['n']}개 — 목표 {w['min_target']}~{w['max']}개보다 적다. 편입 기준을 통과한 후보가 생기면 자동으로 들어온다")
    return "\n".join(L)


def table(out):
    L = [f"## 운용 카드 ({out['as_of']}) — 유지 {out['count']['유지']} · 경고 {out['count']['경고']} · 훼손 {out['count']['훼손']}", "",
         "| 종목 | 구분 | 상태 | 투자 논리 | 지표 | 킬 조건 | 등급·목표 | 목표까지 | 고점 대비 | 다음 사건 |", "|---|---|---|---|---|---|---|---|---|---|"]
    for c in out["cards"]:
        tgt = f"{c['rating'] or UNK} · {c['target']:,.2f}" if isinstance(c["target"], (int, float)) else (c["rating"] or UNK)
        nx = " / ".join(f"{e['date'][5:]} {e['what']}" for e in c["next"]) or "—"
        L.append(f"| {c['ticker']} | {c['status']} | {c['state']} | {c['thesis'][:60]} | {' / '.join(c['kpis'][:3]) or UNK} | {len(c['kills'])}개 | {tgt} | {_pct(c['to_target'])} | {_pct(c['from_peak'])} | {nx} |")
    bad = [c for c in out["cards"] if c["why"]]
    if bad:
        L += ["", "### 상태 사유"] + [f"- {c['ticker']}: " + " · ".join(c["why"]) for c in bad]
    co = out["concentration"]
    L += ["", "### 섹터 집중도", " · ".join(f"{k} {v}" for k, v in co["by_sector"].items()) or UNK]
    if co["top_share"] is not None:
        L.append(f"가장 큰 섹터 {co['top']} {co['top_share'] * 100:.0f}%(종목 수 기준) — 보유 섹터 {', '.join(co['held_sectors']) or UNK}")
    w = out["watch"]
    L += ["", f"관심 종목 {w['n']}개(목표 {w['min_target']}~{w['max']}개)" + (" — 적다. 편입 기준 통과 후보를 기다린다" if w["short"] else "")]
    L += ["", "점검 틀이며 매매·비중·금액 지시가 아니다."]
    return "\n".join(L)


def main(argv):
    sys.stdout.reconfigure(encoding="utf-8")
    out = run()
    if "--daily" in argv:
        print(daily(out))
    elif "--table" in argv:
        print(table(out))
    else:
        print(f"[운용 카드] {len(out['cards'])}종목 · 유지 {out['count']['유지']} · 경고 {out['count']['경고']} · 훼손 {out['count']['훼손']}")
        print(daily(out))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
