"""노션 실시간 감시 (마스터 지시 2026-10-28) — "내가 노션에 올리는 즉시 파악해 결과물을 만들고 텔레그램으로"

결정론 감시(모델 없음): run_poll(5분마다)이 run()을 부른다. NOTION_TOKEN이 있을 때만 동작한다
(없으면 예약 작업 chiip-notion-watch가 노션 커넥터로 매시간 새 페이지를 확인 — 수정 감지는 토큰이 있어야 실시간).
  1) config/notion.yaml pages의 Insights·Informations·Stocks 아래 페이지(child_page)를 나열하고 수정 시각을 본다
     (Informations는 2단계 — 'Memory Channel Check' 아래 IB 노트 등). '치입 검토…' 페이지는 건너뛴다.
  2) 새 페이지·처리 뒤 수정된 페이지가 SETTLE_MIN분 이상 그대로면(작성 중 반쯤 쓴 글 제외) 본문·첨부(xlsx·csv)를
     텍스트로 뽑아 radar/notion/inbox/<id>.md(git 제외 — IB 요지 등 라이선스 자료가 섞일 수 있음)에 두고 작업 대기열에 넣는다.
  3) 별도 프로세스(--worker)가 대기열을 하나씩 헤드리스 Claude Code `/notion-intake <역할> <id> <inbox>`로 처리하고,
     스킬이 남긴 텔레그램 문안(outputs/report/notion/<YYYYMMDD>_<id8>_tg.txt)을 보낸 뒤 처리 표시(scripts/notion_state.py).
노션 API: GET /v1/blocks/{id}/children (developers.notion.com/reference/get-block-children, Notion-Version 2026-03-11 확인)
사용: py radar/notion_watch.py [--dry-run] | --worker | --baseline (지금 있는 페이지를 기준선으로)
"""
import argparse
import json
import os
import re
import subprocess
import sys
import urllib.parse
import urllib.request
import zipfile
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from pollers import common  # noqa: E402
import notion_state  # noqa: E402

SOURCE_ID = "src-notion-watch"
INBOX = common.ROOT / "radar" / "notion" / "inbox"
QUEUE = common.ROOT / "radar" / "state" / "notion_jobs.json"
LOCK = common.ROOT / "radar" / "state" / "notion_worker.lock"
REPORTS = common.ROOT / "outputs" / "report" / "notion"
ROLES = {"insights": 1, "informations": 2, "stocks": 1}   # 역할 → 하위 페이지를 몇 단계까지 볼지
SETTLE_MIN = 10
WATCH_EVERY_MIN = 5
DAILY_JOBS = 20            # 하루 헤드리스 작업 상한(비용 안전장치)
MODEL = {"insights": "opus", "informations": "sonnet", "stocks": "sonnet"}


def cfg():
    return common.load_yaml("config/notion.yaml") or {}


def token():
    return common.load_env().get((cfg().get("api") or {}).get("token_env", "NOTION_TOKEN"))


def api_get(path, params=None, tok=None):
    api = cfg().get("api") or {}
    url = f"{api.get('base', 'https://api.notion.com/v1')}{path}"
    if params:
        url += "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {tok or token()}",
                                               "Notion-Version": api.get("version", "2026-03-11")})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode("utf-8"))


def children(block_id, tok=None):
    out, cursor = [], None
    while True:
        p = {"page_size": 100}
        if cursor:
            p["start_cursor"] = cursor
        data = api_get(f"/blocks/{block_id}/children", p, tok)
        out += data.get("results", [])
        if not data.get("has_more"):
            return out
        cursor = data.get("next_cursor")


def list_pages(root_id, depth, tok=None, _parent=""):
    """(id, 제목, 최근 수정, 부모 제목) — child_page만, depth 단계까지"""
    for b in children(root_id, tok):
        if b.get("type") != "child_page" or b.get("in_trash"):
            continue
        title = (b.get("child_page") or {}).get("title", "")
        yield b["id"], title, b.get("last_edited_time"), _parent
        if depth > 1 and b.get("has_children"):
            yield from list_pages(b["id"], depth - 1, tok, title)


# ---------- 본문 추출 ----------
def _rt(rich):
    return "".join(t.get("plain_text", "") for t in rich or [])


def xlsx_text(raw):
    """표준 라이브러리만으로 xlsx → 'a | b | c' 줄들 (openpyxl 없음)"""
    import io
    ns = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
    z = zipfile.ZipFile(io.BytesIO(raw))
    ss = []
    if "xl/sharedStrings.xml" in z.namelist():
        for si in ET.fromstring(z.read("xl/sharedStrings.xml")).findall(f"{ns}si"):
            ss.append("".join(t.text or "" for t in si.iter(f"{ns}t")))
    lines = []
    for name in sorted(n for n in z.namelist() if re.match(r"xl/worksheets/sheet\d+\.xml", n)):
        lines.append(f"[시트 {name.rsplit('/', 1)[-1]}]")
        for row in ET.fromstring(z.read(name)).iter(f"{ns}row"):
            vals = []
            for c in row.findall(f"{ns}c"):
                v = c.find(f"{ns}v")
                if c.get("t") == "s" and v is not None:
                    vals.append(ss[int(v.text)])
                elif c.get("t") == "inlineStr":
                    vals.append("".join(x.text or "" for x in c.iter(f"{ns}t")))
                else:
                    vals.append(v.text if v is not None else "")
            if any(vals):
                lines.append(" | ".join(vals))
    return "\n".join(lines)


