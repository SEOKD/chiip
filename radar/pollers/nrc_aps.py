"""미국 원자력규제위원회(NRC) ADAMS 공개 문서 — 감시 회사의 인허가 신청·추가 자료 요구·안전성 평가·허가 (원천 src-nrc-aps, 설정 config/nrc_aps.yaml)
(마스터 2026-11-22 "NRC_APS_KEY를 넣었다" — TODO 21-64. 보도자료보다 먼저 나오는 연방 서류, 공공 저작물 17 U.S.C. §105)

API: POST https://adams-api.nrc.gov/aps/api/search, 헤더 Ocp-Apim-Subscription-Key(.env NRC_APS_KEY) — NRC APS API Guide(adams-search.nrc.gov/assets/APS-API-Guide.pdf).
회사마다 작성·수신 기관(AuthorAffiliation·AddresseeAffiliation)에 이름이 든 문서 중 DateAddedTimestamp가 최근 LOOKBACK_D일인 것.
첫 회차는 기준선만. 신호 문서 종류(config signal)만 inbox, 나머지(정례 검사·사본)는 seen에만. 본문은 저장하지 않는다(제목·종류·도켓·링크).
키가 없으면 조용히 건너뛴다. 사용: py -m pollers.nrc_aps [--show]   (radar/에서)
"""
import json
import re
import sys
import urllib.request
from datetime import timedelta

from . import common

SRC = "src-nrc-aps"
STATE = "nrc_aps"
API = "https://adams-api.nrc.gov/aps/api/search"
LOOKBACK_D = 7


def cfg():
    return common.load_yaml("config/nrc_aps.yaml") or {}


def search(key, names, since, post=None):
    body = {"q": "", "filters": [{"field": "DateAddedTimestamp", "value": f"(DateAddedTimestamp ge '{since}')"}],
            "anyFilters": [{"field": f, "value": n, "operator": "contains"} for n in names for f in ("AddresseeAffiliation", "AuthorAffiliation")],
            "legacyLibFilter": False, "mainLibFilter": True, "sort": "DateAddedTimestamp", "sortDirection": 1, "skip": 0}
    req = urllib.request.Request(API, data=json.dumps(body).encode(), headers={"Ocp-Apim-Subscription-Key": key, "Content-Type": "application/json", "User-Agent": common.UA})
    raw = (post or (lambda r: urllib.request.urlopen(r, timeout=60).read()))(req)
    docs = [x.get("document") or {} for x in (json.loads(raw).get("results") or [])]
    # 'contains'는 낱말 단위로 느슨하게 맞는다(2026-11-22 점검: 'American Centrifuge Operating'이 NRC 검사 지침서까지 잡음) — 기관 이름에 실제로 든 것만
    low = [n.lower() for n in names]
    return [d for d in docs if any(n in a.lower() for a in _list(d.get("AuthorAffiliation")) + _list(d.get("AddresseeAffiliation")) for n in low)]


def _list(v):
    return v if isinstance(v, list) else ([v] if v else [])


def poll(env=None, post=None):
    key = (env or common.load_env()).get("NRC_APS_KEY")
    if not key:
        return []
    c = cfg()
    sig = re.compile(c.get("signal") or ".")
    st = common.load_state(STATE, {})
    seen, based = set(st.get("seen") or []), set(st.get("based") or [])
    since = (common.now_kst() - timedelta(days=LOOKBACK_D)).strftime("%Y-%m-%d")
    items, fails = [], []
    for co in c.get("companies") or []:
        try:
            docs = search(key, co["names"], since, post)
        except Exception as exc:
            fails.append(f"{co['id']}:{type(exc).__name__}")
            continue
        first = co["id"] not in based
        based.add(co["id"])
        for d in docs:
            acc = d.get("AccessionNumber")
            if not acc or acc in seen:
                continue
            seen.add(acc)
            kinds = _list(d.get("DocumentType"))
            title = d.get("DocumentTitle") or d.get("Name") or ""
            if first or not sig.search(" ".join(kinds) + " " + title):
                continue
            tk = co.get("ticker") or ""
            items.append(common.make_item(
                SRC, acc, d.get("Url") or f"https://adams-search.nrc.gov/", f"[NRC {'·'.join(kinds[:2])}] {co['names'][0]}{f'({tk})' if tk else ''}: {title}",
                (d.get("DateAddedTimestamp") or d.get("DocumentDate") or "").replace(" ", "T") or common.iso(common.now_kst()), "공시", "en",
                f"도켓 {', '.join(_list(d.get('DocketNumber')))} · 작성 {', '.join(_list(d.get('AuthorAffiliation')))[:120]} · 수신 {', '.join(_list(d.get('AddresseeAffiliation')))[:120]} · 문서일 {d.get('DocumentDate')}",
                extra={"entities_matched": [co["id"]], "ticker": tk, "publisher": "U.S. NRC", "source_class": "미국 연방 규제 서류(1차)",
                       "nrc_accession": acc, "nrc_docket": _list(d.get("DocketNumber")), "nrc_type": kinds}))
    st["seen"] = sorted(seen)[-20000:]
    st["based"] = sorted(based)
    st["fails"] = fails
    common.save_state(STATE, st)
    print(f"nrc_aps: 회사 {len(c.get('companies') or [])} · 실패 {len(fails)} · 새 문서 {len(items)}")
    return items


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    if "--show" in sys.argv:
        k = common.load_env().get("NRC_APS_KEY")
        since = (common.now_kst() - timedelta(days=30)).strftime("%Y-%m-%d")
        for co in cfg().get("companies") or []:
            ds = search(k, co["names"], since)
            print(f"{co['id']:18} 30일 {len(ds):>3}  " + (f"{ds[0].get('DateAddedTimestamp')} {_list(ds[0].get('DocumentType'))[:1]} {(ds[0].get('DocumentTitle') or '')[:70]}" if ds else ""))
    else:
        print(len(poll()))
