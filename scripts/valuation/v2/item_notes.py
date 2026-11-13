"""알파 감지 '왜 감지됐나' 자료 한 줄 풀이 (마스터 지시 2026-11-13 — "새 자료 줄마다 아래에 한 줄 풀이(40자 안팎, 자료 본문을 읽고
작성, 못 읽으면 '본문 미확인', 알파에 영향을 줬으면 무엇이 바뀌었는지)")

수집은 결정론, 판단만 모델(CLAUDE.md):
  1. 캐시(radar/state/alpha_item_notes.json, item_id별) — 같은 자료를 두 번 묻지 않는다
  2. 본문 확보 — 레이더 카드(radar/cards/**, item_ids 일치)의 what_happened → 원문 URL 직접 받기(Google News 중계 주소는 본문이 없어 건너뜀)
  3. 본문이 없으면 모델을 부르지 않고 '본문 미확인 — 제목만 확인'
  4. 본문이 있으면 소형 모델(헤드리스 claude, run_triage.run_claude)에 요약 40자·알파 영향 여부를 JSON으로 받는다
알파 변화 사실(재산정 전후 값)은 모델이 아니라 장부(latest.json)로 붙인다.
"""
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "radar"))
from pollers import common  # noqa: E402

STATE = "alpha_item_notes"
MAX_BODY = 3500
UNREAD = "본문 미확인 — 제목만 확인"
SCHEMA = {"type": "object", "properties": {"summary": {"type": "string"}, "alpha_relevant": {"type": "boolean"},
                                            "change": {"type": "string"}}, "required": ["summary", "alpha_relevant"]}
PROMPT = """너는 반도체·AI 하드웨어 리서치 에이전트 Chiip의 판정기다. 아래 자료가 '{name}'의 알파 잠재력(상방 초과수익 여지 — 실적·가이던스·병목 노출·기대 괴리)에 영향을 주는지 판정하라.
규칙: summary는 자료가 실제로 담은 내용을 한국어 40자 안팎 한 문장으로(추측 금지, 본문에 없는 숫자 금지).
alpha_relevant는 실적·가이던스·수주·공급 관계·가격·캐파처럼 가치 입력을 바꾸는 정보가 본문에 있으면 true, 행사 공지·인사·재인용·다른 회사 자료뿐이면 false.
true면 change에 무엇이 바뀌는지 25자 안팎(예: '4Q 가이던스 상향 → 성장 가정').
제목: {title}
출처: {source}
본문 발췌:
{body}
JSON만 출력."""


def _card_text(item_id):
    base = ROOT / "radar" / "cards"
    if not base.exists() or not item_id:
        return ""
    for p in sorted(base.rglob("*.yaml"), reverse=True)[:4000]:
        try:
            t = p.read_text(encoding="utf-8")
        except OSError:
            continue
        if item_id in t:
            m = re.search(r'what_happened:\s*"?(.+?)"?\s*\n', t)
            return m[1] if m else ""
    return ""


def _fetch(url):
    if not url or "news.google.com" in url:
        return ""
    try:
        raw = common.http_get(url, timeout=15).decode("utf-8", "ignore")
    except Exception:
        return ""
    raw = re.sub(r"(?is)<(script|style|nav|header|footer)[^>]*>.*?</\1>", " ", raw)
    return re.sub(r"\s+", " ", common.strip_tags(raw))[:MAX_BODY]


def body_of(item):
    """(본문 발췌, 근거 종류) — 없으면 ('', '')"""
    card = _card_text(item.get("item_id"))
    if card:
        return card[:MAX_BODY], "레이더 카드"
    b = _fetch(item.get("url"))
    return (b, "원문") if len(b) >= 300 else ("", "")


def model_call(prompt):
    import run_triage
    if not run_triage.claude_exe():
        return None
    out = run_triage.run_claude(prompt, "haiku", SCHEMA, timeout=180)
    res = out.get("structured_output") or out.get("result")
    if isinstance(res, str):
        try:
            res = json.loads(res[res.find("{"):res.rfind("}") + 1])
        except ValueError:
            return None
    return res if isinstance(res, dict) and res.get("summary") else None


def alpha_fact(row, item_day):
    """장부상 알파 변화 — 자료일 이후 재산정이 있었으면 '알파 x→y', 없으면 ''"""
    if not row or row.get("total") is None or row.get("delta") in (None, 0, 0.0):
        return ""
    if str(row.get("scored_on", ""))[:8] < (item_day or "").replace("-", "")[:8]:
        return ""
    prev = round(row["total"] - row["delta"], 2)
    return f"알파 {prev:.1f}→{row['total']:.1f}"


def note(item, name, alpha_row=None, use_model=True, caller=None, state=None):
    """'→ …' 한 줄. caller: 테스트용 모델 대역(prompt → dict)"""
    st = state if state is not None else common.load_state(STATE, {})
    key = item.get("item_id") or item.get("url") or item.get("title")
    if key in st:
        line = st[key]
    else:
        body, kind = body_of(item)
        if not body:
            line = UNREAD
        elif not use_model:
            return f"→ {UNREAD.split(' — ')[0]}(판정 대기)"
        else:
            try:
                res = (caller or model_call)(PROMPT.format(name=name, title=item.get("title", ""), source=item.get("source_id", ""), body=body))
            except Exception as exc:
                common.record_health("src-alpha-notes", False, f"{type(exc).__name__}: {exc}"[:200])
                res = None
            if not res:
                return f"→ 판정 실패 — {UNREAD.split(' — ')[0]}"   # 캐시하지 않는다 — 다음 회차 재시도
            tail = f"알파 영향: {res.get('change') or '가치 입력 변화'}" if res.get("alpha_relevant") else "알파 변화 요인 아님"
            line = f"{res['summary'].strip().rstrip('.')} — {tail}"
        st[key] = line
        if state is None:
            common.save_state(STATE, dict(list(st.items())[-500:]))
    fact = alpha_fact(alpha_row, str(item.get("published_at") or item.get("saved_at") or "")[:10])
    return f"→ {line}" + (f" ({fact})" if fact else "")
