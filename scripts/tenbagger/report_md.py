"""텐배거 리포트 → GitHub에서 그대로 보이는 마크다운 + 차트 SVG (마스터 지시 2026-10-30 "리포트 결과물을 볼 수 있는 github 링크를 제공해야지.
비공개 저장소 링크를 누르니 코드밖에 안 뜬다")

GitHub는 비공개 저장소의 HTML을 소스로만 보여 주지만, 마크다운과 그 안의 그림(같은 저장소 상대 경로)은 로그인한 화면에서 그려 준다(모바일 포함).
그래서 리포트 JSON을 마크다운(report_notion.render — 노션 판과 같은 글)으로 옮기고, 차트는 report_html이 그린 SVG를 꺼내
CSS 변수(var(--x))를 밝은 테마 색으로 바꾸고 범례·배경을 넣은 독립 SVG 파일로 만든다. 새 패키지 없음.
사용: py scripts/tenbagger/report_md.py <리포트 json>   → <같은 이름>.md · charts/<같은 이름>_<n>.svg, 출력 JSON {md, charts}
"""
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import report_html  # noqa: E402
import report_notion  # noqa: E402

LIGHT = dict(re.findall(r"--(\w+):(#[0-9a-fA-F]{3,6})", report_html.CSS.split("}")[0]))
FONT = "-apple-system,'Apple SD Gothic Neo','Malgun Gothic',sans-serif"


def standalone(c):
    """차트 하나 → 독립 SVG 문자열(그릴 수 없으면 None)"""
    fn = report_html.CHARTS.get(c.get("kind"))
    if not fn:
        return None
    out = fn(c)
    m = re.search(r'<svg viewBox="0 0 ([\d.]+) ([\d.]+)">(.*)</svg>', out, re.S)
    if not m:
        return None
    w, h, inner = float(m.group(1)), float(m.group(2)), m.group(3)
    legend, x, y = [], 8.0, 14.0
    for col, name in re.findall(r'<i style="background:var\(--(\w+)\)"></i>([^<]*)', out):
        step = 22 + 6.5 * len(name)
        if x + step > w and x > 8:
            x, y = 8.0, y + 16
        legend.append(f'<rect x="{x:.0f}" y="{y - 9:.0f}" width="10" height="10" rx="2" fill="var(--{col})"/>'
                      f'<text x="{x + 14:.0f}" y="{y:.0f}" style="font-size:12px">{name}</text>')
        x += step
    top = (y + 8) if legend else 0
    svg = (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w:.0f} {h + top:.0f}" width="{w:.0f}" height="{h + top:.0f}">'
           f'<style>text{{fill:{LIGHT.get("mut", "#5d6470")};font-size:10.5px;font-family:{FONT}}}</style>'
           f'<rect width="100%" height="100%" fill="#ffffff"/>{"".join(legend)}<g transform="translate(0,{top:.0f})">{inner}</g></svg>')
    return re.sub(r"var\(--(\w+)\)", lambda k: LIGHT.get(k.group(1), "#5d6470"), svg)


def charts_of(d):
    return [b["chart"] for s in d.get("sections") or [] for b in s.get("blocks") or [] if b.get("type") == "chart"]


def build(src):
    src = Path(src)
    d = json.loads(src.read_text(encoding="utf-8"))
    cdir = src.parent / "charts"
    cdir.mkdir(exist_ok=True)
    rels = []
    for n, c in enumerate(charts_of(d), 1):
        svg = standalone(c)
        p = cdir / f"{src.stem}_{n}.svg"
        if svg:
            p.write_text(report_html.money_units(svg), encoding="utf-8")
            rels.append(f"charts/{p.name}")
        else:
            rels.append(None)
    md = src.with_suffix(".md")
    md.write_text(report_notion.render(d, charts=[r or "" for r in rels], h1=True), encoding="utf-8")
    return {"md": str(md), "charts": [str(src.parent / r) for r in rels if r]}


def main(argv):
    sys.stdout.reconfigure(encoding="utf-8")
    print(json.dumps(build(argv[0]), ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
