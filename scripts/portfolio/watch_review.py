"""관심 종목 편입 기준·유지 심사 (마스터 결정 2026-11-13 "관심 종목 수에는 상한을 두지 않는다. 대신 평가 기준을 까다롭게 적용해 관리하라", ADR-024)

규칙 config/watch_review.yaml. 판단은 이 스크립트(결정론), config/portfolio.yaml은 고치지 않는다.
  1. 편입 기준   알파 ≥ 7.0 · 90일 안 리포트 또는 v2 밸류 동인 · 시총 $1B · 20일 평균 거래대금 $10M · 120일 안 실적 확인 · 킬(반증) 조건 명시 — 전부(미확인도 불통과)
                scripts/portfolio/watchlist.py의 자동 편입은 이 기준을 통과한 종목만 넣는다(entry_ok)
  2. 유지 심사   주 1회(ISO 주차당 한 번). 경고 = 알파 하락(문턱 아래·직전 대비 1점↓) · 테제 훼손(킬 발동) · 장기 무변화(30일 새 정보 없음) · 편입 기준 미충족
                서로 다른 주 2회 연속 경고 → '제외 후보'. '미확인'은 경고가 아니라 메모(없는 숫자로 빼지 않는다)
  3. 제외        자동 삭제 없음 — 제외 후보를 목록·사유로 마스터에게 보고하고, 마스터가 승인하면 마스터 세션이 `--apply <id …>`로 status: 종료 반영
  4. 출력        knowledge/models/portfolio/watch_review_latest.json · watch_review_log.csv · radar/state/watch_review.json(연속 주차)
                Daily에는 변화가 있을 때만 한두 문장(`--daily`), 주간 리뷰에는 전체 심사표(`--table`)
보유(status: 보유)는 심사 대상이 아니다. 지표·연구 관리이며 매매 지시가 아니다. 마스터 포지션 파일은 읽지 않는다.
사용: py scripts/portfolio/watch_review.py [--dry] [--date YYYY-MM-DD]   # 주간 심사(같은 주 재실행은 횟수를 늘리지 않는다)
      py scripts/portfolio/watch_review.py --daily | --table
      py scripts/portfolio/watch_review.py --apply <id> [id …]          # 마스터 승인 뒤에만(마스터 세션)
"""
import csv
import json
import re
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
M = ROOT / "knowledge" / "models"
CO = M / "companies"
PORT = ROOT / "config" / "portfolio.yaml"
CFG = ROOT / "config" / "watch_review.yaml"
REP = ROOT / "outputs" / "tenbagger" / "reports"
TICK = ROOT / "outputs" / "invest" / "portfolio" / "tickers"
STATE = ROOT / "radar" / "state" / "watch_review.json"
LATEST = M / "portfolio" / "watch_review_latest.json"
LOG = M / "portfolio" / "watch_review_log.csv"
KST = timezone(timedelta(hours=9))
DATE = re.compile(r"20\d\d-\d\d-\d\d")


