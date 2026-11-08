"""텐배거 리포트 '생산능력' 절 (마스터 지시 2026-11-02 "기업의 생산능력 관련 시각물과 분석글도 넣자. 현재 생산능력, 앞으로 생산능력 확충 계획,
생산능력 확충에 드는 CAPEX 비용, CAPEX는 매출의 몇 %인지")

숫자는 여기서 계산한다. 모델은 datapack "capacity"에 원자료만 쓴다. 모르는 값은 "미확인"으로 두고 지어내지 않는다.
datapack "capacity":
  {"as_of": "2026-09-30", "unit": "MW/년", "summary": "한 줄",     # unit은 회사가 쓰는 캐파 단위. 시공·서비스는 인력·크루
   "current": {"nameplate": 1000, "utilization": 0.8, "basis": "공시", "source": "10-K p.20"},   # 명목 캐파, 가동률. 모르면 "미확인"
   "plans": [{"name": "테일러 2기", "add": 500,                    # 늘어나는 명목 캐파, 모르면 "미확인"
              "stage": "착공",                                     # STAGES 중 하나. 공시·현장 근거로 확인된 단계만 쓴다
              "online": "2027-06",                                 # 회사가 말한 가동 시점, 모르면 "미확인"
              "capex": 1.2,                                        # 이 계획의 총 CAPEX(리포트 단위), 모르면 "미확인"
              "blocker": "방해 요인", "source": "출처"}],
   "capex": [{"period": "FY25", "capex": 0.5, "rev": 3.0, "kind": "실적"},   # KINDS 중 하나, 오래된 기간부터. 분기가 아니라 연간·TTM으로 쓴다
             {"period": "FY26", "capex": 0.8, "rev": 3.6, "kind": "가이던스"}]}
   "facilities": {"count": 9, "count_basis": "10-K Item 2 — 제조 용도 시설", "source": "10-K URL",   # 마스터 지시 2026-11-08 "생산시설이 몇 곳이 있고 각각의 명칭과 위치, 생산능력 수치"
                  "items": [{"name": "Prachinburi 공장", "location": "태국 Prachinburi", "owned": "소유",     # 소유·임차·소유·임차·위탁·미확인
                             "use": "제조", "area": {"value": 1568000, "unit": "sq ft"},                  # 면적은 선택(공시 있을 때)
                             "capacity": {"value": 20000, "unit": "웨이퍼/월", "source": "출처"} 또는 "미확인",
                             "capacity_basis": "시설별 캐파 미공시",                                       # capacity가 미확인이면 이유
                             "status": "가동"}]}                                                          # FAC_STATUS 중 하나
  생산 설비가 없는 회사: {"none": "이유"} → 절을 넣지 않는다.

금지표대로 투자 발표를 공급 증가로 세지 않는다: 착공 이후 단계만 '착공 이상' 합계에 넣고, 명목 캐파와 가동률 반영 실효 캐파를 나눈다.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from ladder import _money  # noqa: E402
import site_view  # noqa: E402

UNKNOWN = "미확인"
STAGES = ("발표", "인허가", "착공", "장비 반입", "가동", "양산")
FIRM_FROM = STAGES.index("착공")
LIVE_FROM = STAGES.index("가동")
KINDS = ("실적", "가이던스", "컨센서스", "추정")
MIN_PERIODS = 2
FAC_STATUS = ("가동", "증설 중", "건설 중", "계획", "가동 중단", "매각·폐쇄 예정")
OWNED = ("소유", "임차", "소유·임차", "위탁", "미확인")


def _num(x):
    return float(x) if isinstance(x, (int, float)) and not isinstance(x, bool) else None


def compute(dp):
    cap = dp["capacity"]
    now, use = _num(cap["current"].get("nameplate")), _num(cap["current"].get("utilization"))
    plans = cap["plans"]
    pending = [p for p in plans if STAGES.index(p["stage"]) < LIVE_FROM]   # 이미 가동한 계획은 현재 캐파에 들어 있다고 본다
    firm = [p for p in pending if STAGES.index(p["stage"]) >= FIRM_FROM]
    total = lambda rows, key: sum(_num(p.get(key)) or 0 for p in rows)
    priced = [p for p in pending if _num(p.get("add")) and _num(p.get("capex"))]
    return {"now": now, "use": use, "real": now * use if now is not None and use is not None else None, "pending": pending, "firm": firm,
            "add_firm": total(firm, "add"), "add_all": total(pending, "add"), "capex_all": total(pending, "capex"), "capex_firm": total(firm, "capex"),
            "per_unit": total(priced, "capex") / total(priced, "add") if priced else None,
            "unpriced": sum(_num(p.get("capex")) is None for p in pending),
            "years": [{**y, "pct": y["capex"] / y["rev"]} for y in cap["capex"]]}


def check(cap):
    """예약 회차가 빈칸을 그럴듯하게 채우지 않도록 원자료를 검사한다"""
    if cap.get("none"):
        return
    cur, plans, years = cap.get("current") or {}, cap.get("plans"), cap.get("capex") or []
    if plans is None or not cap.get("unit") or len(str(cap.get("as_of") or "")) < 7:
        raise ValueError("datapack capacity에 as_of·unit·current·plans·capex가 필요하다(계획이 없으면 plans는 []) — 설비가 없으면 {'none': '이유'}")
    for k in ("nameplate", "utilization"):
        if _num(cur.get(k)) is None and cur.get(k) != UNKNOWN:
            raise ValueError(f"capacity.current {k}가 필요하다(모르면 '미확인')")
    if not cur.get("source") or not cur.get("basis"):
        raise ValueError("capacity.current에 basis·source가 필요하다")
    u = _num(cur.get("utilization"))
    if u is not None and not 0 <= u <= 1.2:
        raise ValueError(f"capacity 가동률 {u:.0%}는 범위 밖이다")
    for p in plans:
        name = p.get("name") or "이름 없음"
        if p.get("stage") not in STAGES or not p.get("source") or not p.get("blocker") or not p.get("online"):
            raise ValueError(f"capacity.plans {name}: stage({STAGES})·online·blocker·source가 필요하다")
        for k in ("add", "capex"):
            if _num(p.get(k)) is None and p.get(k) != UNKNOWN:
                raise ValueError(f"capacity.plans {name}: {k}가 필요하다(모르면 '미확인')")
    fac = cap.get("facilities") or {}
    if not fac.get("items") or not fac.get("source") or not fac.get("count_basis"):
        raise ValueError("capacity.facilities에 count·count_basis·source·items가 필요하다 — 생산시설 이름·위치·생산능력(마스터 지시 2026-11-08, capacity_view.py 맨 위)")
    if not isinstance(fac.get("count"), int) or fac["count"] < len(fac["items"]):
        raise ValueError("capacity.facilities.count는 정수이고 items 수 이상이어야 한다(이름을 공개하지 않은 시설은 count에만 센다)")
    for f in fac["items"]:
        nm = f.get("name") or "이름 없음"
        if not f.get("name") or not f.get("location") or f.get("status") not in FAC_STATUS or f.get("owned", "미확인") not in OWNED:
            raise ValueError(f"capacity.facilities {nm}: name·location·status({FAC_STATUS})·owned({OWNED})가 필요하다")
        cv = f.get("capacity")
        if cv == UNKNOWN:
            if not f.get("capacity_basis"):
                raise ValueError(f"capacity.facilities {nm}: 생산능력이 미확인이면 capacity_basis(왜 모르는지)가 필요하다")
        elif not (isinstance(cv, dict) and _num(cv.get("value")) is not None and cv.get("unit") and cv.get("source")):
            raise ValueError(f"capacity.facilities {nm}: capacity는 {{value, unit, source}} 또는 '미확인'")
    if len(years) < MIN_PERIODS:
        raise ValueError(f"capacity.capex에 {MIN_PERIODS}개 기간 이상이 필요하다")
    for y in years:
        if _num(y.get("capex")) is None or not _num(y.get("rev")) or y.get("kind") not in KINDS:
            raise ValueError(f"capacity.capex {y.get('period')}: capex·rev·kind({KINDS})가 필요하다")
    site_view.check(cap)


def _cap(v, unit):
    return UNKNOWN if v is None else f"{v:,.0f} {unit}"


def section(dp):
    cap = (dp or {}).get("capacity")
    if not cap:
        raise SystemExit("datapack에 capacity가 없다(scripts/tenbagger/capacity_view.py 맨 위) — 설비가 없으면 {'none': '이유'}, 옛 리포트 정정은 --legacy")
    check(cap)
    if cap.get("none"):
        return None
    c, unit, money = compute(dp), cap["unit"], dp.get("unit", "B$")
    last = next((y for y in reversed(c["years"]) if y["kind"] == "실적"), c["years"][-1])
    head = f"**현재 명목 캐파 {_cap(c['now'], unit)}, 가동률 {UNKNOWN if c['use'] is None else format(c['use'], '.0%')}.**"
    if c["pending"]:
        head += f" 착공 이상 증설은 {_cap(c['add_firm'], unit)}, 발표까지 합치면 {_cap(c['add_all'], unit)}이다."
        if c["now"]:
            head += f" 다 가동하면 지금보다 {c['add_all'] / c['now']:+.0%}, 착공 이상만이면 {c['add_firm'] / c['now']:+.0%}다."
    head += f" {last['period']} CAPEX는 {_money(last['capex'], money)}로 매출의 {last['pct']:.1%}다."
    if c["now"] is None and site_view.headline(dp, unit):
        head += " " + site_view.headline(dp, unit)
    if cap.get("summary"):
        head += " " + str(cap["summary"])
    B = [{"type": "hl", "text": head}]
    B.extend(facility_blocks(cap))
    if c["pending"]:
        B.append({"type": "table", "title": "생산능력 확충 계획", "headers": ["계획", "단계", "증설", "가동 시점", "CAPEX"],
                  "rows": [[p["name"], p["stage"], _cap(_num(p.get("add")), unit), p["online"], UNKNOWN if _num(p.get("capex")) is None else _money(p["capex"], money)] for p in c["pending"]]})
        text = f"남은 계획의 CAPEX 합계는 {_money(c['capex_all'], money)}" + (f"(금액 미확인 {c['unpriced']}건 제외)" if c["unpriced"] else "") + "다."
        if c["per_unit"]:
            text += f" 금액을 아는 계획의 단위당 CAPEX는 {_money(c['per_unit'], money)}/{unit}이다."
        if c["years"][-1]["rev"]:
            text += f" 합계는 {c['years'][-1]['period']} 매출의 {c['capex_all'] / c['years'][-1]['rev']:.0%}다."
        B.append({"type": "p", "text": text})
        B.append({"type": "table", "title": "증설 방해 요인", "headers": ["계획", "방해 요인"], "rows": [[p["name"], p["blocker"]] for p in c["pending"]]})
    else:
        B.append({"type": "p", "text": "공개된 증설 계획은 확인되지 않았다."})
    B.append({"type": "table", "title": "CAPEX와 매출 대비", "headers": ["기간", "CAPEX", "매출", "매출 대비", "구분"],
              "rows": [[y["period"], _money(y["capex"], money), _money(y["rev"], money), f"{y['pct']:.1%}", y["kind"]] for y in c["years"]]})
    B.extend(site_view.blocks(dp))
    import photo_view   # 생산시설 실사 사진(마스터 지시 2026-11-05)
    ph = photo_view.block(dp, "site")
    if ph:
        B.append(ph)
    return {"h2": "생산능력", "blocks": B, "_sources": sorted({str(cap["current"]["source"])} | {str(p["source"]) for p in cap["plans"]} | set(site_view.sources(dp)) | {str((cap.get("facilities") or {}).get("source"))} - {"None"})}


def _fcap(f):
    cv = f.get("capacity")
    return f"{cv['value']:,.0f} {cv['unit']}" if isinstance(cv, dict) else UNKNOWN


def facility_blocks(cap):
    """생산시설 목록 — 몇 곳, 이름·위치·생산능력(마스터 지시 2026-11-08). 시설별 캐파를 둘 이상 알면 그 막대, 모르면 공시 면적을 대용으로 그린다"""
    fac = cap.get("facilities") or {}
    items = fac.get("items") or []
    if not items:
        return []
    known = [f for f in items if isinstance(f.get("capacity"), dict)]
    named = len(items)
    text = f"**생산시설 {fac['count']}곳**({fac['count_basis']})"
    text += f" — 이름·위치를 밝힌 곳 {named}곳" if named < fac["count"] else ""
    own = {}
    for f in items:
        own[f.get("owned", "미확인")] = own.get(f.get("owned", "미확인"), 0) + 1
    text += ", " + " · ".join(f"{k} {v}곳" for k, v in own.items()) + "."
    text += f" 시설별 생산능력은 {len(known)}곳만 공개됐다." if known and len(known) < named else (" 시설별 생산능력은 공개되지 않았다 — 회사 전체 캐파만 위에 적었다." if not known else "")
    has_area = any((f.get("area") or {}).get("value") for f in items)
    head = ["시설", "위치", "용도", "생산능력", "소유·상태"]   # 표는 5열까지(휴대폰 가독성) — 면적은 생산능력 칸에 함께 쓴다
    area = lambda f: f" · 면적 {f['area']['value']:,.0f} {f['area'].get('unit', '')}" if (f.get("area") or {}).get("value") else ""
    rows = [[f["name"], f["location"], f.get("use", ""), (_fcap(f) if isinstance(f.get("capacity"), dict) else f"미확인 — {f.get('capacity_basis', '')}") + area(f),
             f"{f.get('owned', '미확인')} · {f['status']}"] for f in items]
    B = [{"type": "p", "text": text}, {"type": "table", "title": f"생산시설 {fac['count']}곳 — 명칭·위치·생산능력", "headers": head, "rows": rows}]
    units = {f["capacity"]["unit"] for f in known}
    if len(known) >= 2 and len(units) == 1:
        B.append({"type": "chart", "chart": {"kind": "hbars", "w": 480, "label_w": 160, "title": f"시설별 생산능력({units.pop()})", "unit": "",
                                             "rows": [{"label": f["name"], "bars": [{"name": "생산능력", "color": "c", "value": f["capacity"]["value"]}]} for f in known]}})
    elif has_area:
        au = next((f["area"].get("unit", "") for f in items if (f.get("area") or {}).get("value")), "")
        B.append({"type": "chart", "chart": {"kind": "hbars", "w": 480, "label_w": 160, "title": f"시설별 면적({au}) — 생산능력 미공시라 면적을 대용으로", "unit": "",
                                             "rows": [{"label": f["name"], "bars": [{"name": "면적", "color": "e", "value": f["area"]["value"]}]} for f in items if (f.get("area") or {}).get("value")]}})
    return B


def charts(dp):
    """한눈에 보기 그림 두 개 — 캐파 단계와 CAPEX 대 매출"""
    cap = (dp or {}).get("capacity") or {}
    if not cap or cap.get("none"):
        return None, None
    c, unit = compute(dp), cap["unit"]
    steps = []
    if c["real"] is not None:
        steps.append(("가동률 반영 현재", c["real"], "a"))
    if c["now"] is not None:
        steps.append(("명목 현재", c["now"], "c"))
        if c["add_firm"]:
            steps.append(("착공 이상 반영", c["now"] + c["add_firm"], "d"))
        if c["add_all"] > c["add_firm"]:
            steps.append(("발표까지 반영", c["now"] + c["add_all"], "e"))
    ladder = {"kind": "hbars", "w": 480, "label_w": 150, "title": f"생산능력 현재와 확충 계획({unit})", "unit": "",
              "rows": [{"label": n, "bars": [{"name": n, "color": col, "value": round(v, 1)}]} for n, v, col in steps]} if steps else None
    money = dp.get("unit", "B$")
    years = {"kind": "hbars", "w": 480, "label_w": 150, "title": "CAPEX의 매출 대비 비중", "unit": "%",
             "rows": [{"label": f"{y['period']} {_money(y['capex'], money)}", "bars": [{"name": y["kind"], "color": "c" if y["kind"] == "실적" else "e", "value": round(y["pct"] * 100, 1)}]} for y in c["years"]]}
    return ladder, years


def summary_item(dp):
    cap = (dp or {}).get("capacity") or {}
    if not cap or cap.get("none"):
        return None
    c = compute(dp)
    y = c["years"][-1]
    a = f"현재 명목 캐파 {_cap(c['now'], cap['unit'])}, 착공 이상 증설 {_cap(c['add_firm'], cap['unit'])}. {y['period']} CAPEX는 매출의 {y['pct']:.1%}다."
    return {"q": "생산능력은 얼마나 늘어나나?", "a": a, "auto": True}
