"""한국 외 소비 트렌드 — 상향식 발굴(무엇이 막 뜨나) (마스터 지시 2026-11-14 "메인은 미국, 일본, 유럽이다. 한국 외 소비재 시장 트렌드를 파악하는 파이프라인")

결정론(모델 없음). run_hourly 하루 1회. 원천(2026-11-14 확인 — robots·약관 허용, 공식·공개 경로만):
  apple   애플 앱 순위 RSS(미·일·영·독·프 무료·유료 상위 100) — 7일 전 대비 상위 25 신규 진입·50계단 이상 급상승. 개발사 → 상장사(config issuers)
  steam   스팀 상점 featuredcategories 판매 상위(미·일·독) — 7일 전 대비 신규 진입. 퍼블리셔(appdetails, 캐시) → 상장사
  wiki    Wikimedia 일별 상위 1,000 문서(영·일·독·프) — 최근 7일 조회 ÷ 직전 28일 주평균. 브랜드 사전·소비재형 괄호 표기(예: '(video game)')만 남긴다
          (위키백과 자체 API는 robots 금지라 문서 분류를 묻지 않는다 — 사전·표기로만 거른다)
  trends  Google Trends 급상승 RSS(미·일·영·독·프) — 브랜드 사전에 걸린 검색어만(대부분 뉴스·스포츠라 나머지는 버린다)
이력이 없는 원천(애플·스팀·급상승)은 기록을 쌓은 지 7일이 지나야 '신규 진입'을 판정한다. 위키는 지난 35일을 처음에 받아 바로 판정한다.
단서이지 사실이 아니다(금지표: 관심 증가 → 매출). 2026-11-14 C단계 검정에서 관심 신호는 회사 매출 예측을 개선하지 못했다 — '무엇이 뜨나'를 먼저 아는 용도.
저장: radar/state/consumer_discovery.sqlite(git 제외) · knowledge/models/consumer_trends/discovery_latest.json(rising·alerts — Pulse '소비재'가 alerts를 읽는다)
사용: py radar/consumer_discovery.py [--status]
"""
import json
import re
import sqlite3
import sys
import time
import xml.etree.ElementTree as ET
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from pollers import common  # noqa: E402

CFG = "config/consumer_trends.yaml"
OUT = common.ROOT / "knowledge" / "models" / "consumer_trends"
LATEST = OUT / "discovery_latest.json"
DB = common.ROOT / "radar" / "state" / "consumer_discovery.sqlite"
WIKI_TOP = "https://wikimedia.org/api/rest_v1/metrics/pageviews/top/{project}/all-access/{y}/{m:02d}/{d:02d}"
STEAM_TOP = "https://store.steampowered.com/api/featuredcategories?cc={cc}&l=english"
STEAM_APP = "https://store.steampowered.com/api/appdetails?appids={appid}&filters=basic,publishers,developers"
TRENDS = "https://trends.google.com/trending/rss?geo={geo}"
HT = "{https://trends.google.com/trending/rss}"
SKIP_PREFIX = re.compile(r"^(Special|Spezial|Spécial|Wikipedia|Wikipédia|File|Datei|Fichier|Portal|Help|Hilfe|Aide|Category|Kategorie|Catégorie|Template|Vorlage|Modèle|"
                         r"特別|ファイル|ポータル|ヘルプ|Category|カテゴリ|Main_Page|メインページ|Wikipedia:Hauptseite|Hauptseite|Wikipédia:Accueil_principal)", re.I)
