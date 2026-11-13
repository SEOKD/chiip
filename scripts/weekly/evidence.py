"""Weekly Review 근거 묶음 — 종목·사건마다 수집된 모든 경로를 한곳에 모은다 (마스터 지시 2026-11-14
"심텍홀딩스가 오른 건 DART에 3분기 사업보고서가 올라온 영향도 있어 보인다. 텔레그램 Awake 채널을 통해 이를 파악할 수 있도록 해라"
· "엔비디아 CEO 사임은 이미 신문 보도를 통해 이유가 잘 알려져 있는데 공시에 명시돼 있지 않다고 '이유가 없다'고 하면 … 가능한 한 많은 경로를
활용해 시장 정보를 최대한 많이 전달할 수 있도록 파이프라인을 점검하라")

46주차 실패 두 건:
  ① 심텍홀딩스 +67%를 '지주사 자체 사건은 찾지 못했다'고 썼다 — Awake(@darthacking, DART 공시 채널)에 11/9 3분기 잠정실적(영업이익 1,047억 원,
     전년 동기 25억 원)·11/10 IR·11/13 분기보고서가 이미 수집돼 있었다. 급등 분석이 저장된 텔레그램 수집분을 열지 않았다.
  ② 엔비디아 CEO 사임을 '이유는 공시에 없다'로 썼다 — FT·NYT·WSJ·블룸버그·로이터 보도가 같은 텔레그램 수집분에 수십 건 있었다.
     공시에 없는 것은 '알려진 이유가 없다'가 아니다.

결정론: 이 스크립트는 저장된 수집분만 읽는다(네트워크 없음). 경로:
  - DART: Awake 채널 @darthacking(공시 제목·실적 표·공시 링크) — 한국 종목
  - 텔레그램 공개 채널 17곳 전체(보도 인용·속보·실적 요약)
  - 레이더 inbox(src-*.json: 공시·보도자료·RSS 기사·SEC)
모델 몫(--plan이 목록을 준다): TradingView 뉴스(mcp-tv-get-news, 일본은 lang ja, 한국 lang ko) · easyconomics company_news · 실적 정리 ·
  WebSearch(보도 원문). 모델은 모은 경로를 JSON surges[].routes / changes[].routes에 적는다.

사용: py scripts/weekly/evidence.py <주차> --ent "심텍홀딩스|036710" --ent "엔비디아|NVIDIA|Jensen Huang|NVDA"
      py scripts/weekly/evidence.py <주차> --movers        # 미국·유럽·일본·한국 상승률 표 전 종목
출력: radar/state/weekly_evidence/<주차>/<이름>.md(git 제외) + manifest.json(무엇을 몇 건 찾았나 — 렌더러 관문이 읽는다)
"""
import csv
import json
import re
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TG = ROOT / "radar" / "inbox" / "tg_channels"
INBOX = ROOT / "radar" / "inbox"
OUT = ROOT / "radar" / "state" / "weekly_evidence"
MOVERS = ROOT / "knowledge" / "models" / "weekly_movers"
DART_CH = "darthacking"          # Awake — DART 공시 채널(2026-11-08 마스터 지시 'DART 보는 건 텔레그램 채널로 대체')
SKIP_CH = {"easobi_ai"}          # 커뮤니티 심리 요약(종목 언급 집계) — 사건 근거가 아니다
PER_ROUTE = 80


def window(week):
    """ISO 주차 → (전주 토요일 00:00, 이번 주 토요일 12:00) KST 문자열 — 주말 공시·보도까지"""
    y, w = week.split("-W")
    mon = date.fromisocalendar(int(y), int(w), 1)
    return (mon - timedelta(days=2)).isoformat(), (mon + timedelta(days=5)).isoformat() + "T12"


def _term(t):
    """검색어 하나 → 정규식. 영문 티커·일본 4자리 코드는 티커로 쓰인 꼴만 잡는다('TOP'·'NET'이 영어 단어에, '1980'이 연도에 걸리지 않게)"""
    e = re.escape(t)
    if re.fullmatch(r"[A-Z]{1,6}", t):
        return rf"\${e}\b|\({e}\)|(?:NASDAQ|NYSE|AMEX|LSE|SIX|EURONEXT|XETR|BIT|OSL):{e}\b|\b{e} US\b"
    if re.fullmatch(r"\d{4}", t):
        return rf"\({e}\)|\b{e}\.T\b|TSE:{e}\b|\b{e} JP\b|\[{e}\]"
    return rf"(?i:{e})"


def _rx(terms):
    return re.compile("|".join(_term(t.strip()) for t in terms if t.strip()))


def _rank(rows, rx, key):
    """제목·앞부분에 이름이 나온 글(사건 당사자 글)을 먼저, 그 안에서는 시간순"""
    return sorted(rows, key=lambda r: (not rx.search((r.get(key) or "")[:160]), r["at"]))


