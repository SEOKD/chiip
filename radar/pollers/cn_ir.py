"""중국 본토 상장 반도체 — 공시·실적 자료·실적설명회 질의응답 수집 (마스터 지시 2026-11-17 "AMEC(688012.SH)의 공시, 어닝콜 자료 및 스크립트를
가져올 수 있는 데이터 파이프라인을 만들어라 … 중국 반도체 업체 중에 본토 증시에 상장된 종목")

경로(공식·공개 조회만, 결정론):
  ① cninfo 巨潮资讯网(증권감독위원회 지정 공시 매체) — 정기보고(年度·半年度·季度报告)·업적 예고·快报, 投资者关系活动记录表(调研 Q&A),
     业绩说明会召开情况 공고. PDF는 pdftotext로 글자만(원문은 git 제외 폴더 radar/inbox/cn_ir). 일반 중요 공시는 기존 src-cn-hk-disclosure가 본다.
  ② 上证路演中心 roadshow.sseinfo.com(상하이거래소 자회사, robots.txt 'Disallow:' 빈칸 = 전부 허용) 공개 API — 상하이 상장사(6xxxxx·688xxx)
     业绩说明会의 질문·답변·발언 전문. 끝난 설명회만 한 번 받는다. 이것이 중국 본토의 '어닝콜 스크립트'다.
  선전 상장사(00xxxx·30xxxx)의 실적설명회는 대개 全景网 路演天下(rs.p5w.net)에서 열린다 — 다음 단계(지금은 cninfo 활동기록표·결과 공고로 본다).
대상: config/cn_semis.yaml + cn_hk_disclosure.targets()['cn'](와치리스트 SSE·SZSE·아시아 스크리너 중국 후보).
출력: 받은편지함 항목 src-cn-ir-qa(질의응답·스크립트 → Pulse 'IR 질의응답') · src-cn-ir-docs(정기보고 등 → 'IR 자료'). 같은 문서는 한 번만.
사용: py radar/pollers/cn_ir.py                 # 한 회차(run_poll이 poll())
      py radar/pollers/cn_ir.py --about 688012   # 한 종목 최근 120일(Analysis 원천, 받은편지함에 넣지 않고 출력만)
"""
import hashlib
import json
import re
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from pollers import common, cn_hk_disclosure as cnd, jp_ir_qa as qa  # noqa: E402

SRC_QA, SRC_DOC = "src-cn-ir-qa", "src-cn-ir-docs"
STATE = "cn_ir"
CACHE = common.ROOT / "radar" / "inbox" / "cn_ir"
CST = timezone(timedelta(hours=8))
RS = "https://roadshow.sseinfo.com/base-service/api/pub/v1/"
PAUSE_S = 1.0
LOOK_D = 10
# 문서 종류 — 제목 규칙(위에서부터 첫 일치). 摘要·英文·更正 등은 뺀다
KINDS = [("qa", re.compile(r"投资者关系活动记录表|调研活动|业绩说明会召开情况|说明会.*(召开情况|问答|纪要)|接待.*调研")),
         ("report", re.compile(r"(年度报告|半年度报告|季度报告)$")),
         ("prelim", re.compile(r"业绩预告|业绩快报|主要经营数据"))]
SKIP = re.compile(r"摘要|英文|更正|补充|取消|延期|提示性|关于召开|会议资料")


def universe():
    """{6자리 코드: {name, en, ko, sub}}"""
    out = {}
    for c in (common.load_yaml("config/cn_semis.yaml") or {}).get("companies") or []:
        out[str(c["code"]).zfill(6)] = c
    try:
        for code, name in cnd.targets()["cn"].items():
            out.setdefault(code, {"code": code, "name": name})
    except Exception:
        pass
    return out


def kind_of(title):
    t = re.sub(r"\s+", "", title)
    if SKIP.search(t):
        return None
    for k, rx in KINDS:
        if rx.search(t):
            return k
    return None


