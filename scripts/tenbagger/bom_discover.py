"""제품 구성 부품 탐색 — 회사 기술 자료·업계 기술 자료·웹 검색 (마스터 지시 2026-11-08 "BOM에 부품 1개라도 있으면 분해도에 넣어라.
BOM이라는 재무 지표로서 잡히는 부품군을 넘어, 제품을 구성하는 부품을 회사의 기술 자료, 업계의 기술 자료, 웹 검색으로 파악해 분해도에 그릴 수 있도록")

datapack에 bom이 없는 제품은 Gemini(Vertex) + Google 검색 그라운딩으로 물리적 구성 부품을 찾는다.
  - 모델에게 부품마다 그 부품을 이름으로 언급하는 페이지 URL을 요구한다.
  - 그 URL의 도메인이 실제 검색 근거(grounding chunks)에 있으면 '확인'(basis: 웹 검색 근거), 없으면 '추정'(분해도 이름표에서 빠지고 표에만 회색).
  - 회사 자료(제품 설명서·데이터시트·IR)를 먼저 찾게 하고, 없으면 업계 기술 자료를 쓰게 한다.
결과는 knowledge/models/companies/<id>/bom_auto.json(제품 이름별) — datapack bom이 있으면 그쪽이 먼저다. 90일 지나면 다시 찾는다.
공급사·원가 비중은 여기서 만들지 않는다(웹 검색으로는 공시 수준 확인이 안 된다 — '미확인'·'미공개').
"""
import json
import sys
import re
import warnings
from datetime import date
from pathlib import Path
from urllib.parse import urlparse

DISCOVER_MODEL = "gemini-3.5-flash"
ASK = ("You are a hardware engineer writing a parts breakdown for an investment report. Product: {name} made by {company}. Description: {what}. "
       "Use web search. Prefer the company's own technical documents (datasheets, product brochures, manuals, investor materials); "
       "if they do not list components, use industry technical sources (standards bodies, teardown summaries, engineering references). "
       "List the main PHYSICAL components of this product in physical order from top to bottom (or outside to inside), between 4 and 10 items. "
       "For each give the exact URL of a page that names that component for this product or this product type. "
       "Return ONLY a JSON array, no prose: "
       '[{{"part_en": "...", "part_ko": "Korean name", "role_ko": "Korean, one short line on what it does", "source_url": "https://..."}}], '
       'then on the last line: {{"name_en": "English product name"}}')


def _domain(u):
    try:
        return urlparse(u).netloc.lower().removeprefix("www.")
    except ValueError:
        return ""


def _json_parts(text):
    m = re.search(r"\[\s*\{.*\}\s*\]", text, re.S)
    items = json.loads(m.group(0)) if m else []
    n = re.search(r'\{\s*"name_en"\s*:\s*"([^"]+)"\s*\}', text)
    return items, (n.group(1) if n else None)


STOP = {"system", "assembly", "unit", "the", "and", "of", "for", "with", "module", "components", "component", "main"}


def page_names(url, part_en, cache):
    """robots.txt를 지키며(jp_ir_qa.fetch) 페이지를 열어 부품 이름의 핵심 낱말이 있으면 True"""
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "radar"))
    try:
        if url not in cache:
            from pollers import jp_ir_qa as qa
            cache[url] = qa._text(qa.fetch(url, 20)).lower()
        text = cache[url]
    except Exception:
        cache[url] = ""
        return False
    words = [w for w in re.findall(r"[a-z]{4,}", part_en.lower()) if w not in STOP]
    return bool(text) and bool(words) and any(w in text for w in words)


def discover(name, company, what, cfg):
    """→ (bom dict, name_en). bom = {as_of, layers_order, items[...], source_note, basis, this_company_product}"""
    from google import genai
    from google.genai import types
    warnings.filterwarnings("ignore", message=".*quota project.*")
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import vertex_auth   # VERTEX_API_KEY 우선(로그인 만료 없음), 없으면 gcloud 로그인 — 2026-11-08
    cl = vertex_auth.client(cfg)
    r = cl.models.generate_content(model=(cfg.get("bom_auto") or {}).get("model", DISCOVER_MODEL), contents=ASK.format(name=name, company=company, what=what or name),
                                   config=types.GenerateContentConfig(tools=[types.Tool(google_search=types.GoogleSearch())], temperature=0))
    gm = r.candidates[0].grounding_metadata if r.candidates else None
    grounded = {}
    for ch in (gm.grounding_chunks or []) if gm else []:
        w = getattr(ch, "web", None)
        if w and (w.title or w.uri):
            grounded[(w.title or "").lower().removeprefix("www.")] = w.uri
    items, name_en = _json_parts(r.text or "")
    out = []
    pages = {}
    for i, x in enumerate(items[: (cfg.get("bom_auto") or {}).get("max_parts", 10)], 1):
        dom = _domain(x.get("source_url", ""))
        ok = bool(dom) and any(dom == g or dom.endswith("." + g) or g.endswith(dom) for g in grounded)
        if not ok and x.get("source_url"):   # 검색 근거 목록이 비면(2026-11-08 Vertex 3.5-flash) 페이지를 직접 열어 부품 이름이 있는지 본다
            ok = page_names(x["source_url"], x.get("part_en") or "", pages)
        out.append({"no": i, "part": x.get("part_ko") or x.get("part_en"), "part_en": x.get("part_en"), "role": x.get("role_ko") or "",
                    "supplier": "미확인", "this_company": False, "cost_share": None,
                    "source": f"{x.get('source_url')} (웹 검색 근거)" if ok else (x.get("source_url") or ""),
                    "confidence": "확인" if ok else "추정", "basis": "웹 검색(Gemini 검색 그라운딩 + 페이지 대조)"})
    bom = {"as_of": date.today().isoformat(), "layers_order": "위→아래", "items": out, "basis": "웹 검색(회사·업계 기술 자료)",
           "source_note": "구성 부품은 Gemini 검색 그라운딩으로 찾은 회사·업계 기술 자료. 검색 근거에 도메인이 있거나, 출처 페이지를 직접 열어 부품 이름이 확인된 것만 '확인'. 공급사·원가 비중은 공시 수준 확인 전이라 미확인",
           "this_company_product": True, "grounded_domains": sorted(grounded)}
    return bom, name_en
