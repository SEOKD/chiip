"""구루 포지션 추종 — 고른 구루 명단(config/gurus.yaml, CIK 45곳 확인)의 13F 신규·증액·최고 확신·기밀 보유 공개와 공개 포트폴리오 페이지 변화
(마스터 지시 2026-11-15 "패니메이 & 프레디맥과 같이 구루 포지션을 따라가는 전략", 설계 knowledge/methods/discovery_engine.md '구루 추종', 근거 조사 E)

수집(결정론, run_hourly 360분 — 새 13F가 없으면 구루마다 제출 목록 1회만):
  data.sec.gov 제출 목록(명단의 CIK들, 기간 표시) → 보고 기간별 가장 늦은 13F-HR 원본 최근 3분기 → 정보표 XML(주식 SH만, 풋·콜 제외).
  13F-HR/A 중 'NEW HOLDINGS'(기밀 처리했던 보유 공개)는 따로 읽는다. 캐시 radar/state/guru13f/<CIK>_<보고일>[_a].json(git 제외).
  공개 포트폴리오 페이지(pages — robots.txt 허용만, 주 1회): 새로 나온 줄·회사 이름 → guru/thesis(13F에 안 나오는 OTC 종목 — 패니메이·프레디맥 경로).
점수(조사 E §7 GuruScore, 사전값 = config/gurus.yaml rules, 등록부 prm-guru-*):
  종목 점수 = Σ_구루 q_g × (w_type × w_rank) + 합의 가점
    w_type: 신규 1.0(직전 2분기 없음, 비중 0.5% 이상) · 증액 0.5×min(증가율,1)(+25% 이상) · 상위 3 유지 0.3 · 기밀 보유 공개 1.2
    w_rank: 비중 순위 1~5 = 1.0·0.8·0.65·0.55·0.5, 6~10 = 0.2, 그 밖 0 — 비중 2% 미만은 확신 가점 0
    q_g: 상위 5 비중 ≥ 0.5 ×1.2 · 13F 주식 ≥ $10B ×0.8 · 150종목 이상 ×0.5 · 체제 변화 8분기 안 ×0.8 · 비활성 ×0
    합의 가점: 같은 분기 다른 구루가 신규·증액하면 1명당 +0.15(최대 3명) — 그냥 같이 들고 있는 것은 가점 없음(Chen·Jegadeesh·Wermers 2000)
  단서 강도 = 3 + 5 × 점수(상한 10), 5.0 미만은 장부에 넣지 않는다. 날짜 = 그 신호를 만든 13F 제출일(공개 시점).
  쏠림 감점: 시장 전체 13F 보유 기관 비율 20% 이상 −0.3, 40% 이상 −0.6(조사 E의 헤지펀드 상위 10 기준을 보유 기관 비율로 근사 — 초대형주가 위를 덮지 않게)
  아직 없는 것(조사 E): 분기 말→제출 사이 +30% 상승 ×0.7, 구루 매입 단가 대비, 10% 이상 보유 구루의 Form 4.
한계: 13F는 분기 말 기준·최대 45일 지연(금지표: 기관 매입 → 주가 상승 아님). 13(f) 대상 증권만 보인다 — OTC·공매도·해외 직접 보유는 없다.
SEC 접속: 프로젝트 User-Agent(fulltext.sec_ua), 초당 5회 이하(thirteenf_market.get — 429면 전역 휴식).
사용: py radar/guru13f.py [--force] · --show
"""
import hashlib
import json
import re
import sys
import urllib.robotparser
import xml.etree.ElementTree as ET
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from pollers import common  # noqa: E402

