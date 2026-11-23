"""Pulse 텔레그램 양식 (마스터 지시 2026-11-02 "텔레그램 봇으로 피드 제공할 때 Report는 가독성 있게 글을 구성했는데 Pulse는 여전히 가독성이 낮다")

Report 피드처럼 엔진이 조립한다. 모델은 내용만 JSON으로 쓴다. 읽는 순서: 머리줄 → 기업 → ■ 결론 → ■ 근거 → ■ 반대 → ■ 다음 확인 → 출처 → ■ 정량(인사이트·컨빅션, 2026-11-03).
입력(outputs/article/sources/<YYYYMMDD_HHMM>_feed.json):
  {"time": "16:24", "items": [{"icon": "⚡", "name": "Alphabet", "code": "GOOGL", "event": "사건 한 줄", "biz": "사업 1줄",
     "view": "판단 한 문장", "insight": 7, "conviction": 8, "basis": "1차 서류", "why": ["근거 줄"], "against": "다른 해석 → 가를 자료",
     "next": "다음 확인", "links": [["8-K 원문", "https://..."]], "read": "https://… 모델이 실제로 열어 읽은 원문 주소"}],
   "brief": [{"name": "삼성전자", "code": "005930", "line": "결론 한 마디", "link": ["보도", "https://..."]}],
   "empty": ["미보도 원문"], "zacks": false}
  본문 확인 관문(2026-11-14 마스터 지시 "본문을 반드시 확인하는 구조"): items·brief마다 "read"에 실제로 열어 읽은 원문 주소를 쓴다
  (fulltext.url 또는 모델이 WebFetch로 연 사본). 없거나 news.google.com 중계 주소면 _tg.txt를 만들지 않고 멈춘다(종료 코드 2).
  예외(2026-11-14 마스터 개정): 본문을 못 읽었어도 헤드라인만으로 알파 요소 점수가 0.5 이상 움직이는 건은 "headline_alpha": "요소 ±값 — 이유"를
  쓰면 통과한다. 이때 근거 첫 줄에 '본문 미확인 · 헤드라인 기준'을 밝힌다.
사용: py radar/pulse_feed.py <json>   → 같은 이름 _tg.txt(끝의 _feed를 뗀다)를 쓰고 양식 점검 결과를 출력
  중복 관문(2026-11-22 마스터 지시 "Pulse가 중복된 정보를 여러 번 텔레그램 피드로 보내는 것 같다"): 이미 보낸 사건(실시간 알림·이전 Pulse,
  radar/story_ledger.py)은 빼고 '[중복 — 뺌]'으로 출력한다. 갱신으로도 다시 보내지 않는다(2026-11-24 마스터 지시 "Pulse로 중복된 소식을 전달하지 마라.
  소식은 오리지널 소스만 가져오도록 하라") — 재인용·사본 링크는 빼고, 원출처 링크가 하나도 없으면 그 건을 뺀다(radar/source_origin.py).
  전부 빠지면 _tg.txt를 만들지 않고 종료 코드 3(보내지 않는다).
잠금 평가기 pulse_check.py가 그대로 재도록 판단은 **굵게**, 근거·반대·다음 확인은 · 줄로 쓴다.
"""
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import pulse_check  # noqa: E402

CIRCLED = "①②③④⑤⑥⑦⑧⑨⑩"
RULE = "─────────"
FOOT = "1차 판정, 미검증 · 공개 자료 기반 분석이며 투자 권유가 아님"
ZACKS = "Data provided by Zacks Investment Research, Inc., www.zacksdata.com"
MAX_WHY = 3
MAX_BASIS = 20


def links(rows):
    return " · ".join(f"[{a}]({b})" for a, b in rows or []) or "출처 미확인"


