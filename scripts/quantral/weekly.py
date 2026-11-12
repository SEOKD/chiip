"""Chiip Quantral — 주간 리테일 관심 순위 (마스터 지시 2026-11-12 "일요일 아침마다 Reddit, X, Substack에서 언급 수가 가장 많은 종목을
상위 순으로 순위를 매겨 어떤 내러티브로 리테일 투자자들의 관심을 얻고 있는지 분석하는 리포트. Weekly Review와 별개")

수집은 모델이 Quantral MCP로 받아 파일로 넘기고(get_stories 주간 + 상위 종목 get_company_signals), 계산·모양은 여기서 한다(결정론).
  언급 수     그 주(월~일) 이야기(story)들의 postCount를 종목별로 합한다. 두 종목 이야기는 양쪽에 모두 센다.
  채널 비중   상위 종목의 최근 언급 표본(get_company_signals, 최대 50건) 중 그 주 것의 sourceType 비중 → Reddit·X·Substack 몫
  순위 점수   언급 수 × (Reddit+X+Substack 비중) — 유튜브·텔레그램 등 다른 채널 몫은 뺀다. 표본이 없으면 비중 1로 두고 '채널 미확인'
저장은 집계만 — 종목·건수·채널 비중·이야기 제목·종류. 작성자·글 본문·링크는 저장하지 않는다(CLAUDE.md 커뮤니티 경계, ADR-011).
관심은 관심일 뿐 펀더멘털 변화가 아니다(금지표: 주가 급등 → 펀더멘털 변화). 커뮤니티 신호는 S1·S2 — 주장이 아니다.

사용: py scripts/quantral/weekly.py --week                      # 이번 회차 대상 주(직전 월~일)와 주차 이름
      py scripts/quantral/weekly.py --put <stories.json> <signals.json> <YYYY-Www>
            stories.json = get_stories(week=...) 응답 그대로, signals.json = {"TICKER": get_company_signals 응답의 signals 목록, ...}
            → outputs/quantral/<주차>_data.json (순위 상위 TOP)
      py scripts/quantral/weekly.py --render <YYYY-Www>        # <주차>_report.json(모델 글) + _data.json → .md·.html
"""
import html
import json
import re
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "outputs" / "quantral"
TOP = 15
CHANNELS = {"reddit": "Reddit", "x": "X", "twitter": "X", "substack": "Substack"}
DISCLAIMER = "커뮤니티 관심 집계(Quantral)이지 사실·추천이 아님 · 공개 자료 기반 분석이며 투자 권유가 아님 · Chiip Quantral"


def target_week(today=None):
    """일요일 아침 실행 → 막 끝난 월~일(오늘이 일요일이면 지난 월요일~어제 토요일까지 + 오늘 아침분은 같은 주)"""
    today = today or date.today()
    monday = today - timedelta(days=today.weekday())
    if today.weekday() != 6:   # 일요일이 아니면 직전 주
        monday -= timedelta(days=7)
    y, w, _ = monday.isocalendar()
    return monday, f"{y}-W{w:02d}"


def _in_week(ts, monday):
    try:
        d = datetime.fromisoformat(str(ts).replace("Z", "+00:00")).date()
    except ValueError:
        return False
    return monday <= d <= monday + timedelta(days=6)


def build(stories, signals, week, monday):
    rows = {}
    for s in stories.get("stories") or []:
        for c in s.get("companies") or []:
            t = c.get("ticker")
            if not t:
                continue
            r = rows.setdefault(t, {"ticker": t, "name": c.get("name", t), "posts": 0, "stories": []})
            r["posts"] += int(s.get("postCount") or 0)
            r["stories"].append({"headline": s.get("headline", ""), "kind": s.get("kind", ""), "posts": int(s.get("postCount") or 0)})
    for t, r in rows.items():
        sig = [x for x in (signals.get(t) or []) if _in_week(x.get("detectedAt") or x.get("publishedAt") or x.get("date") or "", monday)]
        mix = {}
        for x in sig:
            ch = CHANNELS.get(str(x.get("sourceType", "")).lower(), "기타")
            mix[ch] = mix.get(ch, 0) + 1
        n = sum(mix.values())
        share = (n - mix.get("기타", 0)) / n if n else None
        r["mix"] = {k: round(v / n, 2) for k, v in sorted(mix.items(), key=lambda kv: -kv[1])} if n else {}
        r["sample"] = n
        r["rxs_share"] = round(share, 2) if share is not None else None
        r["score"] = round(r["posts"] * (share if share is not None else 1.0), 1)
        r["stories"].sort(key=lambda x: -x["posts"])
        r["stories"] = r["stories"][:3]
    ranked = sorted(rows.values(), key=lambda r: (-r["score"], -r["posts"]))[:TOP]
    for i, r in enumerate(ranked, 1):
        r["rank"] = i
    return {"week": week, "period": f"{monday:%m/%d}~{monday + timedelta(days=6):%m/%d}", "rows": ranked,
            "n_stories": len(stories.get("stories") or []), "n_companies": len(rows)}


