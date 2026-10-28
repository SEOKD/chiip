"""텔레그램 버튼 처리 + 노션 인텔 아카이브 기록 (BUILD_PROMPT §21.13)

run_poll이 매번(5분) 부른다. 모델은 쓰지 않는다.
1) getUpdates로 '⭐ 노션 기록' 버튼(callback save:<ref>)을 받는다 — 마스터 채팅방에서 온 것만.
   알림에 답장(reply)으로 글을 쓰면 그 글을 '마스터 메모'로 함께 기록한다.
2) radar/state/notion_queue.jsonl 에 넣고, NOTION_TOKEN이 있으면 노션 API로 바로 기록.
   토큰이 없으면 대기열에 남고, 예약 작업(chiip-focus-score)이 노션 커넥터로 기록한다(--export로 목록 출력).
사용: py radar/telegram_inbox.py [--push] [--export] [--mark-done <ref,...>]
"""
import json
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from pollers import common  # noqa: E402
import notify  # noqa: E402

QUEUE = common.STATE / "notion_queue.jsonl"


def _tg(token, method, params):
    data = urllib.parse.urlencode(params).encode()
    with urllib.request.urlopen(f"https://api.telegram.org/bot{token}/{method}", data=data, timeout=20) as r:
        return json.loads(r.read())


def load_queue():
    if not QUEUE.exists():
        return []
    return [json.loads(l) for l in QUEUE.read_text(encoding="utf-8").splitlines() if l.strip()]


def save_queue(rows):
    QUEUE.parent.mkdir(parents=True, exist_ok=True)
    QUEUE.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")


def enqueue(ref, memo=None):
    rows = load_queue()
    for r in rows:
        if r["ref"] == ref:
            if memo:
                r["memo"] = ((r.get("memo") or "") + "\n" + memo).strip()
                r["status"] = "pending" if r["status"] != "done" else "memo_update"
            save_queue(rows)
            return r
    alert = common.load_state(notify.ALERTS, {}).get(ref)
    if not alert:
        return None
    row = {"ref": ref, "status": "pending", "memo": memo or "", "queued_at": common.iso(common.now_kst()), **alert}
    rows.append(row)
    save_queue(rows)
    return row


def poll_updates():
    env = common.load_env()
    token, chat = env.get("TELEGRAM_BOT_TOKEN"), str(env.get("TELEGRAM_CHAT_ID") or "")
    if not token or not chat:
        return 0
    st = common.load_state("telegram_inbox", {"offset": 0, "msg_ref": {}})
    try:
        res = _tg(token, "getUpdates", {"offset": st["offset"], "timeout": 0,
                                        "allowed_updates": json.dumps(["callback_query", "message"])})
    except Exception as exc:  # 토큰이 섞일 수 있는 URL은 기록하지 않음
        common.record_health("telegram-inbox", False, type(exc).__name__)
        return 0
    n = 0
    for u in res.get("result", []):
        st["offset"] = u["update_id"] + 1
        cq = u.get("callback_query")
        if cq:
            msg = cq.get("message") or {}
            if str(msg.get("chat", {}).get("id")) != chat or not str(cq.get("data", "")).startswith("save:"):
                continue
            ref = cq["data"][5:]
            row = enqueue(ref)
            st["msg_ref"][str(msg.get("message_id"))] = ref
            note = "노션 기록 대기열에 추가" if row else "알림 정보를 찾지 못함(오래된 알림)"
            try:
                _tg(token, "answerCallbackQuery", {"callback_query_id": cq["id"], "text": note})
                if row:
                    _tg(token, "editMessageReplyMarkup", {"chat_id": chat, "message_id": msg.get("message_id"),
                            "reply_markup": json.dumps({"inline_keyboard": [[{"text": "✅ 기록함 (답장하면 메모 추가)",
                                                                              "callback_data": "noop"}]]})})
            except Exception:
                pass
            n += 1 if row else 0
            continue
        m = u.get("message") or {}
        if str(m.get("chat", {}).get("id")) != chat:
            continue
        rep = m.get("reply_to_message") or {}
        ref = st["msg_ref"].get(str(rep.get("message_id")))
        if ref and m.get("text"):  # 기록한 알림에 답장 → 마스터 메모
            enqueue(ref, m["text"][:1800])
            n += 1
    if len(st["msg_ref"]) > 2000:
        st["msg_ref"] = dict(list(st["msg_ref"].items())[-2000:])
    common.save_state("telegram_inbox", st)
    common.record_health("telegram-inbox", True)
    return n


# ---------- 노션 ----------
def _ncfg():
    return common.load_yaml("config/notion.yaml") or {}


def _names(ids):
    uni = {u["id"]: u["name"] for u in (common.load_yaml("config/valuation.yaml") or {}).get("universe", [])}
    return [uni.get(i, i).replace(",", " ") for i in ids or []][:10]