def cn_docs(code, org, days, now):
    """cninfo — [(시각, 제목, PDF 주소, 공시 id, 종류)]. 페이지 2쪽(100건)까지"""
    col = "sse" if code[:1] in "68" else "szse"
    more = False
    out = []
    # relation = 투자자관계 탭(선전 상장사의 投资者关系管理信息·活动记录表는 공시 탭이 아니라 여기에만 있다 — 2026-11-17 NAURA)
    for tab, page in (("fulltext", 1), ("fulltext", 2), ("relation", 1)):
        if page == 2 and not more:
            continue
        body = (f"pageNum={page}&pageSize=50&column={col}&tabName={tab}&searchkey=&stock={code},{org}&category=&"
                f"seDate={(now - timedelta(days=days)).date()}~{now.date()}&isHLtitle=true").encode()
        rows = json.loads(cnd._post(cnd.CNINFO, body).decode("utf-8")).get("announcements") or []
        more = len(rows) >= 50
        for r in rows:
            t = re.sub(r"<[^>]+>", "", r.get("announcementTitle") or "").strip()
            k = "qa" if tab == "relation" else kind_of(t)
            if k:
                out.append((datetime.fromtimestamp((r.get("announcementTime") or 0) / 1000, CST), t,
                            "http://static.cninfo.com.cn/" + (r.get("adjunctUrl") or ""), str(r.get("announcementId")), k))
        time.sleep(PAUSE_S)
    return out


