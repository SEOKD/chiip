"""텐배거 리포트 '고객' 절 (마스터 지시 2026-11-02 "고객사가 어디인지, 고객별 믹스가 어느 정도 되는지 추정하는 항목도 넣어라. 시각화로도 나타내고 글로도 나타내라")

숫자는 여기서 계산한다. 모델은 datapack "customers"에 원자료만 쓴다. 모르는 값은 "미확인"으로 두고 지어내지 않는다.
datapack "customers":
  {"as_of": "2026-09-30", "period": "FY25", "summary": "한 줄",
   "items": [{"name": "Lam Research",     # 고객 회사명. 공시가 익명이면 공시 표기 그대로, 또는 추정한 이름에 "alias": "Customer A"
              "share": 0.3,               # 매출 몫. 범위는 [0.25, 0.35], 모르면 "미확인"
              "prior": 0.25,              # 직전 같은 기간 몫, 모르면 "미확인"
              "basis": "공시",            # BASIS 중 하나
              "buys": "무엇을 사나", "source": "10-K p.8",
              "why": "추정 근거"}]}       # 보도·추정이면 필수
  익명 고객을 특정 회사로 옮기는 것은 가설이다: basis '추정'으로 쓰고 why에 근거를 적는다.
  불특정 다수에게 파는 회사는 고객 유형을 items로 쓴다. 고객 구분이 무의미하면 {"none": "이유"} → 절을 넣지 않는다.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from margin_view import share_of  # noqa: E402

UNKNOWN = "미확인"
BASIS = ("공시", "회사 발표", "보도", "추정")
TIE = 0.015
COLOR = {"공시": "c", "회사 발표": "c", "보도": "e", "추정": "a"}
DISPERSED, CONCENTRATED = 0.15, 0.25   # HHI(몫 제곱의 합) 판정 경계


def _num(x):
    return float(x) if isinstance(x, (int, float)) and not isinstance(x, bool) else None


def compute(dp):
    cu = dp["customers"]
    rows = []
    for x in cu["items"]:
        mid, lo, hi = share_of(x.get("share"))
        rows.append({**x, "mid": mid, "lo": lo, "hi": hi})
    known = sorted((r for r in rows if r["mid"] is not None), key=lambda r: -r["mid"])
    named = sum(r["mid"] for r in known)
    hhi = sum(r["mid"] ** 2 for r in known)
    firm = sum(r["mid"] for r in known if r["basis"] in BASIS[:2])
    return {"rows": known + [r for r in rows if r["mid"] is None], "known": known, "named": named, "rest": max(1 - named, 0), "hhi": hhi, "firm": firm,
            "top1": known[0]["mid"], "top3": sum(r["mid"] for r in known[:3]), "grade": "분산" if hhi < DISPERSED else "보통" if hhi < CONCENTRATED else "집중"}


def check(cu):
    """예약 회차가 빈칸을 그럴듯하게 채우지 않도록 원자료를 검사한다"""
    if cu.get("none"):
        return
    items = cu.get("items") or []
    if not items or not cu.get("period") or len(str(cu.get("as_of") or "")) < 7:
        raise ValueError("datapack customers에 as_of·period·items가 필요하다 — 고객 구분이 무의미하면 {'none': '이유'}")
    total = 0.0
    for x in items:
        name = x.get("name") or "이름 없음"
        mid = share_of(x.get("share"))[0]
        if mid is None and x.get("share") != UNKNOWN:
            raise ValueError(f"customers {name}: share는 숫자, [하단, 상단], '미확인' 중 하나")
        if x.get("basis") not in BASIS or not x.get("buys") or not x.get("source"):
            raise ValueError(f"customers {name}: basis({BASIS})·buys·source가 필요하다")
        if x["basis"] in BASIS[2:] and not x.get("why"):
            raise ValueError(f"customers {name}: 보도·추정은 why가 필요하다")
        if _num(x.get("prior")) is None and x.get("prior") != UNKNOWN:
            raise ValueError(f"customers {name}: prior가 필요하다(모르면 '미확인')")
        total += mid or 0
    if total > 1 + TIE:
        raise ValueError(f"customers 몫 합 {total:.0%}이 100%를 넘는다")
    if not any(share_of(x.get("share"))[0] is not None for x in items):
        raise ValueError("customers: 몫을 쓴 고객이 하나 이상 필요하다")


def _share(r):
    if r["mid"] is None:
        return UNKNOWN
    return f"{r['mid'] * 100:.0f}%" if r["lo"] == r["hi"] else f"{r['lo'] * 100:.0f}~{r['hi'] * 100:.0f}%"


def _label(r):
    return f"{r['name']}({r['alias']})" if r.get("alias") else r["name"]


def section(dp):
    cu = (dp or {}).get("customers")
    if not cu:
        raise SystemExit("datapack에 customers가 없다(scripts/tenbagger/customer_view.py 맨 위) — 고객 구분이 무의미하면 {'none': '이유'}, 옛 리포트 정정은 --legacy")
    check(cu)
    if cu.get("none"):
        return None
    c = compute(dp)
    head = f"**{cu['period']} 최대 고객 {_label(c['known'][0])} {c['top1'] * 100:.0f}%, 상위 3곳 {c['top3'] * 100:.0f}%, 집중도 {c['grade']}.**"
    head += f" 공시·회사 발표로 확인한 몫은 매출의 {c['firm'] * 100:.0f}%이고, 나머지 고객 몫은 추정이거나 미분해다."
    if cu.get("summary"):
        head += " " + str(cu["summary"])
    B = [{"type": "hl", "text": head}]
    rows = []
    for r in c["rows"]:
        prior = _num(r.get("prior"))
        rows.append([_label(r), _share(r), UNKNOWN if prior is None or r["mid"] is None else f"{(r['mid'] - prior) * 100:+.0f}%p", r["basis"]])
    if c["rest"] > TIE:
        rows.append(["기타·미분해", f"{c['rest'] * 100:.0f}%", "-", "-"])
    B.append({"type": "table", "title": f"고객별 매출 몫({cu['period']})", "headers": ["고객", "몫", "변화", "근거"], "rows": rows})
    B.append({"type": "boxes", "items": [{"title": _label(r), "tag": r["basis"], "lines": [["사는 것", r["buys"]], ["추정 근거", r.get("why")]]} for r in c["rows"]]})
    return {"h2": "고객", "blocks": B, "_sources": sorted({str(x["source"]) for x in cu["items"]})}


def chart(dp):
    """한눈에 보기 고객 믹스 — 색으로 공시와 추정을 나눈다"""
    cu = (dp or {}).get("customers") or {}
    if not cu or cu.get("none"):
        return None
    c = compute(dp)
    rows = [{"label": _label(r), "bars": [{"name": "공시·회사 발표" if r["basis"] in BASIS[:2] else r["basis"], "color": COLOR[r["basis"]], "value": round(r["mid"] * 100, 1)}]} for r in c["known"][:8]]
    if c["rest"] > TIE:
        rows.append({"label": "기타·미분해", "bars": [{"name": "기타·미분해", "color": "b", "value": round(c["rest"] * 100, 1)}]})
    return {"kind": "hbars", "w": 480, "label_w": 170, "title": f"고객 믹스({cu['period']}, 매출 대비)", "unit": "%", "rows": rows}


def summary_item(dp):
    cu = (dp or {}).get("customers") or {}
    if not cu or cu.get("none"):
        return None
    c = compute(dp)
    return {"q": "누가 사 주나?", "a": f"최대 고객 {_label(c['known'][0])} {c['top1'] * 100:.0f}%, 상위 3곳 {c['top3'] * 100:.0f}%. 공시·회사 발표로 확인한 몫은 {c['firm'] * 100:.0f}%다.", "auto": True}
