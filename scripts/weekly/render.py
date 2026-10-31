"""Chiip Weekly Review 렌더러·품질 관문 (2026-10-31 재설계, config/weekly_review.yaml)

입력 outputs/brief/<주차>_weekly.json + knowledge/models/weekly_movers/<주차>.csv → 같은 이름의 .md·.html.
구성은 여기서 고정한다. 모델은 글만 쓴다. 금지 표현·분량 초과·개수 부족이면 ValueError로 멈춘다.

JSON: {"week": "2026-W44", "week_no": 44, "period": "10/26~10/30", "as_of": "2026-10-31 11:00 KST", "headline": "한 문장",
       "bullets": ["결론 3개"], "indices": [{"name", "pct"}], "changes": [{"title", "what", "why", "winners", "losers", "next"}],
       "sectors": [{"name", "d5", "d20", "dd", "rev30", "read"}], "next": [{"date", "what", "watch", "means"}], "risks": ["3개"], "notes": ["출처·표기 의무"]}
사용: py scripts/weekly/render.py 2026-W44
"""
import csv
import html
import json
import re
import sys
from collections import Counter
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
BRIEF = ROOT / "outputs" / "brief"
MOVERS = ROOT / "knowledge" / "models" / "weekly_movers"


def cfg():
    return yaml.safe_load((ROOT / "config" / "weekly_review.yaml").read_text(encoding="utf-8"))


def load_movers(week, c):
    rows = list(csv.DictReader((MOVERS / f"{week}.csv").read_text(encoding="utf-8").splitlines()))
    out = []
    for r in c["regions"]:
        got = [x for x in rows if x["region"] == r["key"]]
        got.sort(key=lambda x: -float(x["pct_change"]))
        if len(got) != r["count"]:
            raise ValueError(f"{r['title']} {len(got)}종목 — {r['count']}종목 필요")
        out.append({**r, "rows": got})
    return out


def themes(movers, top=6):
    """상승 상위 종목을 업종으로 묶는다 — (업종, 종목 수, 대표 이름 3개)"""
    rows = [x for r in movers for x in r["rows"]]
    n = Counter(x["theme"] for x in rows if x.get("theme"))
    return [(t, k, [x["name_ko"] for x in rows if x.get("theme") == t][:3]) for t, k in n.most_common(top)], len(rows)


def line(x):
    return f"+{round(float(x['pct_change']))}%｜{x['name_ko']}｜{x['desc_ko']}"


def ticker_block(d, movers):
    parts = [f"{d['week_no']}주차 글로벌 증시 주간 상승률"]
    for r in movers:
        parts.append("\n".join([r["title"]] + [line(x) for x in r["rows"]]))
    return "\n\n".join(parts)


def _within(name, items, rng):
    if not rng[0] <= len(items) <= rng[1]:
        raise ValueError(f"{name} {len(items)}개 — {rng[0]}~{rng[1]}개")


def _short(name, s, n):
    if len(s) > n:
        raise ValueError(f"{name} {len(s)}자 — {n}자 이내: {s[:30]}")


def check(d, c):
    """품질 관문 — 분량·개수·금지 표현"""
    lim = c["limits"]
    _short("headline", d["headline"], lim["headline"])
    _within("bullets", d["bullets"], lim["bullets"])
    _within("changes", d["changes"], lim["changes"])
    _within("sectors", d["sectors"], lim["sectors"])
    _within("next", d["next"], lim["next"])
    _within("risks", d["risks"], lim["risks"])
    for b in d["bullets"]:
        _short("bullet", b, lim["bullet"])
    for x in d["changes"]:
        for k in ("title", "what", "why", "winners", "losers", "next"):
            if not x.get(k):
                raise ValueError(f"changes.{k} 없음: {x.get('title')}")
            _short(f"changes.{k}", x[k], lim["change_field"])
    for x in d["next"]:
        for k in ("date", "what", "watch", "means"):
            _short(f"next.{k}", x[k], lim["next_field"])
    for r in d["risks"]:
        _short("risk", r, lim["risk"])
    prose = json.dumps({k: d.get(k) for k in ("headline", "bullets", "changes", "sectors", "next", "risks", "indices")}, ensure_ascii=False)
    if len(prose) > lim["prose_chars"] + 1200:   # JSON 부호 몫
        raise ValueError(f"본문이 길다 {len(prose)}자")
    return prose