def telegram(rx, lo, hi):
    dart, other = [], []
    for f in sorted(TG.glob("*.jsonl")):
        ch = f.stem
        if ch in SKIP_CH:
            continue
        for line in f.read_text(encoding="utf-8", errors="ignore").splitlines():
            try:
                d = json.loads(line)
            except ValueError:
                continue
            at, text = d.get("at") or "", d.get("text") or ""
            if not (lo <= at <= hi) or not rx.search(text):
                continue
            row = {"at": at[:16], "channel": ch, "url": d.get("url"), "text": text.strip()}
            (dart if ch == DART_CH else other).append(row)
    return sorted(dart, key=lambda r: r["at"]), sorted(other, key=lambda r: r["at"])


def inbox(rx, lo, hi):
    out = []
    d0, d1 = date.fromisoformat(lo[:10]), date.fromisoformat(hi[:10])
    day = d0
    while day <= d1:
        folder = INBOX / day.strftime("%Y%m%d")
        for f in sorted(folder.glob("src-*.json")) if folder.exists() else []:
            try:
                it = json.loads(f.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            blob = " ".join(str(it.get(k) or "") for k in ("title", "snippet", "entities_matched", "ticker", "publisher"))
            if rx.search(blob):
                out.append({"at": str(it.get("published_at") or it.get("detected_at") or "")[:16], "source": it.get("source_id"),
                            "publisher": it.get("publisher"), "title": it.get("title"), "url": it.get("url")})
        day += timedelta(days=1)
    seen, uniq = set(), []
    for r in sorted(out, key=lambda r: r["at"]):
        k = (r["title"] or "")[:80]
        if k not in seen:
            seen.add(k)
            uniq.append(r)
    return uniq


def pack(week, name, terms):
    lo, hi = window(week)
    rx = _rx(terms)
    dart, tg = telegram(rx, lo, hi)
    ib = inbox(rx, lo, hi)
    tg, ib = _rank(tg, rx, "text"), _rank(ib, rx, "title")
    L = [f"# 근거 묶음 — {name} ({week}, {lo} ~ {hi[:10]})", f"검색어: {' | '.join(terms)}", "",
         f"## DART(Awake @{DART_CH}) {len(dart)}건"]
    L += [f"- [{r['at']}] {r['url']}\n  " + r["text"][:700].replace("\n", " / ") for r in dart[:PER_ROUTE]]
    L += ["", f"## 텔레그램 공개 채널 {len(tg)}건(보도 인용·속보 — 원보도 이름을 확인해 쓴다, 채널 글은 S1·S2)"]
    L += [f"- [{r['at']} @{r['channel']}] {r['url']}\n  " + r["text"][:500].replace("\n", " / ") for r in tg[:PER_ROUTE]]
    L += ["", f"## 레이더 inbox(공시·보도자료·기사) {len(ib)}건"]
    L += [f"- [{r['at']}] {r['publisher'] or r['source']}: {r['title']} {r['url'] or ''}" for r in ib[:PER_ROUTE]]
    L += ["", "## 모델이 더 볼 경로", "- TradingView 뉴스(mcp-tv-get-news) — 미국 en, 일본 ja, 한국 ko", "- easyconomics company_news·earnings_summary",
          "- WebSearch — 보도 원문(FT·WSJ·블룸버그·로이터·NYT·니케이·한경 등). 회사 공시에 이유가 없으면 보도된 이유를 '보도'로 밝혀 쓴다"]
    d = OUT / week
    d.mkdir(parents=True, exist_ok=True)
    safe = re.sub(r"[^\w가-힣]+", "_", name)[:40]
    (d / f"{safe}.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    return {"name": name, "terms": terms, "dart": len(dart), "telegram": len(tg), "inbox": len(ib), "file": f"{safe}.md",
            "made": datetime.now().isoformat(timespec="seconds")}


def manifest(week, entries=None):
    p = OUT / week / "manifest.json"
    cur = json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}
    for e in entries or []:
        cur[e["name"]] = e
    if entries is not None:
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(cur, ensure_ascii=False, indent=1), encoding="utf-8")
    return cur


def mover_terms(week, regions=("US", "US_SMALL", "EU", "JP", "KR")):
    rows = list(csv.DictReader((MOVERS / f"{week}.csv").read_text(encoding="utf-8").splitlines()))
    out = []
    for r in rows:
        if r["region"] not in regions:
            continue
        terms = [r["name_ko"], r["ticker"]] + ([r["name_en"]] if r.get("name_en") else [])
        out.append((r["ticker"], [t for t in terms if t and len(t) >= 2]))
    return out


def main(argv):
    sys.stdout.reconfigure(encoding="utf-8")
    if not argv or argv[0].startswith("-"):
        print(__doc__)
        return
    week = argv[0]
    got = []
    if "--movers" in argv:
        for tk, terms in mover_terms(week):
            got.append(pack(week, tk, terms))
    for i, a in enumerate(argv):
        if a == "--ent":
            terms = argv[i + 1].split("|")
            got.append(pack(week, terms[0], terms))
    manifest(week, got)
    for g in got:
        print(f"[근거] {g['name']}: DART {g['dart']} · 텔레그램 {g['telegram']} · inbox {g['inbox']} → radar/state/weekly_evidence/{week}/{g['file']}")


if __name__ == "__main__":
    main(sys.argv[1:])
