"""Portfolio Daily 서술형 양식 검사 (마스터 지시 2026-11-13 "항목·숫자 나열이 아니라 직관적인 문장으로 서술하고 글을 구성하라")

문장은 모델이 쓰고, 숫자는 스크립트 값만 쓴다 — 이 검사가 발송 전 관문이다. 양식 knowledge/methods/portfolio_daily_format.md.
  1. 숫자 출처   본문 숫자(%, bp, $, 배, 점 등)가 그날 스크립트 출력 숫자 묶음(아래 FILES + radar/portfolio/<날짜>_*.json)이나
                모델이 1차 출처에서 읽어 radar/state/daily_facts_extra.json에 출처와 함께 적은 숫자와 맞아야 한다(표시 자릿수 반올림 허용)
  2. 구성        머리줄 → 첫 문단 요약(3문장·숫자 6개 이하) → ■ 시장 → ■ 섹터 → (월요일 섹터 배분) → ■ 내 종목 → (Buy Call·와치리스트 변경·종합 9.5) →
                ■ 앞으로 챙길 것 → ■ 모델이 보는 위험 → (월요일 모델 포트폴리오 성적) → ■ 확인 못 한 것 → 면책 줄
  3. 문체        '판단:'·'무엇:'·'기대 대비:'·'의미:' 같은 머릿말 금지, ' · '로 숫자 이어 붙이기 금지, 문장당 숫자 2개 이하,
                전문용어(HRP·승수·오버레이·듀레이션·β·NAV 등) 금지, RPO·디레이팅·오버행·워런트는 처음 나올 때 괄호 풀이
  4. 내 종목     종목마다 한 문단(중복 금지·'간단히' 절 금지), 등락 큰 순(extra moves), 처음 나올 때 '티커(회사 이름…)',
                목표가·의견은 coverage.csv에서 바뀐 종목만, '보유 N개' 같은 개수는 config/portfolio.yaml과 일치
  5. 모아 쓰기   '원문 미확인'은 '확인 못 한 것' 절에만
사용: py scripts/portfolio/daily_check.py <초안.txt> [--date YYYY-MM-DD] [--extra 파일]   → 오류가 있으면 종료 코드 1
      py scripts/portfolio/daily_check.py --risk            # '모델이 보는 위험' 절 문장(스크립트 값)
      py scripts/portfolio/daily_check.py --pool [--date …]  # 숫자 묶음 크기·원천
"""
import csv
import json
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
M = ROOT / "knowledge" / "models"
KST = timezone(timedelta(hours=9))
EXTRA = ROOT / "radar" / "state" / "daily_facts_extra.json"
COVERAGE = M / "portfolio" / "coverage.csv"
FILES = [M / "portfolio" / "market_latest.json", M / "portfolio" / "sector_select_latest.json", M / "portfolio" / "sector_latest.json",
         M / "portfolio" / "buy_call_latest.json", M / "portfolio" / "composite_latest.json", M / "pm" / "latest.json",
         M / "pm" / "construct.json", M / "pm" / "book.json", M / "portfolio" / "overhang.csv"]
DISCLAIMER = "1차 판정, 미검증 · 공개 자료 기반 분석이며 투자 권유가 아님"
SECTIONS = ["시장", "섹터", "내 종목", "앞으로 챙길 것", "모델이 보는 위험", "확인 못 한 것"]
OPTIONAL = {"Buy Call": ("내 종목", "앞으로 챙길 것"), "와치리스트 변경": ("내 종목", "앞으로 챙길 것"), "관심 종목 변동": ("내 종목", "앞으로 챙길 것"), "종합 9.5 연구 명단": ("내 종목", "앞으로 챙길 것"),
            "섹터 배분": ("섹터", "내 종목"), "모델 포트폴리오 성적": ("모델이 보는 위험", "확인 못 한 것")}   # 있을 때만 — (뒤, 앞) 자리