def lint(text, c):
    text = text.replace("```", "")   # 채널용 텍스트 코드 블록 표시
    for pat in c["banned"]:
        m = re.search(pat, text)
        if m:
            raise ValueError(f"보고서에 쓰지 않는 표현: {m.group(0)!r} … {text[max(0, m.start() - 20):m.end() + 20]}")


def _sign(v):
    return f"+{v:.1f}%" if v >= 0 else f"−{-v:.1f}%"


def to_md(d, movers):
    th, total = themes(movers)
    L = [f"# Chiip Weekly Review {d['week_no']}주차", "", f"{d['period']} · {d['as_of']}", "", f"## {d['headline']}", ""]
    L += [f"- {b}" for b in d["bullets"]] + ["", "## 글로벌 지수", "", "| 지수 | 주간 |", "|---|---|"]
    L += [f"| {x['name']} | {_sign(x['pct'])} |" for x in d["indices"]]
    L += ["", "## 글로벌 증시 주간 상승률", "", "```", ticker_block(d, movers), "```", "", "## 이번 주 상승 업종", "", f"상승 상위 {total}종목 기준", "", "| 업종 | 종목 수 | 대표 |", "|---|---|---|"]
    L += [f"| {t} | {k} | {' · '.join(ex)} |" for t, k, ex in th]
    L += ["", "## 이번 주 바뀐 것", ""]
    for i, x in enumerate(d["changes"], 1):
        L += [f"### {i}. {x['title']}", f"- 무엇이: {x['what']}", f"- 왜 중요한가: {x['why']}", f"- 유리: {x['winners']}", f"- 불리: {x['losers']}", f"- 다음 확인: {x['next']}", ""]
    L += ["## 섹터 온도", "", "| 섹터 | 5일 | 20일 | 고점 대비 | EPS 추정 30일 | 읽기 |", "|---|---|---|---|---|---|"]
    L += [f"| {x['name']} | {_sign(x['d5'])} | {_sign(x['d20'])} | {_sign(x['dd'])} | {_sign(x['rev30'])} | {x['read']} |" for x in d["sectors"]]
    L += ["", "## 다음 주 볼 것", "", "| 날짜 | 무엇 | 볼 숫자 | 의미 |", "|---|---|---|---|"]
    L += [f"| {x['date']} | {x['what']} | {x['watch']} | {x['means']} |" for x in d["next"]]
    L += ["", "## 이 판단이 틀릴 조건", ""] + [f"- {r}" for r in d["risks"]] + [""]
    L += d.get("notes") or []
    return "\n".join(L) + "\n"


