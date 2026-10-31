"""텐배거 리포트 '수주·파이프라인' 절 (마스터 지시 2026-10-31 "기업이 진행 중인 수주 및 파이프라인이 있다면 리스트업을 하고
진척도가 몇 %되며, 실행 속도는 어느 수준이며, 방해 요인이 무엇이며 현 진척도에 따른 수익과 진척도 100% 도달했을 때의 총 수익이 얼마인지")

숫자는 여기서 계산한다. 모델은 datapack "pipeline"에 원자료만 쓴다. 모르는 값은 "미확인"으로 두고 지어내지 않는다.
datapack "pipeline":
  {"as_of": "2026-06-30", "reported_backlog": 1.7, "backlog_label": "수주잔고", "summary": "요약에 붙일 한 문장",
   "items": [{"name": "Meta El Paso 366MW", "status": "확정",        # STATUS 중 하나. 확정만 확정 합계에 넣는다(금지표: 수주·MOU → 매출)
              "total": 0.29,                                         # 100% 도달 때 매출(리포트 단위)
              "done": 0.05, 또는 "progress": 0.17, "progress_basis": "납품 62/366MW",   # 둘 다 모르면 "progress": "미확인"
              "margin": 0.25, "margin_kind": "매출총이익", "margin_basis": "2Q 장비 마진",   # 모르면 "margin": "미확인"
              "start": "2026-03", "end": "2027-06",                  # 일정을 알면 계획 대비 속도를 엔진이 잰다
              "speed": "분기 45MW, 목표 300MW",                       # 일정이 없을 때 쓰는 실측 설명
              "blockers": ["조립 램프", "단일 공급원 부품"],
              "source": "10-Q p.12"}]}
  수주·파이프라인이 없는 회사: {"none": "구독 소프트웨어라 개별 수주가 없다"} → 절을 넣지 않는다.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from ladder import _money  # noqa: E402

FIRM = "확정"
STATUS = (FIRM, "조건부", "협상", "프레임워크", "MOU", "파이프라인")
ON_PLAN = 0.05   # 계획 대비 이 폭 안이면 '계획대로'
UNKNOWN = "미확인"


def _num(x):
    return float(x) if isinstance(x, (int, float)) and not isinstance(x, bool) else None


def _months(a, b):
    """'YYYY-MM…' 두 값의 개월 차"""
    y0, m0, y1, m1 = int(a[:4]), int(a[5:7]), int(b[:4]), int(b[5:7])
    return (y1 - y0) * 12 + m1 - m0


def _add_months(a, n):
    i = int(a[:4]) * 12 + int(a[5:7]) - 1 + round(n)
    return f"{i // 12}-{i % 12 + 1:02d}"


def progress_of(x):
    p = _num(x.get("progress"))
    if p is None and _num(x.get("done")) is not None and _num(x.get("total")):
        p = _num(x["done"]) / _num(x["total"])
    return p


def speed_of(x, as_of):
    """{'plan', 'gap', 'finish', 'delay', 'grade'} — 시작·종료·진척도가 모두 있어야 계획과 비교한다"""
    p, start, end = progress_of(x), str(x.get("start") or ""), str(x.get("end") or "")
    if p is None or len(start) < 7 or len(end) < 7:
        return None
    span, past = _months(start, end), _months(start, as_of)
    if span <= 0 or past <= 0:
        return None
    plan = min(past / span, 1.0)
    gap = p - plan
    finish, delay = None, None
    if p > 0:
        left = past * (1 - p) / p
        finish, delay = _add_months(as_of, left), round(_months(as_of, end) * -1 + left)
    grade = "앞섬" if gap > ON_PLAN else "지연" if gap < -ON_PLAN else "계획대로"
    return {"plan": plan, "gap": gap, "finish": finish, "delay": delay, "grade": grade}


def compute(dp):
    pl, out = (dp or {}).get("pipeline") or {}, []
    as_of = str(pl.get("as_of") or "")
    for x in pl.get("items") or []:
        total, p, m = _num(x.get("total")), progress_of(x), _num(x.get("margin"))
        out.append({**x, "total": total, "p": p, "m": m, "speed_calc": speed_of(x, as_of),
                    "rev_now": total * p if total is not None and p is not None else None,
                    "gain_now": total * p * m if None not in (total, p, m) else None,
                    "gain_full": total * m if None not in (total, m) else None})

    def total_of(rows, key):
        vals = [r[key] for r in rows]
        return sum(v for v in vals if v is not None), sum(v is None for v in vals)

    firm, soft = [r for r in out if r.get("status") == FIRM], [r for r in out if r.get("status") != FIRM]
    return {"as_of": as_of, "items": out, "firm": firm, "soft": soft, "total_of": total_of}


def check(pl):
    """예약 회차가 빈칸을 그럴듯하게 채우지 않도록 원자료를 검사한다"""
    if pl.get("none"):
        return
    if not pl.get("items") or len(str(pl.get("as_of") or "")) < 7:
        raise ValueError("datapack pipeline에 as_of와 items가 필요하다 — 수주가 없으면 {'none': '이유'}")
    for x in pl["items"]:
        name = x.get("name") or "이름 없음"
        if x.get("status") not in STATUS:
            raise ValueError(f"pipeline {name}: status는 {STATUS} 중 하나")
        if _num(x.get("total")) is None or not x.get("source") or not x.get("blockers"):
            raise ValueError(f"pipeline {name}: total·source·blockers가 필요하다(방해 요인을 모르면 ['미확인'])")
        p = progress_of(x)
        if p is None and x.get("progress") != UNKNOWN:
            raise ValueError(f"pipeline {name}: progress 또는 done이 필요하다(모르면 '미확인')")
        if p is not None and not 0 <= p <= 1:
            raise ValueError(f"pipeline {name}: 진척도 {p:.0%}는 0~100% 밖이다")
        if _num(x.get("margin")) is None and x.get("margin") != UNKNOWN:
            raise ValueError(f"pipeline {name}: margin이 필요하다(모르면 '미확인')")
        if _num(x.get("margin")) is not None and not x.get("margin_basis"):
            raise ValueError(f"pipeline {name}: margin_basis가 필요하다")


def _pct(p):
    return UNKNOWN if p is None else f"{p * 100:.0f}%"


def _m(v, unit):
    return UNKNOWN if v is None else _money(v, unit)


def speed_text(r):
    s = r["speed_calc"]
    if not s:
        return r.get("speed") or UNKNOWN
    head = f"{s['grade']}(계획 {s['plan'] * 100:.0f}%, {s['gap'] * 100:+.0f}%p)"
    if s["delay"] is None:
        return head
    when = f"이대로면 {s['finish']} 완료"
    return f"{head}, {when}" + (f", {s['delay']}개월 지연" if s["delay"] > 0 else "")


def _sum_row(label, rows, c, unit):
    rev, rev_unknown = c["total_of"](rows, "rev_now")
    gain, gain_unknown = c["total_of"](rows, "gain_now")
    full_gain, full_unknown = c["total_of"](rows, "gain_full")
    total = sum(r["total"] for r in rows)
    mark = lambda v, n: f"{_money(v, unit)}(+{UNKNOWN} {n}건)" if n and v else (UNKNOWN if n else _money(v, unit))
    return [f"**{label}**", _money(total, unit), mark(rev, rev_unknown), mark(gain, gain_unknown), mark(full_gain, full_unknown)]


def report_section(dp, r=None, strict=True):
    pl = (dp or {}).get("pipeline")
    if not pl or pl.get("none"):
        if strict and not pl:
            raise ValueError("datapack에 pipeline이 없다 — docs/tasks/chiip-tenbagger-report.md 2번, 수주가 없으면 {'none': '이유'}")
        return None
    check(pl)
    c, unit = compute(dp), dp.get("unit", "B$")
    B = []
    firm_total, soft_total = sum(x["total"] for x in c["firm"]), sum(x["total"] for x in c["soft"])
    head = f"**{c['as_of']} 기준 수주 {len(c['items'])}건, 확정 {_money(firm_total, unit)}"
    head += f", 미확정 {_money(soft_total, unit)}.**" if c["soft"] else ".**"
    known = [x for x in c["firm"] if x["rev_now"] is not None]
    if known:
        head += f" 진척도를 아는 확정 건의 매출 기준 진척은 {sum(x['rev_now'] for x in known) / sum(x['total'] for x in known) * 100:.0f}%다."
    backlog = _num(pl.get("reported_backlog"))
    if backlog:
        head += f" 공시 {pl.get('backlog_label', '수주잔고')}는 {_money(backlog, unit)}다."
    head += " 미확정 건은 합계에 넣지 않았다. 수익은 항목별 마진 가정을 곱한 추정이다."
    B.append({"type": "hl", "text": head})
    B.append({"type": "table", "title": "수주·파이프라인 진척", "headers": ["항목", "상태", "진척도", "실행 속도", "방해 요인"],
              "rows": [[x["name"], x["status"], _pct(x["p"]), speed_text(x), " · ".join(x["blockers"])] for x in c["items"]]})
    B.append({"type": "table", "title": "진척도별 수익", "headers": ["항목", "마진 가정", "현 진척 매출", "현 진척 이익", "100% 매출", "100% 이익"],
              "rows": [[x["name"], f"{x.get('margin_kind', '이익')} {x['m'] * 100:.0f}%" if x["m"] is not None else UNKNOWN,
                        _m(x["rev_now"], unit), _m(x["gain_now"], unit), _money(x["total"], unit), _m(x["gain_full"], unit)] for x in c["items"]]})
    rows = [_sum_row("확정 합계", c["firm"], c, unit)] if c["firm"] else []
    if c["soft"]:
        rows.append(_sum_row("미확정 합계", c["soft"], c, unit))
    B.append({"type": "table", "title": "합계", "headers": ["구분", "100% 매출", "현 진척 매출", "현 진척 이익", "100% 이익"], "rows": rows})
    mcap = _num((r or {}).get("mcap"))
    gain, missing = c["total_of"](c["firm"], "gain_full")
    if mcap and gain and not missing:
        done, _ = c["total_of"](c["firm"], "gain_now")
        B.append({"type": "p", "text": f"확정 수주를 100% 끝내면 남는 이익은 {_money(gain - done, unit)}로 시가총액의 {(gain - done) / mcap * 100:.0f}%다."})
    return {"h2": "수주·파이프라인 — 진척도와 남은 수익", "blocks": B, "_sources": sorted({str(x["source"]) for x in c["items"]})}


def summary_item(dp):
    pl = (dp or {}).get("pipeline") or {}
    c, unit = compute(dp), dp.get("unit", "B$")
    parts = [f"{x['name']} {_pct(x['p'])}, 100% 매출 {_money(x['total'], unit)}" for x in c["items"][:3]]
    return {"q": "수주는 어디까지 왔나?", "a": " · ".join(parts) + (f". {pl['summary']}" if pl.get("summary") else ""), "auto": True}
