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
KIND = {"event": "사건 때 심층", "monthly": "월간 트래커", "quarterly": "분기 결산"}
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


def ratings_lines(ratings):
    order, groups = [], {}
    for r in ratings or []:
        if r["rating"] not in groups:
            order.append(r["rating"])
        groups.setdefault(r["rating"], []).append(r["name"])
    return [f"{ICON.get(k, '•')} **{k}** — {', '.join(groups[k])}" for k in order]


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


def build(d, artifact=None, notion=None):
    kind = KIND.get(d.get("cycle") or ("event" if d.get("kind") == "industry_event" else ""), "산업 리포트")
    date = str(d.get("date") or "")
    L = [f"[Chiip Industry Report · {kind} · {date[5:].replace('-', '/')}]", "", f"**{d['title']}**"]
    if d.get("event"):
        L.append(f"사건: {first_sentence(d['event'], 90)}")
    L += ["", "**산업 판단**(규칙 계산)"] + ratings_lines(d.get("ratings"))
    qa = d.get("summary") or []
    if qa:
        L += ["", "**핵심**"]
        for i, x in enumerate(qa[:5], 1):
            L.append(f"{'①②③④⑤'[i - 1]} {x['q'].rstrip('?')} → {first_sentence(x['a'])}")
    tiles = d.get("tiles") or []
    if tiles:
        L += ["", "**숫자**"] + [f"• {t['v']} — {t['k']}" + (f"({t['sub'].split('(')[0].strip()})" if t.get("sub") and len(t["sub"].split("(")[0]) <= 24 else "") for t in tiles[:4]]
    cps = checkpoints(d)
    if cps:
        L += ["", "**다음 확인**(날짜 · 무엇 · Chiip 확률)"] + cps
    links = [f"[리포트]({artifact})" if artifact else "", f"[노션]({notion})" if notion else ""]
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
