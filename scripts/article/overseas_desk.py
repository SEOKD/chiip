"""해외 데스크 — 해외 상장사 자료·통계에서 한국 전자부품·반도체 기사 소재를 찾는다
(마스터 지시 2026-11-21 "일본·중국·대만·미국·EU·영국 상장 기업들의 실적 결산 자료와 어닝콜 스크립트, 보도자료, 기술자료, 학회 논문 등을 보고
 삼성전자·SK하이닉스·삼성전기·LG이노텍·DB하이텍 등과 연관 있는 최신 정보를 찾고 경제신문 관점으로 기사 거리가 될 수 있는지 판단하고
 매일 기사 소재를 제공하는 알고리즘 … 국내 매체와 기자들이 쓰지 않은 주제 … 각국 수출입 통계, PPI 등 데이터 변화")

결정론(모델 없음, 새 원천 없음 — 이미 수집 중인 수집함·통계 장부만 읽는다). 세 레인:
  문서  수집함(radar/inbox) 최근 window_hours의 결산·IR / 콜·질의응답 / 보도자료 / 논문·학회 중 공급망 상대방(config/korea_counterparties.yaml)이 든 것
  통계  knowledge/models/trade_ppi/latest.json — 품목 PPI·수입액 전년비가 문턱을 넘은 것(config/article_desk.yaml data_links), 대만 PPI 세부
  (기술 레인은 문서 레인의 '논문·학회' 분류로 함께 나온다)
뉴스가치 점수(10점, 편집국 기준 — knowledge/methods/article_yama_playbook.md):
  새 숫자·뉴스 단어 2 + 한국 연결 2(대상 5개사 직접 2, 그 밖 한국 전자기업 1.5) + 문서의 격 2 + 시의성 2(24시간 2·72시간 1) + 국내 공백 2
  국내 공백 = 최근 3일 수집된 한국어 글(공개 텔레그램 채널 17곳·수집함 한국어 제목)에 그 상대방 이름이 몇 번 나왔나(0건 2 · 1~2건 1 · 3건 이상 0).
  이는 사전 추정이다 — 발송 전 모델이 한국어 검색으로 다시 확인하고 기록해야 한다(novelty_gate).
사용: py scripts/article/overseas_desk.py [--date YYYYMMDD] [--top 12]     # outputs/article/desk/<날짜>_desk.json
      py scripts/article/overseas_desk.py --gate <YYYYMMDD>                 # 기록 파일의 국내 미보도 검색 기록 검사(발송 관문)
"""
import argparse
import json
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "radar"))
KST = timezone(timedelta(hours=9))
OUT = ROOT / "outputs" / "article" / "desk"
PITCH = ROOT / "outputs" / "article" / "pitch"
TARGETS = ("삼성전자", "SK하이닉스", "삼성전기", "LG이노텍", "DB하이텍")   # 마스터가 짚은 다섯 — 직접 연결 2점
NUM_RE = re.compile(r"\d[\d.,]*\s*(%|％|억|조|亿|億|万|萬|兆|円|元|\$|B\b|M\b|bn|million|billion|GW|MW|배|倍)")
HANGUL = re.compile(r"[가-힣]")


def cfg():
    import yaml
    return yaml.safe_load((ROOT / "config" / "article_desk.yaml").read_text(encoding="utf-8"))


def counterparties():
    import yaml
    return (yaml.safe_load((ROOT / "config" / "korea_counterparties.yaml").read_text(encoding="utf-8")) or {}).get("counterparties") or []


