"""공개 잡보드 API — Greenhouse·Lever·Ashby (§11.4 L6 타사 공고 속 T0 언급, §12 해외 법인 채용)
config/job_boards.yaml 대상만. 채용 담당자·지원자 개인 정보는 저장하지 않는다(공고 제목·위치·링크·요구 문구 앞뒤 200자).

2026-11-11 마스터 지시 "대안 만들어" — 링크드인 이력(제외 원천·신원 추적 금지) 대신 협업사 공고의 요구 문구로 파트너십 과제를 잡는다.
  ① 회사 이름(lexicon)과 공정·제품 이름(partner_terms — Samsung SF2·I-Cube, SK hynix …)을 단어 경계로 찾는다.
     전에는 부분 문자열이라 'SEC'가 'security'에 걸렸고, lexicon에 'Samsung' 단독이 없어 'Samsung or TSMC process' 같은 문구를 놓쳤다.
  ② 과제 꼬리표(context_terms — HBM4·base die·PDK·tape-out·2nm …)가 같이 나오면 '파트너십 과제'로 보고 inbox(src-job-boards → Pulse '채용 공고')에도 낸다.
     이름만 나온 공고는 역방향 후보(radar/reverse/inbox, scout 판정)로만 둔다. 채용은 의도이지 실행이 아니다(금지표).
사용: py radar/talent/collectors/jobs_boards.py
"""
import hashlib
import html
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "reverse" / "collectors"))
from common_rev import common, lexicon, save_candidates  # noqa: E402

SOURCE_ID = "src-job-boards"


def fetch(cfg):
    """[(보드, 공고 id, 제목, 위치, 링크, 본문)] — 보드 하나가 실패해도 나머지는 받는다"""
    jobs, errs = [], []
    for token in cfg.get("greenhouse") or []:
        try:
            data = json.loads(common.http_get(f"https://boards-api.greenhouse.io/v1/boards/{token}/jobs", {"content": "true"}, timeout=40))
            for j in data.get("jobs", []):
                jobs.append((token, str(j["id"]), j.get("title", ""), (j.get("location") or {}).get("name", ""),
                             j.get("absolute_url", ""), common.strip_tags(html.unescape(j.get("content", "")))))
        except Exception as e:
            errs.append(f"greenhouse:{token} {type(e).__name__}")
    for slug in cfg.get("lever") or []:
        try:
            for j in json.loads(common.http_get(f"https://api.lever.co/v0/postings/{slug}", {"mode": "json"}, timeout=40)):
                jobs.append((slug, j["id"], j.get("text", ""), (j.get("categories") or {}).get("location", ""),
                             j.get("hostedUrl", ""), common.strip_tags(j.get("descriptionPlain", "") or "")))
        except Exception as e:
            errs.append(f"lever:{slug} {type(e).__name__}")
    for name in cfg.get("ashby") or []:
        try:
            data = json.loads(common.http_get(f"https://api.ashbyhq.com/posting-api/job-board/{name}", timeout=40))
            for j in data.get("jobs", []):
                jobs.append((name, str(j.get("id")), j.get("title", ""), j.get("location", ""),
                             j.get("jobUrl", ""), j.get("descriptionPlain") or common.strip_tags(j.get("descriptionHtml", "") or "")))
        except Exception as e:
            errs.append(f"ashby:{name} {type(e).__name__}")
    for w in cfg.get("workday") or []:   # 대형사 자체 채용(Workday 공개 검색, 2026-11-11 마스터 지시 — 엔비디아·브로드컴·KLA 등). 검색어로 좁힌 공고만 받는다
        try:
            jobs += workday(w, cfg.get("workday_search") or ["Samsung", "SK hynix"])
            WORKDAY.add(w["name"])
        except Exception as e:
            errs.append(f"workday:{w['name']} {type(e).__name__}")
    return jobs, errs


WORKDAY = set()


def workday(w, terms):
    """Workday 공개 채용 검색(/wday/cxs/<테넌트>/<사이트>/jobs, robots 허용 확인 2026-11-11) → 검색어가 걸린 공고와 본문"""
    import urllib.request
    base = f"https://{w['host']}/wday/cxs/{w['tenant']}/{w['site']}"
    found = {}
    for q in terms:
        req = urllib.request.Request(base + "/jobs", data=json.dumps({"appliedFacets": {}, "limit": 20, "offset": 0, "searchText": q}).encode(),
                                     headers={"Content-Type": "application/json", "Accept": "application/json", "User-Agent": common.UA})
        for j in json.loads(urllib.request.urlopen(req, timeout=30).read()).get("jobPostings", []):
            if j.get("externalPath"):
                found.setdefault(j["externalPath"], j)
    cache = common.load_state("job_boards_wd", {})   # 본문은 공고 경로별로 한 번만 받는다(검색어가 늘어 회차가 10분을 넘던 것, 2026-11-11)

    def detail(path):
        if path not in cache:
            d = json.loads(common.http_get(base + path, headers={"Accept": "application/json"}, timeout=30)).get("jobPostingInfo", {})
            cache[path] = [d.get("externalUrl") or f"https://{w['host']}/{w['site']}{path}", common.strip_tags(html.unescape(d.get("jobDescription", "")))[:6000]]
        return path, cache[path]

    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(6) as ex:
        got = dict(ex.map(lambda p: detail(p), list(found)))
    common.save_state("job_boards_wd", dict(list(cache.items())[-3000:]))
    return [(w["name"], p.rsplit("_", 1)[-1], j.get("title", ""), j.get("locationsText", ""), got[p][0], got[p][1]) for p, j in found.items()]


