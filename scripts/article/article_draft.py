"""기사 소재 '채택' → 기사 초안 HTML (2026-11-15 마스터 지시 "버튼을 누르면 기사로 써서 보내는 걸로 바꿔줘. html 파일로 제공해줘")

흐름: 텔레그램 '① 채택' → radar/telegram_inbox.py → pitch_feedback.on_callback → queue() → 작업자(--worker, 별도 프로세스)가
헤드리스 Claude Code `/article-draft <PITCH-ID>`(스킬 .claude/skills/article-draft — 기사 작성 요건)로 JSON을 쓰게 하고,
check() 통과 → render() → outputs/article/drafts/<PITCH-ID>.html → 마스터 개인 텔레그램에 파일로 보낸다.
모델은 글쓰기에만 쓰고, 순서·부제 글자 수·인용 출처 검사와 렌더·발송은 이 파일이 결정론으로 한다.
사용: py scripts/article/article_draft.py check <PITCH-ID>      # 스킬이 쓴 JSON 검사(통과 = 종료 코드 0)
      py scripts/article/article_draft.py render <PITCH-ID>     # HTML만 만든다
      py scripts/article/article_draft.py queue <PITCH-ID>      # 작업 대기열에 넣고 작업자를 띄운다
      py scripts/article/article_draft.py --worker              # 대기열 처리(작업자)
"""
import html
import json
import os
import re
import shutil
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "radar"))
from pollers import common  # noqa: E402

DRAFTS = ROOT / "outputs" / "article" / "drafts"
QUEUE = ROOT / "radar" / "state" / "article_jobs.json"
LOCK = ROOT / "radar" / "state" / "article_worker.lock"
MODEL = "opus"
DAILY_JOBS = 6            # 하루 상한(비용 안전장치) — 아침 소재는 하루 최대 3건
ORDER = ("lead", "newfact", "body1", "body2", "body3")
LABEL = {"lead": "리드", "newfact": "뉴팩트", "body1": "본론1", "body2": "본론2", "body3": "본론3"}
BANNED = ("단독 확인", "에 있어서", "되어지", "엄청난", "충격적", "어마어마")
# 보고서체 표지(2026-11-15 마스터 지시 "내용 서술이 기사가 아니라 보고서 같다. 한국경제·서울경제·매일경제·조선일보·중앙일보 기사체를 참조하라")
# 기사는 사실을 주어·동사로 전하고(밝혔다·나타났다·전망이다), 필자가 독자에게 설명·논평하지 않는다.
REPORT_TONE = ("점을 보여 준다", "점을 보여준다", "짚었다", "눈에 띈다", "남은 질문은", "여기서 ", "이란 ", "라는 뜻이다", "다는 뜻이다",
               "결이 다른", "셈이다", "할 수 있다는 점", "주목할 만하다", "시사한다", "의미가 있다", "살펴보면", "정리하면", "요컨대")
# 설명체 어미 — '~이다.'로 끝나는 문장 비중이 크면 보고서처럼 읽힌다
EXPLAIN_END = re.compile(r"(이다|것이다|때문이다|점이다|셈이다|있다)\.$")
PITCH_ID = re.compile(r"^PITCH-(\d{8})-(\d{2})$")


def path(pid, ext="json"):
    return DRAFTS / f"{pid}.{ext}"


