"""IR 설명회 음성 자체 전사(D등급) — 마스터 승인 2026-11-09(TODO 28 "설명회 영상 자체 전사 도구"), 로컬 faster-whisper(Whisper 모델, CPU)

대상: 회사·IR 대행 사이트가 직접 올린 음성·영상 파일(mp3·m4a·mp4·wav…)만. robots.txt를 지키고(jp_ir_qa.allowed), YouTube는 약관상 내려받기 금지라 제외한다.
찾는 곳: 최근 3일 받은편지함의 일본·대만·홍콩 IR 항목(src-jp-ir-*, src-tw-hk-ir-*) 중 음성 파일 주소 + IR 자료 수집기가 기록한 회사별 영상 링크(radar/state/jp_ir_docs.json video).
처리: 주소에서 음성 스트림만 읽어(영상 전체를 내려받지 않는다) 16kHz 모노로 바꾸고 전사한다. 한 회차 1건(CPU가 무겁다), 최대 MAX_MIN분.
출력: 전사문 radar/inbox/ir_audio/<id>.txt(git 제외 — 원문 복제 금지, 저장소에는 요약·짧은 인용만) + inbox 항목 src-ir-audio('IR 질의응답', D등급 자체 전사) → Pulse ⑥가 분석.
사용: py radar/ir_audio.py            # run_hourly 60분 — 대기가 있으면 떨어진 프로세스(--work)로 1건 전사
      py radar/ir_audio.py --work     # 1건 전사(잠금 파일로 겹치지 않게)
      py radar/ir_audio.py --queue    # 대기열 보기
      py radar/ir_audio.py --url <주소> <회사 id>   # 한 건 바로
"""
import glob
import hashlib
import json
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from pollers import common  # noqa: E402

SRC = "src-ir-audio"
OUT = common.ROOT / "radar" / "inbox" / "ir_audio"
MEDIA_RE = re.compile(r"\.(mp3|m4a|mp4|wav|aac|m4v)(\?|$)", re.I)
BLOCK_RE = re.compile(r"youtube\.com|youtu\.be", re.I)   # 약관상 내려받기 금지
MODEL = "small"   # 일본어·중국어 설명회 품질과 CPU 시간의 절충(시험: 2026-11-09 어드밴테스트 질의응답 영상)
MAX_MIN = 120
STATE = "ir_audio"


