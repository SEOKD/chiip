"""생산시설 위성 판독 — 면적·외관 진척도·면적 비교 캐파 추정 (마스터 지시 2026-11-03 "소유한 공장 또는 데이터센터의 위성 사진을 확보하라.
증설 진척도를 파악하고, 캐파 수치가 없으면 면적을 다른 시설과 비교해 추정하라")

영상 수집은 radar/site_imagery.py, 숫자는 여기서 계산한다. 모델은 시설 등록부에 위치·면적 근거와 영상 판독 단계만 쓴다.
datapack capacity.sites: [시설 id…] 또는 capacity.sites_none: "소유 시설이 없는 이유"
시설 등록부 knowledge/models/sites/<회사 id>.yaml:
  company: co-tsmc
  sites:
  - id: site-tsmc-arizona
    name: TSMC 애리조나
    kind: 팹                     # config kinds 중 하나
    class: 선단 로직 팹           # 같은 class끼리만 비교한다
    owned: 소유                  # 소유·임차·미확인
    center: [33.765, -112.161]
    half_km: 1.5
    location_source: 출처
    units:
    - name: 1공장
      role: 생산                 # 생산만 면적당 캐파에 쓴다. 유틸리티·창고는 지원
      footprint: {osm: [way/1]}  # 또는 {polygon: [[위도, 경도]…], source: 판독 영상} 또는 {area_m2: 100000, source: 공시}
      floors: 2                  # 선택. 양쪽 다 있을 때만 연면적으로 비교한다
      capacity: {value: 20000, unit: 웨이퍼/월, source: 출처, as_of: 2020-05}   # 없으면 생략 → 면적 비교로 추정
      stage_seen: 외장 완료       # config stages 중 하나. 영상을 보고 적는다
      seen_on: 2026-10-23        # 판독한 영상 날짜(수집본에 있어야 한다)
      seen_note: 무엇이 보였나
      box: [33.76, -112.17, 33.77, -112.16]   # 선택. 변화 측정 범위(남, 서, 북, 동)

금지표대로 외관 완공을 가동이나 판매 가능 물량으로 세지 않는다. 추정은 자체추론이고 공시 캐파에 섞지 않는다.
"""
import base64
import datetime
import json
import math
import statistics
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
SITES = ROOT / "knowledge" / "models" / "sites"
CONFIG = ROOT / "config" / "site_imagery.yaml"
UNKNOWN = "미확인"
M_PER_DEG = 111320.0


def config():
    return yaml.safe_load(CONFIG.read_text(encoding="utf-8"))


def _num(x):
    return float(x) if isinstance(x, (int, float)) and not isinstance(x, bool) else None


def registry(root=SITES):
    out = {}
    for p in sorted(Path(root).glob("*.yaml")):
        doc = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
        for s in doc.get("sites") or []:
            out[s["id"]] = {**s, "company": doc["company"]}
    return out


def latest(site_id, root=SITES):
    p = Path(root) / "latest" / f"{site_id}.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None


def footprints(site_id, root=SITES):
    p = Path(root) / "footprints" / f"{site_id}.json"
    return {x["osm"]: x for x in json.loads(p.read_text(encoding="utf-8"))["buildings"]} if p.exists() else {}


def ring_area(ring):
    """[[위도, 경도]…] 면적(㎡) — 시설 규모에서는 등장방형 근사로 충분하다"""
    lat0 = math.radians(sum(p[0] for p in ring) / len(ring))
    xy = [(p[1] * M_PER_DEG * math.cos(lat0), p[0] * M_PER_DEG) for p in ring]
    return abs(sum(a[0] * b[1] - b[0] * a[1] for a, b in zip(xy, xy[1:] + xy[:1]))) / 2


def unit_area(u, fp):
    """면적과 근거 — 공시 > 영상 판독 > OSM 건물 윤곽 순서가 아니라 등록부에 적힌 한 가지만 쓴다"""
    f = u.get("footprint") or {}
    if _num(f.get("area_m2")):
        return float(f["area_m2"]), str(f.get("source") or UNKNOWN)
    if f.get("polygon"):
        return ring_area(f["polygon"]), str(f.get("source") or "영상 판독")
    ids = f.get("osm") or []
    if ids and all(i in fp for i in ids):
        return sum(fp[i]["area_m2"] for i in ids), "OpenStreetMap 건물 윤곽"
    return None, None


def stage_share(u, cfg):
    return cfg["stages"].get(u.get("stage_seen"))


def _scale(a, b):
    """비교 면적 — 층수가 양쪽 다 있을 때만 연면적"""
    fa, fb = _num(a["unit"].get("floors")), _num(b["unit"].get("floors"))
    return (a["area"] * fa, b["area"] * fb) if fa and fb else (a["area"], b["area"])