LABELS = re.compile(r"^\s*[-·•]?\s*(판단|무엇|기대 대비|의미|다음 확인|원문|매크로|마이크로|근거|다른 해석|컨빅션|시너지)\s*:")
JARGON = ["HRP", "승수", "오버레이", "듀레이션", "β", "베타", "NAV", "DSR", "브린슨", "켈리", "샤프"]
EXPLAIN = ["RPO", "디레이팅", "오버행", "워런트"]
APPROX = re.compile(r"^\s*(가까이|남짓|넘게|안팎|정도|수준|쯤)")
# 숫자가 아닌 이름·서식(검사·개수에서 뺀다)
NAMES = re.compile(r"S&P\s?500|나스닥\s?100|러셀\s?2000|\d+년물|10-Q|10-K|8-K|13[DFG]|Form\s?\d+|424B\d|S-[13]|Rule\s?\d+|10b5-1|Q[1-4]|[1-4]Q|"
                   r"\d분기|\d차|20\d\d년|\b20\d\d\b|\d{1,2}/\d{1,2}(?:\([월화수목금토일]\))?|\d{1,2}:\d{2}|\b\d{6}\b|"
                   r"\d+\s?(?:거래일|개월|주일?|일|년)(?!\s?치)(?=\s?(?:동안|사이|만에|간|전|뒤|후|안|평균|상대|선|연속|째|$|[ ,.·]))|\d+위")
NUM = re.compile(r"(?P<sign>[−\-+])?(?P<cur>\$)?(?P<num>\d[\d,]*(?:\.\d+)?)(?P<rng>\s?[~∼–]\s?\$?\d[\d,]*(?:\.\d+)?)?\s?(?P<unit>%p|%|bp|배|점|[BMKT](?![a-zA-Z])|억|조|만)?")
COUNT = re.compile(r"\d+\s?(?:개|곳|건|종목|회|명|가지)")