# 머리 이모지는 회사 업종으로 정한다(2026-11-20 마스터 지시 "이모찌도 회사에 어울리는 이모찌를 써라. ⚡를 쓰면 삼성전자가 전력망 기업으로 보이잖니").
# 감시 목록(config/valuation.yaml·earnings_watch.yaml)의 sub → 이모지. 목록에 없거나 업종을 모르면 모델이 쓴 icon(없으면 📌)
SUB_EMOJI = (("memory|storage", "💾"), ("conglomerate", "🏢"), ("accelerator|edge_ai|edge_compute", "🧠"),
             ("semicap|equipment|materials|substrate|foundry|semis|semi_ip|eda_ip|analog|power_semi|fpga|timing|rf|mcu|auto_semi|test_measurement", "🔬"),
             ("networking|optical|fiber|telecom|comms|iot", "🌐"), ("nuclear", "☢️"), ("battery", "🔋"),
             ("power_infra|utility|dc_power|power_epc|power_services|geothermal|energy_storage", "⚡"),
             ("defense|drones", "🛡️"), ("space", "🛰️"), ("aerospace", "✈️"), ("software|hyperscaler|neocloud", "☁️"),
             ("server|ems", "🖥️"), ("cooling", "❄️"), ("robotics", "🤖"), ("components|instruments|sensing|lasers|optics|precision", "🔩"),
             ("payments|legal_finance", "💳"), ("offshore_drilling", "🛢️"), ("media|gaming", "🎬"), ("fitness", "🏋️"), ("cro", "💊"),
             ("consumer|beauty", "🛍️"), ("education", "🎓"), ("engineering|industrial|workforce|construction", "🏗️"), ("pc_peripherals", "⌨️"))
_SUBS = None


def _subs():
    global _SUBS
    if _SUBS is None:
        import yaml
        _SUBS = {}
        root = Path(__file__).resolve().parents[1]
        for f in ("config/valuation.yaml", "config/earnings_watch.yaml"):
            try:
                d = yaml.safe_load((root / f).read_text(encoding="utf-8")) or {}
            except OSError:
                continue
            for v in d.values():
                for u in v if isinstance(v, list) else []:
                    if isinstance(u, dict) and u.get("code") and u.get("sub"):
                        _SUBS.setdefault(str(u["code"]).split(".")[0].upper(), u["sub"])
    return _SUBS


ICON_OVERRIDE = {"005930": "💾"}   # 삼성전자 — 감시 목록 sub는 conglomerate지만 Chiip이 보는 축은 메모리·반도체


def icon_for(x):
    code = str(x.get("code") or "").split(".")[0].upper()
    if code in ICON_OVERRIDE:
        return ICON_OVERRIDE[code]
    sub = _subs().get(str(x.get("code") or "").split(".")[0].upper())
    for pat, emo in SUB_EMOJI:
        if sub and re.search(pat, sub):
            return emo
    return x.get("icon") or "📌"


def block(n, x):
    icon = icon_for(x)   # 번호(①②…)는 쓰지 않는다(2026-11-20 마스터 지시)
    head = f"**{icon} {x['name']} {x['code']}｜{x['event']}**" if x.get("code") else f"**{icon} {x['name']}｜{x['event']}**"
    parts = [f"{head}\n기업: {x['biz']}", f"**■ 결론**\n**{x['view']}**", "**■ 근거**\n" + "\n".join(f"· {w}" for w in (x.get("why") or [])[:MAX_WHY])]
    if x.get("against"):
        parts.append(f"**■ 반대**\n· {x['against']}")
    if x.get("next"):
        parts.append(f"**■ 다음 확인**\n· {x['next']}")
    parts.append(links(x.get("links")))
    # ■ 정량(인사이트 점수·근거 종류) 문단은 내보내지 않는다(2026-11-20 마스터 지시 "마지막 문단(■ 정량)은 빼라. 앞으로도 그렇게 하라") — 점수는 정렬·기록에만
    return "\n\n".join(parts)


def brief_line(b):
    who = f"{b['name']} {b['code']}" if b.get("code") else b["name"]   # 티커에 괄호를 쓰지 않는다(2026-11-03)
    tail = f" [{b['link'][0]}]({b['link'][1]})" if b.get("link") else ""
    return f"· {who} — {b['line']}{tail}"


