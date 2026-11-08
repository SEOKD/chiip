"""리포트 이미지·BOM 블록 (마스터 지시 2026-11-08, 지시서 5절 · 산업판 5절) — 종목·산업 리포트가 같이 쓴다.

블록:
  {"type":"image","kind","file","title","callouts":[{"no","x","y","own"}],"legend":[[no,part,own]],"caption","photo":"A"}
     → report_html이 base64로 넣고 SVG 이름표(번호 원·지시선)를 겹친다. 위치(callouts)를 모르면 번호 범례만.
  {"type":"bom","scope":"company|industry","rows","equip","candidates","as_of","source_note"}
     → BOM 표. '추정' 행은 회색. 산업판은 공급사 여러 곳·Chiip 감시 여부·공정·장비 구역·후보 메모.
번호: 차트 그림 번호와 겹치지 않게 '사진 A·B·C'.
넣는 자리(종목, 2026-11-08 마스터 지시): 제품·분해도 사진 = 한눈에 보기의 제품·서비스 포트폴리오 바로 다음(report_layout), BOM 표 = '공급망 병목' 절 첫머리. 이름표 = 컴포넌트 위치에 '번호 + 부품 이름'(image_qa.locate).
이미지가 없거나 검수·승인 전이면 그 자리에 '이미지 없음(사유)' 한 줄만 — 리포트 생성은 멈추지 않는다.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import image_check as C  # noqa: E402
import product_images as P  # noqa: E402

LETTERS = "ABCDEFGH"
UNKNOWN = "미공개"


def _watch_ids():
    sys.path.insert(0, str(P.ROOT / "radar"))
    from pollers import common
    return {r["entity_id"] for r in common.load_watchlist()} | set(common.discovery_entities() or [])


def _parts(t):
    """이름표를 붙일 부품 — 분해도는 그 BOM, 제품 개념도는 datapack 제품 BOM(있을 때)"""
    if t["kind"] == "exploded":
        return P.ordered(t["bom"])
    if t["kind"] != "product":
        return []
    try:
        import json
        dp = json.loads((P.company_dir(t["id"]) / "datapack.json").read_text(encoding="utf-8"))
        p = next((x for x in ((dp.get("narrative") or {}).get("lead") or {}).get("products") or [] if x.get("name") == t["name"]), None)
        bom = (p or {}).get("bom") or (P.auto_bom(t["id"], p, discover=False) if p else None)   # datapack BOM이 없으면 웹 검색으로 찾아 둔 부품(새로 찾지는 않는다)
        return P.ordered(bom) if bom else []
    except (OSError, ValueError, KeyError, TypeError):
        return []


def _callouts(t, m, parts, c):
    """메타에 위치가 없으면 Gemini 비전으로 한 번 찾아 메타에 저장(2026-11-08 마스터 지시 — 컴포넌트 위에 텍스트 설명)"""
    if not parts or (m.get("callouts") is not None and (m["callouts"] or m.get("located_by"))):   # 위치가 있거나 이미 찾아봤으면 그대로
        return m.get("callouts") or []
    try:
        import json
        import image_qa
        pos = image_qa.locate(t["dir"] / m["file"], [(x["no"], x.get("part_en") or x["part"]) for x in parts], c)
        m["callouts"], m["located_by"] = pos, c.get("locate_model") or c.get("qa_model")
        P.meta_path(t).write_text(json.dumps(m, ensure_ascii=False, indent=1), encoding="utf-8")
        return pos
    except Exception:   # 위치를 못 찾으면 번호 범례만 — 리포트는 멈추지 않는다
        return []


def image_block(t, m, letter, c=None):
    c = c or P.cfg()
    b = {"type": "image", "kind": t["kind"], "file": str((t["dir"] / m["file"]).relative_to(P.ROOT)).replace("\\", "/"), "photo": letter,
         "title": f"{t['name']} {'분해 개념도' if t['kind'] == 'exploded' else '개념도'}", "caption": c["caption_fixed"]}
    parts = _parts(t)
    if parts:
        own = {x["no"] for x in parts if x.get("this_company")}
        name = {x["no"]: x["part"] for x in parts}
        b["legend"] = [[x["no"], x["part"], x["no"] in own] for x in parts]
        b["callouts"] = [dict(x, own=x["no"] in own, label=name.get(x["no"], "")) for x in _callouts(t, m, parts, c) if x["no"] in name]
    return b


def bom_block(bom, scope, watch=None):
    items = sorted(bom.get("items") or [], key=lambda x: x.get("no") or 0)
    if scope == "company":
        rows = [[x.get("no"), x["part"], x.get("role") or "", x.get("supplier") or "미확인", "이 회사" if x.get("this_company") else (x.get("upstream") or ("이 회사 제품의 부품" if bom.get("this_company_product") else "")),
                 f"{x['cost_share'] * 100:.0f}%" if isinstance(x.get("cost_share"), (int, float)) else UNKNOWN, x.get("source") or "", x.get("confidence") or "추정"]
                for x in items if x.get("kind") not in ("장비", "소재")]
        return {"type": "bom", "scope": scope, "rows": rows, "as_of": bom.get("as_of"), "source_note": (bom.get("source_note") or "") + (f" · 근거: {bom['basis']}" if bom.get("basis") else ""),
                "own_none": bool(bom.get("this_company_none"))}
    watch = watch if watch is not None else _watch_ids()
    rows, equip, cands = [], [], []
    for x in items:
        sups = x.get("suppliers") or []
        names = ", ".join(f"{s['name']}" + ("" if s.get("source") else "(추정)") for s in sups) or "미확인"
        watched = [i for i in x.get("chiip_ids") or [] if i in watch]
        share = "; ".join(s["share_note"] for s in sups if s.get("share_note")) or UNKNOWN
        row = [x.get("no"), x["part"], x.get("role") or "", names, "감시 " + str(len(watched)) if watched else "—", share, x.get("source") or "", x.get("confidence") or "추정"]
        (equip if x.get("kind") in ("장비", "소재") else rows).append(row)
        ids = x.get("chiip_ids") or []
        for j, s in enumerate(sups):   # 감시 목록 밖 상장사 → 후보 메모(자동으로 감시 목록에 넣지 않는다). chiip_ids는 suppliers와 같은 순서
            sid = s.get("chiip_id") or (ids[j] if j < len(ids) else None)
            if s.get("ticker") and sid not in watch:
                cands.append(f"{s['name']}({s['ticker']}) — {x['part']}")
    return {"type": "bom", "scope": scope, "rows": rows, "equip": equip, "candidates": sorted(set(cands)), "as_of": bom.get("as_of"), "source_note": bom.get("source_note") or ""}


def missing(why, what):
    return {"type": "p", "text": f"이미지 없음({why}) — {what}"}


def company_blocks(cid, c=None):
    """{'narrative': [...], 'supply': [...]} — 대상이 없으면 빈 목록"""
    c = c or P.cfg()
    try:
        ts = P.targets_company(cid, c)
    except (OSError, ValueError, KeyError):
        return {"narrative": [], "supply": []}
    out, k, gaps = {"narrative": [], "supply": []}, 0, {}
    for t in ts:
        m, why = C.usable(t, c)
        place = "supply" if t["kind"] == "exploded" else "narrative"
        if m:
            out[place].append(image_block(t, m, LETTERS[k], c))
            k += 1
        else:
            gaps.setdefault(place, {}).setdefault(why, []).append(t["name"])
        if t["kind"] == "exploded":
            out[place].append(bom_block(t["bom"], "company"))
    for place, by in gaps.items():   # 절마다 한 줄 — '이미지 없음(사유) — 제품A·제품B'
        for why, names in by.items():
            out[place].insert(0, missing(why, "·".join(dict.fromkeys(names))))
    # 확인 부품이 6개 미만이라 분해도를 그리지 않는 제품도 BOM 표는 넣는다
    dp = __import__("json").loads((P.company_dir(cid) / "datapack.json").read_text(encoding="utf-8"))
    for p in ((dp.get("narrative") or {}).get("lead") or {}).get("products") or []:
        if p.get("bom") and 0 < len(P.confirmed(p["bom"])) < c["min_confirmed_parts"]:
            out["supply"].append({"type": "p", "text": f"{p['name']}: 출처 있는 부품이 {len(P.confirmed(p['bom']))}개라 분해도 대신 BOM 표만 싣는다."})
            out["supply"].append(bom_block(p["bom"], "company"))
    return out


def product_blocks(slug, start=0, view=None, c=None):
    """산업 리포트 — 한 제품의 이미지·BOM 블록과 다음 사진 번호"""
    c = c or P.cfg()
    import json
    bom = json.loads((P.product_dir(slug) / "bom.json").read_text(encoding="utf-8"))
    B, k = [], start
    for t in P.targets_product(slug, view, c):
        m, why = C.usable(t, c)
        if m:
            B.append(image_block(t, m, LETTERS[k], c))
            k += 1
        else:
            B.append(missing(why, t["name"]))
    if len(P.confirmed(bom)) < c["min_confirmed_parts"]:
        B.append({"type": "p", "text": f"출처 있는 부품이 {len(P.confirmed(bom))}개라 분해도 대신 BOM 표만 싣는다."})
    B.append(bom_block(bom, "industry"))
    return B, k