def _rs(path, data):
    req = urllib.request.Request(RS + path, data=urllib.parse.urlencode(data, doseq=True).encode(),
                                 headers={"User-Agent": common.UA, "Content-Type": "application/x-www-form-urlencoded"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read())["datas"][0]


def rs_company(code, cache):
    if code not in cache:
        rec = _rs("company/select_company_list", {"searchKeyWord": code, "pageSize": 9, "pageNo": 1}).get("records") or []
        cache[code] = next((r["companyId"] for r in rec if r.get("stockCode") == code), None)
    return cache[code]


def rs_activities(cid, n=10):
    """실적설명회 목록(최근 n) — [{id, title, start, end}]"""
    rec = _rs("activity/select_company_activity_list", {"companyId": cid, "pageNo": 1, "pageSize": n}).get("records") or []
    out = []
    for r in rec:
        if r.get("activityType") == 1 or "业绩说明会" in (r.get("title") or ""):
            day = str(r.get("startDate") or "")[:10]   # startTime은 '1970-01-01 16:00:00'처럼 시각만 — 날짜는 startDate
            out.append({"id": r["id"], "title": r.get("title") or "", "start": f"{day} {str(r.get('startTime') or '')[11:19] or '00:00:00'}" if day else "",
                        "end": f"{str(r.get('endDate') or '')[:10] or day} {str(r.get('endTime') or '')[11:19] or '23:59:00'}" if day else "", "multi": r.get("isMulti")})
    return out


def rs_transcript(aid, cid=None):
    """질문·답변·발언을 시간순 글로. 합동 설명회(isMulti)는 그 회사(cid) 답변·발언만. (글, 답변 수)"""
    recs, page = [], 1
    while True:
        d = _rs("question_answer/answer_question_page", {"pageNo": page, "pageSize": 50, "questionTypeList": [2, 3, 4], "activityId": aid, "askTypes": [1]})
        recs += d.get("records") or []
        if page * 50 >= (d.get("total") or 0) or not d.get("records"):
            break
        page += 1
        time.sleep(PAUSE_S)
    recs.sort(key=lambda r: r.get("crtTime") or "")
    lines, n = [], 0
    for r in recs:
        if cid and r.get("questionType") in (2, 3) and r.get("companyId") not in (None, cid):
            continue
        who = r.get("guestName") or r.get("userNickName") or ""
        role = f"({r['guestTitle']})" if r.get("guestTitle") else ""
        body = re.sub(r"\s+", " ", r.get("content") or "").strip()
        if r.get("questionType") == 2:
            n += 1
            lines += [f"问: {re.sub(r'\s+', ' ', r.get('questionContent') or '').strip()}", f"答 {who}{role}: {body}", ""]
        elif r.get("questionType") == 3:
            lines += [f"发言 {who}{role}: {body}", ""]
        else:
            lines += [f"主持: {body}", ""]
    return "\n".join(lines).strip(), n


def period(title):
    m = re.search(r"(20\d\d)\s*年\s*(第([一二三四1-4])季度|半年度|年度)", title)
    if not m:
        return None
    if m[3]:
        return f"{m[1]}Q{ {'一': 1, '二': 2, '三': 3, '四': 4}.get(m[3], m[3]) }".replace(" ", "")
    return f"{m[1]}H1" if m[2] == "半年度" else f"{m[1]}FY"


def save_text(code, key, title, url, text):
    CACHE.mkdir(parents=True, exist_ok=True)
    p = CACHE / f"{code}_{hashlib.sha1(key.encode()).hexdigest()[:10]}.txt"
    p.write_text(f"出典: {url}\n资料: {title}\n\n{text}", encoding="utf-8")
    return str(p.relative_to(common.ROOT))


def entity_of(code, _cache={}):
    """와치리스트에 있으면 그 회사 id(config/tradingview_symbols.csv), 없으면 cn-<코드>"""
    if not _cache:
        import csv
        with (common.ROOT / "config" / "tradingview_symbols.csv").open(encoding="utf-8", newline="") as f:
            for r in csv.DictReader(f):
                if r.get("exchange") in ("SSE", "SZSE") and r.get("entity_id"):
                    _cache[r["ticker"].zfill(6)] = r["entity_id"]
        _cache.setdefault("_", "")
    return _cache.get(code) or f"cn-{code}"


def item(code, c, key, kind, title, url, when, text, path, grade="A"):
    qa_kind = kind in ("qa", "transcript")
    name = c.get("ko") or c.get("en") or c.get("name") or code
    extra = {"entities_matched": [entity_of(code)], "publisher": c.get("name"), "kind": kind, "period": period(title), "doc_date": when.date().isoformat(),
             "local_text": path, "chars": len(text), "grade": grade, "tier": "전문·스크립트" if kind == "transcript" else "Q&A" if kind == "qa" else kind,
             "lang": "zh", "ticker": f"{code}.{'SH' if code[:1] in '68' else 'SZ'}"}
    return common.make_item(SRC_QA if qa_kind else SRC_DOC, hashlib.sha1(key.encode()).hexdigest()[:16], url, f"{name}({code}) IR: {title[:80]}",
                            when.astimezone(common.KST).isoformat(timespec="minutes"), "IR 질의응답" if qa_kind else "IR 자료", "zh",
                            f"{kind} · {period(title) or '기간 미확인'} · 글자 {len(text)}", extra=extra)


def collect(code, c, st, now, days=LOOK_D, first=False):
    """한 종목 — 새 문서 항목 목록"""
    seen = set(st.setdefault("seen", []))
    out = []
    org = cnd.cn_org(code, st.setdefault("org", {}))
    if org:
        for when, title, url, aid, kind in cn_docs(code, org, days, now):
            key = f"cninfo:{aid}"
            if key in seen:
                continue
            seen.add(key)
            if first:
                continue
            try:
                text = qa.to_text(url, common.http_get(url, timeout=60))
            except Exception:
                text = ""
            path = save_text(code, key, title, url, text) if text else ""
            out.append(item(code, c, key, kind, title, url, when, text, path))
            time.sleep(PAUSE_S)
    if code[:1] == "6":   # 상하이 상장 — 上证路演中心 실적설명회 전문
        cid = rs_company(code, st.setdefault("rs_company", {}))
        for a in rs_activities(cid) if cid else []:
            key = f"roadshow:{a['id']}:{code}"
            end = a["end"] or a["start"]
            try:
                ended = datetime.fromisoformat(str(end)[:19]).replace(tzinfo=CST) < now - timedelta(minutes=30)
            except ValueError:
                ended = True
            if key in seen or not ended:
                continue
            text, n = rs_transcript(a["id"], cid if a.get("multi") else None)
            if not n:   # 답변이 아직 없으면 다음 회차에 다시
                continue
            seen.add(key)
            if first:
                continue
            url = f"https://roadshow.sseinfo.com/roadshowIndex?id={a['id']}"
            when = datetime.fromisoformat(str(a["start"] or end)[:19]).replace(tzinfo=CST) if (a["start"] or end) else now
            path = save_text(code, key, a["title"], url, text)
            out.append(item(code, c, key, "transcript", a["title"] + f" — 질의응답 {n}건", url, when, text, path))
            time.sleep(PAUSE_S)
    st["seen"] = sorted(seen)[-5000:]
    return out


def poll(env=None, now=None):
    now = now or datetime.now(CST)
    st = common.load_state(STATE, {})
    first = not st.get("seen")   # 처음 켤 때는 지금 있는 문서를 씨앗으로만(옛 자료를 한꺼번에 보내지 않는다)
    items, errs, bad = [], [], st.setdefault("code_mismatch", {})
    for code, c in universe().items():
        try:
            items += collect(code, c, st, now, first=first)
        except Exception as exc:
            errs.append(f"{code} {type(exc).__name__}")
        time.sleep(PAUSE_S)
    common.save_state(STATE, st)
    common.record_health("src-cn-ir", not errs or len(errs) < 5, "; ".join(errs[:5]) or None)
    return items


def about(code, days=120):
    now = datetime.now(CST)
    st = {"seen": []}
    c = universe().get(code, {"name": code})
    return collect(code, c, st, now, days=days)


def main(argv):
    if "--about" in argv:
        for it in about(argv[argv.index("--about") + 1]):
            print(it["published_at"][:10], it["source_id"], it["title"], it.get("chars"))
        return 0
    print(len(poll()))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
