"""Portfolio '내 종목' 장부 — IB 포트폴리오 매니저식 체계 관리 (마스터 지시 2026-11-20 "내 종목에는 실제 내 포지션과 와치리스트가
모두 포함돼야 한다. 내가 직접 넣은 종목도 알파 점수가 낮으면 빼도록 하라. 월스트리트 IB 포트폴리오 매니저라고 가정하고 체계적으로
내 종목을 관리하도록 하라")

장부 = config/portfolio.yaml의 보유 + 관심(누가 넣었든 — 마스터 직접·pin·Chiip 자동·실적 점검). 매 Portfolio 회차에 결정론으로 판정하고,
모델은 결과를 Daily에 옮겨 적고 재채점이 필요한 종목의 알파 판단만 쓴다.

판정 순서(PM 북 리뷰):
  1. 신선도   알파(knowledge/models/alpha/latest.json)가 없거나 stale_days(config/alpha.yaml, 14일)보다 오래면 '재채점' — 모르는 숫자로 빼지 않는다.
              재채점 대상은 그 회차에 tenbagger-card 알파 루브릭으로 judgments를 쓰고 `py scripts/alpha/score.py --finalize` 뒤 다시 돌린다.
  2. 관심     신선한 알파 < 문턱(config/watchlist.yaml add.alpha_min, 6.0)이면 '제외' — 마스터가 직접 넣은 종목·pin도 같다
              (2026-11-20 지시가 2026-11-17 'pin 유지'·2026-11-13 '제외는 승인 뒤'를 대체). --apply가 status: 종료·ended·end_reason을 쓴다.
              리포트 규칙 등급 킬 조건 발동(composite why '킬')도 제외.
  3. 보유     실제 포지션은 빼지 않는다(마스터 몫). 알파 < 문턱이면 '투자 논리 재점검' — 킬 조건·다음 확인 사건을 Daily에 적는다.
              매도·비중·금액 지시는 쓰지 않는다(치입은 투자자문이 아니다).
  4. 유지     나머지. 알파 변화(delta)·리포트 등급·업사이드·다음 실적일을 함께 보여 준다.
마스터 포지션 수량·평단 파일은 읽지 않는다.
출력: knowledge/models/portfolio/book_latest.json · 기록 knowledge/models/portfolio/book_log.csv(제외·재점검 판정일 지표 — 성적표 재료)
사용: py scripts/portfolio/book.py            # 판정만(JSON 요약)
      py scripts/portfolio/book.py --apply    # 관심 '제외'를 config/portfolio.yaml에 반영
      py scripts/portfolio/book.py --md       # Daily용 표
"""
import csv
import json
import re
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
PORT = ROOT / "config" / "portfolio.yaml"
M = ROOT / "knowledge" / "models"
OUT = M / "portfolio" / "book_latest.json"
LOG = M / "portfolio" / "book_log.csv"
KST = timezone(timedelta(hours=9))
LOG_FIELDS = ["date", "id", "ticker", "status", "verdict", "alpha", "scored_on", "grade", "upside", "added_by", "pin", "reason"]


