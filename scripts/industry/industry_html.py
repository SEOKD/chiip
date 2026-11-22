"""Chiip Industry Report 렌더 (마스터 지시 2026-11-08) — 블록·그림·용어 풀이·금액 표기는 텐배거 렌더러(report_html)를 그대로 쓴다

순서: 제목 → 산업 판단 등급 → Chiip View → 대시보드 → 한 장 요약 → 한눈에 보기 → 본론(event_frame 여덟 단계) → 출처·면책.
사용: py scripts/industry/industry_html.py <리포트 json>   → 같은 이름 .html과 _artifact.html
"""
import html
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tenbagger"))
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "radar"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import report_html as rh  # noqa: E402

DISCLAIMER = ("산업 판단 등급(Attractive·In-Line·Cautious)은 규칙이 계산한 산업 판단이며 개별 종목 매매·비중·금액 지시가 아니다 · "
              "정치·정책 판단은 공개 자료 기반 가설이고 법률 판단이 아니다 · 공개 자료 기반 분석이며 투자 권유가 아님 · Chiip Industry Report")
TONE = {"Attractive": "red", "Cautious": "blue", "In-Line": ""}


# 주기별 머리 표기(2026-11-15 점검 — 주간 리포트에 '사건 때 심층'이 찍히던 결함)
CYCLE = {"weekly": "주간 산업", "quarterly": "분기 결산"}


def render(d):
    for key in ("title", "date", "industry", "event"):
        if not d.get(key):
            raise ValueError(f"필수 항목 없음: {key}")
    if d.get("cycle") == "weekly":   # 주간 산업 리포트는 IB 자료 출처를 리포트 제목만으로(2026-11-22 마스터 지시 — radar/notion_library.py title_cites)
        sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "radar"))
        import notion_library
        d = notion_library.title_cites_obj(d)
    d = rh.scrub(json.loads(rh.plain(json.dumps(d, ensure_ascii=False))))
    t = rh.t
    parts = [f'<!doctype html><html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
             f'<title>Chiip Industry Report</title><style>{rh.CSS}</style></head><body><div class="w">',
             f'<h1>{t(d["title"])}' + (f'<br><span style="font-size:16px">{t(d["subtitle"])}</span>' if d.get("subtitle") else "") + "</h1>",
             f'<p class="lead">{t(d["date"])} · Chiip Industry Report · {CYCLE.get(d.get("cycle"), "사건 때 심층")} · 산업: {t(d["industry"])} · {"사건" if d.get("cycle") not in CYCLE else "주제"}: {t(d["event"])}'
             + (f' · 부가가치: {t(" · ".join(d["value_add"]))}' if d.get("value_add") else "") + "</p>"]
    if d.get("ratings"):
        parts.append('<div class="dash">' + "".join(
            f'<div><div class="k">{t(r["name"])}</div><div class="v {TONE.get(r["rating"], "")}">{t(r["rating"])}</div><div class="s">산업 판단 등급</div></div>' for r in d["ratings"]) + "</div>")
    parts.append(f'<div class="verdict"><b>Chiip View</b><br>{t((d.get("verdict") or {}).get("view"))}</div>')
    if d.get("tiles"):
        parts.append('<div class="dash">' + "".join(
            f'<div><div class="k">{t(x.get("k"))}</div><div class="v {x.get("tone", "")}">{t(x.get("v"))}</div><div class="s">{t(x.get("sub"))}</div></div>' for x in d["tiles"]) + "</div>")
    if d.get("summary"):
        parts.append("<h2>한 장 요약</h2><div class=\"ans\">" + "".join(f'<div><b class="q">{t(s.get("q"))}</b>{t(s.get("a"))}</div>' for s in d["summary"]) + "</div>")
    figs = [c for c in d.get("gallery") or [] if rh.CHARTS.get(c.get("kind"))]
    if figs:
        parts.append("<h2>한눈에 보기</h2><div class=\"gal\">" + "".join(f"<div>{rh.block({'type': 'chart', 'chart': c})}</div>" for c in figs) + "</div>")
    names = [str(s.get("h2")) for s in d.get("sections") or []]
    parts.append('<nav class="toc">' + "".join(f'<a href="#s{i}">{t(n)}</a>' for i, n in enumerate(names)) + "</nav>")
    for i, s in enumerate(d.get("sections") or []):
        parts.append(f"<section id=\"s{i}\"><h2>{t(s.get('h2'))}</h2>" + "".join(rh.block(b) for b in s.get("blocks") or []) + "</section>")
    src = "; ".join(t(x) for x in d.get("sources") or [])
    parts.append(f'<div class="foot">출처: {src or "미기재"}<br>{DISCLAIMER}</div></div>{rh.FIT_JS}</body></html>')
    return rh.money_units(rh.fx_units(rh.chiip_name("".join(parts).replace("치입 판단", "Chiip View"))))


def artifact_html(d):
    full = render(d)
    style = re.search(r"<style>.*?</style>", full, re.S).group(0)
    body = re.search(r"<body>(.*)</body>", full, re.S).group(1)
    name = f"Chiip Industry {str(d['date'])[5:].replace('-', '·')}"
    return f'<title>{html.escape(name)}</title>\n<meta name="claude:viewport-fit-sides" content="cover">\n{style}\n{body}\n'


def main(argv):
    sys.stdout.reconfigure(encoding="utf-8")
    p = Path(argv[0])
    d = json.loads(p.read_text(encoding="utf-8"))
    p.with_suffix(".html").write_text(render(d), encoding="utf-8")
    a = p.with_name(p.stem + "_artifact.html")
    a.write_text(artifact_html(d), encoding="utf-8")
    print(f"[Industry Report] {p.with_suffix('.html')} · {a}")
    # 시각물 하한(2026-11-22 마스터 지시 "시각물이 부족하다. 시각물을 많이 만들어 가독성을 높여라") — 11·22 주간은 표 25개·그래프 0개였다
    import auto_charts as AC
    n = AC.count(d)
    if n < AC.MIN_CHARTS:
        print(f"[시각물 부족] 그래프 {n}개 < {AC.MIN_CHARTS}개 — 데이터팩 charts에 본문 숫자로 그래프를 더하고 다시 조립한다(scripts/industry/auto_charts.py)")
    if not d.get("tiles"):
        print("[시각물 부족] 머리 수치 타일(tiles)이 없다 — 데이터팩 tiles에 핵심 숫자 4~5개")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
