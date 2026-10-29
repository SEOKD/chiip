"""텐배거 리포트 → 노션 페이지 본문(Notion-flavored Markdown) (마스터 지시 2026-10-30 "텐배거 리포트 결과물을 Notion에도 추가하라. Stocks 아래
'회사명 종목코드'(예: 콴타서비스 PWR) 페이지를 만들거나 기존 페이지가 있으면 거기에 텐배거 리포트를 넣어라")

리포트 JSON(outputs/tenbagger/reports/<날짜>_<티커>.json)을 그대로 옮긴다: Chiip View(컨빅션·알파·업사이드) → 한 장 요약 → 핵심 숫자 표 →
절마다 글·표(차트는 노션에 그릴 수 없어 '그래프는 GitHub 원본' 안내와 그림 제목 목록) → 정정 기록 → 출처·면책.
노션에 올리는 일(검색·생성)은 모델이 노션 커넥터로 한다 — 이 스크립트는 본문만 만든다.
사용: py scripts/tenbagger/report_notion.py <리포트 json> [--github <HTML 링크>]   → 같은 이름 _notion.md 와 제목 한 줄 출력
"""
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import report_html  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "radar"))
from units import money_units  # noqa: E402


def cell(x):
    return str(x if x is not None else "").replace("|", "／").replace("\n", " ")


def table(headers, rows):
    if not headers and rows:
        headers = [""] * len(rows[0])
    out = ["| " + " | ".join(cell(h) for h in headers) + " |", "|" + "---|" * len(headers)]
    out += ["| " + " | ".join(cell(c) for c in r) + " |" for r in rows]
    return "\n".join(out)


def render(d, github=None, charts=None, h1=False):
    """github = 원본 링크 줄, charts = 그림 n번의 이미지 경로(GitHub 마크다운 판 — report_md.py), h1 = 맨 위 제목 줄"""
    d = json.loads(report_html.plain(json.dumps(d, ensure_ascii=False)))   # v2·MC 같은 약어 풀어 쓰기(리포트 HTML과 같게)
    v = d.get("verdict") or {}
    up, basis = report_html.upside(d)
    alpha = v.get("insight") if v.get("insight") is not None else v.get("alpha")
    badges = " · ".join(x for x in (f"컨빅션 {v['confidence']}" if v.get("confidence") else "", f"알파 {alpha}/10" if alpha is not None else "",
                                     f"업사이드 {up:+.0%}" if up is not None else "") if x)
    L = [f"# {title(d)}", ""] if h1 else []
    L += [f"> {d.get('date')} · {d.get('company')}({d.get('ticker')}) · 기업: {d.get('biz')}", ""]
    if github:
        L += [f"**그래프 포함 리포트:** [GitHub에서 보기]({github})", ""]
    L += ["## Chiip View", f"**{badges}**" if badges else "", "", str(v.get("view") or "")]
    if up is not None and basis:
        L += ["", f"업사이드 기준: {basis} — 가격 목표가 아니라 시나리오 확률 가중 지표"]
    if d.get("summary"):
        L += ["", "## 한 장 요약"] + [f"- **{s.get('q')}** {s.get('a')}" for s in d["summary"]]
    if d.get("tiles"):
        L += ["", "## 핵심 숫자", table(["항목", "값", "설명"], [[t.get("k"), t.get("v"), t.get("sub")] for t in d["tiles"]])]
    L += ["", report_html.GLOSSARY]
    figs = [b["chart"].get("title") for s in d.get("sections") or [] for b in s.get("blocks") or [] if b.get("type") == "chart"]
    if figs and not charts:
        L += ["", "## 그래프(위 HTML 임베드·GitHub 리포트에서 보기)"] + [f"{i}. {t}" for i, t in enumerate(figs, 1)]
    n = 0
    for s in d.get("sections") or []:
        L += ["", f"## {s.get('h2')}"]
        for b in s.get("blocks") or []:
            k = b.get("type")
            if k in ("p", "hl"):
                L += ["", ("> " if k == "hl" else "") + str(b.get("text") or "")]
            elif k == "h3":
                L += ["", f"### {b.get('text')}"]
            elif k == "ul":
                L += [""] + [f"- {i}" for i in b.get("items") or []]
            elif k == "table":
                L += ["", f"**{b['title']}**" if b.get("title") else "", table(b.get("headers") or [], b.get("rows") or [])]
            elif k == "chart":
                n += 1
                c = b["chart"]
                if charts and n <= len(charts) and charts[n - 1]:   # GitHub 판: 그림을 그 자리에(2026-10-30 마스터 지시 "github 링크로 결과물을 볼 수 있어야")
                    L += ["", f"**그림 {n} · {c.get('title')}**", "", f"![그림 {n}]({charts[n - 1]})"] + ([f"_{c['note']}_"] if c.get("note") else [])
                else:
                    L += ["", f"📊 그림 {n} · {c.get('title')} — 위 HTML 임베드·GitHub 리포트"]
    src = d.get("sources") or []
    if src:
        L += ["", "## 출처"] + [f"- {x}" for x in src]
    L += ["", f"_{report_html.DISCLAIMER}_"]
    text = "\n".join(x for x in L if x is not None)
    text = text.replace("치입 판단", "Chiip View").replace("치입", "Chiip")
    out = money_units(re.sub(r"\n{3,}", "\n\n", text))
    # 노션·GitHub 마크다운은 $...$를 수식으로 읽는다 — 금액의 $는 \$로(2026-10-30 INIO·CBRS 업로드)
    return re.sub(r"(?<!\\)\$", r"\\$", out)


def title(d):
    return f"텐배거 리포트 {d.get('date')} — {re.sub(r'^[^A-Za-z가-힣0-9]+', '', str(d.get('title') or '')).strip()}"


def main(argv):
    sys.stdout.reconfigure(encoding="utf-8")
    src = Path(argv[0])
    gh = argv[argv.index("--github") + 1] if "--github" in argv else None
    d = json.loads(src.read_text(encoding="utf-8"))
    out = src.with_name(src.stem + "_notion.md")
    out.write_text(render(d, gh), encoding="utf-8")
    print(json.dumps({"title": title(d), "file": str(out), "company": d.get("company"), "ticker": d.get("ticker")}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
