"""Industry Report 텔레그램 피드 조립 (마스터 지시 2026-11-08 "산업 리포트를 텔레그램 피드로 제공할 때 글이 가독성 있게 정리되도록 다듬어라")

손으로 쓰던 알림을 리포트 JSON(outputs/industry/<날짜>_<id>.json)에서 결정론으로 만든다. 휴대폰에서 30초 안에 읽히게:
  머리(종류·날짜) → 제목(굵게) → 산업 판단(등급별 묶음) → 핵심 4줄(시장·돈·실행·나머지, 각 한 문장) → 숫자 3~4개 → 다음 확인(날짜·무엇·확률) → 링크 → 안내문.
문단 사이는 빈 줄, 한 줄은 MAX_LINE자 안. notify.send(md=True)가 **굵게**·[이름](주소)를 텔레그램 서식으로 바꾼다.
사용: py scripts/industry/tg_feed.py <리포트 json> --artifact <url> [--notion <url>] [--send]
"""
import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MAX_LINE = 120
DISCLAIMER = "공개 자료 기반 분석이며 투자 권유가 아님"
KIND = {"event": "사건 때 심층", "weekly": "주간 산업", "quarterly": "분기 결산"}   # 월간 트래커 → 주간 산업(2026-11-08 마스터 지시)
ICON = {"Attractive": "🟢", "In-Line": "⚪", "Cautious": "🔴"}