def page_text(pid, tok=None, depth=3):
    lines = []
    for b in children(pid, tok):
        t = b.get("type")
        body = b.get(t) or {}
        if t in ("paragraph", "quote", "callout", "toggle", "to_do"):
            lines.append(_rt(body.get("rich_text")))
        elif t.startswith("heading_"):
            lines.append("#" * int(t[-1]) + " " + _rt(body.get("rich_text")))
        elif t in ("bulleted_list_item", "numbered_list_item"):
            lines.append("- " + _rt(body.get("rich_text")))
        elif t == "table_row":
            lines.append(" | ".join(_rt(c) for c in body.get("cells", [])))
        elif t in ("file", "pdf"):
            f = body.get("file") or body.get("external") or {}
            name = body.get("name") or f.get("url", "").split("?")[0].rsplit("/", 1)[-1]
            lines.append(f"[첨부 {name}]")
            if name.lower().endswith((".xlsx", ".csv", ".txt")) and f.get("url"):
                try:
                    raw = urllib.request.urlopen(f["url"], timeout=60).read()
                    lines.append(xlsx_text(raw) if name.lower().endswith(".xlsx") else raw.decode("utf-8", "replace")[:20000])
                except Exception as exc:
                    lines.append(f"(첨부 읽기 실패: {type(exc).__name__})")
        elif t == "child_page":
            lines.append(f"[하위 페이지: {body.get('title', '')}]")
        elif t == "bookmark" or t == "embed":
            lines.append(f"[링크 {body.get('url', '')}]")
        if b.get("has_children") and depth > 1 and t not in ("child_page", "child_database"):
            lines += ["  " + x for x in page_text(b["id"], tok, depth - 1).splitlines()]
    return "\n".join(x for x in lines if x is not None)


# ---------- 감지 → 대기열 ----------
def _load_queue():
    return json.loads(QUEUE.read_text(encoding="utf-8")) if QUEUE.exists() else []


def _save_queue(q):
    QUEUE.parent.mkdir(parents=True, exist_ok=True)
    QUEUE.write_text(json.dumps(q, ensure_ascii=False, indent=1), encoding="utf-8")


def detect(tok, now=None, dry=False):
    now = now or common.now_kst()
    pages = cfg().get("pages") or {}
    st = notion_state.load()
    queue = _load_queue()
    queued = {j["page_id"] for j in queue}
    found = []
    for role, depth in ROLES.items():
        root = (pages.get(role) or {}).get("id")
        if not root:
            continue
        for pid, title, edited, parent in list_pages(root, depth, tok):
            if edited and now - datetime.fromisoformat(edited.replace("Z", "+00:00")) < timedelta(minutes=SETTLE_MIN):
                continue      # 아직 쓰는 중일 수 있음 — 다음 회차에
            d = notion_state.decide(role, pid, title, edited, st)
            if d in ("NEW", "CHANGED") and pid not in queued:
                found.append({"page_id": pid, "role": role, "title": title, "parent": parent, "edited": edited, "kind": d})
    if not dry:
        notion_state.save(st)
        for j in found:
            j["inbox"] = str((INBOX / f"{j['page_id'].replace('-', '')}.md").relative_to(common.ROOT).as_posix())
            INBOX.mkdir(parents=True, exist_ok=True)
            head = f"# {j['title']}\n역할: {j['role']} / 상위: {j['parent'] or '-'} / 구분: {j['kind']} / 수정: {j['edited']}\n\n"
            (common.ROOT / j["inbox"]).write_text(head + page_text(j["page_id"], tok), encoding="utf-8")
        _save_queue(queue + found)
    return found


def _worker_alive():
    if not LOCK.exists():
        return False
    try:
        info = json.loads(LOCK.read_text(encoding="utf-8"))
        return common.now_kst() - datetime.fromisoformat(info["at"]) < timedelta(minutes=60)
    except (ValueError, KeyError):
        return False


def spawn_worker():
    if _worker_alive():
        return False
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0) | getattr(subprocess, "DETACHED_PROCESS", 0)
    subprocess.Popen([sys.executable, str(Path(__file__).resolve()), "--worker"], cwd=common.ROOT,
                     stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=flags)
    return True


