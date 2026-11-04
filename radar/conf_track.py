"""학회 참여 추적(ADR-015, 마스터 지시 2026-11-05 "설계안대로 구현하라") — 삼성·SK·LG 소속 논문을 학회·연도별로 찾는다

2 수집: config/conferences.yaml의 openalex source id로 그해 전 논문 메타데이터(제목·소속·주제·DOI)를 받는다(키 불필요)
3 매칭: config/conference_orgs.yaml — 기관명 일치 A, 원 소속 문자열만 일치 B. 제외 목록(병원·중공업 등)은 버린다
4 분류: 역할(제1저자 소속·공저), 주제(OpenAlex primary_topic), 제목 숫자(Gb·Gbps·층·nm·pJ/b)
5 채점: 최초 진입·숫자·경쟁사 정면 비교·고객·장비사 공저·침묵(전년 대비 편수 급감) — 가중치 config/conference_pipeline.yaml
6 출력: knowledge/entities/conferences/<cf-id>_<연도>_tracker.md, knowledge/models/conferences/counts.csv(집계)
경계: 저자 이름은 저장하지 않는다(일반 직원은 집계만, CLAUDE.md). 원문은 받지 않고 메타데이터·링크만.
사용: py radar/conf_track.py <cf-id|tier1> [연도] [--prev N]
"""
import csv
import json
import re
import sys
import time
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
from pollers import common  # noqa: E402

ROOT = common.ROOT
CONF = ROOT / "config" / "conferences.yaml"
ORGS = ROOT / "config" / "conference_orgs.yaml"
PIPE = ROOT / "config" / "conference_pipeline.yaml"
OUT = ROOT / "knowledge" / "entities" / "conferences"
COUNTS = ROOT / "knowledge" / "models" / "conferences" / "counts.csv"
CACHE = ROOT / "radar" / "conferences" / "cache"   # git 제외
API = "https://api.openalex.org/works"
NUM = re.compile(r"\d[\d.]*\s?(?:Gb/s|Gbps|GT/s|Tb/s|Gb|Tb|GB|TB|nm|Å|-?[Ll]ayers?|[Ll]ayer|pJ/b|fJ|TOPS/W|TOPS|mW|GHz|Mb)\b")


def yml(p):
    return yaml.safe_load(p.read_text(encoding="utf-8"))


def conferences():
    return {c["id"]: c for c in yml(CONF)["conferences"]}


def get(params, tries=3):
    """일시 오류(429·5xx·시간 초과)는 쉬었다가 다시 묻는다"""
    for k in range(tries):
        try:
            return json.loads(common.http_get(API, params, timeout=60))
        except Exception as exc:
            code = getattr(exc, "code", None)
            if k == tries - 1 or (code and code < 500 and code != 429):
                raise
            time.sleep(5 * (k + 1))


def fetch(source, year, sleep=0.15):
    """그해 그 학회 전 논문 — 캐시가 있으면 재사용(과거 연도는 바뀌지 않는다)"""
    CACHE.mkdir(parents=True, exist_ok=True)
    f = CACHE / f"{source}_{year}.json"
    if f.exists() and year < common.now_kst().year:
        return json.loads(f.read_text(encoding="utf-8"))
    out, page = [], 1
    while True:   # 키 없이는 cursor 페이징이 막혀 page 번호로 받는다(page×per-page ≤ 1만 편 — 학회 한 해는 충분)
        d = get({"filter": f"primary_location.source.id:{source},publication_year:{year}", "per-page": "200", "page": str(page),
                 "select": "id,doi,title,publication_date,authorships,primary_topic"})
        res = d.get("results", [])
        out += res
        if len(res) < 200 or page * 200 >= min(d.get("meta", {}).get("count", 0), 10000):
            break
        page += 1
        time.sleep(sleep)
    f.write_text(json.dumps(out, ensure_ascii=False), encoding="utf-8")
    return out


