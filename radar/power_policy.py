"""AI 밸류체인 전력 섹터 입법·규제 추적 (마스터 지시 2026-11-20 "AI 밸류체인의 전력 섹터에서 이 같은 입법과 주 규제 상황을 팔로업하는 게
중요한데 왜 안하고 있나? 파이프라인과 시스템을 점검하라")

점검 결과(2026-11-20): 전력 입법·규제는 정책 원천(src-policy-us-*)과 뉴스 경로에 걸린 기사로만 한 건씩 해설됐고, 법안·규칙·주 규제마다
'지금 어느 단계인지'를 들고 끝까지 따라가는 장부가 없었다. 공식 의회 사이트(congress.gov·govtrack·senate.gov)는 자동 접속 403 —
Congress.gov API 키(CONGRESS_API_KEY, 무료)가 들어오면 법안 행동을 1차 자료로 받는다(TODO_MASTER).

흐름: config/power_policy.yaml 항목마다 Google News 질의(when:1d) → match 정규식에 맞는 기사만 →
  ① 기사 낱말이 장부의 현재 단계보다 앞선 단계면 '단계 변화 후보' inbox(src-power-policy, P1 승격 대상)
  ② 아니면 '진행 기사' — 항목별로 처음 본 기사만 inbox(Pulse가 묶어 판단)
  장부(knowledge/policy/power_tracker.json)는 기사 낱말로 올리지 않는다 — Pulse가 1차 출처로 확인한 뒤 --set으로만.
사용: py radar/power_policy.py               # run(): 수집(run_poll·run_hourly)
      py radar/power_policy.py --status      # 항목별 현재 단계·최근 기사
      py radar/power_policy.py --set <id> <단계> <근거 URL>   # 1차 출처 확인 뒤 단계 올림
"""
import hashlib
import json
import re
import sys
import urllib.parse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from pollers import common  # noqa: E402
from pollers import rss  # noqa: E402

SOURCE_ID = "src-power-policy"
TRACKER = common.ROOT / "knowledge" / "policy" / "power_tracker.json"
STATE = "power_policy"


def cfg():
    return common.load_yaml("config/power_policy.yaml") or {}


def tracker(c=None):
    c = c or cfg()
    t = json.loads(TRACKER.read_text(encoding="utf-8")) if TRACKER.exists() else {}
    for it in c.get("items") or []:   # 설정의 시작 단계로 빈 칸을 채운다
        t.setdefault(it["id"], {"stage": it.get("stage"), "date": str(it.get("stage_date") or ""), "evidence": it.get("stage_evidence") or "", "history": []})
    return t


def save_tracker(t):
    TRACKER.parent.mkdir(parents=True, exist_ok=True)
    TRACKER.write_text(json.dumps(t, ensure_ascii=False, indent=1), encoding="utf-8")


def stage_of(text, kind, c):
    """기사 문구 → 단계(가장 앞선 단계부터 검사). 못 찾으면 None"""
    for st, pat in (c.get("stage_words") or {}).get(kind, {}).items():
        if re.search(pat, text, re.I):
            return st
    return None


def ahead(new, cur, kind, c):
    order = (c.get("stages") or {}).get(kind) or []
    return new in order and (cur not in order or order.index(new) > order.index(cur))


def classify(item, entries, tr, c, seen):
    out = []
    m = re.compile(item.get("match") or ".", re.I)
    for e in entries:
        text = f"{e['title']} {common.strip_tags(e.get('desc') or '')}"
        if not e.get("link") or e["link"] in seen or not m.search(text):
            continue
        seen.add(e["link"])
        st = stage_of(text, item["kind"], c)
        cur = (tr.get(item["id"]) or {}).get("stage")
        jump = bool(st) and ahead(st, cur, item["kind"], c)
        out.append({"entry": e, "stage": st, "jump": jump, "cur": cur})
    return out


def run(get=None):
    c = cfg()
    tr = tracker(c)
    st = common.load_state(STATE, {})
    seen = set(st.get("seen") or [])
    get = get or common.http_get
    items, errs = [], []
    for it in c.get("items") or []:
        if it.get("status") == "closed":
            continue
        if it.get("congress"):
            try:
                items += congress_actions(it, tr, c, seen, get)
            except Exception as exc:
                errs.append(f"{it['id']} 의회 기록: {type(exc).__name__}")
        entries = []
        for q in it.get("queries") or []:
            try:
                url = rss.GNEWS.format(q=urllib.parse.quote(f"{q} when:1d"), hl="en-US", gl="US")
                entries += rss.parse_feed(get(url))
            except Exception as exc:
                errs.append(f"{it['id']}: {type(exc).__name__}")
        for r in classify(it, entries, tr, c, seen):
            e = r["entry"]
            head = f"[전력 정책·{it['name'].split(' — ')[0]}] " + ("단계 변화 후보 " + f"{r['cur']} → {r['stage']} · " if r["jump"] else "")
            items.append(common.make_item(SOURCE_ID, f"{it['id']}-{hashlib.sha1(e['link'].encode()).hexdigest()[:12]}", e["link"], head + common.strip_tags(e["title"]),
                                          rss.to_iso(e["date"]), "정책", "en", common.strip_tags(e.get("desc") or "")[:300],
                                          extra={"policy_item": it["id"], "stage_hint": r["stage"], "stage_now": r["cur"], "stage_jump": r["jump"],
                                                 "entities_hint": it.get("exposure") or [], "publisher": e.get("publisher") or "",
                                                 "source_class": "정책 보도(1차 확인 필요)"}))
    st["seen"] = sorted(seen)[-3000:]
    st["at"] = common.iso(common.now_kst())
    common.save_state(STATE, st)
    save_tracker(tr)
    saved = common.save_new_items(items) if items else []
    common.record_health(SOURCE_ID, not errs or len(errs) < sum(len(i.get("queries") or []) for i in c.get("items") or []), "; ".join(errs[:3]) or None)
    jumps = sum(1 for i in items if (i.get("extra") or {}).get("stage_jump") or i.get("stage_jump"))
    return f"전력 정책 기사 {len(items)}건(단계 변화 후보 {jumps}) · 새로 저장 {len(saved)}" + (f" · 문제 {', '.join(errs[:3])}" if errs else "")