ROOT = common.ROOT
STATE = ROOT / "radar" / "state" / "guru13f"
OUT = ROOT / "knowledge" / "models" / "guru"
LATEST = OUT / "guru_latest.json"
SOURCE_ID = "src-guru13f"
KIND_KO = {"new": "신규 편입", "add": "증액", "best": "최고 확신 유지", "confidential": "기밀 보유 공개", "cluster": "구루 겹침", "thesis": "공개 논지"}
DEF = {"crowd_lo": 0.20, "crowd_hi": 0.40, "crowd_pen_lo": 0.3, "crowd_pen_hi": 0.6, "w_new": 1.0, "w_add": 0.5, "add_min": 0.25, "w_best": 0.3, "w_confidential": 1.2, "rank_w": [1.0, 0.8, 0.65, 0.55, 0.5], "rank_w_6_10": 0.2,
       "min_w": 0.02, "new_min_w": 0.005, "q_conc": 1.2, "q_giant": 0.8, "q_diversified": 0.5, "q_regime": 0.8, "consensus_step": 0.15, "consensus_cap": 3,
       "strength_base": 3.0, "strength_slope": 5.0, "lead_min": 5.0}


def cfg():
    c = common.load_yaml("config/gurus.yaml") or {}
    return c.get("gurus") or [], {**DEF, **(c.get("rules") or {})}


def _get(url):
    import thirteenf_market
    return thirteenf_market.get(url)


def _q(d):
    """'2026-09-30' → '2026Q3'"""
    y, m = int(d[:4]), int(d[5:7])
    return f"{y}Q{(m - 1) // 3 + 1}"


def filings(ciks):
    """{보고일: (제출일, 접수번호, cik)} 원본 13F-HR(보고 기간마다 가장 늦은 것) + [(보고일, 제출일, 접수번호, cik)] 13F-HR/A"""
    best, amends = {}, []
    for c in ciks:
        cik = str(int(c["cik"]))
        sub = json.loads(_get(f"https://data.sec.gov/submissions/CIK{cik.zfill(10)}.json"))
        r = sub.get("filings", {}).get("recent", {})
        for i in range(len(r.get("form", []))):
            rd, fd, ad = r["reportDate"][i], r["filingDate"][i], r["accessionNumber"][i]
            if not rd:
                continue
            q = _q(rd)
            if (c.get("from") and q < c["from"]) or (c.get("to") and q > c["to"]):
                continue
            if r["form"][i] == "13F-HR" and (rd not in best or fd > best[rd][0]):
                best[rd] = (fd, ad, cik)
            elif r["form"][i] == "13F-HR/A":
                amends.append((rd, fd, ad, cik))
    return best, amends


def parse_table(xml_bytes):
    """{cusip: {"sh", "value", "name"}} — SH만, 풋·콜 제외(같은 CUSIP 여러 줄은 합친다)"""
    root = ET.fromstring(xml_bytes)
    out = {}
    for it in root.iter():
        if not it.tag.endswith("infoTable"):
            continue
        f = {c.tag.split("}")[-1]: c for c in it.iter()}
        txt = lambda k: (f[k].text or "").strip() if f.get(k) is not None and f[k].text else ""
        if txt("putCall") or (txt("sshPrnamtType") or "SH") != "SH":
            continue
        cus = txt("cusip").upper()
        if len(cus) != 9:
            continue
        try:
            sh = float(txt("sshPrnamt").replace(",", "") or 0)
            val = float(txt("value").replace(",", "") or 0)
        except ValueError:
            continue
        cur = out.setdefault(cus, {"sh": 0.0, "value": 0.0, "name": txt("nameOfIssuer")})
        cur["sh"] += sh
        cur["value"] += val
    return out


def _docs(cik, adsh):
    base = f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{adsh.replace('-', '')}"
    idx = json.loads(_get(base + "/index.json"))
    return base, [x["name"] for x in idx["directory"]["item"] if x["name"].lower().endswith(".xml")]


def table(cik, adsh):
    base, xmls = _docs(cik, adsh)
    info = [x for x in xmls if x.lower() != "primary_doc.xml"]
    return parse_table(_get(f"{base}/{info[0]}")) if info else {}


