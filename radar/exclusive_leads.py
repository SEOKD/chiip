"""노션 Exclusive Source 단서 장부 (마스터 지시 2026-11-02 "Exclusive Source는 등급이 F1으로 지정하라. 다만 분석 글을 작성할 때 활용하거나 이 정보와 관련한 추가 근거를 지속 조사하도록 해라")

단서마다 공개 근거를 쌓는다. 본문은 노션에만 두고 여기에는 확인 질문·검색어·판정만 둔다.
저장: 장부 knowledge/exclusive/leads.yaml · 등급·공개 확인 knowledge/exclusive/index.csv · 후보 radar/state/exclusive_leads.json — 모두 git 제외, 이 PC에만(2026-11-02 마스터 지시 "로컬에만 둬")
수집은 이 스크립트(run_hourly 6시간), 판정은 펄스 회차의 모델. 규칙은 docs/channels/notion.md.
사용: py radar/exclusive_leads.py --pending                      # 판정할 후보
      py radar/exclusive_leads.py --judge <FI> <url> <지지|상충|맥락|무관> "<자기 말 메모>"
      py radar/exclusive_leads.py --confirm <FI> <S-id>           # 공개 확인(source-ingest 뒤)
      py radar/exclusive_leads.py --sync <notion-fetch 출력 파일>   # 새 단서·본문 변경 찾기
      py radar/exclusive_leads.py --add <yaml 파일>                # 새 단서 등록
      py radar/exclusive_leads.py --unexplained                  # 해설 피드를 아직 보내지 않은 단서(새 단서·본문 변경)
      py radar/exclusive_leads.py --explained <FI>               # 해설 피드 발송 표시
2026-11-11 마스터 지시 "Exclusive Source는 웹 검색과 대조해 크로스체크하지 말고 1급 기밀로서 정보 유출이 없게 하라. 그리고 올라온 내용 자체를 해설하고 풀이해 Feed로 전하라":
  웹 대조(검색어 질의)를 멈춘다(WEB_CHECK) — 검색어 자체가 단서를 바깥에 내보낸다. 해설은 개인 텔레그램 Chiip Exclusive 피드로만.
"""
import argparse
import csv
import hashlib
import re
import sys
import time
import urllib.parse
from datetime import date, timedelta
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
from pollers import common, rss  # noqa: E402

LEADS = common.ROOT / "knowledge" / "exclusive" / "leads.yaml"
INDEX = common.ROOT / "knowledge" / "exclusive" / "index.csv"
COLUMNS = ["fi_id", "entered_at", "disclosure_class", "source_class", "reliability", "entities", "topics", "linked_theses", "corroboration", "embargo_until", "f1_converted_at",
           "publicly_confirmed_at", "confirm_source_id", "lead_days", "outcome"]
STATE = "exclusive_leads"
HEAD = "# 노션 Exclusive Source 단서 장부 — radar/exclusive_leads.py가 쓴다. 본문·취재원 표현·직접 인용은 넣지 않는다(docs/channels/notion.md)\n"
VERDICTS = ("지지", "상충", "맥락", "무관")
WINDOW = "7d"
PER_LEAD = 5       # 한 단서가 한 번에 내는 후보 상한
MAX_PENDING = 40
ROUND = 5          # 펄스 회차당 판정 상한
HOLD_MIN = 60
WEB_CHECK = False  # 2026-11-11 마스터 지시 — 웹 대조 금지(1급 기밀)      # 후보를 넘긴 뒤 관문을 다시 열 때까지 — 판정이 밀려도 5분마다 회차가 열리지 않게
HEAD_RE = re.compile(r"^\s*(?:<b>)?\s*■(.+?)(?:</b>)?\s*$")
DATE_RE = re.compile(r"^\s*\d{2}\.\d{2}\.\d{2}\s*$")


def load(path=LEADS):
    return yaml.safe_load(path.read_text(encoding="utf-8")) if path.exists() else {"page": "", "leads": []}


def save(data, path=LEADS):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(HEAD + yaml.safe_dump(data, allow_unicode=True, sort_keys=False, width=1000), encoding="utf-8")


def index(path=INDEX):
    if not path.exists():
        return COLUMNS, []
    with path.open(encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        return reader.fieldnames, list(reader)


def write_index(fields, rows, path=INDEX):
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)


def counts(lead):
    ev = lead.get("evidence") or []
    return {v: sum(1 for e in ev if e.get("verdict") == v) for v in VERDICTS[:3]}


def corroboration(lead):
    n = counts(lead)
    return "contradicted" if n["상충"] else "corroborated" if n["지지"] else "pending"


def related(lead, q, cid):
    ql = str(q).lower()
    return cid in (lead.get("entities") or []) or ql in [str(n).lower() for n in lead.get("names") or []]