def build(d):
    rows = sorted(d.get("items") or [], key=lambda x: -x["insight"])
    out = [f"[Chiip Pulse {d['time']}]"]
    for n, x in enumerate(rows):
        out.append(block(n, x))
        if n < len(rows) - 1:
            out.append(RULE)
    if d.get("brief"):
        out += ([RULE] if rows else []) + ["**■ 간단히**\n" + "\n".join(brief_line(b) for b in d["brief"])]
    # '그 외 새 건 없음' 줄과 FOOT(1차 판정·투자 권유 아님)는 Pulse에서 뺀다 — 가독성(마스터 지시 2026-11-13). 다른 채널의 면책은 그대로
    if d.get("zacks"):
        out.append(ZACKS)
    return "\n\n".join(out)


def brief_marks(text):
    """'■ 간단히' 아래 해설 단락마다 머리에 '■ '를 붙인다 — 기업·보도·판단·반증·원문 단락 구분(마스터 지시 2026-11-18 "양식을 바꿔라").
    '· 종목' 줄·이미 ■인 줄·구분선은 그대로. '그 외 새 건 없음' 줄은 뺀다(2026-11-13 지시, 마스터 예시에도 없다)."""
    out, on = [], False
    for line in text.split("\n"):
        t = line.strip()
        if re.fullmatch(r"\**■\s*간단히\**", t):
            on = True
            out.append(line)
            continue
        if t.startswith("─") or re.match(r"\**■\s*(결론|근거|반대|다음 확인|정량)", t):
            on = False
        if on:
            if t.startswith("그 외 새 건 없음"):
                continue
            if t and not t.startswith(("·", "-", "■", "**■", "1차 판정", "Data provided", "공개 자료 기반")):
                line = "■ " + t
            elif re.match(r"■(?=\S)", t):
                line = "■ " + t[1:]
            prev = out[-1].strip() if out else ""
            if line.startswith(("■", "**■")) and prev:   # 단락마다 빈 줄
                out.append("")
            elif t.startswith("·") and prev and not prev.startswith("·") and not re.fullmatch(r"\**■\s*간단히\**", prev):
                out.append("")   # 다음 종목 앞 빈 줄
        out.append(line)
    return re.sub(r"\n{3,}", "\n\n", "\n".join(out))


def unread(d):
    """본문을 읽었다는 주소(read)가 없는 건 — 이름 목록"""
    bad = []
    for x in (d.get("items") or []) + (d.get("brief") or []):
        r = str(x.get("read") or "")
        if (not r.startswith("http") or "news.google.com" in r) and not x.get("headline_alpha"):
            bad.append(f"{x.get('name')} {x.get('code') or ''}".strip())
    return bad


DEEP_KEEP = 7   # (쓰지 않음 — 2026-11-24 마스터 지시로 실시간 알림이 보낸 사건은 심층 판단으로도 다시 보내지 않는다)


def _codes(code):
    return [c for c in re.split(r"[·,/\s]+", str(code or "")) if c]


def _urls(x):
    out = [x.get("read")] + [l[1] for l in x.get("links") or [] if len(l) > 1]
    if x.get("link") and len(x["link"]) > 1:
        out.append(x["link"][1])
    return [u for u in out if u and str(u).startswith("http")]


def _source_titles(src):
    """같은 회차 펄스 파일(radar/pulse/<YYYYMMDD_HHMM>.json)의 원천 — 주소 → (제목, 종목 id)"""
    stamp = src.stem.removesuffix("_feed").removesuffix("_tg")
    f = Path(__file__).resolve().parent / "pulse" / f"{stamp}.json"
    try:
        d = json.loads(f.read_text(encoding="utf-8"))
    except Exception:
        return {}
    import story_ledger
    return {story_ledger.norm_url(s.get("url")): (s.get("title") or "", s.get("entities_matched") or []) for s in d.get("sources") or [] if s.get("url")}


def original_only(x, kind):
    """출처 링크에서 재인용·요약·사본 매체를 뺀다(2026-11-24 마스터 지시 "소식은 오리지널 소스만", radar/source_origin.py).
    남는 링크가 없으면 (None, 뺀 매체). 'read'(본문 확인 주소)는 증빙이라 그대로 둔다 → (건, 뺀 매체)"""
    import source_origin as origin
    if kind == "brief":
        l = x.get("link") or []
        if len(l) > 1 and origin.is_relay(l[1]):
            return None, [origin.host(l[1])]
        return x, []
    rows = [l for l in x.get("links") or [] if len(l) > 1]
    keep = [l for l in rows if not origin.is_relay(l[1]) and not re.search(r"사본|copy|mirror", str(l[0]), re.I)]
    cut = [origin.host(l[1]) for l in rows if l not in keep]
    if rows and not keep:
        return None, cut
    return (dict(x, links=keep) if cut else x), cut