CONSUMER_TAG = {   # 괄호 표기로 본 소비재형 문서(언어별) — 영화·드라마·인물은 넣지 않는다(제작사 매핑 근거가 없다)
    "en": r"\((?:\d{4} )?(?:video game|toy|toy line|brand|company|restaurant|restaurant chain|beverage|drink|snack|food|confectionery|app|mobile app|mobile game|footwear|shoe|sneaker|fashion brand|clothing|cosmetics|cosmetic brand|retailer|card game|board game|game console|console|smartphone)\)",
    "ja": r"[（(](?:ゲーム|コンピュータゲーム|ゲームソフト|玩具|ブランド|企業|飲料|菓子|食品|アプリ|カードゲーム|ゲーム機)[)）]",
    "de": r"\((?:Computerspiel|Videospiel|Spiel|Spielzeug|Marke|Unternehmen|Getränk|App|Spielkonsole|Kartenspiel)\)",
    "fr": r"\((?:jeu vidéo|jeu|jouet|marque|entreprise|boisson|application|console|jeu de cartes)\)",
}


def cfg():
    return common.load_yaml(CFG) or {}


def ua():
    a = (common.load_yaml("config/consumer.yaml") or {}).get("attention") or {}
    return a.get("user_agent") or common.contact_ua()


def _json(url, timeout=60):
    return json.loads(common.http_get(url, headers={"User-Agent": ua()}, timeout=timeout))


def connect(path=DB):
    path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(path)
    con.executescript("""
    create table if not exists apple(day text, cc text, feed text, rank int, app text, name text, artist text, primary key(day, cc, feed, rank));
    create table if not exists steam(day text, cc text, rank int, appid text, name text, primary key(day, cc, rank));
    create table if not exists steam_pub(appid text primary key, publishers text, developers text);
    create table if not exists wiki(day text, project text, title text, rank int, views int, primary key(day, project, title));
    create table if not exists trends(day text, geo text, title text, traffic int, primary key(day, geo, title));
    """)
    return con


# ── 매핑 ─────────────────────────────────────────────────

def issuer_of(name, issuers):
    for it in issuers:
        if re.search(it["rx"], name or "", re.I):
            return {"ticker": it["ticker"], "company": it["name"]}
    return None


def norm(t):
    """소문자·공백 정리·라틴 악센트 접기(Pokémon → pokemon). 가나·한자의 탁점은 건드리지 않는다"""
    import unicodedata
    s = unicodedata.normalize("NFKD", (t or "").replace("_", " "))
    s = "".join(ch for i, ch in enumerate(s) if not (unicodedata.category(ch) == "Mn" and i > 0 and s[i - 1].isascii()))
    return re.sub(r"\s+", " ", unicodedata.normalize("NFC", s)).strip().lower()


def lexicon(c=None):
    """[(정규화 용어, 티커, 회사, 시리즈 여부)] — brands(정확히) + consumer.yaml(한국 제외) 위키 문서 제목 + franchises(앞부분 일치).
    시리즈는 긴 이름부터(예: 'Elden Ring Nightreign' → 반다이남코가 'Elden Ring' → 가도카와보다 먼저)"""
    c = c or cfg()
    d = c.get("discovery") or {}
    out = [(norm(t), b["ticker"], b["name"], False, f"b{i}") for i, b in enumerate(d.get("brands") or []) for t in b.get("terms") or [] if isinstance(t, str)]
    suffix = {"jp": ".T", "hk": ".HK", "eu": ".L", "us": ""}
    for co in (common.load_yaml("config/consumer.yaml") or {}).get("companies") or []:
        if co.get("market") == "kr":
            continue
        tk = f"{co.get('code')}{suffix.get(co.get('market'), '')}"
        out += [(norm(t), tk, co.get("name"), False, f"c{co['id']}") for t in (co.get("wiki") or {}).values()]
    fr = [(norm(t), f["ticker"], f["name"], True, f"f{i}") for i, f in enumerate(d.get("franchises") or []) for t in f.get("terms") or [] if isinstance(t, str)]
    pre = {x[0] for x in fr}   # 브랜드이면서 시리즈인 이름(예: Pokémon)은 시리즈 규칙(앞부분 일치)을 쓴다
    out = [(t, tk, nm, p or t in pre, g) for t, tk, nm, p, g in out] + sorted(fr, key=lambda x: -len(x[0]))
    seen, uniq = set(), []
    for x in out:
        if x[0] and x[0] not in seen:
            seen.add(x[0])
            uniq.append(x)
    return uniq