def _j(p):
    try:
        return json.loads(Path(p).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def followed():
    """Daily가 다루는 내 종목 — config/portfolio.yaml status 보유·관심(종료 제외)"""
    try:
        hs = yaml.safe_load((ROOT / "config" / "portfolio.yaml").read_text(encoding="utf-8")).get("holdings") or []
    except (OSError, ValueError, AttributeError):
        hs = []
    return [str(h["ticker"]) for h in hs if h.get("status") in ("보유", "관심") and h.get("ticker")]


def _leaves(x, out):
    if isinstance(x, bool) or x is None:
        return
    if isinstance(x, (int, float)):
        out.append(float(x))
    elif isinstance(x, str):
        s = x.strip().replace(",", "")
        if re.fullmatch(r"[−\-+]?\d+(?:\.\d+)?", s):
            out.append(float(s.replace("−", "-")))
        else:
            for m in re.finditer(r"\d+(?:\.\d+)?", s):     # 문장 속 숫자(메모·근거 줄)도 스크립트가 낸 값이다
                out.append(float(m.group()))
    elif isinstance(x, dict):
        for v in x.values():
            _leaves(v, out)
    elif isinstance(x, list):
        for v in x:
            _leaves(v, out)


def pool(day=None, extra=EXTRA):
    """{원천: [숫자]} — 그날 스크립트 출력 + 모델이 출처와 함께 적은 숫자"""
    day = day or datetime.now(KST).date().isoformat()
    src = {}
    for f in FILES:
        vals = []
        if f.suffix == ".csv" and f.exists():
            with f.open(encoding="utf-8", newline="") as fh:
                _leaves([list(r.values()) for r in csv.DictReader(fh)], vals)
        else:
            _leaves(_j(f), vals)
        if vals:
            src[f.name] = vals
    for f in sorted((ROOT / "radar" / "portfolio").glob(day.replace("-", "") + "_*.json")):
        vals = []
        _leaves(_j(f), vals)
        src[f.name] = vals
    if COVERAGE.exists():
        vals = []
        with COVERAGE.open(encoding="utf-8", newline="") as fh:
            _leaves([list(r.values())[2:] for r in csv.DictReader(fh) if r.get("date", "") <= day], vals)
        src["coverage.csv"] = vals
    ex = _j(extra) if extra else {}
    vals = []
    for f in ex.get("facts") or []:
        if f.get("src") and f.get("v") is not None:      # 출처 없는 숫자는 받지 않는다
            _leaves(f["v"], vals)
    _leaves(ex.get("moves") or {}, vals)
    if vals:
        src["extra"] = vals
    return src


SCALES = {"%": (1, 100), "%p": (1, 100), "bp": (100, 10000), "B": (1, 1e-3, 1e-9), "M": (1, 1e-6, 1e3), "T": (1, 1e-12, 1e-3)}


def _cands(vals):
    """{배율: 정렬된 |값×배율|} — 단위마다 맞춰 볼 배율만 쓴다(0.13 → 13bp, 0.178 → 17.8%, 26100(M) → $26.1B)"""
    ks = {k for sc in SCALES.values() for k in sc} | {1}
    return {k: sorted({round(abs(v * k), 9) for v in vals}) for k in ks}


def _match(x, dec, cands, approx, unit=None):
    import bisect
    tol = max(0.5 * 10 ** -dec, 0.05 * x if approx else 0) + 1e-9
    for k in SCALES.get(unit, (1,)):
        cs = cands[k]
        i = bisect.bisect_left(cs, x - tol)
        if i < len(cs) and cs[i] <= x + tol:
            return True
    return False


def numbers(sentence):
    """검사 대상 숫자 [(값, 소수 자릿수, 근사 여부, 원문, 단위)] — 이름·날짜·기간·개수는 뺀다"""
    s = NAMES.sub(" ", sentence)
    s = COUNT.sub(" ", s)
    out = []
    for m in NUM.finditer(s):
        if not (m.group("unit") or m.group("cur") or "." in m.group("num")):
            # 단위 없는 정수 — 이름의 일부일 가능성이 커서 세지 않는다(예: '7월', 'Top 3'은 NAMES에서 이미 빠짐)
            continue
        raw = m.group("num").replace(",", "")
        dec = len(raw.split(".")[1]) if "." in raw else 0
        approx = bool(APPROX.match(s[m.end():])) or s[max(0, m.start() - 2):m.start()].strip() == "약"
        out.append((float(raw), dec, approx, m.group(0).strip(), m.group("unit")))
        if m.group("rng"):
            r2 = re.search(r"\d[\d,]*(?:\.\d+)?", m.group("rng")).group().replace(",", "")
            out.append((float(r2), len(r2.split(".")[1]) if "." in r2 else 0, approx, m.group(0).strip(), m.group("unit")))
    return out


FROMTO = re.compile(r"(\$?\d[\d,]*(?:\.\d+)?\s?(?:%|bp|배)?)에서\s?(\$?\d[\d,]*(?:\.\d+)?)")


def _measures(sentence):
    """문장당 숫자 개수 — 범위(15~23%)와 'A에서 B로' 이동은 하나로(마스터 기준 예시 '$97.75에서 $115로')"""
    s = FROMTO.sub(lambda m: m.group(2), NAMES.sub(" ", sentence))
    n = len(COUNT.findall(s))
    s = COUNT.sub(" ", s)
    return n + sum(1 for m in NUM.finditer(s) if m.group("unit") or m.group("cur") or "." in m.group("num"))


def sentences(text):
    return [x.strip() for x in re.split(r"(?<=[.!?])\s+|\n", text) if x.strip()]


def split(text):
    """(머리줄, 첫 문단, [(절 이름, 본문)], 마지막 줄)"""
    lines = [l.rstrip() for l in text.strip().splitlines()]
    head = lines[0] if lines else ""
    secs, lead, cur = [], [], None
    for l in lines[1:]:
        t = l.strip()
        if t.startswith("■ ") or t.startswith("🎯"):
            name = re.sub(r"^(■|🎯)\s*", "", t)
            cur = [name, []]
            secs.append(cur)
        elif cur is None:
            lead.append(l)
        else:
            cur[1].append(l)
    last = next((l.strip() for l in reversed(lines) if l.strip()), "")
    if secs and secs[-1][1] and secs[-1][1][-1].strip() == last:
        secs[-1][1] = secs[-1][1][:-1]
    return head, "\n".join(lead).strip(), [(n, "\n".join(b).strip()) for n, b in secs], last


def _sec_key(name):
    for s in list(OPTIONAL) + SECTIONS:     # '섹터 배분'이 '섹터'로 잡히지 않게 선택 절을 먼저 본다
        if name.startswith(s):
            return s
    return None


def coverage_changed(day):
    """{티커: (목표가 변화, 의견 변화)} — 그날 기록과 그 전 기록 비교"""
    if not COVERAGE.exists():
        return {}
    rows = {}
    with COVERAGE.open(encoding="utf-8", newline="") as fh:
        for r in csv.DictReader(fh):
            if r.get("date", "") <= day:
                rows.setdefault(r["ticker"], []).append(r)
    out = {}
    for t, rs in rows.items():
        rs.sort(key=lambda r: r["date"])
        cur = rs[-1]
        prev = next((r for r in reversed(rs[:-1]) if r["date"] < cur["date"] and r.get("target_mean")), None)
        if not prev or not cur.get("target_mean"):
            out[t] = (False, False)
            continue
        try:
            tm = abs(float(cur["target_mean"]) / float(prev["target_mean"]) - 1) > 0.005
        except (ValueError, ZeroDivisionError):
            tm = False
        op = any((cur.get(k) or "") != (prev.get(k) or "") for k in ("buy", "hold", "sell", "rec"))
        out[t] = (tm, op)
    return out


def check(text, day=None, extra=EXTRA, follow=None):
    """→ (오류 목록, 경고 목록)"""
    day = day or datetime.now(KST).date().isoformat()
    follow = follow if follow is not None else followed()
    err, warn = [], []
    head, lead, secs, last = split(text)
    if not re.fullmatch(r"\[Chiip Portfolio Daily \d{2}/\d{2}\]", head):
        err.append(f"머리줄 '[Chiip Portfolio Daily MM/DD]' 아님: {head[:40]}")
    if last != DISCLAIMER:
        err.append("마지막 줄이 면책 문구가 아님")
    # 구성
    if not lead:
        err.append("첫 문단 요약이 없음")
    else:
        ls = sentences(lead)
        if len(ls) > 3:
            err.append(f"첫 문단 {len(ls)}문장 — 3문장 이하")
        nn = sum(_measures(s) for s in ls)
        if nn > 6:
            err.append(f"첫 문단 숫자 {nn}개 — 6개 이하")
    keys = []
    for name, _ in secs:
        k = _sec_key(name)
        if k is None:
            err.append(f"양식에 없는 절: ■ {name}" + (" ('간단히'는 쓰지 않는다 — 내 종목에 합친다)" if "간단히" in name else ""))
        keys.append(k)
    req = [k for k in keys if k in SECTIONS]
    if req != [s for s in SECTIONS if s in req]:
        err.append("절 순서가 다름: " + " → ".join(req))
    for s in SECTIONS:
        if s not in keys:
            err.append(f"빠진 절: ■ {s}")
    for k in [k for k in keys if k in OPTIONAL]:
        i, (a, b) = keys.index(k), OPTIONAL[k]
        if a in keys and b in keys and not (keys.index(a) < i < keys.index(b)):
            err.append(f"■ {k}은 '{a}'과 '{b}' 사이에 둔다")
    if len(set(k for k in keys if k)) != len([k for k in keys if k]):
        err.append("같은 절이 두 번 나옴")
    # 문체 — 전체
    body = [("첫 문단", lead)] + [(n, b) for n, b in secs]
    seen_explain = set()
    cands = _cands([v for vs in pool(day, extra).values() for v in vs])
    for name, b in body:
        k = _sec_key(name) or name
        for ln in b.splitlines():
            if LABELS.match(ln):
                err.append(f"[{k}] 머릿말 금지: {ln.strip()[:30]}")
            if ln.count(" · ") >= 2:
                err.append(f"[{k}] ' · '로 이어 붙이기 금지: {ln.strip()[:40]}")
        for w in JARGON:
            if w in b:
                err.append(f"[{k}] 전문용어 금지: {w}")
        for w in EXPLAIN:
            i = b.find(w)
            if i >= 0 and w not in seen_explain:
                seen_explain.add(w)
                after = b[i + len(w):i + len(w) + 2].lstrip().startswith("(")
                inside = b[max(0, i - 1):i] == "(" and b[i + len(w):i + len(w) + 1] == ")"   # '물량이 풀리는 일정(오버행)'
                if not (after or inside):
                    err.append(f"[{k}] '{w}'는 처음 나올 때 괄호로 풀어 쓴다")
        if "원문 미확인" in b and k != "확인 못 한 것":
            err.append(f"[{k}] '원문 미확인'은 '확인 못 한 것' 절에만")
        elif "미확인" in b and k not in ("확인 못 한 것", "앞으로 챙길 것"):
            warn.append(f"[{k}] '미확인'은 가능하면 '확인 못 한 것'으로 모은다")
        if k in ("확인 못 한 것",):
            continue
        for s in sentences(b):
            if _measures(s) > 2:
                err.append(f"[{k}] 문장당 숫자 2개 이하: {s[:50]}")
            for x, dec, ap, raw, unit in numbers(s):
                if not _match(x, dec, cands, ap, unit):
                    err.append(f"[{k}] 스크립트·출처 숫자에 없음: {raw} — {s[:40]}")
    # 문단 띄우기(마스터 지시 2026-11-14) — 시장·섹터·앞으로 챙길 것은 줄(문단)마다 빈 줄을 둔다
    for name, b in secs:
        k = _sec_key(name)
        if k in ("시장", "섹터", "앞으로 챙길 것"):
            ls = b.splitlines()
            if any(x.strip() and y.strip() for x, y in zip(ls, ls[1:])):
                err.append(f"[{k}] 문단 사이에 빈 줄을 둔다")
    # 개수 일관성
    allt = text
    for m in re.finditer(r"(?:보유|내|관심)\s?종목\s?(\d+)\s?(?:개|종목|곳)", allt):
        if int(m.group(1)) != len(follow):
            err.append(f"종목 수 불일치: '{m.group(0)}' — config 기준 {len(follow)}개")
    for m in re.finditer(r"(\d+)\s?(?:개|종목|곳)\s?중\s?(\d+)\s?(?:개|종목|곳)", allt):
        n, k2 = int(m.group(1)), int(m.group(2))
        ctx = allt[max(0, m.start() - 12):m.start()]
        if k2 > n:
            err.append(f"개수 앞뒤 모순: {m.group(0)}")
        if "종목" in ctx + m.group(0) and n != len(follow) and n > 5:
            err.append(f"종목 수 불일치: '{m.group(0)}' — config 기준 {len(follow)}개")
    # 내 종목
    mine = next((b for n, b in secs if _sec_key(n) == "내 종목"), "")
    paras = [p.strip() for p in re.split(r"\n\s*\n", mine) if p.strip()]
    tick = re.compile(r"(?<![A-Z0-9])(" + "|".join(sorted(map(re.escape, follow), key=len, reverse=True)) + r")(?![A-Z0-9])") if follow else None
    subjects, singles = [], []
    ch = coverage_changed(day)
    ex = _j(extra) if extra else {}
    moves = {k: abs(v) for k, v in (ex.get("moves") or {}).items() if v is not None}
    for p in paras:
        ts = list(dict.fromkeys(tick.findall(p))) if tick else []
        if not ts:
            continue
        subj = ts[0]
        if subj in subjects:
            err.append(f"[내 종목] {subj} 문단이 두 번 — 한 문단으로")
        subjects.append(subj)
        if len(ts) == 1:
            singles.append(subj)
            m = tick.search(p)
            if not p[m.end():m.end() + 1] == "(":
                err.append(f"[내 종목] {subj} 처음 나올 때 '{subj}(회사 이름…)'으로")
        if re.search(r"목표가|투자의견|의견 분포|매수\s?\d+", p) and subj in ch and not any(ch[subj]):
            err.append(f"[내 종목] {subj} 목표가·의견은 바뀔 때만 쓴다(coverage.csv 변화 없음)")
    if moves and singles:
        ms = [moves.get(t, -1) for t in singles]
        if any(a < b for a, b in zip(ms, ms[1:])):
            err.append("[내 종목] 등락 큰 순이 아님: " + " → ".join(singles))
    # 위험 절
    risk = next((b for n, b in secs if _sec_key(n) == "모델이 보는 위험"), "")
    if risk:
        if len(sentences(risk)) > 3:
            err.append("[모델이 보는 위험] 3문장 이하(위험 수준 + 이유 + 모델 현금 비중)")
        if "현금" not in risk:
            err.append("[모델이 보는 위험] 모델 현금 비중이 없음")
        if not re.search(r"높|보통|낮", risk):
            err.append("[모델이 보는 위험] 위험 수준(높음·보통·낮음)이 없음")
    return err, warn


def risk_lines():
    """'모델이 보는 위험' 절 — 위험 수준 + 이유 한 줄 + 모델 현금 비중(스크립트 값)"""
    pm = _j(M / "pm" / "latest.json")
    hrp = (pm.get("baselines") or {}).get("HRP") or {}
    cash = _j(M / "pm" / "construct.json").get("cash")
    vol, dd_now, ddc = hrp.get("vol_ann"), hrp.get("dd_now"), hrp.get("dd_control_scale")
    if vol is None:
        return ["모델 위험 지표가 아직 없습니다."]
    level = "높음" if vol >= 0.5 or ddc == 0 else "보통" if vol >= 0.3 else "낮음"
    out = [f"모델이 보는 위험은 {dict(높음='높습니다', 보통='보통입니다', 낮음='낮습니다')[level]}."]
    if ddc == 0 and dd_now is not None:
        out.append(f"내 종목으로 짠 모델 포트폴리오가 고점보다 {dd_now * 100:.0f}% 내려와 있고, 1년 변동성도 {vol * 100:.0f}% 수준입니다.")
    else:
        out.append(f"내 종목으로 짠 모델 포트폴리오의 1년 변동성이 {vol * 100:.0f}% 수준입니다.")
    if cash is not None:
        out.append(f"그래서 모델 기준 현금 비중은 {cash * 100:.0f}%입니다.")
    return out


def main(argv):
    day = argv[argv.index("--date") + 1] if "--date" in argv else None
    extra = Path(argv[argv.index("--extra") + 1]) if "--extra" in argv else EXTRA
    if "--risk" in argv:
        print("\n".join(risk_lines()))
        return 0
    if "--pool" in argv:
        for k, v in pool(day, extra).items():
            print(f"{k}: {len(v)}")
        return 0
    args = [a for i, a in enumerate(argv) if not a.startswith("--") and (i == 0 or argv[i - 1] not in ("--date", "--extra"))]
    text = Path(args[0]).read_text(encoding="utf-8")
    err, warn = check(text, day, extra)
    for e in err:
        print("오류 " + e)
    for w in warn:
        print("경고 " + w)
    print("통과" if not err else f"오류 {len(err)}건 — 고친 뒤 다시 검사(발송 금지)")
    return 1 if err else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