def jload(p, default):
    try:
        return json.loads(Path(p).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def settings():
    a = yaml.safe_load((ROOT / "config" / "alpha.yaml").read_text(encoding="utf-8")) or {}
    w = yaml.safe_load((ROOT / "config" / "watchlist.yaml").read_text(encoding="utf-8")) or {}
    return {"stale_days": int(a.get("stale_days", 14)), "alpha_min": float((w.get("add") or {}).get("alpha_min", 6.0))}


def next_earnings(today):
    out = {}
    for e in (jload(M / "earnings" / "fiscal_calendar.json", {}).get("events") or []):
        t = (e.get("ticker") or "").upper()
        if t and e.get("date") and e["date"] >= today.isoformat():
            out[t] = min(out.get(t, e["date"]), e["date"])
    return out


def judge(holdings, alpha_rows, calls, killed, cfg, today, earn=None):
    rows = []
    earn = earn or {}
    for h in holdings:
        if h.get("status") not in ("보유", "관심"):
            continue
        r = alpha_rows.get(h["id"]) or {}
        tot, so = r.get("total"), str(r.get("scored_on") or "")[:8]
        try:
            age = (today - datetime.strptime(so, "%Y%m%d").date()).days
        except ValueError:
            age = None
        c = calls.get(h["id"]) or {}
        row = {"id": h["id"], "ticker": h.get("ticker"), "name": h.get("name"), "status": h["status"], "added_by": h.get("added_by") or "master",
               "pin": bool(h.get("pin")), "alpha": tot, "delta": r.get("delta"), "scored_on": so or None, "age": age,
               "grade": c.get("grade_now"), "upside": c.get("upside"), "next_earnings": earn.get((h.get("ticker") or "").upper())}
        fresh = tot is not None and age is not None and age <= cfg["stale_days"]
        low = fresh and tot < cfg["alpha_min"] - 1e-9
        if h["status"] == "관심" and killed.get(h["id"]):
            row.update(verdict="제외", reason="킬 조건 발동")
        elif not fresh:
            row.update(verdict="재채점", reason="알파 없음" if tot is None else f"알파 {age}일 전 산정(기준 {cfg['stale_days']}일)")
        elif h["status"] == "관심" and low:
            row.update(verdict="제외", reason=f"알파 {tot:.2f} < {cfg['alpha_min']:.1f}")
        elif h["status"] == "보유" and low:
            row.update(verdict="재점검", reason=f"보유 · 알파 {tot:.2f} < {cfg['alpha_min']:.1f} — 투자 논리·킬 조건 점검")
        else:
            row.update(verdict="유지", reason=f"알파 {tot:.2f}")
        rows.append(row)
    order = {"제외": 0, "재점검": 1, "재채점": 2, "유지": 3}
    return sorted(rows, key=lambda x: (order[x["verdict"]], x["status"] != "보유", -(x["alpha"] or 0)))


def load_inputs():
    port = yaml.safe_load(PORT.read_text(encoding="utf-8")) or {}
    alpha = jload(M / "alpha" / "latest.json", {}).get("rows") or {}
    calls = jload(M / "portfolio" / "buy_call_latest.json", {}).get("calls") or {}
    killed = {r["id"]: True for r in (jload(M / "portfolio" / "composite_latest.json", {}).get("rows") or [])
              if r.get("id") and "킬" in " ".join(r.get("why") or [])}
    return port.get("holdings") or [], alpha, calls, killed


def run(today=None):
    today = today or datetime.now(KST).date()
    hs, alpha, calls, killed = load_inputs()
    rows = judge(hs, alpha, calls, killed, settings(), today, next_earnings(today))
    out = {"as_of": today.isoformat(), "rule": settings(), "rows": rows,
           "count": {v: sum(1 for r in rows if r["verdict"] == v) for v in ("유지", "재점검", "재채점", "제외")},
           "rescore": [r["id"] for r in rows if r["verdict"] == "재채점"]}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    return out


def _log(rows, day):
    new = not LOG.exists()
    with LOG.open("a", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=LOG_FIELDS, extrasaction="ignore")
        if new:
            w.writeheader()
        for r in rows:
            w.writerow({**r, "date": day})


def end_block(text, cid, day, reason):
    """config/portfolio.yaml에서 그 종목 블록의 status: 관심 → 종료, ended·end_reason 줄을 더한다(주석·다른 블록은 그대로)"""
    m = re.search(rf"(?m)^  - id: {re.escape(cid)}\s*$", text)
    if not m:
        return text, False
    nxt = re.search(r"(?m)^  - id: ", text[m.end():])
    end = m.end() + nxt.start() if nxt else len(text)
    block = text[m.start():end]
    s = re.search(r"(?m)^(\s+)status:\s*관심\b[^\n]*$", block)
    if not s:
        return text, False
    ind = s.group(1)
    new = (block[:s.start()] + f"{ind}status: 종료\n{ind}ended: {day}\n{ind}end_reason: \"{reason} — 장부 자동 제외(마스터 지시 2026-11-20)\""
           + block[s.end():])
    return text[:m.start()] + new + text[end:], True


def apply(out):
    day = out["as_of"]
    gone = [r for r in out["rows"] if r["verdict"] == "제외" and r["status"] == "관심"]
    text = PORT.read_text(encoding="utf-8")
    done = []
    for r in gone:
        text, ok = end_block(text, r["id"], day, r["reason"])
        if ok:
            done.append(r)
    if done:
        PORT.write_text(text, encoding="utf-8", newline="\n")
        _log(done, day)
    flagged = [r for r in out["rows"] if r["verdict"] == "재점검"]
    if flagged:
        _log(flagged, day)
    return done


def md(out):
    L = [f"| 종목 | 구분 | 판정 | 알파(변화) | 산정일 | 리포트 등급·업사이드 | 다음 실적 | 사유 |", "|---|---|---|---|---|---|---|---|"]
    for r in out["rows"]:
        a = "?" if r["alpha"] is None else f"{r['alpha']:.2f}" + (f"({r['delta']:+.2f})" if isinstance(r.get("delta"), (int, float)) and r["delta"] else "")
        g = "" if not r.get("grade") else f"{r['grade']}" + (f" {r['upside'] * 100:+.0f}%" if isinstance(r.get("upside"), (int, float)) else "")
        L.append(f"| {r['ticker']} | {r['status']}{'·직접' if r['added_by'] == 'master' else ''} | {r['verdict']} | {a} | {r['scored_on'] or '-'} | {g or '-'} | "
                 f"{r.get('next_earnings') or '-'} | {r['reason']} |")
    return "\n".join(L)


def main(argv):
    sys.stdout.reconfigure(encoding="utf-8")
    out = run()
    if "--md" in argv:
        print(md(out))
        return 0
    if "--apply" in argv:
        done = apply(out)
        if done:
            out = run()
        print(json.dumps({"removed": [f"{r['ticker']} ({r['reason']})" for r in done], **out["count"], "rescore": out["rescore"]}, ensure_ascii=False))
        return 0
    print(json.dumps({**out["count"], "rescore": out["rescore"],
                      "rows": [f"{r['ticker']} {r['status']} {r['verdict']} — {r['reason']}" for r in out["rows"]]}, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