# ---------- 검사 ----------
def check(d):
    """기사 작성 요건(마스터 지시) 검사 → 문제 목록(빈 목록 = 통과)"""
    bad = []
    if not str(d.get("title") or "").strip():
        bad.append("제목이 없다")
    sub = [str(s).strip() for s in d.get("subtitle") or [] if str(s).strip()]
    if not 2 <= len(sub) <= 3:
        bad.append(f"부제목은 2~3줄이어야 한다(지금 {len(sub)}줄)")
    elif len({len(s) for s in sub}) != 1:
        bad.append("부제목 줄마다 글자 수(공백 포함)가 같아야 한다: " + " / ".join(f"{len(s)}자" for s in sub))
    for s in sub:
        if s[:1] in "-·•■":
            bad.append(f"부제목 줄머리 기호를 빼라: {s[:12]}")
    b = d.get("body") or {}
    for k in ORDER:
        paras = [p for p in b.get(k) or [] if str(p).strip()]
        if not paras:
            bad.append(f"본문 '{LABEL[k]}'이 없다")
        for p in paras:
            if len(re.findall(r"[^.!?]+[.!?]", str(p))) > 5:
                bad.append(f"{LABEL[k]} 문단이 길다(5문장 초과) — 나눠라: {str(p)[:20]}…")
    q = b.get("quote", "없음")
    if q == "없음":
        bad.append("본문 'quote'가 없다(인용이 없으면 null)")
    elif q:
        for f in ("text", "speaker", "source"):
            if not str(q.get(f) or "").strip():
                bad.append(f"인용문 {f}가 없다 — 실제 공개된 말·글만, 화자·출처와 함께")
        if q.get("source") and not str(q["source"]).startswith("http"):
            bad.append("인용 출처는 링크여야 한다")
    srcs = d.get("sources") or []
    if not srcs or not all(str(s.get("url") or "").startswith("http") for s in srcs):
        bad.append("출처(sources)에 링크가 있어야 한다")
    sents = [x.strip() for k in ORDER for p in b.get(k) or [] for x in re.findall(r"[^.!?]+[.!?]", str(p))]
    for w in REPORT_TONE:
        hit = [x for x in sents if w in x]
        if hit:
            bad.append(f"보고서체 '{w.strip()}' — 기사체로(사실은 주어·동사로, 해석은 출처를 밝혀): {hit[0][:24]}…")
    if sents:
        ex = sum(1 for x in sents if EXPLAIN_END.search(x))
        if ex / len(sents) > 0.35:
            bad.append(f"설명체 어미(~이다·~있다) 비중 {ex / len(sents):.0%} — 35% 이하로. 기사 어미(밝혔다·나타났다·전망이다·분석이다·예정이다)를 쓴다")
    lead = " ".join(b.get("lead") or [])
    if lead and not re.search(r"(했다|밝혔다|나타났다|알려졌다|공개했다|내놨다|선보였다|전망이다|발표했다)\.", lead):
        bad.append("리드는 '누가 무엇을 했다'는 사실 문장으로 연다(밝혔다·공개했다·나타났다)")
    text = json.dumps(d, ensure_ascii=False)
    for w in BANNED:
        if w in text:
            bad.append(f"쓰지 않는 표현: '{w}'")
    if re.search(r"\d+억\s?\$|\$\s?\d[\d,.]*\s?(million|billion)", text):
        bad.append("달러 금액은 $25B·$340M 표기")
    return bad


