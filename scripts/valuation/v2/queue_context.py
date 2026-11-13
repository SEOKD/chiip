"""Valuation Queue·Analysis 판단 전 맥락 묶음 (마스터 지시 2026-11-14 "Quantral → Valuation Queue", ADR-032)

결정론(모델 없음). 이미 쌓이고 있지만 Valuation Queue가 읽지 않던 출력을 종목·시장 단위로 한데 모은다.
  --company <id>  ① Quantral 관심(radar/social_surge.py 집계 knowledge/models/social/latest.json — 급증 Z·관심 점수·채널별 최근 건수·과밀)
                  ② Quantral 주간 리테일 순위(outputs/quantral/<주차>_data.json·_report.json — 순위·언급 수·Quantral 이야기 제목·묶음 테마)
                  ③ IB 커버리지 장부(scripts/valuation/v2/ib_actions.py — 최근 목표가·의견 변경)
  --market        ④ 미국 PPI·CPI 최근 발표(knowledge/models/trade_ppi/history.json·macro/cpi.json) ⑤ 한국 수출(macro/kr_exports.json)
                  ⑥ IPO 감시(config/ipo_watch.yaml 상태)
  --note <id>     동인 notes·내러티브 파일에 붙일 한 줄(커뮤니티 관심 — 펀더멘털 아님)
커뮤니티 경계(ADR-011·ADR-032): 여기서 읽는 Quantral 자료는 집계(건수·점수·sourceType별 비중)와 Quantral 이야기 제목뿐이다. 작성자·글 본문·링크는 없다.
gather.py가 원천 `queue_context`(종목)·`macro_ipo`(시장)로 부른다 — Pulse·Portfolio·Analysis·Valuation Queue 모두 데이터 허브로 같이 본다.
"""
import json
import sys
from datetime import date
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[3]
SOC = ROOT / "knowledge" / "models" / "social" / "latest.json"
QOUT = ROOT / "outputs" / "quantral"
NAMES = {"x": "X", "reddit": "레딧", "youtube": "유튜브", "substack": "서브스택", "insider": "내부자 매수", "congress": "의회 매매"}
sys.path.insert(0, str(Path(__file__).resolve().parent))


