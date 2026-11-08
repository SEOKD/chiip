"""리포트 이미지 자동 눈 검수 — Gemini 비전(Vertex)이 그림을 보고 판정 (마스터 지시 2026-11-08 "검수에 실패한 이미지가 없도록 웬만하면 다 생성되도록")

사람(또는 Claude Read) 눈 검수를 기다리면 정기 회차에서 이미지가 '눈 검수 대기'로 빠진다. 같은 항목을 비전 모델이 JSON으로 답한다:
  글자·숫자(text) · 로고·상표(logo) · 사람(people) · 사진 같은 연출(photoreal) · 분해도면 분리된 부품 덩어리 수(parts)·축을 따라 한 줄로 벌어졌나(single_axis)
판정은 규칙이 한다(모델의 '좋다/나쁘다'를 그대로 믿지 않는다). 실패 사유는 product_images.ensure가 다음 시도의 설명문 보강에 쓴다.
비용: gemini-3.1-flash-lite 이미지 1장 입력 — 장당 1센트 미만(장부에 qa로 남긴다).
"""
import json
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
    v = (cfg or {}).get("vertex") or {}
    cl = genai.Client(vertexai=True, project=v["project"], location=v.get("location", "global"))
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