def title_brand(title, lex):
    """위키 문서 제목 → 브랜드. 사전 용어와 같거나 '용어 (괄호)'(브랜드), 시리즈는 '이름:'·'이름 …'으로 시작하면.
    시리즈 이름 뒤 괄호는 게임·시리즈·작품 표기일 때만(예: 'Cyberpunk (genre)'는 아니다)"""
    t = norm(title)
    hit = lambda x: {"ticker": x[1], "company": x[2], "term": x[0], "group": x[4] if len(x) > 4 else x[1] + ":" + x[0]}
    for x in lex:   # 정확히 같은 것 먼저
        if t == x[0]:
            return hit(x)
    for x in lex:
        term, pre = x[0], x[3]
        rest = t[len(term):] if t.startswith(term) else None
        if rest is None or not rest:
            continue
        if not pre and rest.startswith(" ("):
            return hit(x)
        if pre and (rest.startswith(":") or (rest.startswith(" ") and not rest.startswith(" (")) or
                    (rest.startswith(" (") and re.search(r"game|series|franchise|toy|film|ゲーム|シリーズ|jeu|spiel|serie", rest))):
            return hit(x)
        if pre and re.search(r"[^\x00-\x7f]", term) and rest:   # 일본어 시리즈명 뒤는 띄어쓰기 없이 이어진다(예: 'ゼルダの伝説 時のオカリナ'·'マリオカートワールド')
            return hit(x)
    return None


def query_brand(q, lex):
    """급상승 검색어 안에 사전 용어가 단어로 들어 있으면 그 브랜드(한자·가나는 부분 일치)"""
    s = norm(q)
    for x in lex:
        term, tk, nm = x[0], x[1], x[2]
        if len(term) < 3:
            continue
        if re.search(r"[^\x00-\x7f]", term):
            hit = term in s
        else:
            hit = re.search(rf"(?<![a-z0-9]){re.escape(term)}(?![a-z0-9])", s) is not None
        if hit:
            return {"ticker": tk, "company": nm, "term": term, "group": x[4] if len(x) > 4 else tk + ":" + term}
    return None


# ── 수집 ─────────────────────────────────────────────────

def collect_apple(con, day, a):
    import consumer_attention as ca   # 순위 RSS(504 재시도 포함)·앱 id 추출을 같이 쓴다
    charts = ca.apple_ranks(a["countries"], a["feeds"], ua())
    rows = [(day, cc, feed, rank, (aid or "")[4:] if (aid or "").startswith("app:") else (aid or ""), name, artist)
            for (cc, feed), lst in charts.items() for rank, name, artist, aid in lst]
    con.executemany("insert or replace into apple values(?,?,?,?,?,?,?)", rows)
    return len(charts)


def collect_steam(con, day, s):
    n = 0
    for cc in s["countries"]:
        items = (_json(STEAM_TOP.format(cc=cc)).get("top_sellers") or {}).get("items") or []
        con.executemany("insert or replace into steam values(?,?,?,?,?)", [(day, cc, i + 1, str(x["id"]), x.get("name", "")) for i, x in enumerate(items[:s["top"]])])
        n += len(items[:s["top"]])
        time.sleep(1.0)
    have = {r[0] for r in con.execute("select appid from steam_pub")}
    for (appid,) in con.execute("select distinct appid from steam where day=?", (day,)).fetchall():
        if appid in have:
            continue
        try:
            d = (_json(STEAM_APP.format(appid=appid)).get(appid) or {}).get("data") or {}
            con.execute("insert or replace into steam_pub values(?,?,?)", (appid, "|".join(d.get("publishers") or []), "|".join(d.get("developers") or [])))
        except Exception:
            pass
        time.sleep(1.5)
    return n