def line(lead, row, page):
    n = counts(lead)
    done = row and row.get("publicly_confirmed_at")
    state = "공개 확인" if done else f"공개 미확인(지지 {n['지지']}·상충 {n['상충']}·맥락 {n['맥락']})"
    guard = " | 1급 기밀: 웹 대조 금지·공개 산출물(리포트·Artifact·노션·GitHub) 금지 — 해설은 Chiip Exclusive 피드만"
    guard += " | 내부자 출처: invest·public·Portfolio·텐배거 리포트 금지" if lead.get("insider_like") else ""
    return f"독점 단서 {lead['id']} | F1 | {lead['title']} | {state}{guard} | 본문 notion-fetch {page}"


def lines(q, cid, data=None, rows=None):
    """--need가 붙이는 줄"""
    data = load() if data is None else data
    if not data["leads"]:
        return []
    rows = index()[1] if rows is None else rows
    by = {r["fi_id"]: r for r in rows}
    return [line(x, by.get(x["id"]), data["page"]) for x in data["leads"] if related(x, q, cid)]


def insider(data=None):
    data = load() if data is None else data
    return {x["id"] for x in data["leads"] if x.get("insider_like")}


def passes(title, lead):
    return all(re.search(p, title, re.I) for p in lead.get("must") or [])


def key(title):
    return re.sub(r"\W+", " ", title.rsplit(" - ", 1)[0].lower()).strip()[:90]


def collect(lead, entries, seen, known):
    """피드 항목 → 새 후보. 이미 본 제목과 장부에 있는 주소는 뺀다"""
    out = []
    for e in entries:
        title, k = common.strip_tags(e["title"]), key(common.strip_tags(e["title"]))
        if not e["link"] or e["link"] in known or k in seen or not passes(title, lead):
            continue
        seen.add(k)
        out.append({"fi": lead["id"], "title": title, "url": e["link"], "publisher": (e.get("publisher") or "").strip(), "published_at": rss.to_iso(e["date"])})
    return out[:PER_LEAD]


def run():
    """열린 단서의 검색어를 돈다. 공개 확인이 끝난 단서는 묻지 않는다"""
    data, st = load(), common.load_state(STATE, {})
    if not WEB_CHECK:
        st.update({"pending": []})
        common.save_state(STATE, st)
        common.record_health("exclusive-leads", True, None)
        return "exclusive-leads", 0
    done = {r["fi_id"] for r in index()[1] if r.get("publicly_confirmed_at") or r.get("outcome") in ("refuted", "unresolved")}
    seen, pending, failed = set(st.get("seen", [])), st.get("pending", []), 0
    for lead in data["leads"]:
        if lead["id"] in done:
            continue
        known = {e.get("url") for e in lead.get("evidence") or []}
        for q in lead.get("queries") or []:
            url = rss.GNEWS.format(q=urllib.parse.quote(f"{q['q']} when:{WINDOW}"), hl=q.get("hl", "ko"), gl=q.get("gl", "KR"))
            try:
                pending += collect(lead, rss.parse_feed(common.http_get(url, timeout=30)), seen, known)
            except Exception:
                failed += 1
            time.sleep(0.5)
    st.update({"seen": sorted(seen)[-3000:], "pending": pending[-MAX_PENDING:]})
    common.save_state(STATE, st)
    common.record_health("exclusive-leads", failed == 0, f"검색 실패 {failed}건" if failed else None)
    return "exclusive-leads", len(st["pending"])


def status(now):
    """펄스 관문 — 판정할 후보가 있고 보류 시간이 지났으면 연다"""
    st = common.load_state(STATE, {})
    items = st.get("pending") or []
    return {"due": WEB_CHECK and bool(items) and (st.get("hold") or "") <= common.iso(now), "pending": len(items), "items": items[:ROUND]}


def offered(now):
    st = common.load_state(STATE, {})
    st["hold"] = common.iso(now + timedelta(minutes=HOLD_MIN))
    common.save_state(STATE, st)


def judge(fid, url, verdict, note, today, data=None, rows=None):
    """후보를 판정한다. 무관은 버리고, 나머지는 장부에 쌓아 corroboration을 다시 맞춘다. 돌려주는 값 = 마스터에게 알릴 줄 또는 None"""
    if verdict not in VERDICTS:
        raise SystemExit(f"판정은 {VERDICTS} 중 하나")
    data = load() if data is None else data
    lead = next((x for x in data["leads"] if x["id"] == fid), None)
    if not lead:
        raise SystemExit("없는 단서 id")
    st = common.load_state(STATE, {})
    hit = next((x for x in st.get("pending", []) if x["fi"] == fid and x["url"] == url), {})
    st["pending"] = [x for x in st.get("pending", []) if not (x["fi"] == fid and x["url"] == url)]
    common.save_state(STATE, st)
    if verdict == "무관":
        return None
    lead.setdefault("evidence", []).append({"date": today, "url": url, "title": hit.get("title", ""), "verdict": verdict, "note": note})
    save(data)
    fields, rows = index() if rows is None else rows
    for r in rows:
        if r["fi_id"] == fid:
            r["corroboration"] = corroboration(lead)
    write_index(fields, rows)
    return f"[Chiip Exclusive] {lead['title']} — 공개 근거 {verdict}: {note}\n{url}" if verdict in ("지지", "상충") else None


