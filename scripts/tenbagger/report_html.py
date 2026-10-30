"""텐배거 일일 리포트 HTML 렌더러 (마스터 지시 2026-10-29 "Chiip ten-bagger도 텐배거 종목 리포트를 쓰고 그래프로 시각화해
체계적인 자료를 html 파일로 남겨라. 오후 11시마다 하루 하나씩")

모델(예약 작업 chiip-tenbagger-report)은 내용만 JSON으로 쓰고, 모양·차트는 이 스크립트가 늘 같은 방식으로 그린다.
문자열 안의 **굵게**만 <b>로 바꾸고 나머지 HTML은 모두 이스케이프한다(수집한 웹 문장이 섞여도 스크립트가 끼어들지 않게).
사용: py scripts/tenbagger/report_html.py outputs/tenbagger/reports/20261029_CBRS.json   → 같은 이름 .html

JSON 구조(필수 = *):
{ "title"*, "subtitle", "date"*, "ticker"*, "company"*, "biz"* (사업 1줄), "lead",
  "verdict": {"view"*: "치입 판단 한 줄", "confidence": "고|중|저", "insight": 7, "alpha": 6.1},
  "summary": [{"q": "질문", "a": "답(**굵게** 가능)"}],
  "tiles": [{"k": "이름", "v": "값", "sub": "설명", "tone": "red|grn|blue|"}],
  "sections": [{"h2"*: "제목", "blocks": [블록...]}],
  "sources": ["출처 1", ...] }
블록 종류: {"type":"p","text"} · {"type":"ul","items":[...]} · {"type":"hl","text"} · {"type":"h3","text"}
  · {"type":"table","headers":[...],"rows":[[...]...]}
  · {"type":"chart","chart":{"kind":"line","title","unit","log":false,"series":[{"name","color":"a|b|c|d|e","points":[["2025-03",12.3,"설명"]...]}]}}
  · {"type":"chart","chart":{"kind":"bars","title","unit","categories":[...],"series":[{"name","color","values":[...]}]}}
  · {"type":"chart","chart":{"kind":"hbars","title","unit","rows":[{"label","bars":[{"name","color","value"}]}]}}
  · {"type":"chart","chart":{"kind":"scenario","title","unit","current":112.6,"cases":[{"name":"약세","value":60,"prob":0.3,"color":"b","why":"…"}]}}
  · {"type":"chart","chart":{"kind":"candle","title","unit","bars":[["2026-10-28",600,609.4,581.8,606.9]...],
       "hlines":[{"y":643.4,"label":"38.2% 643","color":"e"}],"zones":[{"y0":599,"y1":602,"label":"지지","tone":"grn|red"}]}}  — 한국식 색(상승 빨강·하락 파랑)
  · {"type":"chart","chart":{"kind":"revision","title","unit","start","end","series":[{"name","color","points":[["2026-02-26",4.2]...]}],
       "events":[{"date","mark":"①","kind":"실적|내러티브","tag","pct":"+110%"}]}}  — 날짜 축 계단선 + 사건 깃발(revision_view.py가 만든다)
  · bars에 "stack": true면 쌓인 막대
  · 차트에 "pin": n이면 갤러리 n번째로 고정(그림 3 = 가격 내포 기대, 5 = EPS 리비전 추이, 8 = 주가 분해 — 마스터 지시 2026-10-30), 나머지는 절 순서대로
금액 단위는 렌더 직후 radar/units.py money_units로 $25B·$M·$T 표기로 바꾼다(마스터 지시 2026-10-29).
학술 논문 표기('저자 연도')는 남기지 않는다(마스터 지시 2026-10-30) — scrub()이 괄호째 지우고 출처 목록에서 빼며, 그래도 남으면 렌더가 실패한다.
데이터 제공처 이름(재무·컨센서스·어닝콜 스크립트를 가져온 곳)도 남기지 않는다. 본문 아래 부가 설명(차트·표 note, 업사이드 기준, 읽는 법)은 그리지 않는다(같은 날 마스터 지시).
전문 용어·기관 약자는 처음 나오는 곳에 '용어(한국어 풀이)'로 적는다 — config/report_glossary.yaml, gloss().
"""
import html
import json
import math
import re
import sys
from datetime import date
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "radar"))
from units import chiip_name, money_units  # noqa: E402

