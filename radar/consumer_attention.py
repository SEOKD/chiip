"""소비재·게임·콘텐츠IP 수요 관심도 — Chiip Consumer (마스터 지시 2026-10-30 "소비재는 트렌드에 민감한 만큼 아마존 같은 글로벌 이커머스
플랫폼의 관심도를 취합하며 온라인 커뮤니티 등 리테일 채널의 반응을 잘 살펴 어떤 내러티브가 있는지 엣지 있게 캐치").

결정론 수집(하루 1회, run_hourly). 대상은 config/consumer.yaml companies. 회사 이름이 아니라 IP·브랜드 이름을 본다 — 수요는 IP에서 먼저 보인다.
  wiki   Wikimedia 조회수 공식 API — 문서별 최근 7일 ÷ 직전 28일 주평균(일별 자료라 기준선을 쌓을 필요가 없다). 사람 조회(user)만.
  steam  상점 앱 정보(store.steampowered.com/api/appdetails, robots 허용)의 누적 추천 수 — 하루 1회 기록, 7일 증가 ÷ 직전 7일 증가
  apple  애플 앱 순위 RSS(rss.applemarketingtools.com, 공식) 무료·유료 — 회사 앱 개수와 최고 순위
  ratings 애플 iTunes 조회 API(itunes.apple.com/lookup, 공식·무료·키 없음) — 개발사 전체 앱의 누적 평점 수, 7일 증가 ÷ 직전 7일 증가
         (다운로드 증가의 대용, 2026-11-12 마스터 지시 'B2C 종목 분석 파이프라인'). 개발사 id는 config apple_artist 또는 순위 RSS에서 자동으로 배운다(apple_artists.json)
  news   브랜드 검색어 Google News 색인 7일 건수(현지어 포함) — 7·14·21·28일 전 기록 평균과 비교(4주 기준선이 쌓인 뒤부터)
아마존·레딧 직접·틱톡은 robots 차단이라 쓰지 않는다(knowledge/methods/consumer_lens.md 3). 리테일·투자자 언급 수는 radar/attention.py가 같은 종목을 함께 센다.
쓰는 것: knowledge/models/consumer/attention.csv(날짜·종목·원천·키·값 누적), attention_latest.json(종목별 수요 가속·원천별 값·급가속 spikes).
  위키 일별 누적 radar/state/wiki_views.sqlite(git 제외, 2015-07~ 백필 + 매일 35일 창) → 월별 요약 wiki_monthly.csv(2026-11-14 설계안 A-2).
  주의: Wikimedia는 2020-05부터 자동화 트래픽을 'automated'로 따로 분류한다 — 그 전 'user'에는 일부 봇이 섞여 있어 2020-05 전후는 수준 단절이 있을 수 있다.
사용: py radar/consumer_attention.py [종목 id…] · --wiki-backfill [종목 id…] · --wiki-monthly
"""
import csv
import json
import re
import sys
import time
import urllib.parse
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from pollers import common  # noqa: E402
from pollers import rss  # noqa: E402

OUT = common.ROOT / "knowledge" / "models" / "consumer"
CSV = OUT / "attention.csv"
LATEST = OUT / "attention_latest.json"
WIKI = "https://wikimedia.org/api/rest_v1/metrics/pageviews/per-article/{lang}.wikipedia/all-access/user/{title}/daily/{start}/{end}"
STEAM = "https://store.steampowered.com/api/appdetails?appids={appid}&filters=recommendations,basic"
APPLE = "https://rss.applemarketingtools.com/api/v2/{cc}/apps/{feed}/100/apps.json"
LOOKUP = "https://itunes.apple.com/lookup"   # robots는 /search만 막는다 — 검색 API는 쓰지 않고 id 조회만
ARTISTS = OUT / "apple_artists.json"
WIKI_DB = common.ROOT / "radar" / "state" / "wiki_views.sqlite"   # 일별 누적(git 제외) — 2015-07~ 백필 + 매일 35일 창
WIKI_MONTHLY = OUT / "wiki_monthly.csv"   # 월별 요약(git) — 나우캐스트 백테스트 입력
LOCALE = {"jp": ("ja", "JP"), "kr": ("ko", "KR"), "hk": ("zh-HK", "HK"), "us": ("en-US", "US"), "eu": ("en-GB", "GB")}