# ---------- 렌더 ----------
CSS = """
:root{--bg:#fbfaf7;--fg:#1c1b19;--sub:#4a4740;--muted:#7a766d;--rule:#d9d4c7;--accent:#0f3d7a;--quote:#f1ede3}
@media (prefers-color-scheme:dark){:root{--bg:#161513;--fg:#ecebe6;--sub:#c9c5bb;--muted:#9a958a;--rule:#3a3832;--accent:#8fb4ea;--quote:#24221e}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--fg);font-family:"Noto Serif KR","Nanum Myeongjo",serif;}
main{max-width:720px;margin:0 auto;padding:28px 18px 60px}
.kicker{font:600 13px/1.4 "Pretendard","Noto Sans KR",sans-serif;color:var(--accent);letter-spacing:.04em;margin-bottom:10px}
h1{font-size:30px;line-height:1.35;margin:0 0 18px;font-weight:800;letter-spacing:-.02em;word-break:keep-all}
.deck{border-left:3px solid var(--accent);padding:2px 0 2px 14px;margin:0 0 22px}
.deck p{margin:0;font:600 17px/1.75 "Pretendard","Noto Sans KR",sans-serif;color:var(--sub);white-space:pre}
.deck p::before{content:"- "}
.meta{font:13px/1.5 "Pretendard","Noto Sans KR",sans-serif;color:var(--muted);border-top:1px solid var(--rule);border-bottom:1px solid var(--rule);padding:8px 0;margin-bottom:26px}
article p{font-size:18px;line-height:1.95;margin:0 0 1.1em;word-break:keep-all;letter-spacing:-.01em}
blockquote{margin:28px 0;padding:18px 20px;background:var(--quote);border-radius:6px}
blockquote p{font-size:19px;line-height:1.8;margin:0 0 8px;font-weight:600}
blockquote cite{font:14px/1.5 "Pretendard","Noto Sans KR",sans-serif;color:var(--muted);font-style:normal}
blockquote .orig{font-size:14px;color:var(--muted);font-weight:400;font-style:italic}
section.notes{margin-top:36px;border-top:1px solid var(--rule);padding-top:14px;font:14px/1.7 "Pretendard","Noto Sans KR",sans-serif;color:var(--sub)}
section.notes h2{font-size:14px;margin:14px 0 6px;color:var(--fg)}
section.notes a{color:var(--accent);word-break:break-all}
@media (max-width:480px){h1{font-size:25px}.deck p{font-size:15px;white-space:pre-wrap}article p{font-size:17px}}
"""


def render(d):
    e = html.escape
    b = d.get("body") or {}
    paras = "".join(f"<p>{e(str(p))}</p>" for k in ORDER for p in b.get(k) or [] if str(p).strip())
    q = b.get("quote")
    quote = ""
    if q:
        orig = f'<p class="orig">{e(q["original"])}</p>' if q.get("original") else ""
        quote = (f'<blockquote><p>“{e(q["text"])}”</p>{orig}<cite>— {e(q.get("speaker", ""))}'
                 f'{", " + e(q["title"]) if q.get("title") else ""} · <a href="{e(q["source"])}">출처</a></cite></blockquote>')
    src = "".join(f'<li>{e(s.get("label") or s["url"])} — <a href="{e(s["url"])}">{e(s["url"])}</a></li>' for s in d.get("sources") or [])
    chk = "".join(f"<li>{e(str(c))}</li>" for c in d.get("checks") or [])
    deck = "".join(f"<p>{e(str(s).strip())}</p>" for s in d.get("subtitle") or [])
    return f"""<!doctype html><html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{e(d.get('title', '기사 초안'))}</title><style>{CSS}</style></head><body><main>
<div class="kicker">Chiip 기사 초안 · {e(d.get('pitch_id', ''))}</div>
<h1>{e(d.get('title', ''))}</h1><div class="deck">{deck}</div>
<div class="meta">{e(d.get('date', ''))} · 공개 자료 기반 초안 — 숫자·인용은 송고 전 원문 대조</div>
<article>{paras}{quote}</article>
<section class="notes"><h2>출처</h2><ol>{src}</ol>{'<h2>보강 취재 · 미확인</h2><ul>' + chk + '</ul>' if chk else ''}</section>
</main></body></html>"""


def render_file(pid):
    d = json.loads(path(pid).read_text(encoding="utf-8"))
    out = path(pid, "html")
    out.write_text(render(d), encoding="utf-8")
    return out, d


# ---------- 대기열·작업자 ----------
def _load():
    return json.loads(QUEUE.read_text(encoding="utf-8")) if QUEUE.exists() else []


def _save(q):
    QUEUE.parent.mkdir(parents=True, exist_ok=True)
    QUEUE.write_text(json.dumps(q, ensure_ascii=False, indent=1), encoding="utf-8")


def queue(pid):
    if not PITCH_ID.match(pid):
        raise ValueError(f"pitch_id 형식이 아니다: {pid}")
    q = _load()
    if not any(j["pitch_id"] == pid for j in q):
        q.append({"pitch_id": pid, "at": common.iso(common.now_kst())})
        _save(q)
    spawn_worker()
    return len(q)