COLORS = {"a": "var(--a)", "b": "var(--b)", "c": "var(--c)", "d": "var(--d)", "e": "var(--e)"}
CSS = """:root{--bg:#fff;--fg:#1a1d23;--mut:#5d6470;--line:#e6e8ec;--card:#f6f8fb;--a:#1a1d23;--b:#d0452f;--c:#2a5bd7;--d:#1f8a5b;--e:#b07d10;--hl:#fff5d6}
@media (prefers-color-scheme:dark){:root:not([data-theme=light]){--bg:#14161a;--fg:#e8eaee;--mut:#9aa1ad;--line:#2b2f36;--card:#1c1f25;--a:#f2f3f5;--b:#ff7d66;--c:#7aa2ff;--d:#4cc38a;--e:#e0b04a;--hl:#2e2a1c;color-scheme:dark}}
:root[data-theme=dark]{--bg:#14161a;--fg:#e8eaee;--mut:#9aa1ad;--line:#2b2f36;--card:#1c1f25;--a:#f2f3f5;--b:#ff7d66;--c:#7aa2ff;--d:#4cc38a;--e:#e0b04a;--hl:#2e2a1c;color-scheme:dark}
body{margin:0;background:var(--bg);color:var(--fg);font-family:-apple-system,'Apple SD Gothic Neo','Malgun Gothic',sans-serif;line-height:1.65;font-size:15px}.w{max-width:820px;margin:0 auto;padding-block:20px 48px;padding-left:max(16px,env(safe-area-inset-left,0px));padding-right:max(16px,env(safe-area-inset-right,0px))}
h1{font-size:21px;margin:0 0 4px;line-height:1.35}h2{font-size:18px;margin:30px 0 8px;padding-top:10px;border-top:2px solid var(--fg)}h3{font-size:15.5px;margin:18px 0 6px}
.lead{color:var(--mut);font-size:13.5px;margin:0 0 12px}.card{background:var(--card);border-radius:12px;padding:12px 14px;margin:12px 0}.hl{background:var(--hl);border-radius:12px;padding:12px 14px;margin:12px 0}
.ans{display:grid;grid-template-columns:1fr;gap:8px}.ans div{background:var(--card);border-radius:10px;padding:10px 12px}.ans b.q{display:block;font-size:12.5px;color:var(--mut)}
table{border-collapse:collapse;width:100%;font-size:13px;margin:6px 0}th,td{border-bottom:1px solid var(--line);padding:6px 5px;text-align:right;vertical-align:top}th:first-child,td:first-child{text-align:left}th{color:var(--mut);font-weight:600}
.tw{overflow-x:auto}.mut{color:var(--mut)}.sm{font-size:12.5px}.red{color:var(--b)}.blue{color:var(--c)}.grn{color:var(--d)}
/* 그래프 한 줄에 하나(마스터 지시 2026-10-30 "가로 한 줄에 두 개라 작게 보인다") */.gal{display:grid;grid-template-columns:1fr;gap:8px}.gal>div{min-width:0}
.tiles{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:8px;margin:10px 0}.tile{background:var(--card);border-radius:10px;padding:10px 12px}.tile .v{font-size:20px;font-weight:700}.tile .k{font-size:12px;color:var(--mut)}
svg{display:block;width:100%;height:auto}svg text{fill:var(--mut);font-size:10.5px}.lg{font-size:12.5px;color:var(--mut)}.lg i{display:inline-block;width:10px;height:10px;border-radius:2px;margin:0 4px 0 8px;vertical-align:-1px}
ul{padding-left:20px;margin:6px 0}li{margin:3px 0}.foot{color:var(--mut);font-size:12px;margin-top:26px;overflow-wrap:anywhere}.verdict{border:2px solid var(--fg);border-radius:12px;padding:12px 14px;margin:12px 0}
.badge{display:inline-block;font-size:12px;border:1px solid var(--line);border-radius:6px;padding:0 6px;margin-right:4px;color:var(--mut)}"""
DISCLAIMER = "연구 후보이지 매수 권유가 아닙니다 · 공개 자료 기반 분석이며 투자 권유가 아님 · 1차 판정, 미검증 · Chiip ten-bagger"


def t(s):
    """이스케이프 후 **굵게**만 허용"""
    return re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", html.escape(str(s if s is not None else "")))


def _legend(series):
    return '<div class="lg">' + "".join(f'<i style="background:{COLORS.get(s.get("color", "c"), "var(--c)")}"></i>{t(s["name"])}' for s in series) + "</div>"


def _fmt(v):
    if v is None:
        return "-"
    return f"{v:,.0f}" if abs(v) >= 100 else (f"{v:,.1f}" if abs(v) >= 10 else f"{v:,.2f}")