def dedupe(d, src, now=None):
    """이미 보낸 사건(실시간 알림·이전 Pulse, radar/story_ledger.py) 건을 뺀다(마스터 지시 2026-11-22 "Pulse가 중복된 정보를 여러 번 … 바꾸도록 하라").
    갱신·심층 판단으로도 다시 보내지 않는다(2026-11-24). → (새 d, 뺀 건 [(이름, 사유)], 장부에 남길 줄)"""
    import story_ledger
    feed = src.stem.removesuffix("_feed")
    titles = _source_titles(src)
    keep, drop, rows = {"items": [], "brief": []}, [], []
    for kind in ("items", "brief"):
        for x in d.get(kind) or []:
            urls = _urls(x)
            src_t = [titles[story_ledger.norm_url(u)] for u in urls if story_ledger.norm_url(u) in titles]
            codes = set(_codes(x.get("code")))
            if not codes:   # 건에 종목이 없을 때만 원천 종목으로 — 한 보고서가 여러 종목을 다루면 다른 종목 줄끼리 묶였다(하나증권 PSK·SK하이닉스)
                for _, ents in src_t:
                    codes |= story_ledger.codes_of(ents)
            head = x.get("event") or x.get("line") or ""
            texts = [head] + [t for t, _ in src_t]
            name = f"{x.get('name')} {x.get('code') or ''}".strip()
            m = story_ledger.match(codes, texts, urls, now, skip_feed=feed)
            if m:   # 같은 사건은 한 번만 — 갱신·심층 판단으로도 다시 보내지 않는다(2026-11-24 마스터 지시 "Pulse로 중복된 소식을 전달하지 마라")
                drop.append((name, f"{m['why']} — {(m.get('at') or '')[11:16]} {'Pulse' if m['ch'] == 'pulse' else '실시간 알림'} '{str(m.get('text') or '')[:40]}'"))
                continue
            x, cut = original_only(x, kind)
            if x is None:
                drop.append((name, f"오리지널 소스 없음 — 재인용·사본 링크만({', '.join(cut)})"))
                continue
            keep[kind].append(x)
            rows.append({"codes": sorted(codes), "text": head, "titles": [t for t, _ in src_t][:3], "urls": [story_ledger.norm_url(u) for u in urls],
                         "entities": sorted({e for _, ents in src_t for e in ents}), "feed": feed})
    return dict(d, **keep), drop, rows


def main(argv):
    sys.stdout.reconfigure(encoding="utf-8")
    src = Path(argv[0])
    d = json.loads(src.read_text(encoding="utf-8"))
    bad = unread(d)
    if bad:
        print("본문 미확인 — 보내지 않는다(마스터 지시 2026-11-14): " + " · ".join(bad)
              + " → 원문(fulltext.url 또는 WebSearch로 찾은 사본)을 열어 읽고 'read'에 그 주소를 쓴다. 못 읽으면 그 건을 빼고 py radar/fulltext.py --hold <item_id>")
        return 2
    import story_ledger
    story_ledger.forget_feed(src.stem.removesuffix("_feed"))   # 같은 묶음 재실행 — 앞서 남긴 줄은 지우고 다시 잰다
    d, dropped, rows = dedupe(d, src)
    for name, why in dropped:
        print(f"[중복·재인용 — 뺌] {name}: {why}")
    out = src.with_name(src.stem.removesuffix("_feed") + "_tg.txt")
    if not (d.get("items") or d.get("brief")):
        print("모두 이미 보낸 사건 — 묶음을 만들지 않는다(텔레그램 보내지 않음)")
        return 3
    text = build(d)
    out.write_text(text, encoding="utf-8")
    story_ledger.record(rows)
    print(out)
    rows = pulse_check.check(text)
    for name, head, detail in rows:
        print(f"{name}: {head[:40]} — {detail[:50]}")
    return 1 if any(r[0] == "link" for r in rows) else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