def references(site, unit, area, reg, cfg, want_unit=None):
    """같은 class의 공시 캐파 시설 — 같은 회사가 있으면 그것만, 없으면 다른 회사"""
    me, refs = {"unit": unit, "area": area}, []
    for s in reg.values():
        if s.get("class") != site.get("class"):
            continue
        fp = footprints(s["id"]) if s["id"] != site["id"] else None
        for u in s.get("units") or []:
            c = u.get("capacity") or {}
            if (s["id"], u["name"]) == (site["id"], unit["name"]) or u.get("role") != "생산" or not _num(c.get("value")):
                continue
            if want_unit and c.get("unit") != want_unit:
                continue
            a, _ = unit_area(u, footprints(s["id"]) if fp is None else fp)
            if a:
                other = {"unit": u, "area": a}
                mine, theirs = _scale(me, other)
                refs.append({"site": s["name"], "name": u["name"], "same_company": s["company"] == site["company"], "capacity": float(c["value"]), "unit": c.get("unit"), "area": a, "density": c["value"] / theirs, "scaled": mine})
    same = [r for r in refs if r["same_company"]]
    return same or refs


def estimate(site, unit, area, reg, cfg):
    """면적당 캐파를 비교 시설에서 빌려 온다. 비교 대상이 없으면 None"""
    refs = references(site, unit, area, reg, cfg)
    units = {r["unit"] for r in refs}
    if not refs or len(units) > 1:   # 단위가 다르면 비교 불가
        return None
    ds = [r["density"] for r in refs]
    mid = statistics.median(ds) * refs[0]["scaled"]
    band = cfg["estimate"]["band_single"]
    low, high = (mid * (1 - band), mid * (1 + band)) if len(refs) == 1 else (min(ds) * refs[0]["scaled"], max(ds) * refs[0]["scaled"])
    return {"mid": mid, "low": low, "high": high, "unit": refs[0]["unit"], "refs": refs,
            "basis": "같은 회사 시설" if refs[0]["same_company"] else "다른 회사 같은 종류 시설", "confidence": "중" if len(refs) >= 2 and refs[0]["same_company"] else "하"}


def view_site(site, reg, cfg, late=None, fp=None):
    """시설 한 곳의 호기별 면적·캐파·진척"""
    late = late if late is not None else latest(site["id"]) or {}
    fp = fp if fp is not None else footprints(site["id"])
    rows = []
    for u in site.get("units") or []:
        area, src = unit_area(u, fp)
        c = u.get("capacity") or {}
        known = _num(c.get("value")) is not None
        est = estimate(site, u, area, reg, cfg) if area and not known and u.get("role") == "생산" else None
        rows.append({"unit": u, "name": u["name"], "area": area, "area_source": src, "known": c if known else None, "estimate": est,
                     "stage": u.get("stage_seen"), "share": stage_share(u, cfg), "seen_on": str(u["seen_on"]) if u.get("seen_on") else None, "activity": (late.get("units") or {}).get(u["name"])})
    return rows


def check_site(site, cfg, late, today=None):
    """리포트 전 검사 — 위치가 틀렸거나 판독이 낡았으면 멈춘다"""
    today = today or datetime.date.today()
    name = site["name"]
    if site.get("kind") not in cfg["kinds"]:
        raise ValueError(f"시설 {name}: kind는 {cfg['kinds']} 중 하나다")
    if not late or not late.get("images"):
        raise ValueError(f"시설 {name}: 영상이 없다 — py radar/site_imagery.py --site {site['id']}")
    if (today - datetime.date.fromisoformat(late["as_of"])).days > cfg["estimate"]["max_age_days"]:
        raise ValueError(f"시설 {name}: 영상이 낡았다 — py radar/site_imagery.py --site {site['id']}")
    dates = [i["date"] for i in late["images"] + (late.get("aerial") or [])]
    for u in site.get("units") or []:
        if u.get("stage_seen") not in cfg["stages"]:
            raise ValueError(f"시설 {name} {u.get('name')}: stage_seen은 {list(cfg['stages'])} 중 하나다")
        seen = str(u.get("seen_on"))
        if seen not in dates:
            raise ValueError(f"시설 {name} {u['name']}: seen_on {seen}은 수집한 영상 날짜가 아니다({dates})")
        if (datetime.date.fromisoformat(max(dates)) - datetime.date.fromisoformat(seen)).days > cfg["estimate"]["stage_stale_days"]:
            raise ValueError(f"시설 {name} {u['name']}: 판독이 낡았다 — 최신 영상을 다시 판독한다")