def chart_line(c):
    W, H, L, R, T, B = 700, 260, 48, 14, 14, 26
    series = c.get("series") or []
    keys = sorted({p[0] for s in series for p in s.get("points") or []})
    vals = [p[1] for s in series for p in s.get("points") or [] if p[1] is not None]
    if not keys or not vals:
        return ""
    log = bool(c.get("log")) and min(vals) > 0
    lo, hi = (min(vals), max(vals))
    if log:
        lo, hi = math.log10(lo) - 0.1, math.log10(hi) + 0.1
    else:
        pad = (hi - lo) * 0.1 or abs(hi) * 0.1 or 1
        lo, hi = min(0, lo - pad) if lo >= 0 else lo - pad, hi + pad
    X = lambda k: L + (keys.index(k) / max(len(keys) - 1, 1)) * (W - L - R)
    Y = lambda v: T + (hi - (math.log10(v) if log else v)) / (hi - lo) * (H - T - B)
    g = []
    for i in range(5):
        v = lo + (hi - lo) * i / 4
        real = 10 ** v if log else v
        g.append(f'<line x1="{L}" x2="{W - R}" y1="{Y(real):.1f}" y2="{Y(real):.1f}" stroke="var(--line)"/><text x="{L - 4}" y="{Y(real) + 3:.1f}" text-anchor="end">{_fmt(real)}</text>')
    step = max(1, len(keys) // 8)
    for i, k in enumerate(keys):
        if i % step == 0 or i == len(keys) - 1:
            g.append(f'<text x="{X(k):.1f}" y="{H - 6}" text-anchor="middle">{t(k)}</text>')
    for s in series:
        col = COLORS.get(s.get("color", "c"), "var(--c)")
        pts = [p for p in s.get("points") or [] if p[1] is not None]
        g.append(f'<polyline fill="none" stroke="{col}" stroke-width="2" points="{" ".join(f"{X(p[0]):.1f},{Y(p[1]):.1f}" for p in pts)}"/>')
        for p in pts:
            note = f" · {p[2]}" if len(p) > 2 and p[2] else ""
            g.append(f'<circle cx="{X(p[0]):.1f}" cy="{Y(p[1]):.1f}" r="4" fill="{col}" stroke="var(--bg)" stroke-width="2"><title>{t(s["name"])} {t(p[0])}: {_fmt(p[1])}{t(c.get("unit", ""))}{t(note)}</title></circle>')
    return _legend(series) + f'<svg viewBox="0 0 {W} {H}">{"".join(g)}</svg>'


def chart_stack(c):
    """쌓인 막대(양수만) — 범주가 많으면 x축 이름을 솎아 낸다"""
    W, H, L, B, T = 700, 250, 48, 30, 18
    cats, series = c.get("categories") or [], c.get("series") or []
    tots = [sum((s.get("values") or [0] * len(cats))[i] or 0 for s in series) for i in range(len(cats))]
    if not cats or not any(tots):
        return ""
    hi = max(tots) * 1.1
    Y = lambda v: T + (hi - v) / hi * (H - T - B)
    gw = (W - L - 10) / len(cats)
    g = [f'<line x1="{L}" x2="{W - 10}" y1="{Y(0):.1f}" y2="{Y(0):.1f}" stroke="var(--line)"/>']
    for i in range(5):
        v = hi * i / 4
        g.append(f'<text x="{L - 4}" y="{Y(v) + 3:.1f}" text-anchor="end">{_fmt(v)}</text>')
    step = max(1, len(cats) // 10)
    for ci, cat in enumerate(cats):
        x, base = L + ci * gw + 1, 0.0
        for s in series:
            v = (s.get("values") or [None] * len(cats))[ci]
            if not v:
                continue
            col = COLORS.get(s.get("color", "c"), "var(--c)")
            g.append(f'<rect x="{x:.1f}" y="{Y(base + v):.1f}" width="{max(gw - 2, 1):.1f}" height="{max(Y(base) - Y(base + v), 0.5):.1f}" fill="{col}"><title>{t(s["name"])} {t(cat)}: {_fmt(v)}{t(c.get("unit", ""))}</title></rect>')
            base += v
        if ci % step == 0:
            g.append(f'<text x="{x + gw / 2:.1f}" y="{H - 10}" text-anchor="middle" style="font-size:9.5px">{t(cat)}</text>')
    return _legend(series) + f'<svg viewBox="0 0 {W} {H}">{"".join(g)}</svg>'


def chart_candle(c):
    """캔들(OHLC) + 수평선·구간 띠. 한국식 색 — 상승(종가 ≥ 시가) 빨강, 하락 파랑"""
    bars = [b for b in c.get("bars") or [] if len(b) >= 5 and None not in b[1:5]]
    if not bars:
        return ""
    W, H, L, R, T, B = 700, 300, 52, 96, 12, 26
    lo = min(min(b[3] for b in bars), *[h["y"] for h in c.get("hlines") or []] or [math.inf], *[z["y0"] for z in c.get("zones") or []] or [math.inf])
    hi = max(max(b[2] for b in bars), *[h["y"] for h in c.get("hlines") or []] or [-math.inf], *[z["y1"] for z in c.get("zones") or []] or [-math.inf])
    pad = (hi - lo) * 0.04 or 1
    lo, hi = lo - pad, hi + pad
    Y = lambda v: T + (hi - v) / (hi - lo) * (H - T - B)
    gw = (W - L - R) / len(bars)
    g = []
    for i in range(5):
        v = lo + (hi - lo) * i / 4
        g.append(f'<line x1="{L}" x2="{W - R}" y1="{Y(v):.1f}" y2="{Y(v):.1f}" stroke="var(--line)"/><text x="{L - 4}" y="{Y(v) + 3:.1f}" text-anchor="end">{_fmt(v)}</text>')
    for z in c.get("zones") or []:
        col = "var(--d)" if z.get("tone") == "grn" else "var(--b)"
        g.append(f'<rect x="{L}" y="{Y(z["y1"]):.1f}" width="{W - L - R}" height="{max(Y(z["y0"]) - Y(z["y1"]), 2):.1f}" fill="{col}" opacity="0.16"><title>{t(z.get("label"))} {_fmt(z["y0"])}~{_fmt(z["y1"])}</title></rect>')
    for h in c.get("hlines") or []:
        col = COLORS.get(h.get("color", "e"), "var(--e)")
        g.append(f'<line x1="{L}" x2="{W - R}" y1="{Y(h["y"]):.1f}" y2="{Y(h["y"]):.1f}" stroke="{col}" stroke-dasharray="4 3"/>'
                 f'<text x="{W - R + 4}" y="{Y(h["y"]) + 3:.1f}" style="font-size:9.5px">{t(h.get("label"))}</text>')
    step = max(1, len(bars) // 8)
    for i, (d, o, hh, ll, cl) in enumerate(b[:5] for b in bars):
        x = L + i * gw + gw / 2
        col = "var(--b)" if cl >= o else "var(--c)"
        g.append(f'<line x1="{x:.1f}" x2="{x:.1f}" y1="{Y(hh):.1f}" y2="{Y(ll):.1f}" stroke="{col}"/>'
                 f'<rect x="{x - max(gw * 0.35, 0.6):.1f}" y="{Y(max(o, cl)):.1f}" width="{max(gw * 0.7, 1.2):.1f}" height="{max(abs(Y(o) - Y(cl)), 0.8):.1f}" fill="{col}">'
                 f'<title>{t(d)} 시 {_fmt(o)} 고 {_fmt(hh)} 저 {_fmt(ll)} 종 {_fmt(cl)}</title></rect>')
        if i % step == 0:
            g.append(f'<text x="{x:.1f}" y="{H - 8}" text-anchor="middle" style="font-size:9.5px">{t(str(d)[2:])}</text>')
    return f'<svg viewBox="0 0 {W} {H}">{"".join(g)}</svg>'


def chart_revision(c):
    """날짜 축 계단선 + 사건 깃발. 사건마다 번호·변화율을 그림에 직접 쓴다(모바일은 마우스오버가 없다)"""
    series = c.get("series") or []
    vals = [p[1] for s in series for p in s.get("points") or [] if p[1] is not None]
    if not vals:
        return ""
    d0, d1 = date.fromisoformat(c["start"]), date.fromisoformat(c["end"])
    span = (d1 - d0).days or 1
    W, H, L, R, T, B = 440, 340, 34, 10, 70, 22   # 휴대폰 폭에서 글자가 읽히게 좁은 좌표계(마스터는 모바일로 본다)
    X = lambda s: L + (date.fromisoformat(str(s)[:10]) - d0).days / span * (W - L - R)
    lo, hi = min(0, min(vals)), max(vals) * 1.08 or 1
    Y = lambda v: T + (hi - v) / (hi - lo) * (H - T - B)
    g = []
    for i in range(5):
        v = lo + (hi - lo) * i / 4
        g.append(f'<line x1="{L}" x2="{W - R}" y1="{Y(v):.1f}" y2="{Y(v):.1f}" stroke="var(--line)"/><text x="{L - 4}" y="{Y(v) + 3:.1f}" text-anchor="end">{_fmt(v)}</text>')
    y, m = d0.year, d0.month
    while date(y, m, 1) <= d1:
        if date(y, m, 1) >= d0 and m % 2 == 0:
            x = X(date(y, m, 1).isoformat())
            g.append(f'<text x="{x:.1f}" y="{H - 6}" text-anchor="middle" style="font-size:9.5px">{str(y)[2:]}-{m:02d}</text>')
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    for i, e in enumerate(c.get("events") or []):
        x = X(e["date"])
        col = "var(--c)" if e.get("kind") == "실적" else "var(--e)"
        ty = 13 + (i % 4) * 15   # 가까운 사건이 겹치지 않게 네 줄로 엇갈린다
        pct = str(e.get("pct") or "")
        tag = f'{e.get("mark")} {pct}' if pct not in ("", "+0%", "-0%", "0%", "-", "겹침") else str(e.get("mark"))   # 변화가 없으면 번호만 — 표에 전부 있다
        tx = min(max(x, L + 14), W - R - 16)
        g.append(f'<line x1="{x:.1f}" x2="{x:.1f}" y1="{ty + 3}" y2="{H - B}" stroke="{col}" stroke-dasharray="3 3" opacity="0.75"/>'
                 f'<text x="{tx:.1f}" y="{ty}" text-anchor="middle" style="fill:{col};font-size:11.5px;font-weight:700">{t(tag)}'
                 f'<title>{t(e["date"])} {t(e.get("tag"))} {t(e.get("pct"))}</title></text>')
    for s in series:
        col = COLORS.get(s.get("color", "c"), "var(--c)")
        pts = [p for p in s.get("points") or [] if p[1] is not None]
        path, prev = [], None
        for p in pts:
            if prev is not None:
                path.append(f"{X(p[0]):.1f},{Y(prev):.1f}")
            path.append(f"{X(p[0]):.1f},{Y(p[1]):.1f}")
            prev = p[1]
        path.append(f"{X(c['end']):.1f},{Y(prev):.1f}")
        g.append(f'<polyline fill="none" stroke="{col}" stroke-width="2.2" points="{" ".join(path)}"/>')
        g.append(f'<text x="{X(c["end"]) - 2:.1f}" y="{Y(prev) - 5:.1f}" text-anchor="end" style="fill:{col};font-size:11px;font-weight:700">{_fmt(prev)}</text>')
        for p in pts:
            g.append(f'<circle cx="{X(p[0]):.1f}" cy="{Y(p[1]):.1f}" r="3" fill="{col}"><title>{t(s["name"])} {t(p[0])}: {_fmt(p[1])}</title></circle>')
    return _legend(series) + f'<svg viewBox="0 0 {W} {H}">{"".join(g)}</svg>'


def chart_bars(c):
    if c.get("stack"):
        return chart_stack(c)
    W, H, L, B, T = c.get("w", 700), 250, 48, 30, 18
    cats, series = c.get("categories") or [], c.get("series") or []
    vals = [v for s in series for v in s.get("values") or [] if v is not None]
    if not cats or not vals:
        return ""
    lo, hi = min(0, min(vals)), max(0, max(vals)) * 1.15 or 1
    Y = lambda v: T + (hi - v) / (hi - lo) * (H - T - B)
    gw = (W - L - 10) / len(cats)
    bw = max(4, (gw - 10) / max(len(series), 1))
    g = [f'<line x1="{L}" x2="{W - 10}" y1="{Y(0):.1f}" y2="{Y(0):.1f}" stroke="var(--line)"/>']
    for i in range(5):
        v = lo + (hi - lo) * i / 4
        g.append(f'<text x="{L - 4}" y="{Y(v) + 3:.1f}" text-anchor="end">{_fmt(v)}</text>')
    for ci, cat in enumerate(cats):
        x0 = L + ci * gw + 5
        for si, s in enumerate(series):
            v = (s.get("values") or [None] * len(cats))[ci]
            if v is None:
                continue
            col = COLORS.get(s.get("color", "c"), "var(--c)")
            y, h = (Y(v), Y(0) - Y(v)) if v >= 0 else (Y(0), Y(v) - Y(0))
            x = x0 + si * bw
            g.append(f'<rect x="{x:.1f}" y="{y:.1f}" width="{bw - 2:.1f}" height="{max(h, 1):.1f}" rx="2" fill="{col}"><title>{t(s["name"])} {t(cat)}: {_fmt(v)}{t(c.get("unit", ""))}</title></rect>')
            if len(series) <= 3:
                g.append(f'<text x="{x + (bw - 2) / 2:.1f}" y="{(y - 3) if v >= 0 else (y + h + 10):.1f}" text-anchor="middle" style="font-size:9.5px">{_fmt(v)}</text>')
        g.append(f'<text x="{x0 + gw / 2 - 5:.1f}" y="{H - 10}" text-anchor="middle" style="font-size:9.5px">{t(cat)}</text>')
    return _legend(series) + f'<svg viewBox="0 0 {W} {H}">{"".join(g)}</svg>'


def chart_hbars(c):
    """가로 막대 — 음수도 그린다(0 기준선 왼쪽). 항목 이름이 긴 그래프(콜 변화 항목 등)를 위해 이름 칸을 넓게(2026-10-30)"""
    rows = c.get("rows") or []
    vals = [b.get("value") or 0 for r in rows for b in r.get("bars") or []]
    if not rows or not vals:
        return ""
    W, L, R = c.get("w", 700), c.get("label_w", 180), 56
    hi, lo = max(max(vals), 0), min(min(vals), 0)
    span = (hi - lo) * 1.12 or 1
    base = lo * 1.12   # 음수가 있으면 왼쪽 여유를 두고 0 기준선을 오른쪽으로 민다
    X = lambda v: L + ((v - base) if lo < 0 else max(v, 0)) / span * (W - L - R)
    x0 = X(0)
    names = []
    for r in rows:
        for b in r.get("bars") or []:
            if b["name"] not in [n["name"] for n in names]:
                names.append({"name": b["name"], "color": b.get("color", "c")})
    g, y = [], 10
    for r in rows:
        bars = r.get("bars") or []
        g.append(f'<text x="{L - 8}" y="{y + 8 * len(bars) + 4}" text-anchor="end" style="fill:var(--fg);font-size:12px">{t(r["label"])}</text>')
        for b in bars:
            v = b.get("value") or 0
            col = COLORS.get(b.get("color", "c"), "var(--c)")
            x1, x2 = sorted((x0, X(v)))
            g.append(f'<rect x="{x1:.1f}" y="{y}" width="{max(2, x2 - x1):.1f}" height="14" rx="3" fill="{col}"><title>{t(r["label"])} {t(b["name"])}: {_fmt(b.get("value"))}{t(c.get("unit", ""))}</title></rect>'
                     + (f'<text x="{x2 + 4:.1f}" y="{y + 11}">{_fmt(b.get("value"))}</text>' if v >= 0 else
                        f'<text x="{x1 - 4:.1f}" y="{y + 11}" text-anchor="end">{_fmt(b.get("value"))}</text>'))
            y += 17
        y += 14
    if lo < 0:
        g.append(f'<line x1="{x0:.1f}" x2="{x0:.1f}" y1="4" y2="{y - 6}" stroke="var(--mut)" stroke-dasharray="3 3"/>')
    return _legend(names) + f'<svg viewBox="0 0 {W} {y + 4}">{"".join(g)}</svg>'


def chart_scenario(c):
    cases = c.get("cases") or []
    if not cases:
        return ""
    cur = c.get("current")
    W, L, R = 700, 120, 70
    mx = max([k.get("value") or 0 for k in cases] + [cur or 0]) * 1.1 or 1
    X = lambda v: L + v / mx * (W - L - R)
    g, y = [], 10
    for k in cases:
        col = COLORS.get(k.get("color", "c"), "var(--c)")
        mult = f" ({k['value'] / cur:.1f}배)" if cur else ""
        prob = f" · 확률 {k['prob'] * 100:.0f}%" if k.get("prob") is not None else ""
        g.append(f'<text x="{L - 6}" y="{y + 12}" text-anchor="end" style="fill:var(--fg);font-size:12px">{t(k["name"])}</text>'
                 f'<rect x="{L}" y="{y}" width="{max(2, X(k["value"]) - L):.1f}" height="16" rx="3" fill="{col}"><title>{t(k["name"])}: {_fmt(k["value"])}{t(c.get("unit", ""))}{mult}{prob} — {t(k.get("why", ""))}</title></rect>'
                 f'<text x="{X(k["value"]) + 4:.1f}" y="{y + 12}">{_fmt(k["value"])}{mult}{prob}</text>')
        y += 26
    if cur:
        g.append(f'<line x1="{X(cur):.1f}" x2="{X(cur):.1f}" y1="4" y2="{y}" stroke="var(--fg)" stroke-dasharray="4 3"/><text x="{X(cur) + 4:.1f}" y="{y + 12}">현재 {_fmt(cur)}</text>')
        ev = sum((k.get("prob") or 0) * k["value"] for k in cases)
        if ev and abs(sum(k.get("prob") or 0 for k in cases) - 1) < 0.02:
            g.append(f'<text x="{L}" y="{y + 26}" style="fill:var(--fg)">확률 가중 {_fmt(ev)} ({ev / cur:.2f}배)</text>')
            y += 14
    return f'<svg viewBox="0 0 {W} {y + 18}">{"".join(g)}</svg>'


CHARTS = {"line": chart_line, "bars": chart_bars, "hbars": chart_hbars, "scenario": chart_scenario, "candle": chart_candle, "revision": chart_revision}


def figures(d):
    """그림 번호 순서 [(절, 블록)…] — pin이 있는 차트를 그 번호에 꽂고 나머지는 절 순서대로. HTML 갤러리·마크다운·노션이 같은 번호를 쓴다"""
    figs = [(s, b) for s in d.get("sections") or [] for b in s.get("blocks") or [] if b.get("type") == "chart" and CHARTS.get((b.get("chart") or {}).get("kind"))]
    pinned = sorted((f for f in figs if f[1]["chart"].get("pin")), key=lambda f: f[1]["chart"]["pin"])
    out = [f for f in figs if not f[1]["chart"].get("pin")]
    for f in pinned:
        out.insert(min(f[1]["chart"]["pin"] - 1, len(out)), f)
    return out


def block(b):
    k = b.get("type")
    if k == "p":
        return f"<p>{t(b.get('text'))}</p>"
    if k == "h3":
        return f"<h3>{t(b.get('text'))}</h3>"
    if k == "hl":
        return f'<div class="hl sm">{t(b.get("text"))}</div>'
    if k == "ul":
        return "<ul>" + "".join(f"<li>{t(i)}</li>" for i in b.get("items") or []) + "</ul>"
    if k == "table":
        head = "".join(f"<th>{t(h)}</th>" for h in b.get("headers") or [])
        rows = "".join("<tr>" + "".join(f"<td>{t(c)}</td>" for c in r) + "</tr>" for r in b.get("rows") or [])
        cap = f"<b>{t(b['title'])}</b>" if b.get("title") else ""
        return f'<div class="card tw">{cap}<table><tr>{head}</tr>{rows}</table></div>'
    if k == "chart":
        c = b.get("chart") or {}
        fn = CHARTS.get(c.get("kind"))
        if not fn:
            return ""
        return f'<div class="card"><b>{t(c.get("title"))}</b>{fn(c)}</div>'
    return ""


# 내부 약어 → 풀어 쓴 말(마스터 지시 2026-10-29 "v2 기본이 뭐였더라? 암호로 해놓으면 직관적으로 못 알아보니 의미를 풀어서 표기하라")
PLAIN = [("DCF(v2, ", "DCF("), ("v2 기본 시나리오", "DCF 기본 시나리오"), ("v2 기본", "DCF 내재가치(기본)"), ("v2 강세", "DCF 내재가치(강세)"), ("v2 약세", "DCF 내재가치(약세)"),
         ("MC P50", "몬테카를로 중앙값"), ("MC 기대", "몬테카를로 기대값"), ("v2 엔진", "현금흐름 할인(DCF) 엔진"), ("v2 DCF", "DCF"),
         ("v2 결과", "DCF 결과"), ("v2의", "DCF의"), ("(v2,", "(DCF,"), ("v2 ", "DCF ")]


def plain(s):
    for a, b in PLAIN:
        s = s.replace(a, b)
    return s


# 양식에 참고 문헌을 남기지 않는다(마스터 지시 2026-10-30 "양식에 'Greenwood & Hanson 2015' 같은 참고 자료 출처를 남기지 마라") — 저자 목록은 저장소 인용에서 뽑았다
REF_NAMES = r"Bessembinder|Greenwood|Mauboussin|Damodaran|Shiller|Bhojraj|Rhodes-Kropf|Boehmer|Lakonishok|LeBaron|Osler|Asquith|Karceski|Yartseva|Rappaport|Peduzzi"
REF_JOURNAL = r"JFE|QJE|JF|RFS|JFQA|JPE|AER|FRBNY|Journal of Finance"
REF_PAREN = re.compile(rf"\s*[(（][^()（）]*(?:\b(?:{REF_NAMES})\b|(?<!\d)(?:19|20)\d\d(?!\d)[^()（）]*\b(?:{REF_JOURNAL})\b)[^()（）]*[)）]")
REF_CITE = re.compile(rf"\b(?:{REF_NAMES})\b[^.。;]{{0,40}}(?<!\d)(?:19|20)\d\d(?!\d)")   # 한글 조사가 붙어도 잡히게 \b 대신 숫자 경계


def _scrub_text(x):
    return REF_PAREN.sub("", x) if isinstance(x, str) else x


def _walk(o, fn):
    if isinstance(o, dict):
        return {k: _walk(v, fn) for k, v in o.items()}
    if isinstance(o, list):
        return [_walk(v, fn) for v in o]
    return fn(o)


# 데이터 제공처 이름을 남기지 않는다(마스터 지시 2026-10-30 "재무 데이터와 컨센서스 데이터, 어닝콜 스크립트를 가져온 출처를 남기지 마라") — 구분이 필요한 곳은 '모델 추정'·'애널리스트 추정'
VENDOR_RE = re.compile(r"Fiscal\.ai|fiscal\.ai|Zacks|zacks|easyconomics|ir_events|company_estimates")
VENDOR_SUBS = [(re.compile(r"\s*\[?\(?Data provided by Zacks Investment Research, Inc\.,?\s*\[?www\.zacksdata\.com\]?(?:\([^)]*\))?\)?\.?"), ""),
               (re.compile(r"[,·]?\s*(?:Fiscal\.ai\s*)?(?:company_)?(?:ir_events(?:_transcript)?|estimates)(?:\s*q\d-\d{4})?"), ""),
               (re.compile(r"\s*\(https?://www\.zacksdata\.com\)"), ""),
               (re.compile(r"(?:Fiscal\.ai|Fiscal)\s*(?:자체\s*)?추정"), "모델 추정"),
               (re.compile(r"Zacks\s*(?:컨센서스|추정)"), "애널리스트 추정"),
               (re.compile(r"Zacks\s*(의견|목표가)"), r"애널리스트 \1"),
               (re.compile(r"Zacks(?=\s*[$CF\d])"), "애널리스트 추정"),
               (re.compile(r"\(Fiscal\)"), "(모델 추정)"),
               (re.compile(r"(?<![A-Za-z])Fiscal(?=\s*\$)"), "모델 추정"),
               (re.compile(r"(?:Fiscal\.ai|Zacks)\s*(?:일별 배수|재무|일봉|장기 월봉|개요|표준화)?\s*(?:기준)?\s*"), ""),
               (re.compile(r"(?<![A-Za-z])Fiscal(?![A-Za-z ]*[Yy]ear)"), "모델"),
               (re.compile(r"\s*[(（]\s*[)）]"), "")]
NOT_SOURCE = re.compile(r"Fiscal|fiscal\.ai|Zacks|zacks|트랜스크립트|easyconomics|보강 적용")


def _strip_vendor(x):
    if not isinstance(x, str):
        return x
    for pat, rep in VENDOR_SUBS:
        x = pat.sub(rep, x)
    return x


def _glossary():
    return yaml.safe_load((ROOT / "config" / "report_glossary.yaml").read_text(encoding="utf-8"))["terms"]


_YEAR = re.compile(r"(?<![A-Za-z0-9])(CY|FY)(20\d\d)(?![A-Za-z0-9(（])")
_URL = re.compile(r"(https?://\S+)")


def gloss_text(s, terms, pat, seen):
    """처음 나온 용어 뒤에 (풀이). 바로 뒤에 괄호가 있으면 이미 풀이된 것으로 본다. 주소는 건드리지 않는다"""
    def one(m):
        w = m.group(0)
        if w in seen:
            return w
        after = m.string[m.end():m.end() + 2]
        if after[:1] in ("(", "（"):
            if after[1:2].isdigit() or after[1:2] in ("+", "-", "−", "$", "~"):
                return w   # '멀티플(−54%)'처럼 숫자 괄호면 다음에 나오는 곳에서 풀이한다
            seen.add(w)
            return w
        seen.add(w)
        return f"{w}({terms[w]})"

    def year(m):
        key = m.group(1)
        if key in seen:
            return m.group(0)
        seen.add(key)
        return f"{m.group(0)}({'캘린더' if key == 'CY' else '회계연도'} {m.group(2)}년)"
    out = []
    for part in _URL.split(s):
        out.append(part if _URL.fullmatch(part) else _YEAR.sub(year, pat.sub(one, part)))
    return "".join(out)


def gloss(d):
    """읽는 순서대로(Chiip View → 요약 → 본문 글·표) 용어를 처음 나오는 곳에서 풀이한다. 숫자 타일·차트 글자는 건드리지 않는다"""
    terms = _glossary()
    names = sorted(terms, key=len, reverse=True)
    pat = re.compile(r"(?<![A-Za-z0-9/.\-])(?:" + "|".join(re.escape(x) for x in names) + r")(?![A-Za-z0-9/\-])")
    seen = set()
    g = lambda x: gloss_text(x, terms, pat, seen) if isinstance(x, str) else x
    if d.get("verdict"):
        d["verdict"]["view"] = g(d["verdict"].get("view"))
    for s in d.get("summary") or []:
        s["a"] = g(s.get("a"))
    for sec in d.get("sections") or []:
        for b in sec.get("blocks") or []:
            k = b.get("type")
            if k in ("p", "hl", "h3"):
                b["text"] = g(b.get("text"))
            elif k == "ul":
                b["items"] = [g(i) for i in b.get("items") or []]
            elif k == "table":
                b["rows"] = [[g(c) for c in r] for r in b.get("rows") or []]
    return d


def scrub(d):
    """참고 문헌·데이터 제공처·읽는 법 문단을 지우고 용어를 풀이한다. 괄호 밖에 인용이나 제공처가 남으면 ValueError — 모델이 문장을 고쳐야 한다"""
    d = {**d, "sources": [x for x in d.get("sources") or [] if not REF_CITE.search(str(x)) and not NOT_SOURCE.search(str(x))]}
    d.pop("lead", None)
    d = _walk(_walk(d, _scrub_text), _strip_vendor)
    for s in d.get("sections") or []:
        s["blocks"] = [b for b in s.get("blocks") or [] if not (b.get("type") in ("p", "hl") and str(b.get("text")).startswith(("**읽는 법", "리비전 출처")))]
    body = json.dumps(d, ensure_ascii=False)
    left = REF_CITE.search(body) or VENDOR_RE.search(body)
    if left:
        raise ValueError(f"남기면 안 되는 표기가 있다: {body[max(0, left.start() - 30):left.end() + 30]}")
    return gloss(d)


def upside(d):
    """Chiip View 업사이드(+%) — verdict.upside가 있으면 그것, 없으면 판단 시나리오 확률 가중값 ÷ 현재값 − 1(기간은 시나리오 제목)"""
    v = d.get("verdict") or {}
    if v.get("upside") is not None:
        return v["upside"], v.get("upside_basis") or ""
    sc = next((b["chart"] for s in d.get("sections") or [] for b in s.get("blocks") or []
               if b.get("type") == "chart" and (b.get("chart") or {}).get("kind") == "scenario"), None)
    if not sc or not sc.get("current") or not sc.get("cases"):
        return None, ""
    ew = sum(float(c.get("prob") or 0) * float(c.get("value") or 0) for c in sc["cases"])
    return ew / float(sc["current"]) - 1, f"판단 시나리오 확률 가중 · {sc.get('title', '')}"


def render(d):
    for key in ("title", "date", "ticker", "company", "biz"):
        if not d.get(key):
            raise ValueError(f"필수 항목 없음: {key}")
    d = scrub(json.loads(plain(json.dumps(d, ensure_ascii=False))))
    v = d.get("verdict") or {}
    parts = [f'<!doctype html><html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
             f'<title>{t(d["company"])} 텐배거 리포트</title><style>{CSS}</style></head><body><div class="w">',
             f'<h1>{t(d["title"])}' + (f'<br><span style="font-size:16px">{t(d["subtitle"])}</span>' if d.get("subtitle") else "") + "</h1>",
             f'<p class="lead">{t(d["date"])} · {t(d["company"])}({t(d["ticker"])}) · 기업: {t(d["biz"])}</p>']
    if v:   # 마스터 지시 2026-10-29: 확신도 → 컨빅션(같은 고·중·저), 인사이트 → 알파(같은 10점 체계), 업사이드 +% 추가
        up, _ = upside(d)
        alpha = v.get("insight") if v.get("insight") is not None else v.get("alpha")
        badges = "".join(f'<span class="badge">{t(x)}</span>' for x in (
            f"컨빅션 {v['confidence']}" if v.get("confidence") else None,
            f"알파 {alpha}/10" if alpha is not None else None,
            f"업사이드 {up:+.0%}" if up is not None else None) if x)
        parts.append(f'<div class="verdict"><b>Chiip View</b> {badges}<br>{t(v.get("view"))}</div>')
    if d.get("summary"):
        parts.append("<h2>한 장 요약</h2><div class=\"ans\">" + "".join(
            f'<div><b class="q">{t(s.get("q"))}</b>{t(s.get("a"))}</div>' for s in d["summary"]) + "</div>")
    if d.get("tiles"):
        parts.append('<div class="tiles">' + "".join(
            f'<div class="tile"><div class="k">{t(x.get("k"))}</div><div class="v {x.get("tone", "")}">{t(x.get("v"))}</div><div class="k">{t(x.get("sub"))}</div></div>'
            for x in d["tiles"]) + "</div>")
    # 그래프 전체를 상단에(마스터 지시 2026-10-29 "Chiip View와 한 장 요약 다음 시각물 그래프를 전부 — 시간이 없을 때 상단만 보고 파악")
    figs = figures(d)
    num = {id(b): i for i, (_, b) in enumerate(figs, 1)}
    if figs:
        parts.append("<h2>한눈에 보기 — 그래프 전체</h2><div class=\"gal\">" + "".join(
            f'<div id="fig{num[id(b)]}">' + block(b).replace("<b>", f'<b>그림 {num[id(b)]} · ', 1) + "</div>"
            for _, b in figs) + "</div>")
    for s in d.get("sections") or []:
        body = "".join(
            (f'<p class="sm mut">📊 <a href="#fig{num[id(b)]}">그림 {num[id(b)]}</a> · {t((b.get("chart") or {}).get("title"))} (위 \'한눈에 보기\')</p>'
             if id(b) in num else block(b)) for b in s.get("blocks") or [])
        parts.append(f"<h2>{t(s.get('h2'))}</h2>" + body)
    src = "; ".join(t(x) for x in d.get("sources") or [])
    parts.append(f'<div class="foot">출처: {src or "미기재"}<br>{DISCLAIMER}</div></div></body></html>')
    out = chiip_name("".join(parts).replace("치입 판단", "Chiip View").replace("Chiip 판단", "Chiip View"))   # GitHub·텔레그램 보고 표기(마스터 지시 2026-10-29)
    return money_units(out)   # $25B·$M·$T 표기(마스터 지시 2026-10-29)


def artifact_html(d):
    """claude.ai 비공개 Artifact 판(마스터 지시 2026-10-30 "리포트 링크는 html로" — 모바일에서 그대로 보이는 보기 링크).
    게시 때 문서 뼈대가 씌워지므로 doctype·html·head·body를 빼고, 이름 같은 짧은 <title>과 옆 여백 약속 메타를 맨 위에 둔다."""
    full = render(d)
    style = re.search(r"<style>.*?</style>", full, re.S).group(0)
    body = re.search(r"<body>(.*)</body>", full, re.S).group(1)
    name = f"{d['ticker']} 텐배거 리포트 {str(d['date'])[5:].replace('-', '·')}"
    return f'<title>{html.escape(name)}</title>\n<meta name="claude:viewport-fit-sides" content="cover">\n{style}\n{body}\n'


def main(argv):
    sys.stdout.reconfigure(encoding="utf-8")
    src = Path(argv[0])
    d = json.loads(src.read_text(encoding="utf-8"))
    out = src.with_suffix(".html")
    out.write_text(render(d), encoding="utf-8")
    print(f"[텐배거 리포트] {out} ({out.stat().st_size // 1024}KB)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