def unit_of(text, orgs):
    """소속 문자열 → (그룹, 단위) 또는 None"""
    low = text.lower()
    if any(x.lower() in low for x in orgs["exclude"]):
        return None
    for g, units in orgs["groups"].items():
        for u in units:
            for m in u["match"]:
                if (m.lower() in low) if len(m) > 4 else re.search(rf"\b{re.escape(m)}\b", text):
                    return g, u["unit"]
    return None


def others(w, names):
    hit = set()
    for a in w.get("authorships", []):
        texts = [i.get("display_name", "") for i in a.get("institutions", [])] + list(a.get("raw_affiliation_strings") or [])
        for n in names:
            if any(n.lower() in t.lower() for t in texts):
                hit.add(n)
    return sorted(hit)


def match(w, orgs):
    """논문 1편 → 매칭 행 또는 None. 저자 이름은 담지 않는다"""
    hits, first = {}, None
    for a in w.get("authorships", []):
        found, conf = None, None
        for i in a.get("institutions", []):
            found = unit_of(i.get("display_name", ""), orgs)
            if found:
                conf = "A"
                break
        if not found:
            for r in a.get("raw_affiliation_strings") or []:
                found = unit_of(r, orgs)
                if found:
                    conf = "B"
                    break
        if found:
            k = found
            hits[k] = min(hits.get(k, "B"), conf)
            if a.get("author_position") == "first":
                first = found
    if not hits:
        return None
    title = w.get("title") or ""
    return {"work": w["id"].rsplit("/", 1)[-1], "doi": w.get("doi"), "title": title, "date": w.get("publication_date"),
            "groups": sorted({g for g, _ in hits}), "units": sorted({u for _, u in hits}), "conf": min(hits.values()),
            "role": "제1저자" if first else "공저", "first_unit": first[1] if first else None,
            "topic": (w.get("primary_topic") or {}).get("display_name"),
            "numbers": NUM.findall(title), "partners": others(w, orgs["partners"])}


def score(row, prev_topics, rival_topics, w8):
    s, why = 0.0, []
    if row["role"] == "제1저자":
        s += w8["first_author"]; why.append("제1저자")
    if row["numbers"]:
        s += w8["numbers"]; why.append("숫자 " + ", ".join(row["numbers"][:3]))
    if row["topic"] and row["topic"] in rival_topics:
        s += w8["rival_same_topic"]; why.append("경쟁사 같은 주제: " + ", ".join(sorted(rival_topics[row["topic"]])[:3]))
    if row["partners"]:
        s += w8["partner"]; why.append("공저(정황): " + ", ".join(row["partners"][:3]))
    if row["topic"] and row["topic"] not in prev_topics:
        s += w8["new_topic"]; why.append("전년 없던 주제")
    return round(s, 1), why


def run(cid, year, prev=2, cfg=None):
    c = conferences()[cid]
    orgs, cfg = yml(ORGS), cfg or yml(PIPE)
    works = [w for s in c.get("openalex", []) for w in fetch(s, year)]
    rows = [r for r in (match(w, orgs) for w in works) if r]
    rival_topics = {}
    for w in works:
        rv = others(w, orgs["rivals"])
        t = (w.get("primary_topic") or {}).get("display_name")
        if rv and t:
            rival_topics.setdefault(t, set()).update(rv)
    history, prev_topics = {}, set()
    for y in range(year - prev, year):
        pw = [w for s in c.get("openalex", []) for w in fetch(s, y)]
        pr = [r for r in (match(w, orgs) for w in pw) if r]
        history[y] = count(pr)
        prev_topics |= {r["topic"] for r in pr if r["topic"]}
    for r in rows:
        r["score"], r["why"] = score(r, prev_topics, rival_topics, cfg["weights"])
    rows.sort(key=lambda r: -r["score"])
    now = count(rows)
    silence = [g for g in ("samsung", "sk", "lg") if history and min(h.get(g, 0) for h in history.values()) >= cfg["silence_min_prev"]
               and now.get(g, 0) <= cfg["silence_ratio"] * min(h.get(g, 0) for h in history.values())]
    return {"cf": cid, "name": c["name"], "year": year, "total": len(works), "rows": rows, "counts": now, "history": history, "silence": silence}


