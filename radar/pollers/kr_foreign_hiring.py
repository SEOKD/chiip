"""해외 반도체 기업의 한국 채용 감시 (마스터 지시 2026-11-11 "마이크론, 샌디스크, KIOXIA, Rapidus, CXMT, YMTC 등 해외 반도체 기업들이
한국 지사에서 한국 엔지니어를 뽑는 공고가 나오면 파악하는 데이터 파이프라인")

링크드인 채용 검색은 robots 전체 금지·제외 원천이라 쓰지 않는다. 설정 config/kr_foreign_hiring.yaml.
  ① 회사 공식 채용 — Workday 공개 검색(마이크론·인텔·엔비디아·KLA·어플라이드)에서 한국 근무지 공고만
  ② 사람인 공개 API(SARAMIN_API_KEY) — 회사 이름 검색, 제목·회사명에 그 회사가 있는 공고만(키가 없으면 '키 대기'로 건너뛴다)
새 공고만 inbox src-kr-foreign-hiring → Pulse '채용 공고'. 첫 회차는 기준선만. 채용 담당자·지원자 정보는 저장하지 않는다.
채용은 의도이지 실행이 아니다(금지표 '채용 증가 → 증설·수주 확정'). 한국 인력 흡수(인재 유출) 신호로 읽되 사람 단위로 추적하지 않는다.
사용: py -m pollers.kr_foreign_hiring   (radar/에서)  /  run_hourly 60분
"""
import hashlib
import json
import re
import sys
import urllib.request
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from pollers import common
else:
    from . import common

SRC = "src-kr-foreign-hiring"
CFG = "config/kr_foreign_hiring.yaml"


def workday(w, terms, loc_re):
    base = f"https://{w['host']}/wday/cxs/{w['tenant']}/{w['site']}"
    out = {}
    for q in terms:
        req = urllib.request.Request(base + "/jobs", data=json.dumps({"appliedFacets": {}, "limit": 20, "offset": 0, "searchText": q}).encode(),
                                     headers={"Content-Type": "application/json", "Accept": "application/json", "User-Agent": common.UA})
        for j in json.loads(urllib.request.urlopen(req, timeout=30).read()).get("jobPostings", []):
            loc = j.get("locationsText") or ""
            path = j.get("externalPath")
            # '2 Locations'처럼 근무지가 접힌 공고는 제목에 한국이 있을 때만
            if path and (loc_re.search(loc) or (re.match(r"\d+ Locations", loc) and loc_re.search(j.get("title", "")))):
                out[path] = {"id": f"{w['tenant']}:{path.rsplit('_', 1)[-1]}", "company": w["name"], "entity": w.get("entity"), "title": j.get("title", ""),
                             "loc": loc, "url": f"https://{w['host']}/{w['site']}{path}", "posted": j.get("postedOn", "")}
    return list(out.values())


def saramin(cfg, key, match):
    out = {}
    for kw in cfg.get("saramin_keywords") or []:
        d = json.loads(common.http_get("https://oapi.saramin.co.kr/job-search", {"access-key": key, "keywords": kw, "count": 110, "sort": "pd"},
                                       headers={"Accept": "application/json"}, timeout=30))
        for j in ((d.get("jobs") or {}).get("job") or []):
            title = (j.get("position") or {}).get("title", "")
            comp = ((j.get("company") or {}).get("detail") or {}).get("name", "")
            if not match.search(f"{title} {comp}"):
                continue
            out[str(j.get("id"))] = {"id": f"saramin:{j.get('id')}", "company": comp, "entity": None, "title": title,
                                     "loc": ((j.get("position") or {}).get("location") or {}).get("name", ""), "url": j.get("url", ""),
                                     "posted": j.get("posting-date", "")}
    return list(out.values())


def run():
    cfg = common.load_yaml(CFG) or {}
    loc_re = re.compile(cfg.get("korea_location") or "Korea", re.I)
    posts, errs = [], []
    for w in cfg.get("workday") or []:
        try:
            posts += workday(w, cfg.get("workday_search") or ["Korea"], loc_re)
        except Exception as e:
            errs.append(f"{w['name']} {type(e).__name__}")
    key = common.load_env().get("SARAMIN_API_KEY")
    if key:
        try:
            posts += saramin(cfg, key, re.compile(cfg.get("company_match") or "$^", re.I))
        except Exception as e:
            errs.append(f"saramin {type(e).__name__}")
    else:
        errs.append("사람인 키 대기(SARAMIN_API_KEY)")
    st = common.load_state("kr_foreign_hiring", {})
    seen, first = set(st.get("seen") or []), not st.get("seen")
    items = []
    for p in posts:
        if p["id"] in seen:
            continue
        seen.add(p["id"])
        if first:
            continue
        items.append(common.make_item(SRC, hashlib.sha1(p["id"].encode()).hexdigest()[:16], p["url"],
                                      f"[해외 반도체 한국 채용] {p['company']}: {p['title']} — {p['loc']}", common.iso(common.now_kst()), "채용", "ko",
                                      f"게시 {p['posted']}", extra={"entities_matched": [p["entity"]] if p["entity"] else [], "counterparty": p["company"],
                                                                   "source_class": "해외 반도체 기업 한국 채용(의도, 실행 아님)"}))
    st["seen"] = sorted(seen)[-20000:]
    common.save_state("kr_foreign_hiring", st)
    saved = common.save_new_items(items) if items else []
    common.record_health(SRC, bool(posts) or not [e for e in errs if "키 대기" not in e], "; ".join(errs) or None)
    return len(posts), len(saved)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    print("해외 반도체 한국 채용: 공고 %d · 새 알림 %d" % run())
    for p in [x for w in (common.load_yaml(CFG) or {}).get("workday", [])[:1] for x in workday(w, ["Korea"], re.compile("Korea|Seoul", re.I))][:8]:
        print(" ", p["company"], "|", p["title"], "|", p["loc"])