def collect_wiki(con, today, w, days=36):
    """빠진 날만 받는다(Wikimedia 상위 문서는 2~3일 늦게 나온다 — 없으면 다음 회차에)"""
    got = 0
    for project in w["projects"]:
        have = {r[0] for r in con.execute("select distinct day from wiki where project=?", (project,))}
        for k in range(1, days + 1):
            d = today - timedelta(days=k)
            if d.isoformat() in have:
                continue
            try:
                arts = _json(WIKI_TOP.format(project=project, y=d.year, m=d.month, d=d.day))["items"][0]["articles"]
            except Exception:
                continue
            rows = [(d.isoformat(), project, a["article"], a["rank"], a["views"]) for a in arts if not SKIP_PREFIX.match(a["article"]) and a["article"] != "-"]
            con.executemany("insert or replace into wiki values(?,?,?,?,?)", rows)
            got += 1
            time.sleep(0.3)
    return got


def traffic(s):
    """'200K+' → 200000"""
    m = re.match(r"^\s*([\d.,]+)\s*([KMB]?)\+?", s or "")
    if not m:
        return 0
    return int(float(m.group(1).replace(",", "")) * {"": 1, "K": 1e3, "M": 1e6, "B": 1e9}[m.group(2)])


def collect_trends(con, day, t):
    n = 0
    for geo in t["geos"]:
        root = ET.fromstring(common.http_get(TRENDS.format(geo=geo), headers={"User-Agent": ua()}, timeout=30))
        rows = [(day, geo, (it.findtext("title") or "").strip(), traffic(it.findtext(f"{HT}approx_traffic"))) for it in root.iter("item")]
        con.executemany("insert or replace into trends values(?,?,?,?)", [r for r in rows if r[2]])
        n += len(rows)
        time.sleep(0.5)
    return n


# ── 판정 ─────────────────────────────────────────────────

def _base_day(con, table, day, k=7):
    """day보다 k일 이상 앞선 가장 최근 기록일 — 없으면 None(아직 기준선이 없다)"""
    r = con.execute(f"select max(day) from {table} where day<=?", ((date.fromisoformat(day) - timedelta(days=k)).isoformat(),)).fetchone()
    return r[0] if r and r[0] else None


def apple_rising(con, day, a, issuers):
    base = _base_day(con, "apple", day)
    if not base:
        return [], None
    out = []
    for cc in a["countries"]:
        for feed in a["feeds"]:
            prev = {app: rank for rank, app in con.execute("select rank, app from apple where day=? and cc=? and feed=?", (base, cc, feed))}
            if not prev:
                continue
            for rank, app, name, artist in con.execute("select rank, app, name, artist from apple where day=? and cc=? and feed=? and rank<=? order by rank", (day, cc, feed, a["top"])):
                p = prev.get(app)
                kind = "신규 진입" if p is None else "급상승" if p - rank >= a["jump"] else None
                if kind:
                    out.append({"source": "apple", "country": cc, "feed": feed, "rank": rank, "prev_rank": p, "kind": kind, "name": name, "artist": artist,
                                "issuer": issuer_of(artist, issuers)})
    return out, base


def steam_rising(con, day, s, issuers):
    base = _base_day(con, "steam", day)
    if not base:
        return [], None
    pubs = {a: (p, dv) for a, p, dv in con.execute("select appid, publishers, developers from steam_pub")}
    out = []
    for cc in s["countries"]:
        prev = {a for (a,) in con.execute("select appid from steam where day=? and cc=?", (base, cc))}
        if not prev:
            continue
        for rank, appid, name in con.execute("select rank, appid, name from steam where day=? and cc=? order by rank", (day, cc)):
            if appid not in prev:
                p, dv = pubs.get(appid, ("", ""))
                out.append({"source": "steam", "country": cc, "rank": rank, "kind": "신규 진입", "name": name, "publisher": p,
                            "issuer": issuer_of(p, issuers) or issuer_of(dv, issuers)})
    return out, base