def amendment_type(cik, adsh):
    base, xmls = _docs(cik, adsh)
    if "primary_doc.xml" not in [x.lower() for x in xmls]:
        return ""
    m = re.search(r"<amendmentType>\s*([^<]+?)\s*</amendmentType>", _get(f"{base}/primary_doc.xml").decode("utf-8", "ignore"), re.I)
    return (m.group(1) if m else "").upper()


def cached(cik, rd, adsh, suffix=""):
    p = STATE / f"{cik}_{rd}{suffix}.json"
    if p.exists():
        d = json.loads(p.read_text(encoding="utf-8"))
        if d.get("adsh") == adsh:
            return d["h"]
    h = table(cik, adsh)
    STATE.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({"adsh": adsh, "h": h}, separators=(",", ":")), encoding="utf-8")
    return h


def book_stats(h, exclude=()):
    """(비중 표 {cusip: (w, rank)}, 상위5 비중, 종목 수, 주식 합계 USD 추정) — 가치를 천 달러로 낸 서류는 주당 가격 중앙값으로 알아본다"""
    items = {c: v for c, v in h.items() if v["value"] > 0 and not any(x.upper() in (v["name"] or "").upper() for x in exclude)}
    tot = sum(v["value"] for v in items.values()) or 1.0
    order = sorted(items, key=lambda c: -items[c]["value"])
    w = {c: (items[c]["value"] / tot, i + 1) for i, c in enumerate(order)}
    top5 = sum(w[c][0] for c in order[:5])
    px = sorted(v["value"] / v["sh"] for v in items.values() if v["sh"] > 0)
    unit = 1000.0 if px and px[len(px) // 2] < 1.0 else 1.0
    return w, top5, len(items), tot * unit


def quality(g, top5, n, usd, r, today):
    if g.get("active") is False:
        return 0.0
    q = 1.0
    q *= r["q_conc"] if top5 >= 0.5 else 1.0
    q *= r["q_giant"] if usd >= 10e9 else 1.0
    q *= r["q_diversified"] if n >= 150 else 1.0
    rc = g.get("regime_change")
    if rc:
        try:
            if (today - date.fromisoformat(str(rc))).days <= 730:
                q *= r["q_regime"]
        except ValueError:
            pass
    return round(q, 3)


def rank_w(rank, w, r):
    if w < r["min_w"]:
        return 0.0
    if rank <= 5:
        return r["rank_w"][rank - 1]
    return r["rank_w_6_10"] if rank <= 10 else 0.0


def events(cur, prev, prev2, wtab, r):
    """구루 한 명 — {cusip: [(종류, w_type, w_rank, 비중, 순위, 증가율)]}"""
    out = {}
    for c, (w, rank) in wtab.items():
        p, p2 = (prev or {}).get(c), (prev2 or {}).get(c)
        rw = rank_w(rank, w, r)
        ev = []
        if prev is not None and not p and not p2 and w >= r["new_min_w"]:
            ev.append(("new", r["w_new"], rw if rw else (0.2 if w >= r["new_min_w"] and rank <= 10 else 0.0)))
        elif p and p["sh"] > 0:
            chg = cur[c]["sh"] / p["sh"] - 1
            if chg >= r["add_min"]:
                ev.append(("add", r["w_add"] * min(chg, 1.0), rw))
            elif rank <= 3 and rw:
                ev.append(("best", r["w_best"], rw))
        chg = None if not p or not p["sh"] else round(cur[c]["sh"] / p["sh"] - 1, 3)
        if ev:
            out[c] = [(k, wt, rk, round(w, 4), rank, chg) for k, wt, rk in ev]
    return out


def score_all(per, gurus, r):
    """per = {guru id: {"q","fd","rd","adsh","cik","ev": {cusip: [...]}, "name": {cusip: 이름}}} → {cusip: 집계}"""
    agg = {}
    for gid, d in per.items():
        for c, evs in d["ev"].items():
            a = agg.setdefault(c, {"name": d["name"].get(c, ""), "score": 0.0, "gurus": [], "buyers": 0, "fd": ""})
            s = sum(wt * rk for _, wt, rk, *_ in evs) * d["q"]
            if s <= 0:
                continue
            a["score"] += s
            kinds = [e[0] for e in evs]
            if any(k in ("new", "add", "confidential") for k in kinds):
                a["buyers"] += 1
            a["gurus"].append({"guru": d["guru"], "kinds": kinds, "w": evs[0][3], "rank": evs[0][4], "chg": evs[0][5], "q": d["q"], "s": round(s, 3),
                               "fd": d["fd"], "adsh": d["adsh"], "cik": d["cik"], "rd": d["rd"]})
            a["fd"] = max(a["fd"], d["fd"])
    for c, a in agg.items():
        extra = min(r["consensus_cap"], max(0, a["buyers"] - 1))
        a["score"] = round(a["score"] + r["consensus_step"] * extra, 3)
        kinds = {k for g in a["gurus"] for k in g["kinds"]}
        a["kind"] = "cluster" if a["buyers"] >= 2 else next((k for k in ("confidential", "new", "add", "best") if k in kinds), None)
    return agg


def crowd_map(rd):
    """{cusip: 13F 보유 기관 비율} — 그 분기 시장 전체 13F 캐시(radar/thirteenf_market.py)를 센다(약 8초, 분기마다 radar/state/guru13f/holders_<분기>.json).
    쏠림 대용치(조사 E: 헤지펀드 상위 10 비중 15% 이상 −0.3 — 가치 칸이 캐시에 없어 보유 기관 비율로 근사). 캐시가 없으면 빈 표(감점 없음 = 미확인)"""
    import thirteenf_market as tm
    q = _q(rd)
    p = STATE / f"holders_{q}.json"
    if p.exists():
        return json.loads(p.read_text(encoding="utf-8"))
    ciks = [r[0] for r in (common.load_state("thirteenf_market", {}).get("filings") or {}).get(q, [])]
    if len(ciks) < 3000:   # 시즌 초반 — 표본이 작으면 쓰지 않는다
        return {}
    y, n = int(q[:4]), int(q[-1])
    cnt = {}
    for c in ciks:
        d = tm.load(y, n, c)
        for cus in (d or {}).get("h") or {}:
            cnt[cus] = cnt.get(cus, 0) + 1
    out = {c: round(v / len(ciks), 4) for c, v in cnt.items() if v >= 50}
    STATE.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(out, separators=(",", ":")), encoding="utf-8")
    return out