CSS = """:root{--bg:#f4f6f8;--panel:#fff;--fg:#16202a;--mut:#5b6b79;--line:#dbe2e8;--up:#0b7a5a;--down:#b5412a;--acc:#0f6a78;--sans:"IBM Plex Sans KR","Apple SD Gothic Neo","Malgun Gothic",sans-serif;--mono:"IBM Plex Mono",Consolas,monospace}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){--bg:#10171d;--panel:#18222b;--fg:#e6ecf1;--mut:#97a8b6;--line:#2c3a46;--up:#4fd0a5;--down:#f1967c;--acc:#5cc2d2;color-scheme:dark}}
:root[data-theme="dark"]{--bg:#10171d;--panel:#18222b;--fg:#e6ecf1;--mut:#97a8b6;--line:#2c3a46;--up:#4fd0a5;--down:#f1967c;--acc:#5cc2d2;color-scheme:dark}
body{background:var(--bg);color:var(--fg);font:16px/1.65 var(--sans);padding-left:max(16px,env(safe-area-inset-left,0px));padding-right:max(16px,env(safe-area-inset-right,0px));padding-block:24px 48px}
main{max-width:760px;margin:0 auto;display:grid;gap:30px}main>*{min-width:0}
.k{font:13px/1.4 var(--mono);color:var(--mut);margin:0 0 8px}h1{font-size:27px;line-height:1.3;margin:0;text-wrap:balance}
ul{margin:12px 0 0;padding-left:20px}li{margin:6px 0}
h2{font-size:18px;margin:0 0 12px;padding-bottom:6px;border-bottom:2px solid var(--acc)}
.idx{display:grid;grid-template-columns:repeat(auto-fit,minmax(112px,1fr));gap:8px}.idx div{background:var(--panel);border:1px solid var(--line);border-radius:10px;padding:9px 11px}.idx b{display:block;font:500 19px/1.3 var(--mono)}.idx span{font-size:12.5px;color:var(--mut)}
.up{color:var(--up)}.down{color:var(--down)}
.reg{display:grid;grid-template-columns:repeat(auto-fit,minmax(300px,1fr));gap:12px}.reg>div{background:var(--panel);border:1px solid var(--line);border-radius:10px;padding:10px 12px;min-width:0}.reg h3{font-size:14px;color:var(--acc);margin:0 0 6px}
.m{display:grid;grid-template-columns:48px minmax(0,1fr);gap:6px;font-size:14px;padding:3px 0;border-top:1px solid var(--line)}.m:first-of-type{border-top:0}.m b{font:500 14px var(--mono);color:var(--up)}.m small{display:block;color:var(--mut);font-size:12.5px}
.card{background:var(--panel);border:1px solid var(--line);border-radius:10px;padding:13px 15px;margin-bottom:12px}.card h3{font-size:16.5px;margin:0 0 8px;text-wrap:balance}.card dl{display:grid;grid-template-columns:72px minmax(0,1fr);gap:4px 10px;margin:0;font-size:14.5px}.card dt{color:var(--mut)}.card dd{margin:0}
.tw{overflow-x:auto;background:var(--panel);border:1px solid var(--line);border-radius:10px}table{border-collapse:collapse;width:100%;font-size:13.5px;line-height:1.5}th{text-align:left;color:var(--mut);font-weight:500;white-space:nowrap}th,td{padding:8px 10px;border-bottom:1px solid var(--line);vertical-align:top}tr:last-child td{border-bottom:0}
details{margin-top:12px}summary{cursor:pointer;color:var(--acc);font-size:14px}pre{white-space:pre-wrap;font:13px/1.55 var(--mono);background:var(--panel);border:1px solid var(--line);border-radius:10px;padding:12px;overflow-wrap:anywhere}button{font:13px var(--sans);padding:6px 12px;border:1px solid var(--line);border-radius:8px;background:var(--panel);color:var(--fg);cursor:pointer}
.note{font-size:12.5px;color:var(--mut);margin:0}"""


def _e(s):
    return html.escape(str(s), quote=False)


def _pct(v):
    return f'<span class="{"up" if v >= 0 else "down"}">{_sign(v)}</span>'