def wiki_rising(con, w, lex, end=None):
    """최근 7일(자료가 있는 마지막 날까지) 조회 ÷ 직전 28일 주평균 — 상위 1,000에 없던 날은 0으로 본다(새로 뜬 문서일수록 가속이 커진다)"""
    out = []
    for project in w["projects"]:
        lang = project.split(".")[0]
        last = end or (con.execute("select max(day) from wiki where project=?", (project,)).fetchone() or [None])[0]
        if not last:
            continue
        L = date.fromisoformat(last)
        r7 = ((L - timedelta(days=6)).isoformat(), last)
        r28 = ((L - timedelta(days=34)).isoformat(), (L - timedelta(days=7)).isoformat())
        n28 = con.execute("select count(distinct day) from wiki where project=? and day between ? and ?", (project, *r28)).fetchone()[0]
        if n28 < 14:   # 기준선이 부족하면 판정하지 않는다
            continue
        cur = dict(con.execute("select title, sum(views) from wiki where project=? and day between ? and ? group by title", (project, *r7)))
        old = dict(con.execute("select title, sum(views) from wiki where project=? and day between ? and ? group by title", (project, *r28)))
        rx = re.compile(CONSUMER_TAG.get(lang, r"$^"))
        rows = []
        for title, v7 in cur.items():
            if v7 < (w["min_views7"].get(lang, 30000)):
                continue
            base = (old.get(title, 0) or 0) / max(n28, 1) * 7
            accel = (v7 + 1) / (base + 1)
            if accel < w["accel"]:
                continue
            brand = title_brand(title, lex)
            tag = None if brand else (rx.search(title.replace("_", " ")) and "소비재형 미매핑")
            if brand or tag:
                rows.append({"source": "wiki", "project": project, "title": title.replace("_", " "), "views7": v7, "base7": round(base), "accel": round(accel, 1),
                             "brand": brand, "kind": "브랜드" if brand else tag, "through": last})
        out += sorted(rows, key=lambda x: -(x["accel"] * x["views7"]))[:w["top"]]
    return out


def trends_hits(con, day, lex):
    out = []
    for geo, title, tr in con.execute("select geo, title, traffic from trends where day=? order by traffic desc", (day,)):
        b = query_brand(title, lex)
        if b:
            out.append({"source": "trends", "geo": geo, "query": title, "traffic": tr, "brand": b})
    return out


def alerts(rising):
    """Pulse로 보낼 것 — 상장사에 매핑되고 순위·조회가 큰 것만, 하루 6건까지(나머지는 보드에만)"""
    out = []
    for r in rising.get("apple") or []:
        if r.get("issuer") and r["rank"] <= (10 if r["country"] in ("us", "jp") else 5):
            out.append({**r, "headline": f"{r['issuer']['company']} 앱 '{r['name'][:30]}' {r['country'].upper()} {('무료' if r['feed'] == 'top-free' else '유료')} {r['rank']}위 {r['kind']}"})
    for r in rising.get("steam") or []:
        if r.get("issuer") and r["rank"] <= 10:
            out.append({**r, "headline": f"{r['issuer']['company']} 게임 '{r['name'][:30]}' 스팀 {r['country'].upper()} 판매 {r['rank']}위 신규 진입"})
    # 같은 회사·같은 시리즈(용어가 서로의 앞부분 — 'grand theft auto' ↔ 'grand theft auto vi')는 가장 센 한 건만, 다른 언어 위키에서도 뜨면 함께 적는다
    groups = []
    for r in sorted([x for x in rising.get("wiki") or [] if x.get("brand")], key=lambda x: -(x["accel"] * x["views7"])):
        tk, term, grp = r["brand"]["ticker"], r["brand"]["term"], r["brand"].get("group")
        g = next((g for g in groups if g["tk"] == tk and (g["grp"] == grp or term.startswith(g["term"]) or g["term"].startswith(term))), None)
        if g:
            g["also"].add(r["project"].split(".")[0])
        else:
            groups.append({"tk": tk, "term": term, "grp": grp, "row": r, "also": set()})
    seen = set()
    for g in groups:
        r, lang = g["row"], g["row"]["project"].split(".")[0]
        also = sorted(g["also"] - {lang})
        seen.add((g["tk"], g["term"], g["grp"]))
        out.append({**r, "also_wikis": also, "headline": f"{r['brand']['company']} '{r['title'][:30]}' 위키({lang}) 7일 조회 {r['views7']:,} ×{r['accel']}"
                    + (f" · {'·'.join(also)} 위키도 급증" if also else "")})
    for r in rising.get("trends") or []:
        k = (r["brand"]["ticker"], r["brand"]["term"], r["brand"].get("group"))
        if r["traffic"] >= 20000 and not any(k[0] == s[0] and (k[2] == s[2] or k[1].startswith(s[1]) or s[1].startswith(k[1])) for s in seen):
            seen.add(k)
            out.append({**r, "headline": f"{r['brand']['company']} — {r['geo']} 급상승 검색 '{r['query'][:30]}' {r['traffic']:,}+"})
    return out[:6]


