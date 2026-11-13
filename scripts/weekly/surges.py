"""Weekly Review '급등 종목, 왜 올랐나' 절 (마스터 지시 2026-11-14 "Weekly Review에 미국, 일본, 유럽(영국 포함), 한국 시장의 주간 상승률
상위 종목 중에 급등한 종목 가운데 몇 개 집어 급등한 이유를 분석하는 항목도 넣어라")

모델은 weekly json에 "surges": [{"ticker", "region", "kind", "why", "source", "next"}]만 쓴다. 종목명·상승률은 주간 상승률 표
(knowledge/models/weekly_movers/<주차>.csv)에서 가져온다. 표에 없는 종목은 쓰지 않는다(숫자를 두 군데서 따로 적지 않는다).

kind(원인 유형) — 금지표 '주가 급등 → 펀더멘털 변화'를 지키려고 원인 사건의 성격을 먼저 밝힌다:
  실적 · 가이던스 상향 · 주주환원 · 수주·계약 — 회사 1차 자료(실적 발표·공시·콜)가 원인
  업종 동조 — 회사 자체 사건 없이 같은 업종 사건(다른 회사 실적 등)에 따라 오른 것
  업황 기대 — 회사 사건 없이 업황·증권사 추정이 원인(추정임을 why에 적는다)
관문: 미국·유럽·일본·한국에서 각 1종목 이상, 전체 4~8종목, 칸마다 글자 수 제한, 출처(source) 필수.
"""
import html

ROUTES = ("DART", "텔레그램", "inbox", "TradingView 뉴스", "easyconomics", "WebSearch", "회사 공시", "실적 발표·콜")   # 근거 경로(2026-11-14 마스터 지시 "가능한 한 많은 경로")
MIN_ROUTES = 2


def routes_ok(where, routes):
    """경로 2곳 이상, 정해진 이름만 — 한 경로만 보고 '원인 없음'을 쓰지 않게"""
    r = [x for x in (routes or []) if x in ROUTES]
    if len(set(r)) < MIN_ROUTES:
        raise ValueError(f"{where} routes {routes!r} — {'·'.join(ROUTES)} 중 {MIN_ROUTES}곳 이상(scripts/weekly/evidence.py 근거 묶음 + 뉴스 경로)")

KINDS = ("실적", "가이던스 상향", "주주환원", "수주·계약", "업종 동조", "업황 기대")
OWN = {"실적", "가이던스 상향", "주주환원", "수주·계약"}   # 회사 자체 1차 자료가 원인인 유형
MARKETS = {"US": "미국", "US_SMALL": "미국", "EU": "유럽", "JP": "일본", "KR": "한국"}
NEED = ("미국", "유럽", "일본", "한국")


def build(d, movers, lim=None, manifest=None):
    """json surges + 상승률 표 → 렌더용 행. 관문을 못 지키면 ValueError.
    manifest(scripts/weekly/evidence.py 근거 묶음)가 주어지면: 종목마다 묶음을 만들었어야 하고, 한국 종목에 DART(Awake) 공시가 있는데
    원인을 회사 밖(업종 동조·업황 기대)으로 쓰면 멈춘다 — 46주차 심텍홀딩스(11/9 3분기 잠정실적을 보지 않고 '자체 사건 없음')의 재발 방지"""
    lim = lim or {}
    rng = lim.get("surges", [4, 8])
    n = lim.get("surge_field", 120)
    items = d.get("surges") or []
    if not rng[0] <= len(items) <= rng[1]:
        raise ValueError(f"surges {len(items)}종목 — {rng[0]}~{rng[1]}종목")
    table = {(r["key"], x["ticker"]): x for r in movers for x in r["rows"]}
    out = []
    for s in items:
        x = table.get((s.get("region"), s.get("ticker")))
        if not x:
            raise ValueError(f"surges {s.get('region')}:{s.get('ticker')} — 이번 주 상승률 표에 없는 종목")
        if s.get("kind") not in KINDS:
            raise ValueError(f"surges.kind {s.get('kind')!r} — {'·'.join(KINDS)} 중 하나")
        for k in ("why", "source", "next"):
            if not s.get(k):
                raise ValueError(f"surges.{k} 없음: {x['name_ko']}")
            if len(s[k]) > n:
                raise ValueError(f"surges.{k} {len(s[k])}자 — {n}자 이내: {s[k][:30]}")
        routes_ok(f"surges {x['name_ko']}", s.get("routes"))
        if manifest is not None:
            m = manifest.get(s["ticker"])
            if not m:
                raise ValueError(f"surges {x['name_ko']} — 근거 묶음 없음: py scripts/weekly/evidence.py <주차> --movers")
            if s["region"] == "KR" and m.get("dart") and s["kind"] not in OWN and "DART" not in (s.get("routes") or []):
                raise ValueError(f"surges {x['name_ko']} — Awake(DART) 공시 {m['dart']}건이 있는데 원인을 '{s['kind']}'로 썼다. 공시를 읽고 반영하라")
        out.append({**s, "market": MARKETS[s["region"]], "name": x["name_ko"], "desc": x["desc_ko"], "pct": float(x["pct_change"])})
    miss = [m for m in NEED if not any(r["market"] == m for r in out)]
    if miss:
        raise ValueError(f"surges — {'·'.join(miss)} 종목 없음(미국·유럽·일본·한국 각 1종목 이상)")
    order = {m: i for i, m in enumerate(NEED)}
    return sorted(out, key=lambda r: (order[r["market"]], -r["pct"]))


NOTE = "원인 유형: 실적·가이던스 상향·주주환원·수주·계약은 회사 1차 자료, 업종 동조는 회사 발표 없이 같은 업종의 사건(다른 회사 실적 등)에 따라 움직인 것, 업황 기대는 증권사 추정이 근거다. 주가 급등만으로 펀더멘털이 바뀌었다고 보지 않는다."


def md_lines(rows):
    if not rows:
        return []
    L = ["", "## 급등 종목, 왜 올랐나", ""]
    for r in rows:
        L += [f"### {r['market']} · {r['name']} +{round(r['pct'])}% — {r['kind']}", f"- 왜: {r['why']}", f"- 근거: {r['source']} (확인 경로: {' · '.join(r.get('routes') or [])})", f"- 다음 확인: {r['next']}", ""]
    return L + [NOTE]


def html_section(rows):
    if not rows:
        return ""
    e = html.escape
    cards = "".join(
        f'<div class="card"><h3>{e(r["market"])} · {e(r["name"])} <span class="up">+{round(r["pct"])}%</span></h3>'
        f'<p class="k">{e(r["desc"])} · {"회사 사건" if r["kind"] in OWN else "회사 외 요인"}: {e(r["kind"])}</p>'
        f'<dl><dt>왜</dt><dd>{e(r["why"])}</dd><dt>근거</dt><dd>{e(r["source"])}<br><small>확인 경로: {e(" · ".join(r.get("routes") or []))}</small></dd><dt>다음 확인</dt><dd>{e(r["next"])}</dd></dl></div>'
        for r in rows)
    return f'<section><h2>급등 종목, 왜 올랐나</h2>{cards}<p class="note">{e(NOTE)}</p></section>'
