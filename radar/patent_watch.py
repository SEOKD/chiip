"""한국 전자기업 특허 등록·특허 분쟁 레이더 (마스터 지시 2026-11-08 "기사 소재 발굴 시스템에 한국 전자기업들의 특허 등록 및 특허 침해 소송 관련
데이터도 가져오는 파이프라인 — 지디넷코리아 이기종 기자 참조, 다른 방안도") — 설정 config/patent_watch.yaml, 모델 없음

키 없이 도는 원천
  ① 기자 페이지: 지디넷코리아 이기종 기자 목록에서 특허 제목만(제목·링크, 본문 복제 금지). 기사는 2차 자료 — 그가 인용한 1차 문서를 다시 연다
  ② Federal Register: 미 ITC 공고(337조 조사 개시·예비판정·종료) 중 한국 기업 이름이 든 것 — 1차 문서
  ③ Google News 색인: 다른 매체의 특허·소송 기사 제목(한·영) — 원문 확인 필요
무료 키가 있어야 도는 원천(없으면 건너뛰고 errors에 '키 대기')
  ④ CourtListener: 미국 연방법원 특허 소송(사건 성격 Patent) 접수 — 당사자에 한국 기업
  ⑤ USPTO Open Data Portal: PTAB 무효심판(IPR·PGR) 청구·특허 등록(감시 기술어가 든 것)
  ⑥ DART: '소송등의제기' 공시(전 종목, 회사 공시 — 특허 여부는 본문 확인)
  KIPRIS(한국 특허심판원)는 키가 오면 공식 문서로 붙인다.
처음 보는 원천은 최근 2일 항목만 새 소식으로 받고 나머지는 기준선으로 기록한다(옛 항목을 새 소식으로 올리지 않는다). 새 항목은 radar inbox src-patent와
knowledge/models/patents/latest.json {as_of, items[], errors[]} — 기사 소재 후보 풀 ⑥이 본다.
금지표: 소송 제기 → 손해 확정이 아니다(판결·합의·배상액), 재심사 청구 → 특허 무효가 아니다(재심사 명령·최종 결정), 특허 등록 → 양산·매출이 아니다.
사용: py radar/patent_watch.py [--status]
"""
import hashlib
import html
import json
import re
import sys
import urllib.parse
from datetime import timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from pollers import common  # noqa: E402

CFG = "config/patent_watch.yaml"
OUT = common.ROOT / "knowledge" / "models" / "patents" / "latest.json"
GN_KO = "https://news.google.com/rss/search?q={q}&hl=ko&gl=KR&ceid=KR:ko"
GN_EN = "https://news.google.com/rss/search?q={q}&hl=en-US&gl=US&ceid=US:en"
FR = "https://www.federalregister.gov/api/v1/documents.json"
CL = "https://www.courtlistener.com/api/rest/v4/search/"
ODP = "https://api.uspto.gov/api/v1"


def cfg():
    return common.load_yaml(CFG)


def who(text, comps):
    """제목·본문에 든 한국 기업 → [(id, 한국어 이름)]"""
    t = text.lower()
    out = [(c.get("id"), c["ko"]) for c in comps if c["ko"].lower() in t or any(e.lower() in t for e in c.get("en") or [])]
    if not out:   # 정식 이름이 없을 때만 약칭(삼성·한미·LGD) — 정식 이름과 겹쳐 두 번 세지 않는다
        out = [(c.get("id"), c["ko"]) for c in comps if any(a.lower() in t for a in c.get("alias") or [])][:2]
    return out


def _day(v):
    """RSS 날짜(RFC 822 또는 ISO) → YYYY-MM-DD"""
    from email.utils import parsedate_to_datetime
    try:
        return parsedate_to_datetime(v).astimezone(common.now_kst().tzinfo).date().isoformat()
    except (TypeError, ValueError):
        return str(v or "")[:10]