def cfg():
    return common.load_yaml("config/consumer.yaml") or {}


def _get_json(url, ua, timeout=30):
    return json.loads(common.http_get(url, headers={"User-Agent": ua}, timeout=timeout))


def wiki_series(lang, title, ua, start, end):
    """{YYYYMMDD: 사람 조회수} — 기간 전체를 한 번에(응답에 쪽 나눔이 없다). 문서가 없으면 None"""
    lang = re.sub(r"\d+$", "", lang)   # en2·en3 = 같은 언어의 두 번째·세 번째 문서
    url = WIKI.format(lang=lang, title=urllib.parse.quote(title.replace(" ", "_"), safe=""), start=start.strftime("%Y%m%d"), end=end.strftime("%Y%m%d"))
    try:
        items = _get_json(url, ua, 60).get("items") or []
    except Exception:
        return None
    return {i["timestamp"][:8]: i["views"] for i in items}


def _wiki_db():
    import sqlite3
    WIKI_DB.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(WIKI_DB)
    con.execute("create table if not exists views(lang text, title text, day text, views integer, primary key(lang, title, day))")
    return con


def wiki_store(lang, title, by):
    """일별 조회를 누적 저장소에 넣는다(같은 날은 덮어씀) — 매일 회차의 35일 창이 백필 뒤 시계열을 이어 붙인다"""
    if not by:
        return 0
    lang = re.sub(r"\d+$", "", lang)
    with _wiki_db() as con:
        con.executemany("insert or replace into views values(?,?,?,?)", [(lang, title, d, int(v)) for d, v in by.items()])
    return len(by)


def wiki_backfill(only=None, start=date(2015, 7, 1)):
    """지도 위키 문서 전체를 2015-07-01(Wikimedia 일별 자료 시작)부터 받는다 — 백테스트·KPI 나우캐스트용(설계안 A-2, 2026-11-14)"""
    ua = (cfg().get("attention") or {}).get("user_agent") or common.contact_ua()
    end = common.now_kst().date() - timedelta(days=1)
    done, miss = 0, []
    for co in cfg().get("companies") or []:
        if only and co["id"] not in only:
            continue
        for lang, title in _wiki_titles(co):
            by = wiki_series(lang, title, ua, start, end)
            if by is None:
                miss.append(f"{co['id']}:{lang}:{title}")
                continue
            done += wiki_store(lang, title, by)
            time.sleep(0.5)
    wiki_monthly()
    return done, miss


def _wiki_titles(co):
    """[(언어 키, 제목)] — 지금 제목 + 옛 제목(wiki_old)"""
    out = list((co.get("wiki") or {}).items())
    for lang, olds in (co.get("wiki_old") or {}).items():
        out += [(lang, t) for t in olds]
    return out


def wiki_monthly():
    """월별 합계 CSV(git에 남는 요약) — 옛 제목(wiki_old) 조회는 지금 제목 행에 더한다(old_views에 따로 표시).
    days = 그 달 자료가 있는 날 수(지금·옛 제목 중 많은 쪽 — 진행 중인 달·문서 생성 전은 적다)"""
    with _wiki_db() as con:
        agg = {(l, t, ym): (v, n) for l, t, ym, v, n in
               con.execute("select lang, title, substr(day,1,6), sum(views), count(*) from views group by 1,2,3").fetchall()}
    out = []
    for co in cfg().get("companies") or []:
        olds = co.get("wiki_old") or {}
        for key, title in (co.get("wiki") or {}).items():
            lang = re.sub(r"\d+$", "", key)
            months = {ym for (l, t, ym) in agg if l == lang and (t == title or t in olds.get(key, []))}
            for ym in sorted(months):
                v, n = agg.get((lang, title, ym), (0, 0))
                prev = [agg.get((lang, t, ym), (0, 0)) for t in olds.get(key, [])]
                old = sum(x[0] for x in prev)
                n = max([n] + [x[1] for x in prev])
                out.append([f"{ym[:4]}-{ym[4:]}", co["id"], lang, title, v + old, n, old])
    with WIKI_MONTHLY.open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["month", "id", "lang", "title", "views", "days", "old_views"])
        w.writerows(out)
    return len(out)