def confirm(fid, source_id, now):
    fields, rows = index()
    for r in rows:
        if r["fi_id"] == fid:
            lead_days = (now.date() - date.fromisoformat(r["entered_at"][:10])).days
            r.update({"publicly_confirmed_at": common.iso(now), "confirm_source_id": source_id, "lead_days": lead_days, "corroboration": "corroborated", "outcome": "confirmed"})
    write_index(fields, rows)


def unexplained(data):
    """해설 피드를 보내지 않았거나 본문이 바뀐 단서"""
    return [x for x in data["leads"] if x.get("explained") != (x.get("block") or "-")]


def explained(fid, data):
    for x in data["leads"]:
        if x["id"] == fid:
            x["explained"] = x.get("block") or "-"
            return True
    return False


def norm(s):
    return re.sub(r"\W+", "", s)


def digest(s):
    return hashlib.sha1(norm(s).encode("utf-8")).hexdigest()[:12]


def blocks(text):
    """노션 본문 → [(제목, 본문)]. ■ 줄부터 다음 ■ 줄이나 날짜 줄까지"""
    out = []
    for raw in text.replace("\\n", "\n").split("\n"):
        m = HEAD_RE.match(raw)
        if m:
            out.append([m.group(1).strip(), ""])
        elif DATE_RE.match(raw):
            out.append(None)
        elif out and out[-1]:
            out[-1][1] += raw
    return [(b[0], b[1]) for b in out if b]


def sync(text, data):
    """(새 단서 제목들, 본문이 바뀐 단서 id들). 첫 대조는 기준값만 잡는다"""
    by = {x["key"]: x for x in data["leads"] if x.get("key")}
    new, changed = [], []
    for title, body in blocks(text):
        lead = by.get(digest(title))
        if not lead:
            new.append(title)
            continue
        h = digest(body)
        if lead.get("block") and lead["block"] != h:
            changed.append(lead["id"])
        lead["block"] = h
    return new, changed


def add(spec, now, data, fields, rows):
    """새 단서를 F1로 올린다(Exclusive Source 페이지 전체가 F1, 2026-11-02 마스터 지정)"""
    fid = f"FI-{max([int(r['fi_id'][3:]) for r in rows] + [0]) + 1:04d}"
    lead = {"id": fid, "key": digest(spec.pop("notion_title")), "block": "", **{k: v for k, v in spec.items() if k not in ("source_class", "reliability", "topics")}, "evidence": []}
    data["leads"].append(lead)
    t = common.iso(now)
    rows.append({"fi_id": fid, "entered_at": t, "disclosure_class": "F1", "source_class": spec["source_class"], "reliability": spec["reliability"], "entities": ";".join(spec["entities"]),
                 "topics": ";".join(spec["topics"]), "linked_theses": "", "corroboration": "pending", "embargo_until": "", "f1_converted_at": t, "publicly_confirmed_at": "",
                 "confirm_source_id": "", "lead_days": "", "outcome": "pending"})
    return fid


def main(argv):
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("--pending", action="store_true")
    ap.add_argument("--judge", nargs=4, metavar=("FI", "URL", "VERDICT", "NOTE"))
    ap.add_argument("--confirm", nargs=2, metavar=("FI", "SOURCE"))
    ap.add_argument("--sync")
    ap.add_argument("--add")
    ap.add_argument("--unexplained", action="store_true")
    ap.add_argument("--explained")
    a = ap.parse_args(argv)
    now = common.now_kst()
    if a.unexplained:
        data = load()
        for x in unexplained(data):
            print(f"{x['id']} | {x['title']} | 본문 notion-fetch {data['page']}")
        return 0
    if a.explained:
        data = load()
        if not explained(a.explained, data):
            raise SystemExit("없는 단서 id")
        save(data)
        print(f"[Exclusive] {a.explained} 해설 발송 표시")
        return 0
    if a.pending:
        for x in common.load_state(STATE, {}).get("pending", []):
            print(f"{x['fi']} | {x['published_at'][:10]} | {x['publisher']} | {x['title']} | {x['url']}")
        return 0
    if a.judge:
        msg = judge(*a.judge, now.date().isoformat())
        print(msg or "[Exclusive] 알림 없음")
        return 0
    if a.confirm:
        confirm(a.confirm[0], a.confirm[1], now)
        print(f"[Exclusive] {a.confirm[0]} 공개 확인")
        return 0
    if a.sync:
        data = load()
        new, changed = sync(Path(a.sync).read_text(encoding="utf-8"), data)
        save(data)
        print(f"[Exclusive] 새 단서 {len(new)}건 · 본문 변경 {changed or '없음'}")
        for t in new:
            print(f"새 단서: {t}")
        return 0
    if a.add:
        data = load()
        fields, rows = index()
        fid = add(yaml.safe_load(Path(a.add).read_text(encoding="utf-8")), now, data, fields, rows)
        save(data)
        write_index(fields, rows)
        print(f"[Exclusive] {fid} 등록")
        return 0
    print(__doc__)
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