def run():
    """run_poll용 — 토큰 없으면 조용히 건너뜀(예약 작업이 대신)"""
    tok = token()
    if not tok:
        return 0
    if not common.is_due(SOURCE_ID, WATCH_EVERY_MIN):
        return 0
    try:
        found = detect(tok)
        common.record_health(SOURCE_ID, True)
    except Exception as exc:
        common.record_health(SOURCE_ID, False, f"{type(exc).__name__}: {exc}")
        raise
    finally:
        common.mark_run(SOURCE_ID)
    if found or _load_queue():
        spawn_worker()
    return len(found)


# ---------- 작업자 ----------
def _jobs_today(add=0):
    s = common.load_state("notion_jobs_count")
    day = common.now_kst().strftime("%Y-%m-%d")
    s = {day: s.get(day, 0) + add}
    common.save_state("notion_jobs_count", s)
    return s[day]


def run_job(job, tok):
    import shutil
    exe = shutil.which("claude")
    if not exe:
        raise RuntimeError("claude CLI 없음")
    prompt = f"/notion-intake {job['role']} {job['page_id']} {job['inbox']}"
    cmd = [exe, "-p", prompt, "--model", MODEL.get(job["role"], "sonnet"), "--output-format", "json",
           "--allowedTools", "Read,Glob,Grep,Write,Edit,WebSearch,WebFetch,Bash(py scripts/*),Bash(py radar/*)",
           "--permission-mode", "dontAsk", "--permission-prompts", "none"]
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    proc = subprocess.run(cmd, cwd=common.ROOT, capture_output=True, text=True, encoding="utf-8",
                          stdin=subprocess.DEVNULL, timeout=2400, creationflags=flags)
    out = json.loads(proc.stdout) if proc.stdout.strip().startswith("{") else {}
    if proc.returncode != 0 or out.get("is_error"):
        raise RuntimeError(f"claude 실패({proc.returncode}): {str(out.get('result', proc.stderr))[:200]}")
    return out


def tg_path(job, day=None):
    day = day or common.now_kst().strftime("%Y%m%d")
    return REPORTS / f"{day}_{job['page_id'].replace('-', '')[:8]}_tg.txt"


def worker():
    LOCK.parent.mkdir(parents=True, exist_ok=True)
    LOCK.write_text(json.dumps({"pid": os.getpid(), "at": common.iso(common.now_kst())}), encoding="utf-8")
    import notify
    tok = token()
    try:
        while True:
            q = _load_queue()
            if not q:
                return 0
            job = q[0]
            if _jobs_today() >= DAILY_JOBS:
                notify.send(f"[노션 감시] 오늘 처리 상한({DAILY_JOBS}건) 도달 — 대기 {len(q)}건은 내일 처리", "NOTION")
                return 0
            LOCK.write_text(json.dumps({"pid": os.getpid(), "at": common.iso(common.now_kst()), "job": job["page_id"]}),
                            encoding="utf-8")
            try:
                run_job(job, tok)
                _jobs_today(1)
                tg = tg_path(job)
                if tg.exists():
                    notify.send(tg.read_text(encoding="utf-8"), "NOTION")
                # 치입 검토 하위 페이지를 만들면 부모 수정 시각도 바뀐다 → 처리 직후 시각으로 표시
                edited = job.get("edited")
                try:
                    edited = api_get(f"/pages/{job['page_id']}", tok=tok).get("last_edited_time", edited)
                except Exception:
                    pass
                notion_state.mark(job["page_id"], edited, str(tg.relative_to(common.ROOT).as_posix()) if tg.exists() else "")
            except Exception as exc:
                common.record_health(SOURCE_ID, False, f"작업 실패 {job['title'][:30]}: {exc}")
                notify.send(f"[노션 감시] '{job['title'][:40]}' 처리 실패 — {type(exc).__name__}. 다음 회차에 다시 시도하지 않음(수정하면 재감지)", "NOTION")
                notion_state.mark(job["page_id"], job.get("edited"), "실패")
            _save_queue(_load_queue()[1:])
    finally:
        LOCK.unlink(missing_ok=True)


def baseline_all(tok):
    pages = cfg().get("pages") or {}
    st = notion_state.load()
    n = 0
    for role, depth in ROLES.items():
        root = (pages.get(role) or {}).get("id")
        for pid, title, edited, _ in list_pages(root, depth, tok):
            if notion_state._key(pid) not in st["pages"]:
                notion_state.baseline(role, pid, title, edited, st)
                n += 1
    notion_state.save(st)
    return n


def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument("--worker", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--baseline", action="store_true")
    a = ap.parse_args(argv)
    if a.worker:
        return worker()
    tok = token()
    if not tok:
        print("NOTION_TOKEN 없음 — 예약 작업 chiip-notion-watch(노션 커넥터, 매시간)가 대신 확인합니다")
        return 0
    if a.baseline:
        print(f"기준선 {baseline_all(tok)}건")
        return 0
    found = detect(tok, dry=a.dry_run)
    print(f"[노션 감시] 새·수정 {len(found)}건" + (" (dry-run)" if a.dry_run else ""))
    for j in found:
        print(f"- {j['role']} {j['kind']} {j['title']}")
    if found and not a.dry_run:
        spawn_worker()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