def first_sentence(text, limit=MAX_LINE - 30, min_len=28):
    """앞 문장(…다./…요.) — '그렇다.'처럼 짧으면 다음 문장까지 잇는다. 괄호 풀이는 빼고, 길면 절 경계(, · 고 · 며)에서 끊는다"""
    t = re.sub(r"\s+", " ", re.sub(r"\([^()]*\)", "", str(text or ""))).strip()
    parts = [x.strip() for x in re.findall(r".+?[다요음]['’\"]?\.(?=\s|$)|.+$", t)]
    s = ""
    for x in parts:
        s = (s + " " + x).strip()
        if len(s) >= min_len:
            break
    if len(s) <= limit:
        return s
    cut = max(s.rfind(", ", 0, limit), s.rfind("고 ", 0, limit), s.rfind("며 ", 0, limit))
    return (s[:cut + (1 if s[cut] != "," else 0)].rstrip(" ,") if cut > limit // 2 else s[:limit - 1].rstrip(" ,·")) + "…"


def short_what(text, limit=70):
    """체크포인트 문장 — 괄호 풀이를 빼고 짧게"""
    t = re.sub(r"\([^)]*\)", "", str(text or "")).strip()
    t = re.sub(r"\s+", " ", t)
    return t if len(t) <= limit else t[:limit - 1].rstrip(" ,·") + "…"


def _plain(name):
    """판단 대상 이름 — 괄호 풀이(다음 분기·가이던스 등)는 리포트에 두고 피드에서는 뺀다(2026-11-25 마스터 지시 '간결하게')"""
    return re.sub(r"\s*\([^()]*\)", "", str(name)).strip() or str(name)


def ratings_lines(ratings):
    order, groups = [], {}
    for r in ratings or []:
        if r["rating"] not in groups:
            order.append(r["rating"])
        groups.setdefault(r["rating"], []).append(_plain(r["name"]))
    return [f"{ICON.get(k, '•')} **{k}** — {', '.join(groups[k])}" for k in order]


def number_lines(tiles, n=3):
    """같은 지표의 기간 변형(예: 매출(전분기)·매출(전년))은 한 줄로 묶는다 — '매출 +15.9% 전분기 · +35.8% 전년 ($6.6B)'"""
    order, groups, subs = [], {}, {}
    for t in tiles or []:
        k = str(t.get("k") or "")
        m = re.match(r"^(.*?)\(([^()]*)\)$", k)
        base, period = (m.group(1), m.group(2)) if m else (k, "")
        base = re.sub(r"\s*\([^()]*\)", "", base).strip()
        if base not in groups:
            order.append(base)
        groups.setdefault(base, []).append(f"{t['v']} {period}".strip())
        sub = str(t.get("sub") or "").split("(")[0].split(" · ")[0].strip()
        if sub and base not in subs and len(sub) <= 24 and "근거" not in sub and "기준" not in sub:   # '2사 기준'·'근거 100%' 같은 메모는 뺀다
            subs[base] = sub
    return [f"• {b} {' · '.join(groups[b])}" + (f" ({subs[b]})" if b in subs else "") for b in order[:n]]


def checkpoints(d, n=4):
    rows = []
    for s in d.get("sections") or []:
        if s.get("h2", "").startswith("⑧"):
            for b in s.get("blocks") or []:
                if b.get("type") == "table" and "기한" in (b.get("headers") or []):
                    h = b["headers"]
                    for r in b["rows"]:
                        rows.append({k: r[h.index(k)] for k in ("기한", "무엇", "확률") if k in h})
    rows.sort(key=lambda r: r["기한"])
    return [f"• {r['기한'][5:].replace('-', '/')} {short_what(r['무엇'])} — {r.get('확률', '')}".rstrip(" —") for r in rows[:n]]


def brief_answer(text, limit=80):
    """답 첫 문장 하나. '투자다.'처럼 너무 짧으면 다음 문장의 첫 절(쉼표·'고' 앞)까지만 붙인다 — 말줄임표 없이"""
    one = first_sentence(text, limit, min_len=0)
    if len(one) >= 14:
        return one
    rest = re.sub(r"\s+", " ", re.sub(r"\([^()]*\)", "", str(text))).strip()[len(one):].strip()
    m = re.match(r"(.+?)(?:, |고 |며 |\.)", rest)
    nxt = (m.group(1) if m else rest)[: limit - len(one)].rstrip(" ,")
    return f"{one} {nxt}".strip() if nxt else one


def split_title(title):
    """'주제 — 결론' 제목은 굵은 주제 한 줄 + 결론 한 줄로 나눈다"""
    t = str(title or "")
    return (t.split(" — ", 1) + [""])[:2] if " — " in t else (t, "")


MEANING = {"Attractive": "유리", "In-Line": "중립", "Cautious": "신중"}


def takeaways(take):
    """결론 한 줄을 문장 단위 📌 줄로 — 두 문장이면 두 줄"""
    parts = [x.strip() for x in re.split(r"(?<=\.)\s+", str(take or "")) if x.strip()]
    return [f"📌 {x if x.endswith('.') else x + '.'}" for x in parts[:3]]


def build(d, artifact=None, notion=None):
    """직관 양식(2026-11-25 마스터 지시 '배치·구성·표기를 더 직관적으로'):
    머리 → 주제(굵게) → 📌 결론 문장들 → 📊 숫자 → 판단(등급 뜻 병기) → 왜(질문 ▸ / 답 ↳, 최대 5) → ⏭ 다음 확인 → 링크"""
    kind = KIND.get(d.get("cycle") or ("event" if d.get("kind") == "industry_event" else ""), "산업 리포트")
    date = str(d.get("date") or "")
    head, take = split_title(d["title"])
    L = [f"[Chiip Industry · {kind} · {date[5:].replace('-', '/')}]", "", f"**{head}**"]
    if d.get("event") and kind == KIND["event"]:   # 분기·주간은 머리에 이미 종류가 있어 '사건' 줄을 뺀다
        L.append(f"사건: {first_sentence(d['event'], 90)}")
    if take:
        L += [""] + takeaways(take)
    nums = number_lines(d.get("tiles"))
    if nums:
        L += [""] + [f"📊 {x[2:]}" for x in nums]
    rl = ratings_lines(d.get("ratings"))
    if rl:
        L += ["", "**판단**(규칙 계산)"] + [re.sub(r"\*\*(\S+?)\*\*", lambda m: f"**{m.group(1)}**({MEANING.get(m.group(1), '')})" if m.group(1) in MEANING else m.group(0), x, 1) for x in rl]
    qa = d.get("summary") or []
    if qa:
        L += ["", "**왜**"]
        for x in qa[:5]:
            L += [f"▸ {x['q'].rstrip('?？ ')}?", f"   ↳ {brief_answer(x['a'])}"]
    cps = checkpoints(d, 3)
    if cps:
        L += ["", "**⏭ 다음 확인**"] + cps
    links = [f"[📄 리포트]({artifact})" if artifact else "", f"[노션]({notion})" if notion else ""]
    if any(links):
        L += ["", " · ".join(x for x in links if x)]
    L += ["", DISCLAIMER]
    return "\n".join(L)


def check(text):
    """양식 점검 — 긴 줄·빈 문단 연속 (문구 목록, 없으면 [])"""
    bad = [f"{len(x)}자: {x[:30]}…" for x in text.split("\n") if len(re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", x)) > MAX_LINE + 10]
    if "\n\n\n" in text:
        bad.append("빈 줄 연속")
    return bad


def main(argv):
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("json")
    ap.add_argument("--artifact")
    ap.add_argument("--notion")
    ap.add_argument("--send", action="store_true")
    a = ap.parse_args(argv)
    d = json.loads(Path(a.json).read_text(encoding="utf-8"))
    text = build(d, a.artifact, a.notion)
    out = Path(a.json).with_name(Path(a.json).stem + "_tg.txt")
    out.write_text(text, encoding="utf-8")
    print(text)
    bad = check(text)
    if bad:
        print("[양식] " + " / ".join(bad))
        return 1
    if a.send:
        sys.path.insert(0, str(ROOT / "radar"))
        import notify
        notify.send(text, "REPORT", md=True)
        print("[발송]")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
