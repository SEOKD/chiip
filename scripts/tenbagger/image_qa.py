"""리포트 이미지 자동 눈 검수 — Gemini 비전(Vertex)이 그림을 보고 판정 (마스터 지시 2026-11-08 "검수에 실패한 이미지가 없도록 웬만하면 다 생성되도록")

사람(또는 Claude Read) 눈 검수를 기다리면 정기 회차에서 이미지가 '눈 검수 대기'로 빠진다. 같은 항목을 비전 모델이 JSON으로 답한다:
  글자·숫자(text) · 로고·상표(logo) · 사람(people) · 사진 같은 연출(photoreal) · 분해도면 분리된 부품 덩어리 수(parts)·축을 따라 한 줄로 벌어졌나(single_axis)
판정은 규칙이 한다(모델의 '좋다/나쁘다'를 그대로 믿지 않는다). 실패 사유는 product_images.ensure가 다음 시도의 설명문 보강에 쓴다.
비용: gemini-3.1-flash-lite 이미지 1장 입력 — 장당 1센트 미만(장부에 qa로 남긴다).
"""
import json
import sys
import warnings
from pathlib import Path

QA_MODEL = "gemini-3.1-flash-lite"
SCHEMA = {"type": "OBJECT", "properties": {
    "text": {"type": "BOOLEAN"}, "logo": {"type": "BOOLEAN"}, "people": {"type": "BOOLEAN"}, "photoreal": {"type": "BOOLEAN"},
    "parts": {"type": "INTEGER"}, "single_axis": {"type": "BOOLEAN"}, "note": {"type": "STRING"}},
    "required": ["text", "logo", "people", "photoreal", "parts", "single_axis", "note"]}
ASK = ("You are a strict QA reviewer for technical illustrations used in an investment research report. Look at the image and answer as JSON: "
       "text = any readable letters, words, digits or numbers anywhere (including on parts, labels, screens); "
       "logo = any brand logo, trademark, wordmark or brand-like emblem; people = any human or human body part; "
       "photoreal = it looks like a real photograph rather than an illustration/render; "
       "parts = number of clearly separated component pieces if it is an exploded view (0 if not exploded); "
       "single_axis = components are separated along one straight axis (true if not exploded); note = one short sentence.")


def review(path, kind, expect_parts=None, cfg=None):
    """→ {ok, reasons[], raw}. reasons는 'text'·'logo'·'people'·'photoreal'·'parts'·'axis' 중"""
    from google import genai
    from google.genai import types
    warnings.filterwarnings("ignore", message=".*quota project.*")
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import vertex_auth   # VERTEX_API_KEY 우선(로그인 만료 없음), 없으면 gcloud 로그인 — 2026-11-08
    cl = vertex_auth.client(cfg)
    p = Path(path)
    mime = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png", ".webp": "image/webp"}.get(p.suffix.lower(), "image/png")
    r = cl.models.generate_content(model=(cfg or {}).get("qa_model", QA_MODEL),
                                   contents=[types.Part.from_bytes(data=p.read_bytes(), mime_type=mime), ASK],
                                   config=types.GenerateContentConfig(response_mime_type="application/json", response_schema=SCHEMA, temperature=0))
    raw = json.loads(r.text)
    reasons = [k for k in ("text", "logo", "people", "photoreal") if raw.get(k)]
    if kind == "exploded":
        if expect_parts and abs(int(raw.get("parts") or 0) - expect_parts) > 1:
            reasons.append("parts")
        if not raw.get("single_axis", True):
            reasons.append("axis")
    return {"ok": not reasons, "reasons": reasons, "raw": raw}


FIX = {   # 실패 사유 → 다음 시도 설명문에 덧붙일 문장
    "text": "Absolutely no text of any kind: no letters, no digits, no labels, no markings, no screens showing characters; all surfaces plain.",
    "logo": "No logos, emblems, badges or brand marks anywhere; all surfaces unbranded and plain.",
    "people": "No humans, hands or figures anywhere in the image.",
    "photoreal": "Render as a clean vector-style technical illustration with flat shading and outlines, clearly not a photograph.",
    "parts": "Show exactly {n} clearly separated components, evenly spaced, nothing else.",
    "axis": "All components stacked along a single vertical axis with equal gaps, like an assembly diagram.",
}


def fixes(reasons, n=None):
    return " ".join(FIX[r].format(n=n) for r in reasons if r in FIX)


LOCATE = ("This is an illustration of a product or an exploded assembly. For each numbered component in the list, give the point (x, y) at the center of "
          "where that component appears, as fractions of image width and height (0 = left/top, 1 = right/bottom). Use null for a component you cannot see. "
          "Components: {parts}")


def locate(path, parts, cfg=None):
    """컴포넌트 이름표 위치 — [{no, x, y}](마스터 지시 2026-11-08 "각 컴포넌트 위에 텍스트로 설명"). 보이지 않는 부품은 뺀다"""
    from google.genai import types
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import vertex_auth
    cl = vertex_auth.client(cfg)
    p = Path(path)
    mime = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png", ".webp": "image/webp"}.get(p.suffix.lower(), "image/png")
    schema = {"type": "ARRAY", "items": {"type": "OBJECT", "properties": {"no": {"type": "INTEGER"}, "x": {"type": "NUMBER", "nullable": True}, "y": {"type": "NUMBER", "nullable": True}}, "required": ["no"]}}
    listing = "; ".join(f"{no}. {name}" for no, name in parts)
    import time
    for wait in (0, 8, 25):   # 429(한도 초과)는 잠깐 쉬고 다시 — 과금 없는 오류
        time.sleep(wait)
        try:
            r = cl.models.generate_content(model=(cfg or {}).get("locate_model") or (cfg or {}).get("qa_model", QA_MODEL), contents=[types.Part.from_bytes(data=p.read_bytes(), mime_type=mime), LOCATE.format(parts=listing)],
                                           config=types.GenerateContentConfig(response_mime_type="application/json", response_schema=schema, temperature=0))
            break
        except Exception as e:
            if getattr(e, "code", None) != 429 or wait == 25:
                raise
    ok = {int(no) for no, _ in parts}
    return [{"no": int(x["no"]), "x": round(float(x["x"]), 3), "y": round(float(x["y"]), 3)} for x in json.loads(r.text)
            if int(x.get("no") or 0) in ok and x.get("x") is not None and x.get("y") is not None and 0 <= float(x["x"]) <= 1 and 0 <= float(x["y"]) <= 1]