def reporter_rows(c, errors):
    """① 기자 목록 페이지 — 특허 제목만"""
    rx = re.compile(c["title_re"], re.I)
    out = []
    for r in c.get("reporters") or []:
        try:
            h = common.http_get(r["url"], timeout=30).decode("utf-8", errors="replace")
            for path, no, title in re.findall(r'<a href="(/view/\?no=(\d+))">\s*<h3>(.*?)</h3>', h, re.S):
                t = html.unescape(common.strip_tags(title)).strip()
                if rx.search(t):
                    d = f"{no[:4]}-{no[4:6]}-{no[6:8]}"
                    out.append({"src": r["id"], "kind": "기자 기사(2차)", "title": t, "url": r["base"] + path, "date": d, "primary": False,
                                "note": f"{r['name']} — 기사가 인용한 1차 문서(USPTO·ITC·법원·특허심판원)를 다시 연다"})
        except Exception as e:
            errors.append(f"{r['id']}: {type(e).__name__}")
    return out


def fedreg_rows(c, since, errors):
    """② 미 ITC 공고 — 회사 이름 전문 검색(337조 사건은 제목에 회사가 없어 본문 검색)"""
    out = []
    for co in c["companies"]:
        for name in co.get("en") or []:
            try:
                q = {"conditions[agencies][]": "international-trade-commission", "conditions[term]": f'"{name}"',
                     "conditions[publication_date][gte]": since, "order": "newest", "per_page": 20,
                     "fields[]": ["title", "publication_date", "html_url", "document_number", "type"]}
                url = FR + "?" + urllib.parse.urlencode(q, doseq=True)
                for d in json.loads(common.http_get(url, timeout=30)).get("results") or []:
                    out.append({"src": "fedreg-itc", "kind": "미 ITC 공고(1차)", "title": d["title"], "url": d["html_url"], "date": d["publication_date"],
                                "primary": True, "companies": [co["ko"]], "ids": [co["id"]] if co.get("id") else [],
                                "note": "337조 조사 — 침해 인정 시 수입금지명령 가능. 개시·예비판정·최종판정·종료 단계를 구분한다"})
            except Exception as e:
                errors.append(f"fedreg {name}: {type(e).__name__}")
    return out


def gn_rows(c, errors):
    """③ Google News 색인 — 회사 묶음 × 특허어, 한·영"""
    from pollers import rss
    comps, n = c["companies"], int(c.get("gn_batch") or 6)
    out = []
    for i in range(0, len(comps), n):
        grp = comps[i:i + n]
        ko = " OR ".join(f'"{x["ko"]}"' for x in grp)
        en = " OR ".join(f'"{e}"' for x in grp for e in (x.get("en") or [])[:1])
        for lang, base, q in (("ko", GN_KO, f"({ko}) {c['terms_ko']} when:2d"), ("en", GN_EN, f"({en}) {c['terms_en']} when:2d" if en else "")):
            if not q:
                continue
            try:
                for e in rss.parse_feed(common.http_get(base.format(q=urllib.parse.quote(q)), timeout=30))[:40]:
                    t = html.unescape(common.strip_tags(e["title"]))
                    if re.search(c["title_re"], t, re.I):
                        out.append({"src": f"gn-{lang}", "kind": "언론 색인(제목)", "title": t, "url": e["link"], "date": _day(e.get("date")),
                                    "primary": False, "note": "색인 제목 — 원문·1차 문서 확인 필요"})
            except Exception as e:
                errors.append(f"gn-{lang} {i}: {type(e).__name__}")
    return out


def courtlistener_rows(c, token, since, errors):
    """④ 미국 연방법원 특허 소송 접수(CourtListener RECAP 검색, v4) — 키가 있을 때만"""
    out = []
    names = " OR ".join(f'"{e}"' for x in c["companies"] for e in (x.get("en") or [])[:1])
    q = {"type": "r", "q": f"({names}) AND suitNature:Patent", "filed_after": since, "order_by": "dateFiled desc"}
    try:
        d = json.loads(common.http_get(CL + "?" + urllib.parse.urlencode(q), headers={"Authorization": f"Token {token}"}, timeout=40))
        for r in d.get("results") or []:
            out.append({"src": "courtlistener", "kind": "미 연방법원 특허 소송(1차)", "title": f"{r.get('caseName')} ({r.get('court')}, {r.get('docketNumber')})",
                        "url": "https://www.courtlistener.com" + str(r.get("docket_absolute_url") or r.get("absolute_url") or ""), "date": str(r.get("dateFiled") or "")[:10],
                        "primary": True, "note": "소장 접수 — 손해·금지명령은 판결·합의 전까지 확정이 아니다"})
    except Exception as e:
        errors.append(f"courtlistener: {type(e).__name__}")
    return out


