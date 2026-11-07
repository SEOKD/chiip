"""Weekly Review 'Earnings 알파 점검' 절 (마스터 지시 2026-11-07 "매주 주중 어닝을 발표한 종목들을 점검하고 알파 평가 점수를 매긴 이후
6점 이상인 종목을 Watchlist에 넣고 Analysis 리포트를 적어라 … Weekly Review Report에도 관련 내용을 넣어라")

재료: scripts/discovery/earnings_sweep.py 요약(knowledge/models/discovery/earnings_sweep/<주차>.json). 모델은 weekly json에
  "earnings_alpha": {"read": "이번 주 점검 한 줄", "notes": {"<id>": "통과 종목 한 줄 — 왜 알파가 높은가(1차 자료)"}} 만 쓴다.
점검 결과 파일이 없으면 절을 싣지 않는다(판정할 수 없는 항목은 빼는 Weekly 원칙).
"""
import html
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "discovery"))
MKT = {"america": "미국", "korea": "한국", "japan": "일본", "taiwan": "대만"}


def load(week):
    try:
        import earnings_sweep
        return earnings_sweep.summary(week)
    except Exception:   # 점검 파일이 없거나 깨졌으면 절을 뺀다
        return None


def _universe(s):
    parts = [f"{MKT.get(m, m)} {n:,}" for m, n in (s.get("universe") or {}).items() if n]
    return " · ".join(parts) if parts else "발표 종목 수 미집계"


def head(s):
    return (f"발표 종목 {_universe(s)} → 정량 후보 풀 {s['pool']} → 정량 산정 {s.get('ranked') or 0} → 판단 {s['judged']} → "
            f"알파 {s['floor']:.0f}점 이상 {len(s['passed'])}종목(와치리스트 +{len(s['watchlist_added'])}, Analysis 리포트 대기열 +{len(s['report_queued'])})")


def md_lines(d):
    s = d.get("_earnings_alpha")
    if not s:
        return []
    ea = d.get("earnings_alpha") or {}
    notes = ea.get("notes") or {}
    L = ["", "## Earnings 알파 점검", "", head(s), ""]
    if ea.get("read"):
        L += [ea["read"], ""]
    if s["passed"]:
        L += ["| 종목 | 발표일 | 알파 | 정량 | 한 줄 |", "|---|---|---|---|---|"]
        L += [f"| {x['name']}({x['ticker']}) | {x.get('release') or '-'} | {x['alpha']:.1f} | {x['alpha_q'] if x.get('alpha_q') is not None else '-'} | {notes.get(x['id'], '')} |" for x in s["passed"]]
    else:
        L.append(f"이번 주는 알파 {s['floor']:.0f}점 이상 종목이 없다.")
    if s.get("near"):
        L += ["", "문턱 아래 1점 안: " + " · ".join(f"{x['name']}({x['ticker']}) {x['alpha']:.1f}" for x in s["near"])]
    L += ["", "알파 점수는 연구 후보 지표이며 투자 권유가 아니다."]
    return L


def html_section(d):
    s = d.get("_earnings_alpha")
    if not s:
        return ""
    e = lambda x: html.escape(str(x))
    ea = d.get("earnings_alpha") or {}
    notes = ea.get("notes") or {}
    rows = "".join(f"<tr><td>{e(x['name'])}<br><small>{e(x['ticker'])}</small></td><td>{e(x.get('release') or '-')}</td><td>{x['alpha']:.1f}</td>"
                   f"<td>{e(x['alpha_q']) if x.get('alpha_q') is not None else '-'}</td><td>{e(notes.get(x['id'], ''))}</td></tr>" for x in s["passed"])
    body = (f'<div class="tw"><table><tr><th>종목</th><th>발표일</th><th>알파</th><th>정량</th><th>한 줄</th></tr>{rows}</table></div>' if rows
            else f"<p>이번 주는 알파 {s['floor']:.0f}점 이상 종목이 없다.</p>")
    near = ("<p class=\"note\">문턱 아래 1점 안: " + " · ".join(f"{e(x['name'])}({e(x['ticker'])}) {x['alpha']:.1f}" for x in s["near"]) + "</p>") if s.get("near") else ""
    read = f"<p>{e(ea['read'])}</p>" if ea.get("read") else ""
    return (f'<section><h2>Earnings 알파 점검</h2><p class="k">{e(head(s))}</p>{read}{body}{near}'
            f'<p class="note">알파 점수는 연구 후보 지표이며 투자 권유가 아니다. 통과 종목은 Portfolio 와치리스트에 넣고 Analysis 리포트를 차례로 쓴다.</p></section>')