def _alive():
    if not LOCK.exists():
        return False
    try:
        info = json.loads(LOCK.read_text(encoding="utf-8"))
        return common.now_kst() - datetime.fromisoformat(info["at"]) < timedelta(minutes=45)
    except (ValueError, KeyError):
        return False


def spawn_worker():
    if _alive() or not _load():
        return False
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0) | getattr(subprocess, "DETACHED_PROCESS", 0)
    subprocess.Popen([sys.executable, str(Path(__file__).resolve()), "--worker"], cwd=ROOT,
                     stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=flags)
    return True


def _jobs_today(add=0):
    s = common.load_state("article_jobs_count")
    day = common.now_kst().strftime("%Y-%m-%d")
    s = {day: s.get(day, 0) + add}
    common.save_state("article_jobs_count", s)
    return s[day]


def write(pid):
    """헤드리스 Claude Code로 기사 JSON을 쓴다"""
    exe = shutil.which("claude")
    if not exe:
        raise RuntimeError("claude CLI 없음")
    cmd = [exe, "-p", f"/article-draft {pid}", "--model", MODEL, "--output-format", "json",
           "--allowedTools", "Read,Glob,Grep,Write,Edit,WebSearch,WebFetch,Bash(py scripts/*),Bash(py radar/*)",
           "--permission-mode", "dontAsk", "--permission-prompts", "none"]
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    proc = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, encoding="utf-8",
                          stdin=subprocess.DEVNULL, timeout=2400, creationflags=flags)
    out = json.loads(proc.stdout) if proc.stdout.strip().startswith("{") else {}
    if proc.returncode != 0 or out.get("is_error"):
        raise RuntimeError(f"claude 실패({proc.returncode}): {str(out.get('result', proc.stderr))[:200]}")


def deliver(pid, d=None):
    import notify
    out, d = render_file(pid) if d is None else (path(pid, "html"), d)
    cap = f"[기사 초안] {d.get('title', '')}\n" + "\n".join(f"- {s}" for s in d.get("subtitle") or [])
    return notify.send_document(out, cap, "PITCH")


def worker():
    import notify
    LOCK.parent.mkdir(parents=True, exist_ok=True)
    try:
        while True:
            q = _load()
            if not q:
                return 0
            pid = q[0]["pitch_id"]
            LOCK.write_text(json.dumps({"pid": os.getpid(), "at": common.iso(common.now_kst()), "job": pid}), encoding="utf-8")
            try:
                if _jobs_today() >= DAILY_JOBS:
                    notify.send(f"[기사 초안] 오늘 작성 상한({DAILY_JOBS}건) — {pid}는 내일 다시 눌러 주세요", "PITCH")
                else:
                    write(pid)
                    _jobs_today(1)
                    d = json.loads(path(pid).read_text(encoding="utf-8"))
                    bad = check(d)
                    if bad:
                        raise RuntimeError("요건 미달: " + "; ".join(bad[:3]))
                    render_file(pid)
                    deliver(pid, d)
                    common.record_health("article-draft", True)
            except Exception as exc:
                common.record_health("article-draft", False, f"{pid}: {type(exc).__name__}")
                notify.send(f"[기사 초안] {pid} 작성 실패 — {str(exc)[:160]}", "PITCH")
            _save([j for j in _load() if j["pitch_id"] != pid])
    finally:
        LOCK.unlink(missing_ok=True)


def main(argv):
    sys.stdout.reconfigure(encoding="utf-8")
    if argv[:1] == ["--worker"]:
        return worker()
    if len(argv) == 2 and argv[0] == "check":
        bad = check(json.loads(path(argv[1]).read_text(encoding="utf-8")))
        print("통과" if not bad else "\n".join(f"- {x}" for x in bad))
        return 1 if bad else 0
    if len(argv) == 2 and argv[0] == "render":
        print(render_file(argv[1])[0])
        return 0
    if len(argv) == 2 and argv[0] == "queue":
        print(f"[기사 초안] 대기 {queue(argv[1])}건")
        return 0
    print(__doc__)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