def _focus_score(ids):
    p = common.ROOT / "knowledge" / "models" / "focus" / "latest.json"
    if not p.exists() or not ids:
        return None
    rows = {r["id"]: r.get("total") for r in json.loads(p.read_text(encoding="utf-8")).get("rows", [])}
    vals = [rows[i] for i in ids if rows.get(i) is not None]
    return max(vals) if vals else None


def notion_properties(row):
    c = _ncfg()

    def txt(s):
        return {"rich_text": [{"text": {"content": (s or "")[:1900]}}]}
    props = {
        "제목": {"title": [{"text": {"content": (row.get("title") or "")[:200]}}]},
        "유형": {"select": {"name": (c.get("type_map") or {}).get(row.get("doc_type"), "기타")}},
        "등급": {"select": {"name": row.get("level") if row.get("level") in ("P0", "P1", "P2") else "P2"}},
        "요지": txt(row.get("what")), "영향": txt(row.get("impact")),
        "출처": txt(" · ".join(x for x in (row.get("publisher"), row.get("source_id")) if x)),
        "마스터 메모": txt(row.get("memo")), "치입 ID": txt(" ".join(x for x in (row.get("item_id"), row.get("card")) if x)),
        "종목": {"multi_select": [{"name": n} for n in _names(row.get("entities"))]},
    }
    if row.get("url"):
        props["링크"] = {"url": row["url"]}
    if (row.get("published_at") or "")[:10]:
        props["날짜"] = {"date": {"start": row["published_at"][:10]}}
    fs = _focus_score(row.get("entities"))
    if fs is not None:
        props["포커스 점수"] = {"number": fs}
    return props


def push():
    """NOTION_TOKEN이 있으면 대기열을 노션 API로 기록"""
    c = _ncfg()
    api = c.get("api") or {}
    token = common.load_env().get(api.get("token_env", "NOTION_TOKEN"))
    if not token:
        return 0
    rows, n = load_queue(), 0
    for r in rows:
        if r["status"] not in ("pending", "memo_update"):
            continue
        headers = {"Authorization": f"Bearer {token}", "Notion-Version": api.get("version", "2026-03-11"),
                   "Content-Type": "application/json"}
        try:
            if r["status"] == "memo_update" and r.get("page_id"):
                body = {"properties": {"마스터 메모": notion_properties(r)["마스터 메모"]}}
                req = urllib.request.Request(f"{api['base']}/pages/{r['page_id']}", json.dumps(body).encode(), headers,
                                             method="PATCH")
            else:
                body = {"parent": {"type": "data_source_id", "data_source_id": c["archive"]["data_source"]},
                        "properties": notion_properties(r)}
                req = urllib.request.Request(f"{api['base']}/pages", json.dumps(body).encode(), headers, method="POST")
            with urllib.request.urlopen(req, timeout=30) as resp:
                r["page_id"] = json.loads(resp.read()).get("id", r.get("page_id"))
            r["status"], r["done_at"] = "done", common.iso(common.now_kst())
            n += 1
        except urllib.error.HTTPError as exc:
            r["error"] = f"HTTP {exc.code}"
            common.record_health("notion", False, f"HTTP {exc.code}")
            break
    save_queue(rows)
    if n:
        common.record_health("notion", True)
    return n


def export_pending():
    """커넥터로 기록할 대기 항목(예약 작업용) — 노션 속성 값을 그대로 출력"""
    out = []
    for r in load_queue():
        if r["status"] in ("pending", "memo_update"):
            p = notion_properties(r)
            out.append({"ref": r["ref"], "status": r["status"], "page_id": r.get("page_id"),
                        "제목": r.get("title"), "유형": p["유형"]["select"]["name"], "등급": p["등급"]["select"]["name"],
                        "요지": r.get("what"), "영향": r.get("impact"), "링크": r.get("url"),
                        "출처": p["출처"]["rich_text"][0]["text"]["content"], "마스터 메모": r.get("memo"),
                        "치입 ID": p["치입 ID"]["rich_text"][0]["text"]["content"],
                        "종목": [x["name"] for x in p["종목"]["multi_select"]],
                        "날짜": (r.get("published_at") or "")[:10], "포커스 점수": p.get("포커스 점수", {}).get("number")})
    return out


def mark_done(refs, page_ids=None):
    rows = load_queue()
    for r in rows:
        if r["ref"] in refs:
            r["status"], r["done_at"] = "done", common.iso(common.now_kst())
            if page_ids and page_ids.get(r["ref"]):
                r["page_id"] = page_ids[r["ref"]]
    save_queue(rows)


def run():
    n = poll_updates()
    pushed = push()
    return n, pushed


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    if "--export" in sys.argv:
        print(json.dumps(export_pending(), ensure_ascii=False, indent=1))
    elif "--mark-done" in sys.argv:
        refs = sys.argv[sys.argv.index("--mark-done") + 1].split(",")
        mark_done(set(refs))
        print(f"완료 표시 {len(refs)}건")
    else:
        print("버튼·답장 %d, 노션 기록 %d" % run())