def check(cap, reg=None, cfg=None, today=None):
    if cap.get("sites_none"):
        return
    ids = cap.get("sites")
    if not ids:
        raise ValueError("datapack capacity에 sites(시설 id 목록)가 필요하다 — 소유 시설이 없으면 sites_none에 이유 (scripts/tenbagger/site_view.py 맨 위)")
    reg, cfg = reg if reg is not None else registry(), cfg or config()
    for i in ids:
        if i not in reg:
            raise ValueError(f"시설 {i}가 등록부에 없다(knowledge/models/sites/)")
        check_site(reg[i], cfg, latest(i), today)


def _area(a):
    return UNKNOWN if a is None else f"{a / 10000:,.1f}만㎡"


def _cap(v):
    return f"{v:,.0f}"


def cap_text(r):
    if r["known"]:
        return f"{_cap(r['known']['value'])} {r['known'].get('unit', '')}".strip()
    e = r["estimate"]
    return f"추정 {_cap(e['low'])}~{_cap(e['high'])} {e['unit']}" if e else UNKNOWN


def _units(dp, reg=None, cfg=None):
    cap = (dp or {}).get("capacity") or {}
    reg, cfg = reg if reg is not None else registry(), cfg or config()
    return [(reg[i], view_site(reg[i], reg, cfg)) for i in cap.get("sites") or []], cfg


def blocks(dp, reg=None, cfg=None):
    views, cfg = _units(dp, reg, cfg)
    if not views:
        return []
    B = []
    for site, rows in views:
        B.append({"type": "table", "title": f"위성 판독: {site['name']}", "headers": ["시설", "면적", "캐파", "외관 진척", "판독일"],
                  "rows": [[r["name"], _area(r["area"]), cap_text(r), f"{r['stage']} {r['share']:.0%}" if r["share"] is not None else UNKNOWN, r["seen_on"] or UNKNOWN] for r in rows]})
        for r in rows:
            e = r["estimate"]
            if e:
                ref = ", ".join(f"{x['site']} {x['name']}({_cap(x['capacity'])} {x['unit']}, {_area(x['area'])})" for x in e["refs"])
                B.append({"type": "p", "text": f"{r['name']} 캐파는 {e['basis']} {ref}의 면적당 캐파로 잰 추정이다. 중앙값 {_cap(e['mid'])} {e['unit']}, 확신도 {e['confidence']}."})
        active = [(r["name"], r["activity"]["recent"]) for r in rows if (r["activity"] or {}).get("recent") is not None and r["activity"]["recent"] >= cfg["change"]["active_share"]]
        if active:
            B.append({"type": "p", "text": "최근 6개월 영상 변화: " + ", ".join(f"{n} {v:.0%}" for n, v in active) + "."})
    B.append({"type": "p", "text": f"외관 진척은 영상에 보이는 공사 단계다. 장비 반입·수율·가동은 영상으로 알 수 없어 판매 가능 물량으로 세지 않는다. 건물 면적: {cfg['credit']['osm']}."})
    return B


def headline(dp, unit):
    """공시 캐파가 없을 때 쓰는 합계 — 같은 단위만 더한다"""
    views, _ = _units(dp)
    rows = [r for _, rs in views for r in rs if r["estimate"] and r["estimate"]["unit"] == unit]
    if not rows:
        return None
    total = lambda k: sum(r["estimate"][k] for r in rows)
    return f"면적 비교로 추정한 시설 {len(rows)}곳의 캐파 합계는 {_cap(total('low'))}~{_cap(total('high'))} {unit}(공시 값이 아니다)."


def sources(dp):
    views, _ = _units(dp)
    out = {str(s["location_source"]) for s, _ in views}
    return sorted(out | {str(r["known"]["source"]) for _, rs in views for r in rs if r["known"]})


def credit(late, cfg):
    c, out = cfg["credit"], []
    if late.get("images"):
        out.append(c["sentinel"].format(year=late["images"][-1]["date"][:4]))
    return " · ".join(out)


def chart(dp, reg=None, cfg=None):
    """처음과 최신 영상을 나란히 — 파일은 이 PC의 radar/state/sites에 있고 렌더 때 넣는다"""
    cap = (dp or {}).get("capacity") or {}
    ids = (cap.get("sites") or [])
    if not ids:
        return None
    reg, cfg = reg if reg is not None else registry(), cfg or config()
    panels = []
    for i in ids[:cfg["estimate"]["chart_sites"]]:
        late = latest(i)
        if not late or len(late.get("images") or []) < 1:
            continue
        pair = [late["images"][-1]] if len(late["images"]) == 1 else [late["images"][0], late["images"][-1]]
        panels.append({"name": reg[i]["name"], "credit": credit(late, cfg), "images": [{"path": x["path"], "date": x["date"]} for x in pair]})
    return {"kind": "satellite", "title": "위성 판독", "panels": panels} if panels else None


def image_uri(path):
    p = ROOT / path
    return "data:image/png;base64," + base64.b64encode(p.read_bytes()).decode() if p.exists() else None