def apply_crowding(agg, crowd, r):
    for c, a in agg.items():
        share = crowd.get(c)
        a["crowd"] = share
        if share is None:
            continue
        pen = r["crowd_pen_hi"] if share >= r["crowd_hi"] else (r["crowd_pen_lo"] if share >= r["crowd_lo"] else 0.0)
        if pen:
            a["score"] = round(max(0.0, a["score"] - pen), 3)
            a["crowd_pen"] = pen
    return agg


def ticker_by_name(name, tab):
    """CUSIP 매핑이 비면 SEC 티커 표의 회사 이름으로(정규화 후 완전 일치만)"""
    import re as _re
    norm = lambda x: _re.sub(r"\b(INC|CORP|CORPORATION|CO|LTD|PLC|N\.?V|S\.?A|HLDNGS|HOLDINGS|HLDGS|GROUP|SHS|CLASS [A-C]|CL [A-C]|ORD|COM|NEW|DEL)\b|[^A-Z0-9 ]", " ", str(name).upper())
    key = " ".join(norm(name).split())
    if not key:
        return ""
    for tk, (_cik, nm, _ex) in tab.items():
        if " ".join(norm(nm).split()) == key:
            return tk
    return ""


def strength(score, r):
    return round(min(10.0, r["strength_base"] + r["strength_slope"] * score), 1)