def wiki_accel(lang, title, ua, today, days=7):
    """(최근 7일 조회, 직전 28일 주평균, 가속) — 문서가 없으면 None"""
    end, start = today - timedelta(days=1), today - timedelta(days=days + 28)
    by = wiki_series(lang, title, ua, start, end)
    if by is None:
        return None
    try:
        wiki_store(lang, title, by)
    except Exception:
        pass   # 누적 저장 실패가 오늘 가속 계산을 막지 않는다
    recent = sum(by.get((end - timedelta(days=k)).strftime("%Y%m%d"), 0) for k in range(days))
    prior = sum(by.get((end - timedelta(days=days + k)).strftime("%Y%m%d"), 0) for k in range(28)) / 4
    return recent, prior, (recent + 1) / (prior + 1)


def steam_total(appid, ua):
    try:
        d = _get_json(STEAM.format(appid=appid), ua).get(str(appid)) or {}
    except Exception:
        return None
    rec = ((d.get("data") or {}).get("recommendations") or {}).get("total")
    return int(rec) if d.get("success") and rec is not None else None


def apple_ranks(countries, feeds, ua):
    """{(국가, 피드): [(순위, 앱 이름, 개발사)]}"""
    out = {}
    for cc in countries:
        for feed in feeds:
            rs = None
            for wait in (0, 5, 20):   # 순위 RSS는 504를 자주 낸다(2026-11-14 시험) — 두 번 더 묻는다
                time.sleep(wait)
                try:
                    rs = _get_json(APPLE.format(cc=cc, feed=feed), ua, 40)["feed"]["results"]
                    break
                except Exception:
                    continue
            if rs is None:
                continue
            out[(cc, feed)] = [(i + 1, r.get("name", ""), r.get("artistName", ""), _artist_id(r) or ("app:" + str(r["id"]) if r.get("id") else None))
                               for i, r in enumerate(rs)]
            time.sleep(0.5)
    return out


def resolve_artists(app_ids, ua, cache):
    """순위 RSS 앱 id → 개발사 id(iTunes 조회 API). RSS v2 결과에는 개발사 id가 없다(2026-11-14 확인, 앱 id만).
    cache = {앱 id: 개발사 id} — 한 번 푼 앱은 다시 묻지 않는다"""
    todo = [a for a in dict.fromkeys(app_ids) if a not in cache]
    for i in range(0, len(todo), 50):
        try:
            d = _get_json(f"{LOOKUP}?id={','.join(todo[i:i + 50])}", ua, 40)
            time.sleep(3.5)
        except Exception:
            continue
        for x in d.get("results") or []:
            if x.get("trackId") and x.get("artistId"):
                cache[str(x["trackId"])] = str(x["artistId"])
    return [cache[a] for a in app_ids if a in cache]


def news_count(term, market, days):
    hl, gl = LOCALE.get(market, ("en-US", "US"))
    url = rss.GNEWS.format(q=urllib.parse.quote(f'"{term}" when:{days}d'), hl=hl, gl=gl)
    try:
        return len(rss.parse_feed(common.http_get(url, timeout=25)))
    except Exception:
        return None


def _artist_id(r):
    a = r.get("artistId") or re.search(r"/id(\d+)", r.get("artistUrl") or "")
    return str(a.group(1) if hasattr(a, "group") else a) if a else None


def apple_ratings(artists, cc, ua):
    """개발사 id들의 전체 앱 누적 평점 수 합계(국가별 상점) — 실패하면 None"""
    try:
        d = _get_json(f"{LOOKUP}?id={','.join(artists)}&entity=software&country={cc}&limit=200", ua, 40)
    except Exception:
        return None
    apps = [x for x in d.get("results") or [] if x.get("wrapperType") == "software"]
    return (sum(int(x.get("userRatingCount") or 0) for x in apps), len(apps)) if apps else None


def _history():
    if not CSV.exists():
        return {}
    h = {}
    with CSV.open(encoding="utf-8", newline="") as f:
        for r in csv.DictReader(f):
            if r["value"] not in ("", None):
                h.setdefault((r["id"], r["source"], r["key"]), {})[r["date"]] = float(r["value"])
    return h