def _j(p, default=None):
    try:
        return json.loads(Path(p).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {} if default is None else default


def _d(s):
    """'2026-11-07', '20261107', '2026-11-07T09:30+09:00' → date"""
    s = str(s or "")
    m = re.match(r"(20\d\d)-?(\d\d)-?(\d\d)", s)
    return date(int(m[1]), int(m[2]), int(m[3])) if m else None


def cfg():
    return yaml.safe_load(CFG.read_text(encoding="utf-8"))


# ---------- 재료 ----------
def reports():
    """({id: 가장 최근 리포트 날짜}, {id: 리포트에 쓰인 티커들}) — 티커가 바뀐 종목(CCXI → AGLT)도 id로 잇는다"""
    out, tk, p = {}, {}, REP / "log.csv"
    if p.exists():
        with p.open(encoding="utf-8", newline="") as f:
            for r in csv.DictReader(f):
                d = _d(r.get("date"))
                if r.get("id") and d and (r["id"] not in out or d > out[r["id"]]):
                    out[r["id"]] = d
                if r.get("id") and r.get("ticker"):
                    tk.setdefault(r["id"], set()).add(r["ticker"].upper())
    return out, tk


def kills():
    """{티커: (킬 조건 문구, 닫힘 사유)} — tenbagger watch.csv 최신 줄"""
    out, p = {}, M / "tenbagger" / "watch.csv"
    if p.exists():
        with p.open(encoding="utf-8", newline="") as f:
            for r in csv.DictReader(f):
                if r.get("ticker"):
                    out[r["ticker"].upper()] = (r.get("kill_conditions") or "", r.get("close_reason") or "", r.get("status") or "")
    return out


def report_has_kill(tickers):
    fs = sorted((f for t in tickers for f in REP.glob(f"*_{t}.json")), key=lambda f: f.name)
    if not fs:
        return False
    t = fs[-1].read_text(encoding="utf-8")
    return "킬 조건" in t or "반증" in t     # Analysis 리포트는 판단마다 '반증:'(무엇이 나오면 틀렸나)을 적는다


def tv_quotes():
    """{티커: (close, 30일 평균 거래량)} — sector_select·composite 입력에서(ohlcv가 없을 때)"""
    out = {}
    q = _j(ROOT / "radar" / "state" / "sector_select_in.json").get("q") or {}
    for k, v in q.items():
        if isinstance(v, list) and len(v) > 5 and v[0] and v[5]:
            out[k.split(":")[-1].upper()] = (v[0], v[5])
    for r in _j(ROOT / "radar" / "state" / "composite_in.json").get("rows") or []:
        tv = r.get("tv") or {}
        t = str(r.get("ticker") or "").split(":")[-1].upper()
        if tv.get("close") and tv.get("average_volume_30d_calc"):
            out.setdefault(t, (tv["close"], tv["average_volume_30d_calc"]))
    return out


def adv_m(cid, ticker, tvq):
    """20거래일 평균 거래대금($M) — ohlcv.csv, 없으면 TradingView 30일 평균 거래량 × 종가"""
    p = CO / cid / "ohlcv.csv"
    if p.exists():
        rows = [l.split(",") for l in p.read_text(encoding="utf-8").splitlines() if l and l[0].isdigit()]
        rows = [r for r in rows if len(r) >= 6 and r[4] and r[5]][-20:]
        if rows:
            return sum(float(r[4]) * float(r[5]) for r in rows) / len(rows) / 1e6
    if ticker.upper() in tvq:
        c, v = tvq[ticker.upper()]
        return c * v / 1e6
    return None


def last_info(cid, ticker, rep_date, alpha_on):
    """새 정보가 마지막으로 들어온 날 — 리포트·데이터팩·종목 장부·알파 산정 중 가장 늦은 날"""
    ds = [rep_date, _d(alpha_on), _d(_j(CO / cid / "datapack.json").get("as_of"))]
    p = TICK / f"{ticker}.md"
    if p.exists():
        ds += [_d(x) for x in DATE.findall(p.read_text(encoding="utf-8"))]
    ds = [d for d in ds if d]
    return max(ds) if ds else None


def facts(h, today, ctx):
    """한 종목의 심사 재료"""
    cid, t = h["id"], str(h.get("ticker") or "")
    a = (ctx["alpha"].get(cid) or {})
    dp = _j(CO / cid / "datapack.json")
    pr = dp.get("profile") or {}
    mcap = pr["price"] * pr["shares_basic"] if pr.get("price") and pr.get("shares_basic") and dp.get("unit") == "B$" else None
    ts = {t.upper()} | ctx["rep_tickers"].get(cid, set())
    kc, close, st = next((ctx["kills"][x] for x in ts if x in ctx["kills"]), ("", "", ""))
    rep = ctx["reports"].get(cid)
    return {"id": cid, "ticker": t, "name": h.get("name"), "pin": bool(h.get("pin")), "added_by": h.get("added_by"),
            "alpha": a.get("total"), "alpha_on": a.get("scored_on"), "alpha_floor": h.get("alpha_floor"),
            "report": rep.isoformat() if rep else None, "drivers": (CO / cid / "drivers.yaml").exists(),
            "mcap_b": round(mcap, 2) if mcap else None, "adv_m": (lambda x: round(x, 1) if x is not None else None)(adv_m(cid, t, ctx["tv"])),
            "earnings": (dp.get("call") or {}).get("date"), "kill_written": bool(kc.strip()) or report_has_kill(ts),
            "killed": "킬" in close or st in ("킬",) or t.upper() in ctx.get("killed", set()),
            "last_info": (lambda d: d.isoformat() if d else None)(last_info(cid, t, rep, a.get("scored_on")))}


# ---------- 판정 ----------
def entry(f, c, today):
    """{기준: (True/False/None, 설명)} — None = 미확인"""
    e = c["entry"]
    def age(s):
        d = _d(s)
        return (today - d).days if d else None
    ra = age(f["report"])
    out = {
        "알파": (None if f["alpha"] is None else f["alpha"] >= e["alpha_min"], f"알파 {f['alpha']}" if f["alpha"] is not None else "알파 미산정"),
        "리서치": (bool((ra is not None and ra <= e["research_days"]) or f["drivers"]),
                 f"리포트 {f['report']}" if f["report"] else ("v2 밸류 동인 있음" if f["drivers"] else "리포트·밸류 동인 없음")),
        "시총": (None if f["mcap_b"] is None else f["mcap_b"] >= e["mcap_min_b"], f"시총 ${f['mcap_b']}B" if f["mcap_b"] is not None else "시총 미확인"),
        "유동성": (None if f["adv_m"] is None else f["adv_m"] >= e["adv_min_m"], f"거래대금 ${f['adv_m']}M/일" if f["adv_m"] is not None else "거래대금 미확인"),
        "실적 확인": (None if age(f["earnings"]) is None else age(f["earnings"]) <= e["earnings_days"],
                  f"최근 어닝콜 {f['earnings']}" if f["earnings"] else "어닝콜 기록 없음"),
        "킬 조건": (f["kill_written"] or not e.get("kill_required", True), "킬 조건 있음" if f["kill_written"] else "킬 조건 없음"),
    }
    return out


def entry_ok(f, c, today):
    return all(v is True for v, _ in entry(f, c, today).values())


def warnings(f, prev, c, today):
    """(경고 목록, 메모 목록)"""
    r, w, memo = c["review"], [], []
    floor = float(f.get("alpha_floor") or r["alpha_floor"])
    if f["killed"]:
        w.append("테제 훼손 — 킬 조건 발동")
    if f["alpha"] is not None:
        if f["alpha"] < floor:
            w.append(f"알파 {f['alpha']} < {floor}")
        if prev and prev.get("alpha") is not None and prev["alpha"] - f["alpha"] >= r["alpha_drop"] - 1e-9:
            w.append(f"알파 {prev['alpha']} → {f['alpha']}(직전 심사 대비 {prev['alpha'] - f['alpha']:.1f}점↓)")
    else:
        memo.append("알파 미산정")
    li = _d(f["last_info"])
    if li is None or (today - li).days > r["stale_days"]:
        w.append(f"장기 무변화 — 마지막 새 정보 {f['last_info'] or '없음'}")
    if r.get("entry_recheck", True):
        for k, (ok, why) in entry(f, c, today).items():
            if k == "알파":
                continue
            if ok is False:
                w.append(f"편입 기준 미충족 — {why}")
            elif ok is None:
                memo.append(why)
    return w, memo


def review(holdings, ctx, c, st, today):
    """→ (행 목록, 새 상태). 같은 ISO 주차 재실행은 연속 횟수를 늘리지 않는다"""
    wk = "%d-W%02d" % today.isocalendar()[:2]
    st = {"weeks": dict(st.get("weeks") or {}), "last": dict(st.get("last") or {})}
    rows = []
    for h in holdings:
        if h.get("status") != "관심":
            continue
        f = facts(h, today, ctx)
        last = st["last"].get(f["id"]) or {}
        base = last.get("base") if last.get("week") == wk else last.get("alpha")   # 비교 기준 = 직전 주차 심사의 알파
        ws, memo = warnings(f, {"alpha": base}, c, today)
        s = st["weeks"].get(f["id"]) or {"n": 0, "week": None}
        if s.get("week") != wk:
            s = {"n": s["n"] + 1 if ws else 0, "week": wk}
        st["weeks"][f["id"]] = s
        verdict = "제외 후보" if ws and s["n"] >= c["review"]["confirm_weeks"] else ("경고" if ws else "통과")
        rows.append({**f, "week": wk, "verdict": verdict, "streak": s["n"], "warnings": ws, "memo": memo,
                     "entry": {k: v for k, (v, _) in entry(f, c, today).items()}})
        st["last"][f["id"]] = {"week": wk, "alpha": f["alpha"], "verdict": verdict, "base": base}
    order = {"제외 후보": 0, "경고": 1, "통과": 2}
    rows.sort(key=lambda r: (order[r["verdict"]], r["ticker"]))
    return rows, st


def context(killed=()):
    rep, tk = reports()
    return {"alpha": (_j(M / "alpha" / "latest.json").get("rows") or {}), "reports": rep, "rep_tickers": tk, "kills": kills(), "tv": tv_quotes(), "killed": set(killed)}


def run(dry=False, today=None, killed=()):
    c = cfg()
    today = today or datetime.now(KST).date()
    holdings = yaml.safe_load(PORT.read_text(encoding="utf-8")).get("holdings") or []
    prev = _j(LATEST)
    rows, st = review(holdings, context(killed), c, _j(STATE), today)
    before = {r["id"]: r["verdict"] for r in prev.get("rows") or []}
    changes = [r for r in rows if before.get(r["id"]) != r["verdict"] and not (r["verdict"] == "통과" and r["id"] not in before)]
    out = {"as_of": today.isoformat(), "week": rows[0]["week"] if rows else None, "rows": rows,
           "changes": [{"ticker": r["ticker"], "from": before.get(r["id"]), "to": r["verdict"]} for r in changes],
           "proposals": _j(STATE.with_name("watch_proposals.json"), []),
           "note": "제외 후보는 마스터 승인 뒤에만 반영 — 자동 삭제 없음"}
    if not dry:
        LATEST.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
        STATE.parent.mkdir(parents=True, exist_ok=True)
        STATE.write_text(json.dumps(st, ensure_ascii=False, indent=1), encoding="utf-8")
        new = not LOG.exists()
        with LOG.open("a", encoding="utf-8", newline="") as f:
            w = csv.writer(f)
            if new:
                w.writerow(["date", "week", "id", "ticker", "verdict", "streak", "alpha", "warnings"])
            for r in rows:
                w.writerow([today.isoformat(), r["week"], r["id"], r["ticker"], r["verdict"], r["streak"], r["alpha"], " / ".join(r["warnings"])])
    return out


# ---------- 문장·표 ----------
def daily(out=None):
    """Daily '관심 종목 변동' 한두 문장 — 변화가 없으면 빈 문자열"""
    out = out or _j(LATEST)
    rows = {r["ticker"]: r for r in out.get("rows") or []}
    ch = out.get("changes") or []
    cand = [x for x in out.get("proposals") or [] if x.get("kind") == "편입 후보"]
    s = []
    rm = [c["ticker"] for c in ch if c["to"] == "제외 후보"]
    wn = [c["ticker"] for c in ch if c["to"] == "경고"]
    if rm:
        why = rows[rm[0]]["warnings"][0] if rows.get(rm[0], {}).get("warnings") else ""
        s.append(f"{', '.join(rm)}는 두 주 연속 경고가 이어져 제외 후보로 올렸습니다({why}). 승인해 주시면 관심 목록에서 뺍니다.")
    if wn:
        s.append(f"{', '.join(wn)}에는 이번 주 심사에서 경고가 붙었습니다. 다음 주에도 이어지면 제외 후보가 됩니다.")
    if cand:
        s.append(f"{', '.join(x['ticker'] for x in cand[:3])}는 알파는 높지만 편입 기준을 다 채우지 못해 후보로만 둡니다.")
    return " ".join(s[:2])


def table(out=None):
    """주간 리뷰용 전체 심사표(마크다운)"""
    out = out or _j(LATEST)
    ok = lambda v: "✓" if v is True else ("✗" if v is False else "?")   # noqa: E731
    ls = [f"관심 종목 심사 {out.get('week')} — 통과 {sum(r['verdict'] == '통과' for r in out['rows'])} · 경고 {sum(r['verdict'] == '경고' for r in out['rows'])} · "
          f"제외 후보 {sum(r['verdict'] == '제외 후보' for r in out['rows'])}", "",
          "| 종목 | 판정 | 연속 | 알파 | 리서치 | 시총 | 유동성 | 실적 확인 | 킬 조건 | 사유 |", "|---|---|---|---|---|---|---|---|---|---|"]
    for r in out["rows"]:
        e = r["entry"]
        why = " / ".join(r["warnings"]) or "—"
        if r["memo"]:
            why += " (메모: " + ", ".join(r["memo"]) + ")"
        ls.append(f"| {r['ticker']}{' (마스터 지정)' if r['pin'] else ''} | {r['verdict']} | {r['streak']} | {r['alpha'] if r['alpha'] is not None else '?'} | "
                  f"{ok(e['리서치'])} | {ok(e['시총'])} | {ok(e['유동성'])} | {ok(e['실적 확인'])} | {ok(e['킬 조건'])} | {why} |")
    ls += ["", "제외 후보는 마스터 승인 뒤에만 반영합니다(자동 삭제 없음). 보유 종목은 심사하지 않습니다."]
    return "\n".join(ls)


def apply(ids, today=None, port=PORT):
    """마스터 승인분만 status: 종료로(지우지 않는다). 마스터 세션에서만 부른다"""
    today = today or datetime.now(KST).date().isoformat()
    text = port.read_text(encoding="utf-8")
    rows = {r["id"]: r for r in _j(LATEST).get("rows") or []}
    done = []
    for iid in ids:
        m = re.search(rf"(?ms)^  - id: {re.escape(iid)}\n(.*?)(?=^  - id: |^\S)", text)
        if not m or "status: 관심" not in m[1]:
            continue
        why = " / ".join((rows.get(iid) or {}).get("warnings") or []) or "마스터 승인"
        body = re.sub(r"(?m)^    status: 관심[ \t]*$", f"    status: 종료\n    ended: {today}\n    ended_reason: \"마스터 승인 제외 — {why}\"", m[1], count=1)
        text = text[:m.start(1)] + body + text[m.end(1):]
        done.append(iid)
    if done:
        port.write_text(text, encoding="utf-8")
    return done


def main(argv):
    sys.stdout.reconfigure(encoding="utf-8")
    if "--daily" in argv:
        print(daily())
        return
    if "--table" in argv:
        print(table())
        return
    if "--apply" in argv:
        print(apply(argv[argv.index("--apply") + 1:]))
        return
    day = date.fromisoformat(argv[argv.index("--date") + 1]) if "--date" in argv else None
    out = run(dry="--dry" in argv, today=day)
    print(table(out))


if __name__ == "__main__":
    main(sys.argv[1:])