def candidates(st, days=3):
    seen = set(st.get("done") or []) | set(st.get("failed") or [])
    out = {}
    for f in sorted(glob.glob(str(common.ROOT / "radar" / "inbox" / "*" / "src-*.json")))[-4000:]:
        if not re.search(r"src-(jp-ir|tw-hk-ir)", f):
            continue
        try:
            it = json.loads(Path(f).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        u = it.get("url") or ""
        if MEDIA_RE.search(u) and not BLOCK_RE.search(u) and u not in seen:
            ents = it.get("entities_matched") or []
            out[u] = {"url": u, "cid": (ents[0] if isinstance(ents, list) and ents else ""), "title": it.get("title", ""), "at": it.get("saved_at", "")}
    d = common.load_state("jp_ir_docs", {})
    for cid, v in (d.get("companies") or d).items():
        u = (v or {}).get("video") or ""
        if MEDIA_RE.search(u) and not BLOCK_RE.search(u) and u not in seen:
            out.setdefault(u, {"url": u, "cid": cid, "title": f"{cid} 설명회 음성", "at": v.get("last_new") or ""})
    return sorted(out.values(), key=lambda x: x["at"], reverse=True)


def audio(url, max_min=MAX_MIN):
    """주소에서 음성 스트림만 읽어 16kHz 모노 float32"""
    import av
    import numpy as np
    c = av.open(url, options={"user_agent": "chiip-radar/0.1 (personal research)"}, timeout=60)
    st = c.streams.audio[0]
    rs = av.AudioResampler(format="s16", layout="mono", rate=16000)
    buf = []
    for fr in c.decode(st):
        for r in rs.resample(fr):
            buf.append(r.to_ndarray().reshape(-1))
        if fr.time and fr.time > max_min * 60:
            break
    c.close()
    return np.concatenate(buf).astype("float32") / 32768 if buf else None


def transcribe(url, lang=None):
    from faster_whisper import WhisperModel
    a = audio(url)
    if a is None:
        raise RuntimeError("음성 스트림 없음")
    m = WhisperModel(MODEL, device="cpu", compute_type="int8")
    segs, info = m.transcribe(a, language=lang, vad_filter=True)
    lines = [f"[{int(s.start // 60):02d}:{int(s.start % 60):02d}] {s.text.strip()}" for s in segs]
    return "\n".join(lines), info.language, len(a) / 16000


def process(c, st):
    from pollers import jp_ir_qa
    if not jp_ir_qa.allowed(c["url"]):
        st.setdefault("failed", []).append(c["url"])
        return f"robots 차단: {c['url']}"
    t = time.time()
    text, lang, sec = transcribe(c["url"], None)   # 언어 자동 — 일본 설명회는 통역(일·영)이 섞인다(2026-11-09 어드밴테스트 시험)
    uid = hashlib.sha1(c["url"].encode()).hexdigest()[:16]
    OUT.mkdir(parents=True, exist_ok=True)
    p = OUT / f"{uid}.txt"
    p.write_text(f"# {c['title']}\n# {c['url']}\n# 자체 전사(D등급, faster-whisper {MODEL}) — 오인식 가능, 인용 전 원음 확인\n\n{text}\n", encoding="utf-8")
    it = common.make_item(SRC, uid, c["url"], f"{c['title'][:80]} — 설명회 음성 자체 전사", common.iso(common.now_kst()), "IR 질의응답", lang or "ja",
                          f"자체 전사 {sec / 60:.0f}분 · 글자 {len(text)} · 로컬 {p.name}",
                          extra={"entities_matched": [c["cid"]] if c["cid"] else [], "local_text": str(p.relative_to(common.ROOT)), "chars": len(text),
                                 "source_class": "IR 질의응답", "grade": "D", "tier": "설명회 음성(자체 전사)"})
    common.save_new_items([it])
    st.setdefault("done", []).append(c["url"])
    return f"전사 {sec / 60:.0f}분 → {len(text)}자({time.time() - t:.0f}초) · {p.name}"


LOCK = common.STATE / "ir_audio.lock"


def run():
    """run_hourly 진입점 — 전사는 1시간짜리 설명회에 약 25분(실시간 0.4배, 2026-11-09 시험)이라 떨어진 프로세스로 돌리고 바로 돌아온다"""
    import subprocess
    if LOCK.exists() and time.time() - LOCK.stat().st_mtime < 3 * 3600:
        return "전사 진행 중 — 건너뜀"
    if not candidates(common.load_state(STATE, {})):
        return "대기 없음"
    subprocess.Popen([sys.executable, str(Path(__file__)), "--work"], creationflags=getattr(subprocess, "DETACHED_PROCESS", 0) | getattr(subprocess, "CREATE_NO_WINDOW", 0),
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, close_fds=True)
    return "전사 작업 시작(떨어진 프로세스)"


def work():
    LOCK.write_text(common.iso(common.now_kst()), encoding="utf-8")
    try:
        return _work()
    finally:
        try:
            LOCK.unlink()
        except OSError:
            pass


def _work():
    st = common.load_state(STATE, {})
    q = candidates(st)
    if not q:
        return "대기 없음"
    try:
        msg = process(q[0], st)
    except Exception as e:
        st.setdefault("failed", []).append(q[0]["url"])
        msg = f"실패 {type(e).__name__}: {str(e)[:120]}"
    st["done"] = (st.get("done") or [])[-500:]
    st["failed"] = (st.get("failed") or [])[-500:]
    common.save_state(STATE, st)
    return msg + f" · 남은 대기 {len(q) - 1}"


def main(argv):
    sys.stdout.reconfigure(encoding="utf-8")
    if "--queue" in argv:
        for c in candidates(common.load_state(STATE, {})):
            print(c["cid"], c["url"])
        return 0
    if "--url" in argv:
        i = argv.index("--url")
        st = common.load_state(STATE, {})
        print(process({"url": argv[i + 1], "cid": argv[i + 2] if len(argv) > i + 2 else "", "title": argv[i + 2] if len(argv) > i + 2 else "IR"}, st))
        common.save_state(STATE, st)
        return 0
    print(work() if "--work" in argv else run())
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