def put(stories_path, signals_path, week):
    monday = date.fromisocalendar(int(week[:4]), int(week[6:]), 1)
    d = build(json.loads(Path(stories_path).read_text(encoding="utf-8")),
              json.loads(Path(signals_path).read_text(encoding="utf-8")) if signals_path != "-" else {}, week, monday)
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / f"{week}_data.json").write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
    return d


def t(s):
    s = html.escape(str(s if s is not None else ""))
    return re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", s)


CSS = """:root{--bg:#fbfaf7;--fg:#1b1d22;--mut:#5f6570;--line:#e5e2da;--card:#f2efe8;--acc:#d9480f;--x:#1d9bf0;--rd:#ff4500;--ss:#ff6719;--mk:#ffe58a}
@media (prefers-color-scheme:dark){:root:not([data-theme=light]){--bg:#15161a;--fg:#e9e9ec;--mut:#9da2ab;--line:#2c2e35;--card:#1d1f25;--acc:#ff8a4c;--x:#5bb8f5;--rd:#ff7a4d;--ss:#ff9a57;--mk:#5a4a12;color-scheme:dark}}
:root[data-theme=dark]{--bg:#15161a;--fg:#e9e9ec;--mut:#9da2ab;--line:#2c2e35;--card:#1d1f25;--acc:#ff8a4c;--x:#5bb8f5;--rd:#ff7a4d;--ss:#ff9a57;--mk:#5a4a12;color-scheme:dark}
body{margin:0;background:var(--bg);color:var(--fg);font-family:'Noto Sans KR',-apple-system,'Apple SD Gothic Neo','Malgun Gothic',sans-serif;line-height:1.75;font-size:16px;word-break:keep-all}
.w{max-width:820px;margin:0 auto;padding-block:20px 48px;padding-left:max(16px,env(safe-area-inset-left,0px));padding-right:max(16px,env(safe-area-inset-right,0px))}
h1{font-size:clamp(21px,1.1rem + 1vw,28px);line-height:1.35;margin:0 0 4px;text-wrap:balance}h2{font-size:19px;margin:30px 0 8px;padding-top:10px;border-top:2px solid var(--acc)}
.lead{color:var(--mut);font-size:13.5px}.hl{background:var(--card);border-left:4px solid var(--acc);border-radius:4px 12px 12px 4px;padding:12px 15px}
.hl b{background:linear-gradient(transparent 60%,var(--mk) 60%)}.tw{overflow-x:auto}table{border-collapse:collapse;width:100%;font-size:14px;font-variant-numeric:tabular-nums}
th,td{border-bottom:1px solid var(--line);padding:6px 5px;text-align:right;vertical-align:top}th:nth-child(2),td:nth-child(2){text-align:left}th{color:var(--mut);font-weight:600}
.bar{display:flex;height:8px;border-radius:4px;overflow:hidden;min-width:90px;background:var(--line);margin-top:6px}.bar i{display:block}.rd{background:var(--rd)}.x{background:var(--x)}.ss{background:var(--ss)}.ot{background:var(--mut);opacity:.4}
.card{background:var(--card);border-radius:12px;padding:12px 15px;margin:12px 0}.card h3{margin:0 0 4px;font-size:17px}.rk{color:var(--acc);font-weight:700;margin-right:6px}
.k{display:inline-block;font-size:12px;border:1px solid var(--line);border-radius:6px;padding:0 6px;margin-right:4px;color:var(--mut)}.card b{color:var(--acc)}.card u{text-decoration-color:var(--acc);text-decoration-thickness:2px;text-underline-offset:3px}
.foot{color:var(--mut);font-size:12px;margin-top:26px}.lg{font-size:12.5px;color:var(--mut)}.lg i{display:inline-block;width:10px;height:10px;border-radius:2px;margin:0 4px 0 8px;vertical-align:-1px}"""


def _bar(mix):
    cls = {"Reddit": "rd", "X": "x", "Substack": "ss"}
    return '<div class="bar">' + "".join(f'<i class="{cls.get(k, "ot")}" style="width:{v * 100:.0f}%"></i>' for k, v in mix.items()) + "</div>" if mix else ""