def collect(only=None, today=None):
    c = cfg()
    a = c.get("attention") or {}
    ua, days = a.get("user_agent") or common.contact_ua(), int(a.get("window_days", 7))
    today = today or common.now_kst().date()
    hist = _history()
    rows, latest, notes = [], {}, []
    charts = apple_ranks(a.get("apple_countries") or [], a.get("apple_feeds") or [], ua)
    learned = json.loads(ARTISTS.read_text(encoding="utf-8")) if ARTISTS.exists() else {}
    notes.append(f"애플 순위 {len(charts)}개 표")
    for co in c.get("companies") or []:
        cid = co["id"]
        if only and cid not in only:
            continue
        o = latest.setdefault(cid, {"name": co["name"], "segment": co.get("segment"), "wiki": {}, "steam": {}, "apple": [], "news": {}, "missing": []})
        for lang, olds in (co.get("wiki_old") or {}).items():   # 옛 제목은 누적만(가속 계산에는 쓰지 않는다)
            for t in olds:
                try:
                    wiki_store(lang, t, wiki_series(lang, t, ua, today - timedelta(days=35), today - timedelta(days=1)))
                except Exception:
                    pass
        for lang, title in (co.get("wiki") or {}).items():
            r = wiki_accel(lang, title, ua, today, days)
            if r is None:
                o["missing"].append(f"wiki:{lang}:{title}")
                continue
            o["wiki"][f"{lang}:{title}"] = {"views7": r[0], "base7": round(r[1]), "accel": round(r[2], 2)}
            rows.append((today.isoformat(), cid, "wiki", f"{lang}:{title}", r[0]))
            time.sleep(0.2)
        for appid in co.get("steam") or []:
            tot = steam_total(appid, ua)
            if tot is None:
                o["missing"].append(f"steam:{appid}")
                continue
            rows.append((today.isoformat(), cid, "steam", str(appid), tot))
            s = hist.get((cid, "steam", str(appid)), {})
            w1, w2 = s.get((today - timedelta(days=7)).isoformat()), s.get((today - timedelta(days=14)).isoformat())
            o["steam"][str(appid)] = {"total": tot, "gain7": tot - w1 if w1 is not None else None,
                                      "accel": round((tot - w1 + 1) / (w1 - w2 + 1), 2) if w1 is not None and w2 is not None else None}
            time.sleep(1.0)
        if co.get("apps"):
            rx = re.compile(co["apps"], re.I)
            hit_apps = []
            for (cc, feed), lst in charts.items():
                for rank, name, artist, aid in lst:
                    if rx.search(artist):
                        o["apple"].append({"country": cc, "feed": feed, "rank": rank, "app": name[:40]})
                        if aid and aid.startswith("app:"):
                            hit_apps.append(aid[4:])
                        elif aid:
                            learned.setdefault(cid, [])
                            if aid not in learned[cid]:
                                learned[cid].append(aid)
            for aid in resolve_artists(hit_apps, ua, learned.setdefault("_app_artist", {})):
                learned.setdefault(cid, [])
                if aid not in learned[cid]:
                    learned[cid].append(aid)
            rows.append((today.isoformat(), cid, "apple", "best_rank", min((x["rank"] for x in o["apple"]), default="")))
        artists = list(dict.fromkeys([str(x) for x in co.get("apple_artist") or []] + learned.get(cid, [])))
        if artists:
            o["ratings"] = {}
            for cc in dict.fromkeys(["us", co.get("market", "us")]):
                r = apple_ratings(artists, cc, ua)
                time.sleep(3.5)   # 애플 Search API 문서 한도 분당 약 20회 안쪽(2026-11-12 확인)
                if r is None:
                    o["missing"].append(f"ratings:{cc}")
                    continue
                rows.append((today.isoformat(), cid, "apple_ratings", cc, r[0]))
                s = hist.get((cid, "apple_ratings", cc), {})
                w1, w2 = s.get((today - timedelta(days=7)).isoformat()), s.get((today - timedelta(days=14)).isoformat())
                o["ratings"][cc] = {"total": r[0], "apps": r[1], "gain7": r[0] - w1 if w1 is not None else None,
                                    "accel": round((r[0] - w1 + 1) / (w1 - w2 + 1), 2) if w1 is not None and w2 is not None and w1 >= w2 else None}
        hl = co.get("market", "us")
        for term in (co.get("terms") or [])[:2]:
            n7 = news_count(term, hl, days)
            if n7 is None:
                continue
            # 직전 4주 같은 요일 기록의 평균과 비교(attention.py와 같은 방식) — Google News 'when:35d'는 건수가 불안정해 쓰지 않는다(2026-10-30 시험)
            s = hist.get((cid, "news", term), {})
            past = [s[d] for d in ((today - timedelta(days=k)).isoformat() for k in (7, 14, 21, 28)) if d in s]
            prior = sum(past) / len(past) if past else None
            o["news"][term] = {"n7": n7, "accel": round((n7 + 1) / (prior + 1), 2) if prior is not None else None, "saturated": n7 >= 100}
            rows.append((today.isoformat(), cid, "news", term, n7))
            time.sleep(0.3)
        o["demand_accel"] = demand_accel(o)
    OUT.mkdir(parents=True, exist_ok=True)
    ARTISTS.write_text(json.dumps(learned, ensure_ascii=False, indent=1), encoding="utf-8")
    return rows, latest, notes