def patterns(cfg, lex):
    """entity → 단어 경계 정규식. 세 글자 이하 대문자 약어('SEC')는 다른 뜻이 많아 뺀다"""
    out = {}
    for eid, info in lex.items():
        names = [n for n in info["names"] if re.search(r"[A-Za-z]", n) and not re.fullmatch(r"[A-Z]{2,3}", n)]
        terms = [re.escape(n) for n in names] + list((cfg.get("partner_terms") or {}).get(eid) or [])
        if terms:
            out[eid] = re.compile(r"(?<![A-Za-z0-9])(?:" + "|".join(terms) + r")(?![A-Za-z0-9])", re.I)
    return out


def run():
    cfg = common.load_yaml("config/job_boards.yaml") or {}
    lex = lexicon()
    pats = patterns(cfg, lex)
    ctx = re.compile(r"(?<![A-Za-z0-9])(?:" + "|".join(cfg.get("context_terms") or ["$^"]) + r")(?![A-Za-z0-9])", re.I)
    neg = re.compile("|".join(re.escape(x) for x in cfg.get("negative_terms") or []) or r"$^", re.I)
    jobs, errs = fetch(cfg)
    kwo = re.compile(r"(?<![A-Za-z0-9])(?:" + "|".join(cfg.get("keyword_only") or ["$^"]) + r")(?![A-Za-z0-9])", re.I)
    hits = []
    for board, jid, title, loc, url, body in jobs:
        text = neg.sub(" ", re.sub(r"\s+", " ", f"{title}. {body}"))
        named = False
        for eid, pat in pats.items():
            m = pat.search(text)
            if m:
                hits.append((board, jid, title, loc, url, text, eid, m))
                named = True
        if not named and kwo.search(text):   # 회사 이름 없이 과제어만(zHBM·NVHBM·HBM5·SF2P 등, 2026-11-11 마스터 키워드 목록)
            hits.append((board, jid, title, loc, url, text, None, kwo.search(text)))
    # 회사 소개 상용구(FuriosaAI 공고마다 'ecosystem includes … SK Hynix') — 보드 공고의 boilerplate_share 이상이면 보드당 1건, Pulse 없음
    from collections import Counter
    per_board = Counter(b for b, *_ in jobs)
    per_hit = Counter((h[0], h[6]) for h in hits)
    share = cfg.get("boilerplate_share", 0.4)
    boiler = {k for k, n in per_hit.items() if n >= 5 and n / per_board[k[0]] >= share and k[0] not in WORKDAY}   # Workday는 검색어로 좁혀 받아 비율이 뜻이 없다
    cands, items, kept = [], [], set()
    for board, jid, title, loc, url, text, eid, m in hits:
        if (board, eid) in boiler:
            if (board, eid) in kept:
                continue
            kept.add((board, eid))
            jid, title = "boilerplate", f"{title} (회사 소개 상용구 — 공고 {per_hit[(board, eid)]}건 공통)"
        if True:
            snip = text[max(0, m.start() - 200):m.end() + 200]
            tags = sorted({x.group(0) for x in ctx.finditer(snip)}, key=str.lower)
            if eid is None:
                tags = sorted(set(tags) | {m.group(0)}, key=str.lower)
            cands.append({"uid": f"{board}:{jid}", "mentioned_entity": eid or "keyword", "match_text": m.group(0), "counterparty": board,
                          "form": "채용", "published_at": "", "language": "en", "url": url, "snippet": snip, "location": loc,
                          "tags": tags, "signal_type_hint": "채용"})
            if tags and jid != "boilerplate":   # 파트너십 과제(이름 + 과제 꼬리표) — Pulse로
                items.append(common.make_item(SOURCE_ID, hashlib.sha1(f"{board}:{jid}:{eid or 'kw'}".encode()).hexdigest()[:16], url,
                                              f"[협업사 채용] {board}: {title} — {m.group(0)} · {', '.join(tags[:5])}",
                                              common.iso(common.now_kst()), "채용", "en", snip[:400],
                                              extra={"entities_matched": [eid] if eid else [], "counterparty": board, "location": loc, "tags": tags,
                                                     "source_class": "협업사 공개 채용 공고(의도, 실행 아님)"}))
    n = save_candidates("L6", SOURCE_ID, cands)
    st = common.load_state("job_boards", {})
    base = set(st.get("based") or [])
    fresh = [it for it in items if it.get("counterparty") in base]
    saved = common.save_new_items(fresh) if fresh else []   # 처음 보는 보드는 기준선만(지난 공고를 Pulse로 쏟지 않는다)
    common.save_state("job_boards", {"based": sorted(base | {b for b, *_ in jobs})})
    common.record_health(SOURCE_ID, not errs or bool(jobs), "; ".join(errs[:5]) or None)
    return len(jobs), n, len(saved)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    print("잡보드: 공고 %d, 역방향 후보 %d, 파트너십 과제(Pulse) %d" % run())
