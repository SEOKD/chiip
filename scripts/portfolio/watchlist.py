"""Portfolio 와치리스트 자동 편입·제외 (마스터 지시 2026-11-04 "에이전트가 스스로 판단해 추가하고 제외하라. 단, 체계적인 판단 흐름과
정량적 지표에 따라") — 규칙은 config/watchlist.yaml, 판단은 이 스크립트(결정론). 모델은 결과를 데일리에 옮겨 적기만 한다.

흐름(매 Portfolio 회차, composite.py·buy_call.py 다음):
  1. 지표 모으기  알파(knowledge/models/alpha/latest.json) · 종합 점수·기술적·거래대금·킬(composite_latest.json rows) · 리포트 등급(buy_call_latest.json)
  2. 편입 후보    킬·거래대금 미달이 아니고, 알파 ≥ alpha_min, 그리고 (종합 ≥ composite_min 또는 Buy Call)
                 서로 다른 날 confirm_days일 연속 충족 → 편입. 자동 편입 상한(max_auto)이면 가장 낮은 자동 편입보다 replace_margin 이상 높을 때만 교체
  3. 제외         status 관심만(보유는 마스터 몫이라 건드리지 않는다). 킬 발동은 즉시, 알파 < alpha_below 또는 종합 < composite_below가
                 confirm_days일 연속이면 제외. 지표가 없는 날은 판정하지 않는다(모르면 미확인 — 없는 숫자로 빼지 않는다)
  4. 반영         config/portfolio.yaml에 블록 추가(added_by: chiip) 또는 status: 종료 + ended·ended_reason(지우지 않는다).
                 기록 knowledge/models/portfolio/watchlist_log.csv(편입·제외일 지표 — 성적표 재료)
지표·연구 후보이지 매수 권유가 아니다. 마스터 포지션 파일은 읽지 않는다.
사용: py scripts/portfolio/watchlist.py [--dry]
"""
import csv
import json
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
PORT = ROOT / "config" / "portfolio.yaml"
CFG = ROOT / "config" / "watchlist.yaml"
M = ROOT / "knowledge" / "models"
STATE = ROOT / "radar" / "state" / "watchlist_auto.json"
LOG = M / "portfolio" / "watchlist_log.csv"
KST = timezone(timedelta(hours=9))