def signal_text(a):
    gs = sorted(a["gurus"], key=lambda g: -g["s"])
    parts = [f"{g['guru']} {'·'.join(KIND_KO.get(k, k) for k in g['kinds'])} 비중 {g['w'] * 100:.1f}%" + (f"({g['rank']}위)" if g.get("rank") else "") for g in gs[:3]]
    more = f" 외 {len(gs) - 3}명" if len(gs) > 3 else ""
    head = f"구루 {a['buyers']}명 같은 분기 매수 — " if a["kind"] == "cluster" else ""
    return head + " · ".join(parts) + more + f" · 점수 {a['score']:.2f}"


def to_leads(agg, r, cmap, today):
    import thirteenf_market
    sys.path.insert(0, str(ROOT / "scripts" / "discovery"))
    import tvsym
    tab = tvsym.sec_table()
    rows = []
    for c, a in agg.items():
        if not a.get("kind") or not a["gurus"]:
            continue
        st = strength(a["score"], r)
        if (a.get("crowd") or 0) >= r["crowd_hi"]:   # 13F 보유 기관 40% 이상 = 이미 모두가 아는 종목 — 장부에는 남기되 경보·선별 문턱(6.0) 아래로
            st = min(st, r.get("crowd_cap", 5.9))
        if a["kind"] == "best":   # 신규·증액 없이 상위 보유만 유지 = 사건이 아니다 — 성적표 재료로만(최고 확신 효과는 잰다), 선별·경보 문턱 아래
            st = min(st, r.get("crowd_cap", 5.9))
        if st < r["lead_min"]:
            continue
        m = cmap.get(c) or {}
        if str(m.get("type") or "").startswith(thirteenf_market.EXCLUDE_TYPES):
            continue
        tk = (m.get("ticker") or ticker_by_name(m.get("name") or a["name"], tab) or "").replace("/", ".")
        top = max(a["gurus"], key=lambda g: g["s"])
        rows.append({"channel": "guru", "kind": a["kind"] if a["kind"] != "confidential" else "new", "market": "us", "ticker": tk, "name": m.get("name") or a["name"],
                     "tv": tvsym.us(tk, tab) if tk else "", "date": a["fd"] or today.isoformat(), "strength": st, "signal": signal_text(a),
                     "url": f"https://www.sec.gov/Archives/edgar/data/{int(top['cik'])}/{top['adsh'].replace('-', '')}/",
                     "extra": {"cusip": c, "quarter_end": top["rd"], "score": a["score"], "buyers": a["buyers"], "crowd": a.get("crowd"),
                               "gurus": [{k: g[k] for k in ("guru", "kinds", "w", "rank", "chg", "q", "s")} for g in a["gurus"]][:12]}})
    return rows


# ---------- 공개 포트폴리오 페이지 ----------
def _robots_ok(url):
    import urllib.parse
    u = urllib.parse.urlparse(url)
    rp = urllib.robotparser.RobotFileParser()
    try:
        raw = common.http_get(f"{u.scheme}://{u.netloc}/robots.txt", timeout=15)
        raw = raw.decode("utf-8", "ignore") if isinstance(raw, bytes) else raw
        rp.parse([] if "<html" in raw[:300].lower() else raw.splitlines())
    except Exception:  # noqa: BLE001 — robots.txt가 없으면(404) 제한 없음
        rp.parse([])
    return rp.can_fetch(common.UA, url) and rp.can_fetch("ClaudeBot", url)


def page_lines(html_text):
    t = re.sub(r"(?is)<(script|style|noscript)[^>]*>.*?</\1>", " ", html_text or "")
    t = re.sub(r"(?i)<\s*(br|/p|/div|/li|/h\d|/tr|/td)\s*>", "\n", t)
    lines = [re.sub(r"\s+", " ", common.strip_tags(x)).strip() for x in t.split("\n")]
    return [x for x in lines if 3 <= len(x) <= 120]