def uspto_rows(c, key, since, errors):
    """⑤ USPTO Open Data Portal — PTAB 무효심판 청구와 감시 기술어가 든 등록 특허. 키가 있을 때만(첫 실행 때 응답 구조를 확인해 고친다)"""
    out = []
    H = {"X-API-KEY": key, "Accept": "application/json"}
    for co in c["companies"]:
        name = (co.get("en") or [None])[0]
        if not name:
            continue
        try:
            q = {"q": f'"{name}"', "rangeFilters": f"trialMetaData.petitionFilingDate {since}:2100-01-01", "limit": 25}
            d = json.loads(common.http_get(f"{ODP}/patent/trials/proceedings/search?" + urllib.parse.urlencode(q), headers=H, timeout=40))
            for r in d.get("patentTrialProceedingDataBag") or d.get("results") or []:
                tid = r.get("trialNumber") or r.get("proceedingNumber") or ""
                out.append({"src": "uspto-ptab", "kind": "PTAB 무효심판(1차)", "title": f"{tid} — {name} 관련 심판", "url": f"https://data.uspto.gov/ptab/{tid}",
                            "date": since, "primary": True, "companies": [co["ko"]], "ids": [co["id"]] if co.get("id") else [],
                            "note": "IPR·PGR 청구 → 개시 결정(약 6개월) → 최종 결정(약 1년). 청구는 무효가 아니다"})
        except Exception as e:
            errors.append(f"uspto-ptab {name}: {type(e).__name__}")
        try:
            kw = " OR ".join(f'"{k}"' for k in c.get("grant_keywords") or [])
            q = {"q": f'applicationMetaData.firstApplicantName:"{name}" AND ({kw})', "rangeFilters": f"applicationMetaData.grantDate {since}:2100-01-01", "limit": 25}
            d = json.loads(common.http_get(f"{ODP}/patent/applications/search?" + urllib.parse.urlencode(q), headers=H, timeout=40))
            for r in d.get("patentFileWrapperDataBag") or []:
                m = r.get("applicationMetaData") or {}
                out.append({"src": "uspto-grant", "kind": "미국 특허 등록(1차)", "title": f"{m.get('patentNumber')} {m.get('inventionTitle')}",
                            "url": f"https://patents.google.com/patent/US{m.get('patentNumber')}", "date": m.get("grantDate") or "", "primary": True,
                            "companies": [co["ko"]], "ids": [co["id"]] if co.get("id") else [], "note": "등록은 권리 확보이지 양산·매출이 아니다"})
        except Exception as e:
            errors.append(f"uspto-grant {name}: {type(e).__name__}")
    return out


def dart_rows(key, since, errors):
    """⑥ DART '소송등의제기' — 전 종목 거래소·주요사항 공시. 특허 소송인지는 본문 확인"""
    out = []
    for ty in ("I", "B"):
        try:
            for page in range(1, 6):
                d = json.loads(common.http_get("https://opendart.fss.or.kr/api/list.json", {"crtfc_key": key, "bgn_de": since.replace("-", ""),
                               "end_de": common.now_kst().strftime("%Y%m%d"), "pblntf_ty": ty, "page_no": page, "page_count": 100}, timeout=30))
                if d.get("status") != "000":
                    if d.get("status") != "013":
                        errors.append(f"dart {ty}: {d.get('status')} {d.get('message')}")
                    break
                for x in d["list"]:
                    if "소송" in x["report_nm"]:
                        out.append({"src": "dart", "kind": "DART 소송 공시(1차)", "title": f"{x['corp_name']} {x['report_nm'].strip()}",
                                    "url": f"https://dart.fss.or.kr/dsaf001/main.do?rcpNo={x['rcept_no']}", "date": x["rcept_dt"][:4] + "-" + x["rcept_dt"][4:6] + "-" + x["rcept_dt"][6:],
                                    "primary": True, "note": "특허 소송인지·청구 금액은 공시 본문 확인"})
                if page >= int(d.get("total_page") or 1):
                    break
        except Exception as e:
            errors.append(f"dart {ty}: {type(e).__name__}")
    return out