def _j(p, default=None):
    try:
        return json.loads(Path(p).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def ticker_of(eid):
    dp = _j(ROOT / "knowledge" / "models" / "companies" / eid / "datapack.json", {}) or {}
    t = dp.get("ticker")
    if not t:
        r = ((_j(SOC, {}) or {}).get("rows") or {}).get(eid) or {}
        t = r.get("ticker")
    if not t and eid.startswith("us-"):
        t = eid[3:].upper()
    return str(t or "").upper()


def social(eid):
    """Quantral 관심 집계 한 줄 묶음 — 없으면 None"""
    d = _j(SOC, {}) or {}
    r = (d.get("rows") or {}).get(eid)
    if not r:
        return None
    ch = r.get("channels") or {}
    recent = {NAMES.get(k, k): int(v.get("recent_n") or 0) for k, v in ch.items() if v.get("recent_n")}
    return {"as_of": d.get("as_of"), "Z": r.get("Z"), "score": r.get("score"), "attention": r.get("attention"),
            "alert": r.get("alert"), "q7": r.get("q7"), "sent7": r.get("sent7"), "recent": recent,
            "crowded": bool(r.get("q7") and float(r["q7"]) >= 70 and (r.get("Z") or 0) < 1)}


def weekly(ticker, weeks=None):
    """가장 최근 Quantral 주간 순위에서 이 티커 — {week, rank, posts, rxs_share, stories, themes} 또는 None"""
    files = sorted(QOUT.glob("*_data.json"), reverse=True)[: weeks or 2]
    for p in files:
        d = _j(p, {}) or {}
        row = next((r for r in d.get("rows") or [] if str(r.get("ticker", "")).upper() == ticker), None)
        if not row:
            continue
        rp = _j(QOUT / f"{d.get('week')}_report.json", {}) or {}
        if "시험" in str(rp.get("as_of", "")) + str(rp.get("headline", "")):   # 개발 중 시험 출력(2026-11-12 W46)은 판단에 넣지 않는다
            continue
        themes = [t.get("name") for t in rp.get("themes") or [] if ticker in [str(x).upper() for x in t.get("tickers") or []]]
        note = (rp.get("notes") or {}).get(ticker) or {}
        return {"week": d.get("week"), "period": d.get("period"), "rank": row.get("rank"), "posts": row.get("posts"),
                "rxs_share": row.get("rxs_share"), "stories": [s.get("headline") for s in row.get("stories") or []][:3],
                "themes": themes, "narrative": note.get("narrative"), "n": len(d.get("rows") or [])}
    return None


def ib(eid):
    try:
        import ib_actions
        return "; ".join(ib_actions.fmt(r) for r in ib_actions.recent(eid)) or None
    except Exception:   # 장부 없음·형식 오류 — 맥락이 없을 뿐 멈추지 않는다
        return None


def note_line(eid):
    """동인 notes·내러티브 파일용 한 줄 — 관심의 크기와 방향만, 펀더멘털 아님을 붙인다"""
    s, w = social(eid), weekly(ticker_of(eid))
    parts = []
    if s and s.get("Z") is not None:
        parts.append(f"관심 급증 {s['score']}/10(결합 Z {s['Z']:+.1f}, 알파 관심 요소 {s['attention']})" + (" · 과밀(관심 높고 증가 멈춤)" if s["crowded"] else ""))
    if w:
        parts.append(f"리테일 관심 {w['week']} {w['rank']}위(이야기 게시 {w['posts']}건" + (f", 테마 {'·'.join(w['themes'])}" if w["themes"] else "") + ")")
    if not parts:
        return None
    return f"커뮤니티 관심(Quantral, {date.today().isoformat()}): " + " · ".join(parts) + " — 관심은 시장 기대의 증거이지 펀더멘털이 아니다."


def company_lines(eid):
    out = [f"[queue_context] {eid} {ticker_of(eid)}"]
    s = social(eid)
    if s:
        rec = ", ".join(f"{k} {v}" for k, v in s["recent"].items()) or "최근 언급 없음"
        out.append(f"Quantral 관심({s['as_of']}): 급증 {s['score']}/10, 결합 Z {s['Z']:+.2f}, 알파 v2 관심 요소 {s['attention']}, Quantral 7일 점수 {s['q7']}, "
                   f"7일 감성 {s['sent7']}, 최근 창 {rec}" + (" · 경보" if s["alert"] else "") + (" · 과밀" if s["crowded"] else ""))
    else:
        out.append("Quantral 관심: 집계 없음(social_surge 대상 밖 — Pulse가 --due로 고른 종목만 받는다)")
    w = weekly(ticker_of(eid))
    if w:
        out.append(f"Quantral 주간 리테일 순위 {w['week']}({w['period']}): {w['rank']}위/{w['n']}, 이야기 게시 {w['posts']}건, Reddit·X·Substack 비중 {w['rxs_share']}, "
                   f"Quantral 이야기 제목 {w['stories']}" + (f", 묶음 테마 {w['themes']}" if w["themes"] else "") + (f", 리테일 내러티브(치입 요약) {w['narrative']}" if w["narrative"] else ""))
    else:
        out.append("Quantral 주간 리테일 순위: 최근 2주 상위권 밖")
    r = ib(eid)
    out.append(f"IB 커버리지 장부: {r}" if r else "IB 커버리지 장부: `py scripts/valuation/v2/ib_actions.py --show " + eid + "`로 확인(최근 변경 없음 또는 장부 없음)")
    return out


def market_lines():
    out = ["[macro_ipo] 거시 지표 발표·IPO 감시"]
    h = _j(ROOT / "knowledge" / "models" / "trade_ppi" / "history.json", {}) or {}
    try:
        import importlib
        sys.path.insert(0, str(ROOT / "radar"))
        pr = importlib.import_module("ppi_release")
        us = h.get("us_raw") or {}
        months = sorted({m for s in us.values() for m in s})
        if months:
            out.append("PPI: " + pr.summary(us, [r for r in h.get("revisions") or [] if r.get("market") == "us"][-5:], months[-1]))
        cr = importlib.import_module("cpi_release")
        c = cr.load()
        if c.get("raw"):
            m = max(p for s in c["raw"].values() for p in s)
            out.append("CPI: " + cr.summary(c["raw"], m, c.get("revisions") or []))
        ke = importlib.import_module("kr_exports")
        k = ke.load()
        if k.get("releases"):
            m = max(k["releases"])
            out.append("한국 수출: " + ke.summary(m, k["releases"][m]))
        if k.get("gaps"):
            out.append(f"한국 수출 공백: {k['gaps'][-1]['why']}")
    except Exception as exc:   # 한 지표가 깨져도 나머지는 낸다
        out.append(f"거시 지표 읽기 실패: {type(exc).__name__}: {str(exc)[:80]}")
    ipo = yaml.safe_load((ROOT / "config" / "ipo_watch.yaml").read_text(encoding="utf-8")) or {}
    rows = ipo.get("companies") or []
    act = [r for r in rows if r.get("status") in ("filed", "reported")]
    out.append(f"IPO 감시 {len(rows)}곳 중 서류 제출·추진 보도 {len(act)}곳: " + "; ".join(f"{r['name']}({r['status']}) {str(r.get('why', ''))[:90]}" for r in act))
    return out


def main(argv):
    sys.stdout.reconfigure(encoding="utf-8")
    if len(argv) >= 2 and argv[0] == "--company":
        print("\n".join(company_lines(argv[1])))
        return 0
    if argv and argv[0] == "--market":
        print("\n".join(market_lines()))
        return 0
    if len(argv) >= 2 and argv[0] == "--note":
        print(note_line(argv[1]) or "커뮤니티 관심: 집계 없음")
        return 0
    print(__doc__)
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