def _load(p):
    try:
        return json.loads(Path(p).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def kind_of(role, c):
    for k, pat in c["role_kind"].items():
        if re.search(pat, role or ""):
            return k
    return "competitor"


def doc_class(source_id, c):
    for name, pres in c["doc_sources"].items():
        if any(source_id == p or (p.endswith("-") and source_id.startswith(p)) for p in pres):
            return name
    return None


def country(it):
    sid, lang, ids = str(it.get("source_id")), it.get("language"), " ".join(it.get("entities_matched") or [])
    for key, name in (("jp", "일본"), ("tw", "대만"), ("cn", "중국"), ("hk", "중국·홍콩")):
        if f"-{key}-" in sid or re.search(rf"\b{key}-", ids):
            return name
    if re.search(r"\b(eu|gb|uk|de|nl|fr)-", ids) or "fiscal-ir" in sid:
        return "유럽·영국"
    return {"ja": "일본", "zh": "중화권"}.get(lang, "미국")


def match_cp(text, ids, cps):
    for x in cps:
        if set(ids) & set(x.get("ids") or []) or any(re.search(r"(?<![A-Za-z])" + re.escape(n) + r"(?![A-Za-z])", text) for n in x["names"]):
            hit = next((n for n in x["names"] if re.search(r"(?<![A-Za-z])" + re.escape(n) + r"(?![A-Za-z])", text)), x["names"][0])
            return {**x, "hit": hit}
    return None


def korean_corpus(now, days=3):
    """최근 n일 한국어 글(제목·본문 앞부분) — 공개 텔레그램 채널 + 수집함 한국어 제목. 국내 공백 사전 추정용"""
    out, cut = [], (now - timedelta(days=days)).isoformat()
    try:
        from pollers import tg_channels as tg
        for ch in tg.config()["channels"]:
            out += [p["text"][:400] for p in tg.load(ch["handle"]).values() if p.get("at", "") >= cut and HANGUL.search(p.get("text") or "")]
    except Exception:
        pass
    for d in range(days + 1):
        folder = ROOT / "radar" / "inbox" / (now - timedelta(days=d)).strftime("%Y%m%d")
        for f in folder.glob("src-*.json") if folder.exists() else []:
            if f.name.startswith(("src-patent", "src-sec-", "src-price-", "src-gpu-", "src-partner-", "src-legistar")):
                continue
            t = str(_load(f).get("title") or "")
            if HANGUL.search(t):
                out.append(t)
    return out


def gap_score(names, corpus):
    n = sum(1 for t in corpus if any(x and x in t for x in names))
    return (2.0 if n == 0 else 1.0 if n <= 2 else 0.0), n


def doc_lane(now, c, cps, corpus):
    since = now - timedelta(hours=c["window_hours"])
    routine, news = re.compile(c["routine"], re.I), re.compile(c["news_words"], re.I)
    best = {}
    for d in range(c["window_hours"] // 24 + 2):
        folder = ROOT / "radar" / "inbox" / (now - timedelta(days=d)).strftime("%Y%m%d")
        for f in folder.glob("src-*.json") if folder.exists() else []:
            it = _load(f)
            cls = doc_class(str(it.get("source_id") or ""), c)
            if not cls:
                continue
            title = str(it.get("title") or "")
            is_filing = it.get("doc_type") in ("공시", "IR 질의응답", "보도자료", "회사 원문") or cls != "결산·IR" or it.get("source_id") not in ("src-jp-disclosure",)
            if not is_filing and not news.search(title):   # 일본 적시공시 미러의 기사 색인(애널리스트 평가·주가 동향)은 뉴스 단어가 있을 때만 단서로
                continue
            if cls == "보도자료" and not (news.search(title) or NUM_RE.search(title)):
                continue
            if routine.search(title) or HANGUL.search(title[:6]) and "IR:" not in title and cls != "콜·질의응답" and it.get("source_id") != "src-jp-ir-docs":
                continue
            try:
                seen = datetime.fromisoformat(str(it.get("saved_at") or it.get("detected_at")))
            except ValueError:
                continue
            if seen < since:
                continue
            dd = str(it.get("doc_date") or it.get("published_at") or "")[:10]
            if dd and dd < (now - timedelta(days=c["doc_max_age_days"])).date().isoformat():
                continue
            text = f"{title} {it.get('snippet') or ''} {it.get('company_en') or ''}"
            cp = match_cp(text, it.get("entities_matched") or [], cps)
            if cls == "논문·학회" and not cp:   # 논문은 상대방 이름이 없어도 한국 대상 기업·기술이 제목에 있으면 본다
                if not re.search(r"Samsung|SK hynix|SK Hynix|LG Innotek|DB HiTek|HBM|hybrid bonding|MLCC|glass (core|substrate)|FC-?BGA|DRAM|NAND|GaN|SiC", text):
                    continue
                cp = {"names": ["연구"], "korea": [k for k, p in (("삼성전자", "Samsung|DRAM|NAND|HBM"), ("SK하이닉스", "hynix|Hynix|HBM|DRAM|NAND"), ("삼성전기", "MLCC|glass|FC-?BGA"), ("LG이노텍", "Innotek|FC-?BGA|glass"), ("DB하이텍", "HiTek|GaN|SiC")) if re.search(p, text)], "role": "기술"}
            if not cp or not cp.get("korea"):
                continue
            kind = "tech" if cls == "논문·학회" else kind_of(cp.get("role"), c)
            name = cp.get("hit") or cp["names"][0]
            ko = c["ko_names"].get(name, []) + c["ko_names"].get(cp["names"][0], []) + [n for n in cp["names"] if HANGUL.search(n)]
            gap, mentions = gap_score(ko or [name], corpus) if name != "연구" else (1.5, None)
            age_h = (now - seen).total_seconds() / 3600
            parts = {"새 숫자": (1.0 if NUM_RE.search(text) else 0) + (1.0 if news.search(text) else 0),
                     "한국 연결": 2.0 if set(cp["korea"]) & set(TARGETS) else 1.5,
                     "문서의 격": c["doc_weight"][cls],
                     "시의성": 2.0 if age_h <= 24 else 1.0 if age_h <= 72 else 0.5,
                     "국내 공백": gap}
            cand = {"lane": "문서", "class": cls, "country": country(it), "counterparty": name, "role": cp.get("role", ""), "korea": cp["korea"], "kind": kind,
                    "archetype": c["archetypes"][kind]["name"], "lead_frame": c["archetypes"][kind]["lead"], "title": title, "url": it.get("url"), "primary": is_filing,
                    "doc": it.get("local_text") or it.get("local_pdf") or it.get("fetch") or it.get("url"), "doc_date": dd, "seen": seen.isoformat(timespec="minutes"),
                    "source_id": it.get("source_id"), "ids": it.get("entities_matched") or [], "kr_mentions_3d": mentions, "parts": parts, "score": round(sum(parts.values()), 2)}
            key = (name, cls)
            if key not in best or cand["score"] > best[key]["score"]:
                cand["more"] = (best.get(key) or {}).get("more", []) + ([best[key]["title"]] if key in best else [])
                best[key] = cand
            else:
                best[key].setdefault("more", []).append(title)
    return list(best.values())


def data_lane(now, c):
    d = _load(ROOT / "knowledge" / "models" / "trade_ppi" / "latest.json")
    out = []
    fresh = (now - timedelta(days=75)).strftime("%Y-%m")   # 두 달 반 넘은 통계는 새 숫자가 아니다
    names = {"us": "미국", "uk": "영국", "jp": "일본", "eu": "유럽연합", "kr": "한국", "tw": "대만", "hk": "홍콩"}
    for key, link in (c.get("data_links") or {}).items():
        m = (d.get("inputs") or {}).get(key) or {}
        hits = []
        for reg, v in (m.get("ppi") or {}).items():
            if v and v.get("yoy") is not None and abs(v["yoy"]) >= link["ppi_yoy"] and str(v.get("period")) >= fresh and reg != "hk":
                hits.append({"what": f"{names.get(reg, reg)} 생산자물가 {v['yoy']:+.1%}({v['period']})", "size": abs(v["yoy"]) / link["ppi_yoy"]})
        for reg, v in (m.get("trade") or {}).items():
            if reg in ("tw", "tw_goods"):   # 구조가 달라 대만 PPI 세부로 본다. 일본 값은 2026-11-22에 고쳤다(전년 표가 2021~2025년을 한 표에 담아 다섯 해가 더해지던 결함 — radar/trade_ppi.py trade_estat)
                continue
            rows = ([(reg, v)] if "yoy" in v else []) + [(f"{reg}←{p}", pv) for p, pv in (v.get("partners") or {}).items() if p in ("KR", "大韓民国")]
            for label, pv in rows:
                if pv.get("yoy") is not None and abs(pv["yoy"]) >= link["trade_yoy"] and pv["yoy"] > -0.6 and str(pv.get("period")) >= fresh:   # −60% 아래 급감은 부분 집계·분류 변경일 수 있어 후보로 올리지 않는다(원자료 확인 대상)
                    r, _, p = label.partition("←")
                    hits.append({"what": f"{names.get(r, r)} 수입액{'(한국산)' if p else ''} {pv['yoy']:+.0%}({pv['period']})" + (f" · 한국산 비중 {pv['share']:.0%}" if p and pv.get("share") else ""),
                                 "size": abs(pv["yoy"]) / link["trade_yoy"] * (1.5 if p else 1)})
        if not hits:
            continue
        hits.sort(key=lambda h: -h["size"])
        parts = {"새 숫자": 2.0, "한국 연결": 2.0 if set(link["korea"]) & set(TARGETS) else 1.5, "문서의 격": 1.5,
                 "시의성": 1.0, "국내 공백": 1.5 if len(hits) >= 2 else 1.0}   # 통계 세부 품목·나라별 값은 국내 보도가 드물다(사전 추정 — 검색으로 확인)
        out.append({"lane": "통계", "class": "수출입·PPI", "country": "다국", "counterparty": m.get("name", key), "role": "통계", "korea": link["korea"], "kind": "data",
                    "archetype": c["archetypes"]["data"]["name"], "lead_frame": c["archetypes"]["data"]["lead"], "title": f"{m.get('name', key)}(HS {m.get('hs', '')}) — " + " / ".join(h["what"] for h in hits[:4]),
                    "angle": link["angle"], "input": key, "doc": "knowledge/models/trade_ppi/latest.json", "doc_date": d.get("as_of"), "ids": [], "parts": parts, "score": round(sum(parts.values()), 2),
                    "caution": "금액 = 가격 × 물량(나누지 않음). 특정 기업 매출로 바로 잇지 않는다. 별표(업종 대용) 지수는 품목 지수가 아니다 — py radar/trade_ppi.py --status로 확인"})
    for name, v in ((d.get("taiwan") or {}).get("ppi") or {}).items():
        for pat, link in (c.get("tw_ppi_links") or {}).items():
            if pat in name and v.get("yoy") is not None and abs(v["yoy"]) >= link["yoy"] and str(v.get("period")) >= fresh:
                parts = {"새 숫자": 2.0, "한국 연결": 2.0, "문서의 격": 1.5, "시의성": 1.0, "국내 공백": 1.5}
                out.append({"lane": "통계", "class": "수출입·PPI", "country": "대만", "counterparty": f"대만 생산자물가 {name}", "role": "통계", "korea": link["korea"], "kind": "data",
                            "archetype": c["archetypes"]["data"]["name"], "lead_frame": c["archetypes"]["data"]["lead"], "title": f"대만 생산자물가 {name} {v['yoy']:+.1%}({v['period']})",
                            "doc": "knowledge/models/trade_ppi/latest.json", "doc_date": d.get("as_of"), "ids": [], "parts": parts, "score": round(sum(parts.values()), 2),
                            "caution": "대만 주계총처 생산자물가 세부 — 한국 기업 판가와 같은 품목·같은 기간인지 맞춘 뒤 비교"})
    return out


DATA_STATE = ROOT / "radar" / "state" / "article_desk_data.json"
DATA_FRESH_DAYS = 2   # 통계는 새 달 값이 처음 잡힌 날부터 이틀만 후보다 — 같은 숫자가 매일 상위를 채우지 않게


def fresh_data(cands, now, state_path=None, write=True):
    """통계 후보 중 '새로 나온 값'만. 값 서명(제목 = 품목·기간·변화율)이 처음 보인 날을 기록한다"""
    state_path = state_path or DATA_STATE
    st = _load(state_path) or {}
    today, keep = now.date().isoformat(), []
    cut = (now - timedelta(days=DATA_FRESH_DAYS)).date().isoformat()
    for x in cands:
        first = st.setdefault(x["title"], today)
        if first >= cut:
            keep.append({**x, "first_seen": first})
    if write:
        state_path.parent.mkdir(parents=True, exist_ok=True)
        state_path.write_text(json.dumps({k: v for k, v in st.items() if v >= (now - timedelta(days=120)).date().isoformat()}, ensure_ascii=False, indent=1), encoding="utf-8")
    return keep


def recent_yama(now, days=7):
    log = PITCH / "log.csv"
    if not log.exists():
        return ""
    cut = (now - timedelta(days=days)).date().isoformat()
    return " ".join(x for x in log.read_text(encoding="utf-8").splitlines() if x[:10] >= cut)


def run(now=None, c=None, write=True):
    now, c = now or datetime.now(KST), c or cfg()
    corpus = korean_corpus(now)
    cands = doc_lane(now, c, counterparties(), corpus) + fresh_data(data_lane(now, c), now, write=write)
    used = recent_yama(now)
    for x in cands:
        names = [x["counterparty"]] + c["ko_names"].get(x["counterparty"], [])
        if x["lane"] == "문서" and any(n in used for n in names):
            x["score"] = round(x["score"] - 2, 2)
            x["note"] = "최근 7일 기사 소재에 나온 상대방 — 후속 각도만"
    # 한 유형·한 나라가 상위를 독차지하지 않게: 같은 (나라, 유형) 두 번째부터 0.5씩 깎는다
    cands.sort(key=lambda x: -x["score"])
    seen = {}
    for x in cands:
        k = (x["country"], x["kind"])
        x["rank_score"] = round(x["score"] - 0.5 * seen.get(k, 0), 2)
        seen[k] = seen.get(k, 0) + 1
    cands.sort(key=lambda x: -x["rank_score"])
    return cands


SEC_RE = re.compile(r"(?m)^#{1,3}\s*기사\s*[①②③④⑤⑥⑦⑧⑨\d]")


def novelty_gate(md, c=None):
    """기록 파일(outputs/article/pitch/<날짜>.md) 검사 — 기사마다 '국내 보도 검색' 기록(검색어 n개 이상·판정)과 '야마 유형'이 있어야 한다"""
    c = c or cfg()
    nv, bad = c["novelty"], []
    idx = [m.start() for m in SEC_RE.finditer(md)]
    if not idx:
        return ["기록 파일에 '## 기사①' 같은 기사 절이 없다"]
    for i, s in enumerate(idx):
        sec = md[s: idx[i + 1] if i + 1 < len(idx) else len(md)]
        head = sec.splitlines()[0].strip("# ")
        m = re.search(r"국내 보도 검색[^\n]*\n((?:\s*[-*·].*\n?)+)", sec)
        qs = [x for x in (m.group(1).splitlines() if m else []) if "검색어" in x]
        if len(qs) < nv["min_queries"]:
            bad.append(f"{head}: '국내 보도 검색' 아래 검색어 줄 {len(qs)}개 — {nv['min_queries']}개 이상(검색어·검색처·날짜·결과 건수)")
        if not any(v in sec for v in nv["verdicts"]):
            bad.append(f"{head}: 판정({'·'.join(nv['verdicts'])}) 없음 — 이미 보도된 각도면 뺀다")
        if "야마 유형" not in sec:
            bad.append(f"{head}: '야마 유형'(고객이 먼저 말했다·경쟁사의 수·공급사 장부·통계·기술 변곡·사라진 문장) 없음")
    return bad


def main(argv):
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("--date")
    ap.add_argument("--top", type=int)
    ap.add_argument("--gate")
    a = ap.parse_args(argv)
    if a.gate:
        f = PITCH / f"{a.gate}.md"
        bad = novelty_gate(f.read_text(encoding="utf-8")) if f.exists() else [f"{f.name} 없음"]
        print("통과" if not bad else "\n".join(f"- {b}" for b in bad))
        return 1 if bad else 0
    c = cfg()
    now = datetime.strptime(a.date, "%Y%m%d").replace(hour=6, tzinfo=KST) if a.date else datetime.now(KST)
    cands = run(now, c)
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / f"{now:%Y%m%d}_desk.json").write_text(json.dumps(cands, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    top = a.top or c["top"]
    print(f"[해외 데스크] 후보 {len(cands)}건 — 문서 {sum(x['lane'] == '문서' for x in cands)} · 통계 {sum(x['lane'] == '통계' for x in cands)} — 상위 {min(top, len(cands))}")
    for i, x in enumerate(cands[:top], 1):
        gap = "" if x.get("kr_mentions_3d") is None else f" · 국내 채널 3일 언급 {x['kr_mentions_3d']}건"
        print(f"{i:2d}. {x['rank_score']:4.1f} [{x['country']}·{x['class']}·{x['archetype']}] {x['counterparty']} → {', '.join(x['korea'][:3])}{gap}\n      {x['title'][:110]}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