def pages(gurus, st, today, every_days=7):
    """주 1회 — 새로 나타난 줄(첫 회차는 기준선만). 이름표(names)에 걸리면 티커를 붙인다. 본문은 저장하지 않는다(줄 해시만)"""
    rows, notes = [], []
    for g in gurus:
        for pg in g.get("pages") or []:
            url = pg["url"]
            k = "page:" + url
            last = st.get(k, {})
            if last.get("date") and (today - date.fromisoformat(last["date"])).days < every_days:
                continue
            if not _robots_ok(url):
                notes.append(f"{g['name']} 페이지 robots 금지 — 건너뜀")
                continue
            try:
                lines = page_lines(common.http_get(url, timeout=30).decode("utf-8", "ignore"))
            except Exception as exc:  # noqa: BLE001
                notes.append(f"{g['name']} 페이지 {type(exc).__name__}")
                continue
            hs = {hashlib.sha1(x.encode()).hexdigest()[:12]: x for x in lines}
            seen = set(last.get("h") or [])
            if seen:
                for h, line in hs.items():
                    if h in seen:
                        continue
                    hit = next(((n, t) for n, t in (pg.get("names") or {}).items() if n.lower() in line.lower()), None)
                    if not hit and not re.search(r"[A-Z][a-z]+ (?:Inc|Corp|Holdings|Group|Ltd|plc|SA|AG|N\.V\.)|\(([A-Z]{1,5})\)", line):
                        continue
                    rows.append({"channel": "guru", "kind": "thesis", "market": "us", "ticker": hit[1] if hit else "", "name": hit[0] if hit else line[:60],
                                 "date": today.isoformat(), "strength": 6.5, "url": url, "signal": f"{g['name']} 공개 포트폴리오 페이지에 새 줄: {line[:90]}",
                                 "extra": {"page": url}})
            st[k] = {"date": today.isoformat(), "h": sorted(hs)[:2000]}
    return rows, notes