def to_html(d, movers):
    th, total = themes(movers)
    block = ticker_block(d, movers)
    regs = "".join(f"<div><h3>{_e(r['title'])}</h3>" + "".join(f'<div class="m"><b>+{round(float(x["pct_change"]))}%</b><span>{_e(x["name_ko"])}<small>{_e(x["desc_ko"])}</small></span></div>' for x in r["rows"]) + "</div>" for r in movers)
    idx = "".join(f'<div><span>{_e(x["name"])}</span><b class="{"up" if x["pct"] >= 0 else "down"}">{_sign(x["pct"])}</b></div>' for x in d["indices"])
    cards = "".join(f'<div class="card"><h3>{i}. {_e(x["title"])}</h3><dl><dt>무엇이</dt><dd>{_e(x["what"])}</dd><dt>왜 중요</dt><dd>{_e(x["why"])}</dd><dt>유리</dt><dd>{_e(x["winners"])}</dd><dt>불리</dt><dd>{_e(x["losers"])}</dd><dt>다음 확인</dt><dd>{_e(x["next"])}</dd></dl></div>' for i, x in enumerate(d["changes"], 1))
    sec = "".join(f"<tr><td>{_e(x['name'])}</td><td>{_pct(x['d5'])}</td><td>{_pct(x['d20'])}</td><td>{_pct(x['dd'])}</td><td>{_pct(x['rev30'])}</td><td>{_e(x['read'])}</td></tr>" for x in d["sectors"])
    nxt = "".join(f"<tr><td>{_e(x['date'])}</td><td>{_e(x['what'])}</td><td>{_e(x['watch'])}</td><td>{_e(x['means'])}</td></tr>" for x in d["next"])
    tb = "".join(f"<tr><td>{_e(t)}</td><td>{k}</td><td>{_e(' · '.join(ex))}</td></tr>" for t, k, ex in th)
    return f"""<title>Chiip {d['week_no']}주차 리뷰</title>
<meta name="claude:viewport-fit-sides" content="cover">
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500&family=IBM+Plex+Sans+KR:wght@400;500;700&display=swap">
<style>{CSS}</style>
<main>
<header><p class="k">Chiip Weekly Review {d['week_no']}주차 · {_e(d['period'])}</p><h1>{_e(d['headline'])}</h1><ul>{''.join(f'<li>{_e(b)}</li>' for b in d['bullets'])}</ul></header>
<section><h2>글로벌 지수</h2><div class="idx">{idx}</div></section>
<section><h2>글로벌 증시 주간 상승률</h2><div class="reg">{regs}</div><details><summary>채널용 텍스트</summary><p><button id="cp">복사</button></p><pre id="tk">{_e(block)}</pre></details></section>
<section><h2>이번 주 상승 업종</h2><div class="tw"><table><tr><th>상승 상위 {total}종목</th><th>수</th><th>대표</th></tr>{tb}</table></div></section>
<section><h2>이번 주 바뀐 것</h2>{cards}</section>
<section><h2>섹터 온도</h2><div class="tw"><table><tr><th>섹터</th><th>5일</th><th>20일</th><th>고점 대비</th><th>EPS 추정 30일</th><th>읽기</th></tr>{sec}</table></div></section>
<section><h2>다음 주 볼 것</h2><div class="tw"><table><tr><th>날짜</th><th>무엇</th><th>볼 숫자</th><th>의미</th></tr>{nxt}</table></div></section>
<section><h2>이 판단이 틀릴 조건</h2><ul>{''.join(f'<li>{_e(r)}</li>' for r in d['risks'])}</ul></section>
{''.join(f'<p class="note">{_e(n)}</p>' for n in d.get('notes') or [])}
</main>
<script>document.getElementById("cp").addEventListener("click",function(){{var t=document.getElementById("tk").textContent,b=this;navigator.clipboard.writeText(t).then(function(){{b.textContent="복사됨"}}).catch(function(){{var r=document.createRange();r.selectNodeContents(document.getElementById("tk"));var s=getSelection();s.removeAllRanges();s.addRange(r)}})}});</script>
"""


def render(week):
    c = cfg()
    d = json.loads((BRIEF / f"{week}_weekly.json").read_text(encoding="utf-8"))
    movers = load_movers(week, c)
    check(d, c)
    md = to_md(d, movers)
    lint(md, c)
    (BRIEF / f"{week}_weekly.md").write_text(md, encoding="utf-8")
    (BRIEF / f"{week}_weekly.html").write_text(to_html(d, movers), encoding="utf-8")
    return md


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    print(f"[Weekly Review] {sys.argv[1]} {len(render(sys.argv[1]))}자")
