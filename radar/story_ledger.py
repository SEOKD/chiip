"""보낸 사건 장부 — 실시간 알림과 Pulse가 같은 소식을 따로 보내지 않게
(마스터 지시 2026-11-22 "Pulse가 중복된 정보를 여러 번 텔레그램 피드로 보내는 것 같다. 이를 바꾸도록 하라")

점검(11-19~22 발송 262통): 같은 소식이 두 갈래로 나갔다.
  ① 실시간 알림(run_poll·run_triage → radar/state/alerts.json)과 Pulse 본문이 서로 모른 채 몇 분 사이에 — 인텔 EMIB 01:01·01:14,
     MasTec 인수 06:12·06:30, 오라클 07:29·07:32, Corpay 09:00·09:08, AMD 숏 8분 사이 3통
  ② Pulse끼리 출처 주소만 다른 같은 사건을 다른 회차에 — SK하이닉스 키옥시아 전환 16:18·17:56, TrendForce NAND 12:37·19:21
  실시간 알림끼리는 promote.duplicate_of(alerts.json, 12시간)가 이미 막는다. 빈 곳은 Pulse가 이 장부에 남기지도, 보지도 않는 것.
구조:
  · Pulse가 묶음을 만들 때(pulse_feed.build_gate) 건마다 종목·머리 사건·원문 주소·원천 제목을 이 장부에 남긴다(radar/state/story_ledger.json)
  · 같은 사건 판정 — 지난 HOURS 안에 (가) 같은 원문 주소, (나) 같은 종목 + 제목 겹침(promote._words, 한글은 두 글자씩) 문턱 이상
  · Pulse 건은 이미 보낸 사건이면 뺀다. 새 사실이 있으면 모델이 "update"에 한 줄로 적고 머리에 '갱신'이 붙는다(지시문 '이미 보낸 사건은 새 사실이 있을 때만 갱신')
  · 실시간 알림은 Pulse가 이미 보낸 사건이면 보내지 않는다(promote.duplicate_of가 이 장부도 본다)
  · pulse.py는 이미 보낸 원문 주소의 원천을 모델에 넘기지 않고, 최근 보낸 사건 목록(sent_recent)을 함께 넘긴다
결정론 — 모델 없음.
"""
import json
import re
import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from pollers import common  # noqa: E402

STATE = "story_ledger"
HOURS = 12          # 같은 사건으로 보는 기간
SAME_CODE_SIM = 0.5  # 같은 종목일 때 제목 겹침 문턱(Jaccard) — 0.4는 같은 증권사 보고서의 다른 종목 줄(하나증권 PSK·SK하이닉스 0.41)을 묶었다
NEAR_MIN = 20        # 같은 종목을 다른 채널(실시간 알림 ↔ Pulse)·다른 회차가 이 분 안에 보냈으면 제목이 달라도 같은 사건
#   (11-10~22 재생: 20분 안 같은 종목 쌍 17개 중 15개가 같은 사건 — 한·영 제목이라 겹침이 0.05여도. 예외 2개는 다른 사건 기사에 같이 걸린 종목)
ANY_SIM = 0.7        # 종목 무관 문턱
KEEP = 1500


def _words(t):
    import promote
    return promote._words(t or "")


def _sim(a, b):
    a, b = _words(a), _words(b)
    return len(a & b) / len(a | b) if a and b else 0.0


def norm_url(u):
    """추적 꼬리(utm_·oc=)만 떼고 비교한다"""
    u = (u or "").strip()
    u = re.sub(r"([?&])(utm_[a-z]+|oc)=[^&#]*", r"\1", u)
    return re.sub(r"[?&]+$|[?&](?=#)", "", u).rstrip("/")


def codes_of(entity_ids):
    try:
        import notify
        tk = notify._tickers()
    except Exception:
        return set()
    return {str(tk.get(e, (None, None))[1]).upper() for e in entity_ids or [] if tk.get(e, (None, None))[1]}


def _ago(at, now, hours):
    try:
        return now - timedelta(hours=hours) <= datetime.fromisoformat(at) <= now
    except (TypeError, ValueError):
        return False


def recent(now=None, hours=HOURS):
    """지난 hours 안에 보낸 사건 — Pulse 장부 + 실시간 알림(alerts.json)을 같은 꼴로"""
    now = now or common.now_kst()
    out = [dict(e, ch="pulse") for e in common.load_state(STATE, {"rows": []}).get("rows", []) if _ago(e.get("at"), now, hours)]
    for a in common.load_state("alerts", {}).values():
        if a.get("level") in ("P0", "P1") and _ago(a.get("sent_at"), now, hours):
            out.append({"at": a.get("sent_at"), "ch": "alert", "codes": sorted(codes_of(a.get("entities"))), "entities": a.get("entities") or [],
                        "text": (a.get("title") or "").rsplit(" - ", 1)[0], "titles": [(a.get("title") or "").rsplit(" - ", 1)[0]],
                        "urls": [norm_url(a.get("url"))] if a.get("url") else [], "feed": None})
    return out


def match(codes, texts, urls, now=None, hours=HOURS, skip_feed=None, only=None):
    """같은 사건이면 그 장부 줄, 아니면 None. texts = 이 건의 제목·머리 사건들(한·영 섞여도 된다)"""
    codes = {str(c).upper() for c in codes or [] if c}
    urls = {norm_url(u) for u in urls or [] if u}
    texts = [t for t in texts or [] if t]
    for e in recent(now, hours):
        if skip_feed and e.get("feed") == skip_feed:   # 같은 묶음을 다시 만들 때(링크 고친 뒤 재실행) 자기 자신과 겹치지 않게
            continue
        if only and e["ch"] != only:
            continue
        if urls & set(e.get("urls") or []):
            return dict(e, why="같은 원문")
        try:
            near = (now or common.now_kst()) - datetime.fromisoformat(e.get("at")) <= timedelta(minutes=NEAR_MIN)
        except (TypeError, ValueError):
            near = False
        if near and codes & set(e.get("codes") or []):
            return dict(e, why=f"같은 종목 {NEAR_MIN}분 안")
        theirs = [e.get("text")] + list(e.get("titles") or [])
        best = max((_sim(a, b) for a in texts for b in theirs if b), default=0.0)
        if best >= ANY_SIM or (codes & set(e.get("codes") or []) and best >= SAME_CODE_SIM):
            return dict(e, why=f"같은 사건(제목 겹침 {best:.2f})")
    return None


def record(rows, now=None):
    now = now or common.now_kst()
    st = common.load_state(STATE, {"rows": []})
    st["rows"] = [r for r in st.get("rows", []) if _ago(r.get("at"), now, 72)] + [dict(r, at=r.get("at") or common.iso(now)) for r in rows]
    st["rows"] = st["rows"][-KEEP:]
    common.save_state(STATE, st)


def forget_feed(feed):
    """같은 묶음을 다시 만들 때 앞서 남긴 줄을 지운다(재실행해도 한 번만 남게)"""
    st = common.load_state(STATE, {"rows": []})
    st["rows"] = [r for r in st.get("rows", []) if r.get("feed") != feed]
    common.save_state(STATE, st)


def brief_list(now=None, hours=24, n=40):
    """모델에 넘길 최근 보낸 사건 — 'HH:MM 채널 종목 머리' 줄"""
    rows = sorted(recent(now, hours), key=lambda e: e.get("at") or "", reverse=True)[:n]
    return [f"{(e.get('at') or '')[11:16]} {'Pulse' if e['ch'] == 'pulse' else '실시간'} {'·'.join(e.get('codes') or []) or '-'} {str(e.get('text') or '')[:70]}" for e in rows]