def run(force=False, today=None):
    """run_hourly용 — 명단 구루의 새 13F가 있을 때만 정보표를 받고 단서를 낸다. 공개 페이지는 주 1회"""
    import thirteenf_market
    today = today or date.today()
    gurus, r = cfg()
    if not gurus:
        return "명단 없음(config/gurus.yaml)", 0
    if not thirteenf_market.ua():
        return "SEC_USER_AGENT 없음 — 건너뜀", 0
    st = common.load_state("guru13f", {})
    per, errors, changed = {}, [], False
    for g in gurus:
        if g.get("active") is False:
            continue
        try:
            best, amends = filings(g["ciks"])
        except Exception as exc:  # noqa: BLE001 — 한 구루 실패가 전체를 막지 않게
            errors.append(f"{g['name']}: {type(exc).__name__}")
            continue
        rds = sorted(best, reverse=True)[:3]
        if not rds:
            continue
        sig = "|".join(best[d][1] for d in rds) + "|" + "|".join(a[2] for a in amends[-4:])
        if st.get(g["id"]) != sig:
            changed = True
        try:
            hs = [cached(best[d][2], d, best[d][1]) for d in rds]
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{g['name']} 정보표: {type(exc).__name__}")
            continue
        cur, prev, prev2 = hs[0], (hs[1] if len(hs) > 1 else None), (hs[2] if len(hs) > 2 else None)
        wtab, top5, n, usd = book_stats(cur, g.get("exclude_names") or ())
        q = quality(g, top5, n, usd, r, today)
        ev = events(cur, prev, prev2, wtab, r)
        for rd, fd, ad, cik in amends:   # 기밀 보유 공개 — 최근 분기 것만
            if rd != rds[0] or (today - date.fromisoformat(fd)).days > 120:
                continue
            try:
                if amendment_type(cik, ad) != "NEW HOLDINGS":
                    continue
                h = cached(cik, rd, ad, "_a")
            except Exception as exc:  # noqa: BLE001
                errors.append(f"{g['name']} 13F-HR/A: {type(exc).__name__}")
                continue
            tot = sum(v["value"] for v in cur.values()) + sum(v["value"] for v in h.values()) or 1.0
            for c, v in h.items():
                w = v["value"] / tot
                ev[c] = [("confidential", r["w_confidential"], max(rank_w(3, w, r), 0.2), round(w, 4), None, None)]
                cur.setdefault(c, v)
        per[g["id"]] = {"guru": g["name"], "q": q, "fd": best[rds[0]][0], "rd": rds[0], "adsh": best[rds[0]][1], "cik": best[rds[0]][2], "ev": ev,
                        "name": {c: v["name"] for c, v in cur.items()}, "top5": round(top5, 3), "n": n, "usd": usd}
        st[g["id"]] = sig
    page_rows, notes = pages(gurus, st, today)
    sys.path.insert(0, str(ROOT / "scripts" / "discovery"))
    import leads
    new = leads.add(page_rows, today=today) if page_rows else []
    if not changed and not force:
        common.save_state("guru13f", st)
        common.record_health(SOURCE_ID, not errors, "; ".join(errors)[:300] or None)
        return f"새 13F 없음 · 페이지 단서 {len(new)}" + (f" · {'; '.join(notes)}" if notes else ""), len(new)
    agg = score_all(per, gurus, r)
    rd_now = max((d["rd"] for d in per.values()), default="")
    agg = apply_crowding(agg, crowd_map(rd_now) if rd_now else {}, r)
    cmap_p = thirteenf_market.MAP
    cmap = json.loads(cmap_p.read_text(encoding="utf-8")) if cmap_p.exists() else {}
    need = [c for c, a in agg.items() if a.get("kind") and strength(a["score"], r) >= r["lead_min"]]
    cmap = thirteenf_market.figi(sorted(need), cmap)
    cmap_p.parent.mkdir(parents=True, exist_ok=True)
    cmap_p.write_text(json.dumps(cmap, ensure_ascii=False, indent=0, sort_keys=True), encoding="utf-8")
    new += leads.add(to_leads(agg, r, cmap, today), today=today)
    OUT.mkdir(parents=True, exist_ok=True)
    summary = {"as_of": common.iso(common.now_kst()),
               "gurus": {d["guru"]: {"report": d["rd"], "filed": d["fd"], "positions": d["n"], "top5": d["top5"], "q": d["q"],
                                     "events": sum(1 for v in d["ev"].values() if v)} for d in per.values()},
               "stocks": {c: {**a, "ticker": (cmap.get(c) or {}).get("ticker"), "strength": strength(a["score"], r)}
                          for c, a in sorted(agg.items(), key=lambda x: -x[1]["score"]) if a.get("kind")},
               "errors": errors, "notes": notes, "new_leads": len(new)}
    LATEST.write_text(json.dumps(summary, ensure_ascii=False, indent=1), encoding="utf-8")
    common.save_state("guru13f", st)
    common.record_health(SOURCE_ID, not errors, "; ".join(errors)[:300] or None)
    if new:
        import channels
        channels.run()
    return f"구루 {len(per)}명 · 신호 종목 {len(need)} · 새 단서 {len(new)}" + (f" · 오류 {len(errors)}" if errors else ""), len(new)


def main(argv):
    sys.stdout.reconfigure(encoding="utf-8")
    if "--show" in argv:
        d = json.loads(LATEST.read_text(encoding="utf-8")) if LATEST.exists() else {}
        for c, a in list((d.get("stocks") or {}).items())[:40]:
            print(f"{a.get('ticker') or c} {a['name']} · {a['kind']} · 점수 {a['score']} · 강도 {a.get('strength')} · 매수 구루 {a['buyers']}")
        return 0
    print(run(force="--force" in argv)[0])
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
