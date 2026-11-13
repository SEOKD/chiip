"""한국 반도체 수출 — 산업부 월간 수출입 동향(매월 1일) 수집·개정·알림 (마스터 지시 2026-11-13 "만들어라", ppi_release.py와 같은 구조)

결정론(모델 없음). run_hourly 30분 — 매월 1~3일 KST 09:00~20:00에만 산업부 보도자료 게시판(motie.go.kr, robots 허용)을 보고
제목 'N월 수출입 동향'의 새 글이 있으면 본문에서 숫자를 읽는다:
  전체 수출액·전년 대비, 조업일수 고려 일평균 수출·전년 대비, 반도체·컴퓨터(서버·SSD 포함 품목) 수출액·전년 대비, 메모리 고정가격 줄(있으면)
fail-closed: 필요한 숫자(전체·반도체)를 하나라도 못 읽으면 값을 지어내지 않고 공백·이유만 남기고 알리지 않는다.
다른 공식 경로(2026-11-13 확인):
  · 관세청 10일·20일 잠정치(11·21일) — customs.go.kr 기사 경로(/na/ntt/)는 robots가 수집을 막고, 무역통계 tradedata.go.kr은 자동 접속을 차단한다 → 공백
  · 공공데이터포털 관세청_품목별 수출입실적(1220000/Itemtrade) — DATA_GO_KR_KEY는 있으나 이 API 활용신청이 안 돼 403 → 승인되면 HS 8542(반도체)·8471(컴퓨터)·8523(SSD 등 저장매체) 월별을 붙인다
저장: knowledge/models/macro/kr_exports.json {releases: {YYYY-MM: {...}}, revisions: [...], gaps: [...]}
"""
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from pollers import common  # noqa: E402

OUT = common.ROOT / "knowledge" / "models" / "macro" / "kr_exports.json"
BOARD = "https://www.motie.go.kr/kor/article/ATCL3f49a5a8c"
ITEMTRADE = "https://apis.data.go.kr/1220000/Itemtrade/getItemtradeList"
STATE = "kr_exports"
DAYS, HOURS = (1, 2, 3), (9, 20)
NUM = r"([\d,]+(?:\.\d+)?)"
PCT = r"([+△−-]?\s*[\d,]+(?:\.\d+)?)"


def _f(x):
    x = x.replace(",", "").replace(" ", "")
    neg = x.startswith(("△", "−", "-"))
    v = float(x.lstrip("+△−-"))
    return -v if neg else v


def text_of(html):
    t = re.sub(r"<script.*?</script>|<style.*?</style>", " ", html, flags=re.S)
    t = re.sub(r"<[^>]+>", " ", t)
    t = t.replace("&nbsp;", " ").replace("&lsquo;", "'").replace("&rsquo;", "'").replace("&middot;", "·").replace("&rarr;", "→")
    return re.sub(r"\s+", " ", t)


def parse(t):
    """보도자료 본문 → 숫자. 못 읽은 칸은 넣지 않는다"""
    out = {}
    m = re.search(r"월 수출은 전년 동월 대비 " + PCT + r"\s*% (증가|감소)한 " + NUM + r" 억 달러", t)
    if m:
        out["total"] = {"usd_100m": _f(m.group(3)), "yoy": _f(m.group(1)) / 100 * (1 if m.group(2) == "증가" else -1)}
    m = re.search(r"일평균 수출은 " + PCT + r"\s*% (증가|감소)한 " + NUM + r" 억 달러", t)
    if m:
        out["daily_avg"] = {"usd_100m": _f(m.group(3)), "yoy": _f(m.group(1)) / 100 * (1 if m.group(2) == "증가" else -1)}
    for name in ("반도체", "컴퓨터", "무선통신기기", "디스플레이"):
        m = re.search(re.escape(name) + r"\s*\(\s*" + NUM + r"\s*억 달러\s*,\s*" + PCT + r"\s*%\s*\)", t)
        if m:
            out[name] = {"usd_100m": _f(m.group(1)), "yoy": _f(m.group(2)) / 100}
    if "반도체" not in out:   # 표 꼴 '반도체 디스플레이 … 564 (+259)'
        m = re.search(r"반도체 디스플레이 무선통신기기 컴퓨터[^\d△]*" + NUM + r"\s*\(\s*" + PCT + r"\s*\)", t)
        if m:
            out["반도체"] = {"usd_100m": _f(m.group(1)), "yoy": _f(m.group(2)) / 100, "from": "표(정수)"}
    m = re.search(r"메모리 고정가격 추이[^:]*:\s*(.{0,160}?)(?= [가-힣]{2,}\s*\()", t)
    if m:
        out["memory_price_line"] = m.group(1).strip()
    return out


def latest_posts(pages=6):
    posts = []
    for pg in range(1, pages + 1):
        html = common.http_get(BOARD, {"pageIndex": pg}, timeout=30).decode("utf-8", "replace")
        for m in re.finditer(r'href="(/kor/article/ATCL3f49a5a8c/(\d+)/view[^"]*)"[^>]*>(.*?)</a>', html, re.S):
            title = re.sub(r"<[^>]+>|\s+", " ", m.group(3)).strip()
            ym = re.search(r"(\d{4})년\s*(\d{1,2})월 수출입 동향", title)
            if ym:
                posts.append({"id": m.group(2), "title": title, "month": f"{ym.group(1)}-{int(ym.group(2)):02d}", "url": "https://www.motie.go.kr" + m.group(1).split("?")[0]})
        if posts:
            break
    return posts