def demand_accel(o):
    """종목 수요 가속 — 위키(조회 가중 평균)·스팀·뉴스(포화 제외) 가속의 평균. 원천이 없으면 None"""
    parts = []
    w = [(v["views7"], v["accel"]) for v in o["wiki"].values() if v["views7"] > 0]
    if w:
        tot = sum(x for x, _ in w)
        parts.append(sum(x * a for x, a in w) / tot)
    parts += [v["accel"] for v in o["steam"].values() if v.get("accel")]
    parts += [v["accel"] for v in (o.get("ratings") or {}).values() if v.get("accel")]
    parts += [v["accel"] for v in o["news"].values() if v.get("accel") and not v["saturated"]]
    return round(sum(parts) / len(parts), 2) if parts else None


def spikes(latest, spike_accel, min_views):
    """펄스 '관심 급가속' 원본 — 위키 문서 단위(조회 문턱 이상) 또는 스팀 가속"""
    out = []
    for cid, o in latest.items():
        for k, v in o["wiki"].items():
            if v["accel"] >= spike_accel and v["views7"] >= min_views:
                out.append({"id": cid, "name": o["name"], "source": "wiki", "key": k, "accel": v["accel"], "views7": v["views7"]})
        for k, v in o["steam"].items():
            if (v.get("accel") or 0) >= spike_accel:
                out.append({"id": cid, "name": o["name"], "source": "steam", "key": k, "accel": v["accel"], "gain7": v["gain7"]})
        for k, v in (o.get("ratings") or {}).items():
            if (v.get("accel") or 0) >= spike_accel and (v.get("gain7") or 0) >= 1000:   # 평점 1,000건 미만 증가는 잡음
                out.append({"id": cid, "name": o["name"], "source": "apple_ratings", "key": k, "accel": v["accel"], "gain7": v["gain7"]})
    return sorted(out, key=lambda x: -x["accel"])


def run(only=None):
    OUT.mkdir(parents=True, exist_ok=True)
    rows, latest, notes = collect(only)
    new = not CSV.exists()
    with CSV.open("a", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        if new:
            w.writerow(["date", "id", "source", "key", "value"])
        w.writerows(rows)
    a = cfg().get("attention") or {}
    sp = spikes(latest, float(a.get("spike_accel", 2.0)), int(a.get("spike_min_views", 20000)))
    LATEST.write_text(json.dumps({"date": common.now_kst().strftime("%Y-%m-%d"), "as_of": common.iso(common.now_kst()), "rows": latest, "spikes": sp},
                                 ensure_ascii=False, indent=1), encoding="utf-8")
    top = sorted(((k, v["demand_accel"]) for k, v in latest.items() if v.get("demand_accel")), key=lambda x: -x[1])[:3]
    miss = sum(len(v["missing"]) for v in latest.values())
    return (f"소비재 수요 관심도 {len(latest)}종목 · 가속 상위 " + (", ".join(f"{k} {a_:.2f}" for k, a_ in top) or "없음")
            + f" · 급가속 {len(sp)}건 · 못 찾은 문서·앱 {miss}" + "".join(f" · {n}" for n in notes)), len(sp)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    args = sys.argv[1:]
    if "--wiki-backfill" in args:
        n, miss = wiki_backfill([a for a in args if not a.startswith("--")] or None)
        print(f"위키 백필 {n:,}일·문서 · 못 찾은 문서 {len(miss)}" + "".join("\n  " + m for m in miss))
    elif "--wiki-monthly" in args:
        print(f"위키 월별 {wiki_monthly():,}행")
    else:
        print(run(args or None))