def jload(p, default):
    try:
        return json.loads(Path(p).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def metrics():
    """id → {ticker, name, alpha, composite, technical, adv_ok, killed, buy}"""
    out = {}
    for k, v in (jload(M / "alpha" / "latest.json", {}).get("rows") or {}).items():
        out.setdefault(k, {})
        out[k].update({"alpha": v.get("total"), "name": v.get("name")})
    for r in jload(M / "portfolio" / "composite_latest.json", {}).get("rows") or []:
        if not r.get("id"):
            continue
        why = " ".join(r.get("why") or [])
        out.setdefault(r["id"], {}).update({"ticker": r.get("ticker"), "composite": r.get("composite"), "technical": r.get("technical"),
                                            "adv_ok": "거래대금" not in why, "killed": "킬" in why})
        out[r["id"]].setdefault("name", r.get("name"))
    for k, v in (jload(M / "portfolio" / "buy_call_latest.json", {}).get("calls") or {}).items():
        d = out.setdefault(k, {})
        d["buy"] = v.get("grade_now") in ("Strong Buy", "Buy")
        d.setdefault("ticker", v.get("ticker"))
        d["name"] = d.get("name") or v.get("company")
    return out


def pct(vals, q):
    v = sorted(x for x in vals if x is not None)
    return v[int(q * (len(v) - 1))] if v else None


def cuts(mt, c):
    """그날 분포의 분위 문턱 — 고정값 대신(점수 눈금 변화에 강하고 피팅이 아니다)"""
    al, co = [m.get("alpha") for m in mt.values()], [m.get("composite") for m in mt.values()]
    return {"add_comp": pct(co, c["add"]["composite_pct"]), "rm_alpha": pct(al, c["remove"]["alpha_pct"]), "rm_comp": pct(co, c["remove"]["composite_pct"])}


def qualifies(m, c, k):
    a = c["add"]
    if m.get("killed") or m.get("adv_ok") is False or m.get("alpha") is None or not m.get("ticker"):
        return False
    return m["alpha"] >= a["alpha_min"] and ((m.get("composite") or 0) >= (k["add_comp"] or 99) or bool(a["buy_call_counts"] and m.get("buy")))


def failing(m, c, k):
    """None = 판정 불가(지표 없음), "" = 기준 충족, 그 밖 = 미달 이유"""
    if m.get("killed") and c["remove"]["killed_immediate"]:
        return "킬 조건 발동"
    if m.get("alpha") is None or m.get("composite") is None or k["rm_alpha"] is None:
        return None
    if m["alpha"] < k["rm_alpha"] and m["composite"] < k["rm_comp"]:
        return f"알파 {m['alpha']:.1f}·종합 {m['composite']:.1f} 둘 다 중앙값({k['rm_alpha']:.1f}·{k['rm_comp']:.1f}) 아래"
    return ""


def streak(st, key, iid, today, hit):
    """서로 다른 날 연속 충족 일수(같은 날 여러 회차는 한 번). 끊기면 0부터"""
    book = st.setdefault(key, {})
    if not hit:
        book.pop(iid, None)
        return 0
    s = book.get(iid)
    if s and s["last"] == today:
        return s["n"]
    y = (datetime.fromisoformat(today) - timedelta(days=1)).date().isoformat()
    book[iid] = {"n": s["n"] + 1 if s and s["last"] == y else 1, "last": today}
    return book[iid]["n"]


def decide(holdings, mt, c, st, today):
    watch = {h["id"]: h for h in holdings if h.get("status") == "관심"}
    held = {h["id"] for h in holdings if h.get("status") in ("보유", "관심")}
    held |= {h["id"] for h in holdings if h.get("status") == "종료" and h.get("added_by") != "chiip"}   # 마스터가 뺀 종목은 자동으로 다시 넣지 않는다(2026-11-05 AEIS 제외 지시)
    adds, drops, k = [], [], cuts(mt, c)
    for iid, h in watch.items():
        why = failing(mt.get(iid, {}), c, k)
        if why is None:
            continue
        if why == "킬 조건 발동":
            drops.append((iid, why))
            continue
        if streak(st, "fail", iid, today, bool(why)) >= c["remove"]["confirm_days"]:
            drops.append((iid, f"{why} {c['remove']['confirm_days']}일 연속"))
    auto = [i for i, h in watch.items() if h.get("added_by") == "chiip" and i not in dict(drops)]
    cands = []
    for iid, m in mt.items():
        if iid in held:
            continue
        if streak(st, "pass", iid, today, qualifies(m, c, k)) >= c["add"]["confirm_days"]:
            cands.append(iid)
    cands.sort(key=lambda i: -(mt[i].get("composite") or 0))
    for iid in cands:
        if len(auto) < c["cap"]["max_auto"]:
            adds.append(iid)
            auto.append(iid)
            continue
        low = min(auto, key=lambda i: mt.get(i, {}).get("composite") or 0)
        if (mt[iid].get("composite") or 0) - (mt.get(low, {}).get("composite") or 0) >= c["cap"]["replace_margin"]:
            drops.append((low, f"상한 {c['cap']['max_auto']} — {mt[iid].get('ticker')}(종합 {mt[iid].get('composite')})로 교체"))
            auto.remove(low)
            adds.append(iid)
            auto.append(iid)
    return adds, drops


def block(iid, m, today):
    why = f"알파 {m.get('alpha')} · 종합 {m.get('composite')}" + (" · Buy Call" if m.get("buy") else "")
    name = str(m.get("name") or m.get("ticker")).replace('"', "'")
    return (f"  - id: {iid}\n    ticker: {m['ticker']}\n    name: \"{name}\"\n    names: [\"{name}\"]\n    related: []\n"
            f"    since: {today}\n    status: 관심\n    added_by: chiip                         # 와치리스트 자동 편입(scripts/portfolio/watchlist.py) — {why}\n")


def apply(text, adds, drops, mt, today):
    for iid, why in drops:   # 지우지 않고 종료로
        m = re.search(rf"(?ms)^  - id: {re.escape(iid)}\n(.*?)(?=^  - id: |^\S)", text)
        if not m:
            continue
        body = re.sub(r"(?m)^    status: 관심[ \t]*$", f"    status: 종료\n    ended: {today}\n    ended_reason: \"자동 제외 — {why}\"", m[1], count=1)
        text = text[:m.start(1)] + body + text[m.end(1):]
    if adds:   # holdings 끝(events: 위 주석 앞)에 붙인다
        cut = re.search(r"(?m)^(?:#.*\n)*events:", text)
        pos = cut.start() if cut else len(text)
        text = text[:pos].rstrip("\n") + "\n" + "".join(block(i, mt[i], today) for i in adds) + "\n" + text[pos:]
    return text


def log(rows):
    new = not LOG.exists()
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with LOG.open("a", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        if new:
            w.writerow(["date", "action", "id", "ticker", "alpha", "composite", "buy_call", "reason"])
        w.writerows(rows)


def run(dry=False, today=None):
    c = yaml.safe_load(CFG.read_text(encoding="utf-8"))
    text = PORT.read_text(encoding="utf-8")
    holdings = yaml.safe_load(text).get("holdings") or []
    today = today or datetime.now(KST).date().isoformat()
    st = jload(STATE, {})
    mt = metrics()
    adds, drops = decide(holdings, mt, c, st, today)
    tick = {h["id"]: h.get("ticker") for h in holdings}
    out = {"add": [{"id": i, "ticker": mt[i].get("ticker"), "alpha": mt[i].get("alpha"), "composite": mt[i].get("composite"), "buy_call": bool(mt[i].get("buy"))} for i in adds],
           "remove": [{"id": i, "ticker": tick.get(i), "reason": w} for i, w in drops]}
    if not dry:
        if adds or drops:
            PORT.write_text(apply(text, adds, drops, mt, today), encoding="utf-8")
            log([[today, "편입", a["id"], a["ticker"], a["alpha"], a["composite"], a["buy_call"], ""] for a in out["add"]] +
                [[today, "제외", r["id"], r["ticker"], mt.get(r["id"], {}).get("alpha"), mt.get(r["id"], {}).get("composite"), "", r["reason"]] for r in out["remove"]])
        STATE.parent.mkdir(parents=True, exist_ok=True)
        STATE.write_text(json.dumps(st, ensure_ascii=False), encoding="utf-8")
    return out


def main(argv):
    sys.stdout.reconfigure(encoding="utf-8")
    print(json.dumps(run(dry="--dry" in argv), ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main(sys.argv[1:])