def summary(month, r):
    pc = lambda x: f"{x * 100:+.1f}%"
    s = r["반도체"]
    text = f"한국 {int(month[5:])}월 반도체 수출은 ${s['usd_100m'] / 10:,.2f}B로 전년 대비 {pc(s['yoy'])}다"
    if "total" in r:
        text += f"(전체 수출 ${r['total']['usd_100m'] / 10:,.1f}B, {pc(r['total']['yoy'])}"
        text += f", 조업일수 고려 일평균 ${r['daily_avg']['usd_100m'] / 10:,.2f}B {pc(r['daily_avg']['yoy'])})." if "daily_avg" in r else ")."
    if "컴퓨터" in r:
        text += f" 서버·SSD가 든 컴퓨터는 ${r['컴퓨터']['usd_100m'] / 10:,.2f}B({pc(r['컴퓨터']['yoy'])})다."
    return text


def load():
    return json.loads(OUT.read_text(encoding="utf-8")) if OUT.exists() else {"releases": {}, "revisions": [], "gaps": []}


def gap(doc, why, now):
    doc.setdefault("gaps", []).append({"at": common.iso(now), "why": why})
    doc["gaps"] = doc["gaps"][-50:]


def collect(now=None, force=False):
    """(새 달, 요약) 또는 (None, 이유)"""
    now = now or common.now_kst()
    doc = load()
    posts = latest_posts()
    if not posts:
        gap(doc, "게시판에서 '수출입 동향' 글을 찾지 못함", now)
        OUT.parent.mkdir(parents=True, exist_ok=True)
        OUT.write_text(json.dumps(doc, ensure_ascii=False, indent=1), encoding="utf-8")
        return None, "글 없음"
    p = posts[0]
    old = doc["releases"].get(p["month"])
    if old and old.get("id") == p["id"] and not force:
        return None, f"{p['month']} 이미 반영"
    t = text_of(common.http_get(p["url"], timeout=30).decode("utf-8", "replace"))
    r = parse(t)
    if "반도체" not in r or "total" not in r:   # fail-closed
        gap(doc, f"{p['month']} 본문에서 {'반도체' if '반도체' not in r else '전체 수출'} 수치를 읽지 못함 — 값 없음({p['url']})", now)
        OUT.write_text(json.dumps(doc, ensure_ascii=False, indent=1), encoding="utf-8")
        raise RuntimeError(doc["gaps"][-1]["why"])
    if old:
        for k in ("반도체", "total", "daily_avg", "컴퓨터"):
            if k in old and k in r and old[k]["usd_100m"] != r[k]["usd_100m"]:
                doc["revisions"].append({"month": p["month"], "item": k, "old": old[k]["usd_100m"], "new": r[k]["usd_100m"], "at": common.iso(now)})
    doc["releases"][p["month"]] = {**r, "id": p["id"], "title": p["title"], "url": p["url"], "at": common.iso(now), "unit": "억 달러(usd_100m)"}
    doc["as_of"] = common.iso(now)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(doc, ensure_ascii=False, indent=1), encoding="utf-8")
    return p["month"], summary(p["month"], r)


def itemtrade_status():
    """공공데이터 관세청 품목별 수출입실적 접근 — 활용신청 전이면 403(공백으로 적는다)"""
    k = common.load_env().get("DATA_GO_KR_KEY")
    if not k:
        return "DATA_GO_KR_KEY 없음"
    try:
        common.http_get(ITEMTRADE, {"serviceKey": k, "strtYymm": "202601", "endYymm": "202601", "hsSgn": "8542"}, timeout=30)
        return "ok"
    except Exception as exc:
        return f"{type(exc).__name__}: {str(exc)[:60]} — 공공데이터포털에서 '관세청_품목별 수출입실적' 활용신청 필요"


def run(now=None):
    now = now or common.now_kst()
    if now.day not in DAYS or not HOURS[0] <= now.hour < HOURS[1]:
        return "발표 창 아님"
    try:
        month, text = collect(now)
    except Exception as exc:
        common.record_health("kr-exports", False, str(exc)[:200])
        return f"수집 실패 — {exc}"
    common.record_health("kr-exports", True, None)
    if not month:
        return text
    st = common.load_state(STATE, {})
    if st.get("sent") == month:
        return f"{month} 이미 알림"
    common.save_new_items([common.make_item("src-kr-exports", f"kr-exports:{month}", load()["releases"][month]["url"], f"[지표 발표] 한국 {month} 수출입 동향 — 반도체",
                                            common.iso(now), "지표", "ko", text, extra={"tier": "T0", "kind": "kr_exports"})])
    st.update({"sent": month, "at": common.iso(now)})
    common.save_state(STATE, st)
    return f"{month} 반영 · {text}"


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    if "--now" in sys.argv:
        m, t = collect(force=True)
        print(json.dumps({"month": m, "text": t, "data_go_kr": itemtrade_status()}, ensure_ascii=False, indent=1))
    else:
        print(run())