def count(rows):
    out = {}
    for r in rows:
        for g in r["groups"]:
            out[g] = out.get(g, 0) + 1
    return out


GROUP = {"samsung": "삼성", "sk": "SK", "lg": "LG"}


def tracker(res, top=None):
    cfg = yml(PIPE)
    top = top or cfg["tracker_top"]
    lines = [f"# {res['name']} {res['year']} — 삼성·SK·LG 참여 추적", "",
             f"전체 {res['total']}편 중 3사 소속 {len(res['rows'])}편 · 출처: OpenAlex 메타데이터(소속 매칭, 저자 이름은 저장하지 않음)", "",
             "| 연도 | 삼성 | SK | LG |", "|---|---|---|---|"]
    for y, h in sorted({**res["history"], res["year"]: res["counts"]}.items()):
        lines.append(f"| {y} | {h.get('samsung', 0)} | {h.get('sk', 0)} | {h.get('lg', 0)} |")
    if res["silence"]:
        lines += ["", "**침묵 신호:** " + ", ".join(GROUP[g] for g in res["silence"]) + " — 전년들보다 편수가 크게 줄었다(확인 질문 대상, 원인은 미확인)"]
    lines += ["", f"## 상위 {min(top, len(res['rows']))}편 (기사 가치 점수순)", "", "| 점수 | 제목 | 소속 단위 | 역할 | 주제 | 근거 | 매칭 |", "|---|---|---|---|---|---|---|"]
    for r in res["rows"][:top]:
        link = r["doi"] or f"https://openalex.org/{r['work']}"
        lines.append(f"| {r['score']} | [{r['title'][:90]}]({link}) | {', '.join(r['units'])} | {r['role']} | {r['topic'] or '-'} | {'; '.join(r['why']) or '-'} | {r['conf']} |")
    lines += ["", "- 학회 발표는 연구 결과다. 양산·고객 채택·매출로 잇지 않는다(금지표). 공저는 정황이지 공급 관계가 아니다."]
    return "\n".join(lines) + "\n"


def save(res):
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / f"{res['cf']}_{res['year']}_tracker.md").write_text(tracker(res), encoding="utf-8")
    COUNTS.parent.mkdir(parents=True, exist_ok=True)
    old = list(csv.DictReader(COUNTS.open(encoding="utf-8"))) if COUNTS.exists() else []
    keep = {(r["cf"], r["year"]): r for r in old}
    for y, h in {**res["history"], res["year"]: res["counts"]}.items():
        keep[(res["cf"], str(y))] = {"cf": res["cf"], "year": y, "samsung": h.get("samsung", 0), "sk": h.get("sk", 0), "lg": h.get("lg", 0)}
    with COUNTS.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, ["cf", "year", "samsung", "sk", "lg"])
        w.writeheader()
        for k in sorted(keep):
            w.writerow(keep[k])


def main(argv):
    sys.stdout.reconfigure(encoding="utf-8")
    year = next((int(a) for a in argv if a.isdigit() and len(a) == 4), common.now_kst().year - 1)
    prev = int(argv[argv.index("--prev") + 1]) if "--prev" in argv else 2
    cs = conferences()
    ids = [i for i, c in cs.items() if c.get("tier") == 1 and c.get("openalex")] if argv and argv[0] == "tier1" else [argv[0]]
    for cid in ids:
        try:
            res = run(cid, year, prev)
        except Exception as exc:   # 한 학회 실패가 나머지를 막지 않게
            print(json.dumps({"cf": cid, "year": year, "error": f"{type(exc).__name__}: {str(exc)[:120]}"}, ensure_ascii=False))
            continue
        save(res)
        print(json.dumps({"cf": cid, "year": year, "total": res["total"], "counts": res["counts"], "history": res["history"], "silence": res["silence"],
                          "top": [(r["score"], r["title"][:70]) for r in res["rows"][:3]]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