def collect(c, env, today, errors):
    since = (today - timedelta(days=int(c.get("lookback_days") or 7))).isoformat()
    rows = reporter_rows(c, errors) + fedreg_rows(c, since, errors) + gn_rows(c, errors)
    keys = c.get("keys") or {}
    for name, fn in (("courtlistener", lambda k: courtlistener_rows(c, k, since, errors)), ("uspto", lambda k: uspto_rows(c, k, since, errors)),
                     ("dart", lambda k: dart_rows(k, since, errors)), ("kipris", None)):
        k = (env.get(keys.get(name, "")) or "").strip()
        if not k:
            errors.append(f"{name}: 키 대기({keys.get(name)}) — docs/TODO_MASTER.md 21-39")
        elif fn:
            rows += fn(k)
    for r in rows:
        hit = who(r["title"], c["companies"])
        r.setdefault("companies", [n for _, n in hit])
        r.setdefault("ids", [i for i, _ in hit if i])
        r["id"] = hashlib.sha1(r["url"].encode()).hexdigest()[:16]
    return rows


def run(today=None):
    today = today or common.now_kst().date()
    c, errors = cfg(), []
    rows = collect(c, common.load_env(), today, errors)
    st = common.load_state("patent_watch", {})
    seen = st.setdefault("seen", {})
    new = []
    titles = set()
    for r in sorted(rows, key=lambda r: not r["primary"] and r["src"].startswith("gn")):   # 같은 기사(기자 페이지·색인)는 한 번만 — 매체명 꼬리를 떼고 비교
        k = re.sub(r"\s+-\s+[^-]+$", "", r["title"]).strip()
        r["dup"] = k in titles
        titles.add(k)
    for r in rows:
        if r.get("dup"):
            continue
        if r["src"] not in seen and r.get("date", "") < (today - timedelta(days=2)).isoformat():   # 처음 보는 원천은 최근 2일 항목만 새 소식, 나머지는 기준선
            continue
        if r["id"] not in seen.get(r["src"], ()) and r["id"] not in {x["id"] for x in new}:
            new.append(r)
    for src in {r["src"] for r in rows}:
        seen[src] = sorted(set(seen.get(src, [])) | {r["id"] for r in rows if r["src"] == src})[-2000:]
    common.save_state("patent_watch", st)
    items = [common.make_item("src-patent", r["id"], r["url"], r["title"], common.iso(common.now_kst()), r["kind"],
                              "ko" if re.search("[가-힣]", r["title"]) else "en", r.get("note", ""), extra={"companies": r["companies"], "primary": r["primary"]})
             for r in new]
    n_in = common.save_new_items(items)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    keep = [r for r in (json.loads(OUT.read_text(encoding="utf-8")).get("items") if OUT.exists() else []) or [] if r.get("first_seen", "") >= (today - timedelta(days=7)).isoformat()]
    for r in new:
        r["first_seen"] = today.isoformat()
    OUT.write_text(json.dumps({"as_of": common.iso(common.now_kst()), "items": new + [r for r in keep if r["id"] not in {x["id"] for x in new}], "errors": errors},
                              ensure_ascii=False, indent=1), encoding="utf-8")
    base = [s for s in {r["src"] for r in rows}]
    return f"수집 {len(rows)} · 새 항목 {len(new)}(inbox {len(n_in) if isinstance(n_in, list) else n_in}) · 원천 {len(base)}" + (f" · 오류·대기 {len(errors)}" if errors else "")


def main(argv):
    sys.stdout.reconfigure(encoding="utf-8")
    if "--status" in argv:
        d = json.loads(OUT.read_text(encoding="utf-8")) if OUT.exists() else {}
        for r in d.get("items") or []:
            print(f"{r.get('first_seen')} | {r['kind']} | {', '.join(r.get('companies') or []) or '-'} | {r['title'][:90]}")
        print(f"오류·대기 {d.get('errors')}")
        return 0
    print(run())
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