def render(week):
    d = json.loads((OUT / f"{week}_data.json").read_text(encoding="utf-8"))
    rp = json.loads((OUT / f"{week}_report.json").read_text(encoding="utf-8"))   # {"headline", "bullets": [3], "themes": [{"name","tickers","read"}], "notes": {"TICKER": {"narrative","why_now","check"}}, "as_of"}
    notes = rp.get("notes") or {}
    miss = [r["ticker"] for r in d["rows"][:10] if r["ticker"] not in notes]
    if miss:
        raise ValueError(f"상위 10 내러티브 누락: {miss}")
    H = [f'<!doctype html><html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">'
         f'<title>Chiip Quantral {week}</title><style>{CSS}</style></head><body><div class="w">',
         f'<h1>{t(rp.get("headline"))}</h1><div class="lead">Chiip Quantral · {week} ({d["period"]}) · 기준 {t(rp.get("as_of", ""))} · '
         f'Reddit·X·Substack 언급 순위</div>',
         '<div class="hl">' + "<br>".join(f"· {t(b)}" for b in rp.get("bullets") or []) + "</div>",
         '<h2>언급 순위</h2><div class="lg"><i class="rd"></i>Reddit<i class="x"></i>X<i class="ss"></i>Substack<i class="ot"></i>기타 채널</div>',
         '<div class="tw"><table><tr><th>#</th><th>종목</th><th>언급(R·X·S)</th><th>전체</th><th>채널 비중</th></tr>']
    for r in d["rows"]:
        share = f'{r["rxs_share"]:.0%}' if r["rxs_share"] is not None else "채널 미확인"
        H.append(f'<tr><td>{r["rank"]}</td><td><b>{t(r["ticker"])}</b> <span class="lead">{t(r["name"])}</span></td><td>{r["score"]:,.0f}</td>'
                 f'<td>{r["posts"]:,}</td><td>{share}{_bar(r["mix"])}</td></tr>')
    H.append("</table></div>")
    if rp.get("themes"):
        H.append("<h2>이번 주 리테일 내러티브 흐름</h2>")
        for th in rp["themes"]:
            H.append(f'<div class="card"><h3>{t(th.get("name"))}</h3><span class="k">{t(" · ".join(th.get("tickers") or []))}</span><p>{t(th.get("read"))}</p></div>')
    H.append("<h2>종목별 내러티브</h2>")
    for r in d["rows"]:
        n = notes.get(r["ticker"])
        if not n:
            continue
        kinds = " ".join(f'<span class="k">{t(s["kind"])}</span>' for s in r["stories"][:1])
        H.append(f'<div class="card"><h3><span class="rk">{r["rank"]}</span>{t(r["ticker"])} <span class="lead">{t(r["name"])}</span></h3>{kinds}'
                 f'<p><b>내러티브</b> {t(n.get("narrative"))}</p><p><b>왜 지금</b> {t(n.get("why_now"))}</p>'
                 + (f'<p><u>확인할 것</u> {t(n.get("check"))}</p>' if n.get("check") else "") + "</div>")
    H.append(f'<div class="foot">이야기 {d["n_stories"]}건 · 언급 종목 {d["n_companies"]}개 집계. 언급 수 = 그 주 Quantral 이야기의 게시 수 합, '
             f'R·X·S = 최근 언급 표본의 Reddit·X·Substack 비중을 곱한 값(추정). {DISCLAIMER}</div></div></body></html>')
    page = "".join(H)
    (OUT / f"{week}.html").write_text(page, encoding="utf-8")
    md = [f"# {rp.get('headline')}", f"Chiip Quantral · {week} ({d['period']})", ""] + [f"- {b}" for b in rp.get("bullets") or []] + ["", "| # | 종목 | 언급(R·X·S) | 전체 |", "|---|---|---|---|"]
    md += [f"| {r['rank']} | {r['ticker']} | {r['score']:,.0f} | {r['posts']:,} |" for r in d["rows"]]
    md += [""] + [f"**{r['rank']}. {r['ticker']}** — {notes[r['ticker']].get('narrative')}" for r in d["rows"] if r["ticker"] in notes] + ["", DISCLAIMER]
    (OUT / f"{week}.md").write_text("\n".join(md), encoding="utf-8")
    return OUT / f"{week}.html"


def main(argv):
    sys.stdout.reconfigure(encoding="utf-8")
    if argv[:1] == ["--week"]:
        m, w = target_week()
        print(w, m.isoformat(), (m + timedelta(days=5)).isoformat())   # 주차 · 월요일 · get_stories에 넘길 날짜(토요일)
    elif argv[:1] == ["--put"]:
        d = put(argv[1], argv[2], argv[3])
        for r in d["rows"]:
            print(r["rank"], r["ticker"], r["score"], r["posts"], r["rxs_share"], r["mix"])
    elif argv[:1] == ["--render"]:
        print(render(argv[1]))
    else:
        print(__doc__)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