def run(today=None):
    c = cfg()
    dcfg = c["discovery"]
    today = today or common.now_kst().date()
    day = today.isoformat()
    con = connect()
    errors, got = [], {}
    for key, fn in (("apple", lambda: collect_apple(con, day, dcfg["apple"])), ("steam", lambda: collect_steam(con, day, dcfg["steam"])),
                    ("wiki", lambda: collect_wiki(con, today, dcfg["wiki"])), ("trends", lambda: collect_trends(con, day, dcfg["trends"]))):
        try:
            got[key] = fn()
            con.commit()
        except Exception as exc:
            errors.append(f"{key}: {type(exc).__name__}: {str(exc)[:100]}")
    lex = lexicon(c)
    apple, abase = apple_rising(con, day, dcfg["apple"], dcfg["issuers"])
    steam, sbase = steam_rising(con, day, dcfg["steam"], dcfg["issuers"])
    rising = {"apple": apple, "steam": steam, "wiki": wiki_rising(con, dcfg["wiki"], lex), "trends": trends_hits(con, day, lex)}
    days = {t: con.execute(f"select count(distinct day) from {t}").fetchone()[0] for t in ("apple", "steam", "wiki", "trends")}
    con.close()
    al = alerts(rising)
    OUT.mkdir(parents=True, exist_ok=True)
    LATEST.write_text(json.dumps({"as_of": common.iso(common.now_kst()), "day": day, "rising": rising, "alerts": al, "baseline_days": days,
                                  "baseline_from": {"apple": abase, "steam": sbase}, "collected": got, "errors": errors,
                                  "note": "단서이지 사실이 아니다(금지표: 관심 증가 → 매출). 상장사 매핑은 개발사·퍼블리셔·브랜드 사전 기준."},
                                 ensure_ascii=False, indent=1), encoding="utf-8")
    common.record_health("consumer-discovery", len(errors) < 4, "; ".join(errors[:3]) or None)
    if len(errors) == 4:
        raise RuntimeError("소비 트렌드 원천을 하나도 받지 못했다: " + "; ".join(errors[:3]))
    return (f"소비 트렌드 발굴 — 애플 {len(apple)}·스팀 {len(steam)}·위키 {len(rising['wiki'])}·급상승 {len(rising['trends'])} · 경보 {len(al)}건 · "
            f"기준선 일수 {days} · 오류 {len(errors)}")


def status():
    d = json.loads(LATEST.read_text(encoding="utf-8"))
    print(d["day"], "기준선", d["baseline_days"], "오류", d["errors"])
    for k, rows in d["rising"].items():
        print(f"== {k} {len(rows)}")
        for r in rows[:15]:
            print("  ", {x: r.get(x) for x in ("country", "project", "geo", "rank", "kind", "name", "title", "query", "views7", "accel", "traffic") if r.get(x) is not None},
                  (r.get("issuer") or r.get("brand") or {}).get("company"))
    print("== alerts", [a["headline"] for a in d["alerts"]])


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    if "--status" in sys.argv:
        status()
    else:
        print(run())