CONGRESS_API = "https://api.congress.gov/v3/bill/{congress}/{type}/{number}/actions?format=json&limit=50&api_key={key}"
BILL_PAGE = {"hr": "house-bill", "s": "senate-bill", "hjres": "house-joint-resolution", "sjres": "senate-joint-resolution"}
# 의회 행동 문구 → 단계(위에서부터, 대소문자 무시) — Congress.gov 'actions'의 text
ACTION_STAGE = (
    ("대통령 서명", r"became public law|signed by president"),
    ("하원 수정안 처리·양원 조정", r"(resolving differences|house agreed to senate amendment|conference report)"),
    ("상원 통과", r"passed senate|passed/agreed to in senate"),
    ("상원 토론 종결", r"cloture on the measure invoked|cloture motion on the measure|substitute amendment"),
    ("하원 통과", r"passed house|passed/agreed to in house|on passage passed"),
    ("위원회 통과", r"ordered to be reported|reported by"),
)


def action_stage(text):
    for st, pat in ACTION_STAGE:
        if re.search(pat, text or "", re.I):
            return st
    return None


def congress_actions(item, tr, c, seen, get):
    """Congress.gov API 행동 기록(1차 자료) — 새 행동은 진행 항목, 장부보다 앞선 단계면 장부를 바로 올리고 '단계 확정(의회 기록)' 항목.
    키(CONGRESS_API_KEY)가 없으면 조용히 건너뛴다. 키는 주소에만 쓰고 기록·출력에는 쓰지 않는다"""
    key = common.load_env().get("CONGRESS_API_KEY")
    if not key:
        return []
    g = item["congress"]
    acts = json.loads(get(CONGRESS_API.format(key=key, **g)))["actions"]
    page = f"https://www.congress.gov/bill/{g['congress']}th-congress/{BILL_PAGE.get(g['type'], g['type'])}/{g['number']}/all-actions"
    out, order = [], (c.get("stages") or {}).get("bill") or []
    rec = tr[item["id"]]
    for a in sorted(acts, key=lambda x: (x.get("actionDate") or "", x.get("actionTime") or "")):
        text = a.get("text") or ""
        sig = f"congress:{item['id']}:{a.get('actionDate')}:{hashlib.sha1(text.encode()).hexdigest()[:10]}"
        st = action_stage(text)
        if st and ahead(st, rec.get("stage"), "bill", c):
            rec["history"].append({"stage": rec.get("stage"), "date": rec.get("date"), "evidence": rec.get("evidence")})
            rec.update({"stage": st, "date": a.get("actionDate"), "evidence": page, "by": "congress.gov 행동 기록"})
            jump = True
        else:
            jump = False
        if sig in seen:
            continue
        seen.add(sig)
        if not st and not jump:
            continue   # 단계와 무관한 절차 행동('Considered by Senate')은 넘기지 않는다
        head = f"[전력 정책·{item['name'].split(' — ')[0]}] " + (f"단계 확정(의회 기록) → {st} · " if jump else f"의회 기록 · {st} · ")
        out.append(common.make_item(SOURCE_ID, sig.split(":", 1)[1].replace(":", "-"), page, head + text[:220], f"{a.get('actionDate')}T00:00:00-05:00",
                                    "정책", "en", text[:400],
                                    extra={"policy_item": item["id"], "stage_hint": st, "stage_jump": jump, "stage_confirmed": jump,
                                           "entities_hint": item.get("exposure") or [], "source_class": "1차(의회 행동 기록)"}))
    return out


def poll(env=None):
    """run_poll용 — run()이 inbox에 직접 저장한다"""
    run()
    return []


def set_stage(pid, stage, evidence):
    c = cfg()
    tr = tracker(c)
    item = next((i for i in c.get("items") or [] if i["id"] == pid), None)
    if not item:
        raise SystemExit(f"항목 없음: {pid}")
    order = (c.get("stages") or {}).get(item["kind"]) or []
    if stage not in order:
        raise SystemExit(f"단계 이름이 틀림 — {order}")
    if not re.match(r"https?://", evidence or ""):
        raise SystemExit("근거 URL(1차 출처)이 필요하다")
    r = tr[pid]
    r["history"].append({"stage": r.get("stage"), "date": r.get("date"), "evidence": r.get("evidence")})
    r.update({"stage": stage, "date": common.now_kst().date().isoformat(), "evidence": evidence})
    save_tracker(tr)
    return r


def status():
    c = cfg()
    tr = tracker(c)
    return [{"id": i["id"], "name": i["name"], "stage": tr[i["id"]]["stage"], "date": tr[i["id"]]["date"], "ladder": (c.get("stages") or {}).get(i["kind"]),
             "why": i.get("why")} for i in c.get("items") or [] if i.get("status") != "closed"]


def main(argv):
    sys.stdout.reconfigure(encoding="utf-8")
    if argv[:1] == ["--set"]:
        print(json.dumps(set_stage(argv[1], argv[2], argv[3]), ensure_ascii=False, indent=1))
    elif argv[:1] == ["--status"]:
        print(json.dumps(status(), ensure_ascii=False, indent=1))
    else:
        print(run())
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
