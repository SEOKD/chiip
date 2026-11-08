"""리포트 제품·서비스 이미지와 BOM 분해도 생성 (마스터 지시 2026-11-08, 지시서 '리포트 제품 이미지·BOM 분해도' v1.2 · 산업판 v1.1)

원칙(ADR-017): 그림은 Gemini가 글자 없는 개념도로만 그리고, 부품 이름·번호·공급사·출처는 Chiip이 BOM 사실로 SVG 이름표·표를 얹는다.
  출처 없는 부품('추정')은 분해도 이름표에 올리지 않는다. 모든 이미지에 고정 캡션. 로고·상표·글자·숫자·실존 인물·사진 같은 연출 금지.
비용 두 겹: 구글 예산 한도 ₩13,000/월(마스터 설정, 손대지 않는다) + Chiip 장부 월 $9(knowledge/models/images/ledger.csv).
  생성 전에 이번 달 합계 + 예상이 한도를 넘으면 만들지 않고 over_budget. 산업 몫(scope=industry)은 한도의 40%까지.
  구글이 결제·한도 오류(402·서비스 일시중지)를 주면 그달 생성을 모두 멈추고 google_cap을 남긴다. 같은 오류로 재시도하지 않는다.
대상:
  회사 — datapack narrative.lead.products(제품 최대 2·서비스 1), 분해도는 bom의 '확인' 부품 6개 이상인 제품만(최대 2)
  제품 단위(산업 리포트) — knowledge/models/products/<slug>/bom.json. 종목·산업 리포트가 같은 제품이면 같은 이미지를 쓴다(0원).
캐시: 설명문+모델+크기+보기 해시가 같으면 다시 만들지 않는다. BOM as_of 90일 초과·BOM 변경이면 분해도만 다시.
수동 경로: 마스터가 Gemini 앱에서 만든 그림을 같은 폴더에 두고 메타에 "source": "Gemini 앱 수동 생성"이면 그대로 쓴다.
키: D:\\local-only\\secrets\\.env의 GEMINI_API_KEY를 common.load_env()로만 읽는다. 출력·로그·파일·커밋 금지.
사용:
  py scripts/tenbagger/product_images.py plan <id> | plan --product <slug>
  py scripts/tenbagger/product_images.py make <id> [--batch] [--only exploded|product|service]
  py scripts/tenbagger/product_images.py make --product <slug>[,<slug2> --pair] [--batch] [--view cross-section] [--only …]
  py scripts/tenbagger/product_images.py fetch-batch · ledger
"""
import argparse
import base64
import csv
import hashlib
import io
import json
import sys
import urllib.error
import urllib.request
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "radar"))
CFG = ROOT / "config" / "report_images.yaml"
IMG = ROOT / "knowledge" / "models" / "images"
LEDGER = IMG / "ledger.csv"
JOBS = IMG / "batch_jobs.json"
API = "https://generativelanguage.googleapis.com/v1beta"
KST = timezone(timedelta(hours=9))
COLS = ["date", "scope", "id", "kind", "model", "size", "batch", "usd", "status"]
STOP = ("google_cap", "billing", "model_rejected")   # 이번 달 생성을 멈추는 상태


def cfg():
    return yaml.safe_load(CFG.read_text(encoding="utf-8"))


def now():
    return datetime.now(KST)


# ── 대상 ──
def company_dir(cid):
    return ROOT / "knowledge" / "models" / "companies" / cid


def product_dir(slug):
    return ROOT / "knowledge" / "models" / "products" / slug


def confirmed(bom):
    return [x for x in (bom or {}).get("items") or [] if x.get("confidence") == "확인" and x.get("kind") not in ("장비", "소재")]


def ordered(bom):
    """분해도에 그릴 순서 — '확인' 부품을 no 순(layers_order가 그 방향)"""
    return sorted(confirmed(bom), key=lambda x: x.get("no") or 0)


def targets_company(cid, c=None):
    c = c or cfg()
    dp = json.loads((company_dir(cid) / "datapack.json").read_text(encoding="utf-8"))
    prods = ((dp.get("narrative") or {}).get("lead") or {}).get("products") or []
    out, mx = [], c["per_company_max"]
    goods = [p for p in prods if p.get("kind") != "서비스"][:mx["product"]]
    svcs = [p for p in prods if p.get("kind") == "서비스"][:mx["service"]]
    for i, p in enumerate(goods, 1):
        out.append({"scope": "company", "id": cid, "kind": "product", "n": i, "name": p["name"], "what": p.get("what_en") or p.get("what") or p["name"], "name_en": p.get("name_en"), "dir": company_dir(cid) / "images"})
    for i, p in enumerate(svcs, 1):
        out.append({"scope": "company", "id": cid, "kind": "service", "n": i, "name": p["name"], "use": p.get("use_en") or p.get("use") or p.get("what") or p["name"], "name_en": p.get("name_en"), "dir": company_dir(cid) / "images"})
    n = 0
    for p in prods:
        if p.get("bom") and len(confirmed(p["bom"])) >= c["min_confirmed_parts"] and n < mx["exploded"]:
            n += 1
            out.append({"scope": "company", "id": cid, "kind": "exploded", "n": n, "name": p["name"], "bom": p["bom"], "dir": company_dir(cid) / "images"})
    return out


def targets_product(slug, view=None, c=None):
    c = c or cfg()
    bom = json.loads((product_dir(slug) / "bom.json").read_text(encoding="utf-8"))
    d = product_dir(slug) / "images"
    out = [{"scope": "industry", "id": slug, "kind": "product", "n": 1, "name": bom["product"], "what": bom.get("what") or bom["product"], "dir": d}]
    if len(confirmed(bom)) >= c["min_confirmed_parts"]:
        out.append({"scope": "industry", "id": slug, "kind": "exploded", "n": 1, "name": bom["product"], "bom": bom, "dir": d, "view": view})
    return out


# ── 설명문 ──
def prompt(t, c=None):
    """영어로 보낸다 — datapack에 name_en·what_en·use_en·part_en이 있으면 그것을, 없으면 한국어 원문(Gemini가 읽는다)"""
    c = c or cfg()
    st = c["style"]
    t = dict(t, name=t.get("name_en") or t["name"])
    if t["kind"] == "product":
        return f"{t['what']}. Generic unbranded product render of a {t['name']}, {st}. No text, no letters, no numbers, no logos, no people. Not photorealistic."
    if t["kind"] == "service":
        return f"{t['use']} scene showing how {t['name']} is used, {st}, no text, no logos, no identifiable people. Not photorealistic."
    parts = ", ".join(x["part_en"] if x.get("part_en") else x["part"] for x in ordered(t["bom"]))
    order = t["bom"].get("layers_order") or "top to bottom"
    generic = " Generic, no brand features." if t["scope"] == "industry" else ""
    if t.get("view") == "cross-section":
        return (f"Cross-section cutaway illustration of a generic {t['name']}, layers stacked in this order ({order}): {parts}. {st}.{generic} "
                "Leave clear empty space beside each layer for callout labels. No text, no letters, no numbers, no logos.")
    return (f"Exploded isometric technical illustration of a generic {t['name']}, components separated along one vertical axis in this order ({order}): {parts}. {st}.{generic} "
            "Leave clear empty space beside each component for callout labels. No text, no letters, no numbers, no logos.")


def model_size(t, c=None):
    c = c or cfg()
    k = "exploded" if t["kind"] == "exploded" else "default"
    return c["models"][k], c["size"][k], c["aspect"][t["kind"]]


def est_cost(t, batch, c=None):
    c = c or cfg()
    m, s, _ = model_size(t, c)
    return round(c["price_usd"][m][s] * (c["batch_discount"] if batch else 1), 4)


def key_of(t, c=None):
    m, s, a = model_size(t, c)
    return hashlib.sha1(json.dumps([prompt(t, c), m, s, a, t.get("view")], ensure_ascii=False).encode()).hexdigest()[:16]


def stem(t):
    return f"{t['kind']}_{t['n']}"


def meta_path(t):
    return t["dir"] / f"{stem(t)}.json"


def load_meta(t):
    p = meta_path(t)
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None


def cached(t, c=None):
    """같은 해시의 이미지가 있으면 메타, 분해도 BOM이 90일 넘었으면 None. 수동 생성은 항상 쓴다"""
    m = load_meta(t)
    if not m or not (t["dir"] / m.get("file", "")).exists():
        return None
    if m.get("source") == "Gemini 앱 수동 생성":
        return m
    if m.get("hash") != key_of(t, c):
        return None
    if t["kind"] == "exploded":
        try:
            if (date.today() - date.fromisoformat(str(t["bom"].get("as_of")))).days > (c or cfg())["bom_stale_days"]:
                return None
        except ValueError:
            return None
    return m


# ── 장부 ──
def ledger_rows():
    if not LEDGER.exists():
        return []
    with LEDGER.open(encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def month_spend(scope=None, today=None):
    ym = (today or date.today()).isoformat()[:7]
    return round(sum(float(r["usd"] or 0) for r in ledger_rows() if r["date"].startswith(ym) and r["status"] in ("ok", "batch_ordered") and (scope is None or r.get("scope") == scope)), 4)


def month_stopped(today=None):
    """이번 달 생성 중단 상태 — 마지막 중단 뒤에 마스터가 resume(충전·한도 조정 확인)을 남기면 풀린다"""
    ym = (today or date.today()).isoformat()[:7]
    st = None
    for r in ledger_rows():
        if r["date"].startswith(ym):
            if r["status"] in STOP:
                st = r["status"]
            elif r["status"] == "resumed":
                st = None
    return st


def log(t, model, size, batch, usd, status):
    IMG.mkdir(parents=True, exist_ok=True)
    new = not LEDGER.exists()
    with LEDGER.open("a", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, COLS)
        if new:
            w.writeheader()
        w.writerow({"date": now().isoformat(timespec="minutes"), "scope": t["scope"], "id": t["id"], "kind": stem(t) if t.get("kind") != "resume" else "resume", "model": model, "size": size,
                    "batch": int(bool(batch)), "usd": usd, "status": status})


def budget_ok(t, batch, c=None):
    """(될지, 사유)"""
    c = c or cfg()
    stop = month_stopped()
    if stop:
        return False, f"이번 달 생성 중단({stop})"
    cost = est_cost(t, batch, c)
    if month_spend() + cost > c["monthly_budget_usd"]:
        return False, "over_budget"
    if t["scope"] == "industry" and month_spend("industry") + cost > c["monthly_budget_usd"] * c["industry_share"]:
        return False, "over_budget_industry"
    return True, ""


# ── API ──
def _key():
    import pollers.common as common
    k = common.load_env().get("GEMINI_API_KEY")
    if not k:
        raise RuntimeError("GEMINI_API_KEY 없음")
    return k


def _post(url, body, timeout=180):
    req = urllib.request.Request(url, data=json.dumps(body).encode(), method="POST", headers={"Content-Type": "application/json", "x-goog-api-key": _key()})
    return json.load(urllib.request.urlopen(req, timeout=timeout))


def _get(url, timeout=60):
    return json.load(urllib.request.urlopen(urllib.request.Request(url, headers={"x-goog-api-key": _key()}), timeout=timeout))


def vertex_generate(t, c=None, model=None, extra="", quality=None):
    """Vertex AI(google-genai, ADC 인증) — (bytes, mime). 인증 파일·토큰은 읽거나 찍지 않는다(라이브러리가 쓴다)"""
    import warnings
    from google import genai
    from google.genai import types
    c = c or cfg()
    warnings.filterwarnings("ignore", message=".*quota project.*")
    m, s, a = model_size(t, c)
    m = model or m
    v = c["vertex"]
    cl = genai.Client(vertexai=True, project=v["project"], location=v.get("location", "global"))
    def call(**kw):
        return cl.models.generate_content(model=m, contents=(prompt(t, c) + (" " + extra if extra else "")),
                                          config=types.GenerateContentConfig(response_modalities=["IMAGE"], image_config=types.ImageConfig(image_size=s, aspect_ratio=a, **kw)))
    try:   # JPEG로 받아 200KB 안에 — flash-image 기본 PNG는 1MB가 넘는다(2026-11-08). 형식 지정을 거부하는 모델이면 기본 형식으로
        r = call(output_mime_type="image/jpeg", output_compression_quality=quality or c.get("jpeg_quality", 80))
    except Exception as e:
        if getattr(e, "code", None) != 400:
            raise
        r = call()
    for p in (r.candidates[0].content.parts if r.candidates else []):
        d = getattr(p, "inline_data", None)
        if d and d.data:
            return d.data, d.mime_type or "image/jpeg"
    return None, None


def request_body(t, c=None):
    _, s, a = model_size(t, c)
    return {"contents": [{"parts": [{"text": prompt(t, c)}]}],
            "generationConfig": {"responseModalities": ["IMAGE"], "imageConfig": {"aspectRatio": a, "imageSize": s}}}


def classify_error(e):
    """HTTP·google-genai 오류 → 장부 상태. 402·결제·한도 = google_cap(그달 중단), 404·모델 = model_rejected, 429 = quota"""
    code = getattr(e, "code", None) or getattr(e, "status_code", None)
    try:
        msg = e.read().decode("utf-8", "replace")[:300] if hasattr(e, "read") else str(e)
    except Exception:
        msg = str(e)
    low = msg.lower()
    if code == 402 or "billing" in low or "spend" in low or "paused" in low or "payment" in low:
        return "google_cap", msg
    if code == 404 or "not found" in low or "not supported" in low:
        return "model_rejected", msg
    if code == 429 or "quota" in low or "resource_exhausted" in low:
        return "quota", msg
    return "error", msg


def image_bytes(resp):
    for cand in resp.get("candidates") or []:
        for p in (cand.get("content") or {}).get("parts") or []:
            d = p.get("inlineData") or p.get("inline_data")
            if d and d.get("data"):
                return base64.b64decode(d["data"]), d.get("mimeType") or d.get("mime_type") or "image/png"
    return None, None


def shrink(raw, c=None):
    """긴 변 1600px·200KB 이하 webp로. Pillow가 없으면 원본 그대로(검수에서 용량 경고) — (bytes, 확장자, 메모)"""
    c = c or cfg()
    try:
        from PIL import Image
    except ImportError:
        return raw, None, "Pillow 없음 — 원본 형식 저장(webp 변환·축소 안 함)"
    im = Image.open(io.BytesIO(raw)).convert("RGB")
    im.thumbnail((c["max_long_side"], c["max_long_side"]))
    for q in (82, 72, 62, 52, 42):
        buf = io.BytesIO()
        im.save(buf, "WEBP", quality=q, method=6)
        if buf.tell() <= c["max_kb"] * 1024:
            break
    return buf.getvalue(), ".webp", f"webp q{q}"


def save(t, raw, mime, model, size, batch, usd, c=None):
    data, ext, note = shrink(raw, c)
    ext = ext or {"image/png": ".png", "image/jpeg": ".jpg", "image/webp": ".webp"}.get(mime, ".png")
    t["dir"].mkdir(parents=True, exist_ok=True)
    f = t["dir"] / f"{stem(t)}{ext}"
    f.write_bytes(data)
    meta = {"file": f.name, "kind": t["kind"], "name": t["name"], "prompt": prompt(t, c), "prompt_ko": f"{t['name']} — {'분해도' if t['kind'] == 'exploded' else '제품·서비스'} 개념도",
            "model": model, "size": size, "made_at": now().isoformat(timespec="minutes"), "usd": usd, "batch": bool(batch), "hash": key_of(t, c),
            "bom_as_of": (t.get("bom") or {}).get("as_of"), "bytes": len(data), "convert": note, "scope": t["scope"], "view": t.get("view"),
            "source": "Gemini API", "check": None, "approved": None}
    meta_path(t).write_text(json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8")
    return meta


def make_one(t, batch=False, c=None):
    """(상태, 메타 또는 사유)"""
    c = c or cfg()
    hit = cached(t, c)
    if hit:
        return "cached", hit
    ok, why = budget_ok(t, batch, c)
    model, size, _ = model_size(t, c)
    if not ok:
        log(t, model, size, batch, 0, why if why.startswith("over_budget") else "stopped")
        return why, None
    if batch and c.get("batch_supported", True):
        return "batch", t
    try:
        if c.get("backend") == "vertex":
            raw, mime = vertex_generate(t, c)
            resp = {}
        else:
            resp = _post(f"{API}/models/{model}:generateContent", request_body(t, c))
            raw, mime = image_bytes(resp)
    except urllib.error.HTTPError as e:
        st, msg = classify_error(e)
        log(t, model, size, False, 0, st)
        return st, msg
    except Exception as e:   # google-genai 오류는 code를 갖는다 — 결제·한도면 google_cap, 아니면 과금 없는 오류
        if getattr(e, "code", None) is not None:
            st, msg = classify_error(e)
        else:
            st, msg = "error", f"{type(e).__name__}: {e}"[:200]
        log(t, model, size, False, 0, st)
        return st, msg
    if not raw:
        log(t, model, size, False, 0, "no_image")
        return "no_image", json.dumps(resp, ensure_ascii=False)[:300]
    usd = est_cost(t, False, c)
    log(t, model, size, False, usd, "ok")
    return "ok", save(t, raw, mime, model, size, False, usd, c)


def ensure(t, c=None, qa=None):
    """검수를 통과할 때까지 다시 그린다(마스터 지시 2026-11-08 "검수에 실패한 이미지가 없도록 웬만하면 다 생성되도록").
    시도마다: 예산 확인 → 생성(모델 오류면 다음 모델) → 200KB 넘으면 다음 시도 품질↓ → 자동 눈 검수(image_qa) → 실패 사유를 다음 설명문에 덧붙인다.
    → (상태, 메타 또는 사유). 상태: cached·pass·fail(시도 다 씀)·over_budget·stopped·error"""
    import image_check
    import image_qa
    c = c or cfg()
    qa = qa or image_qa.review
    hit = cached(t, c)
    if hit and (hit.get("check") or {}).get("result") == "pass":
        return "cached", hit
    e = c.get("ensure") or {}
    kind = "exploded" if t["kind"] == "exploded" else "default"
    models = list(dict.fromkeys([model_size(t, c)[0]] + list((e.get("fallback") or {}).get(kind) or [])))
    qs = e.get("jpeg_quality_steps") or [80]
    cap = est_cost(t, False, c) * e.get("cost_cap_x", 3)
    spent, extra, reasons, mi = 0.0, "", [], 0
    n_parts = len(ordered(t["bom"])) if t["kind"] == "exploded" else None
    for i in range(e.get("max_attempts", 3)):
        ok, why = budget_ok(t, False, c)
        if not ok:
            log(t, models[mi], model_size(t, c)[1], False, 0, why if why.startswith("over_budget") else "stopped")
            return why, None
        if spent + est_cost(t, False, c) > cap + 1e-9:
            break
        model, size = models[mi], model_size(t, c)[1]
        try:
            raw, mime = vertex_generate(t, c, model=model, extra=extra, quality=qs[min(i, len(qs) - 1)])
        except Exception as ex:
            st, msg = classify_error(ex) if getattr(ex, "code", None) is not None else ("error", f"{type(ex).__name__}: {ex}"[:200])
            log(t, model, size, False, 0, st)
            if st == "google_cap":
                return st, msg
            if mi + 1 < len(models):   # 모델 거부·할당량·일시 오류 → 다음 모델
                mi += 1
            continue
        if not raw:
            log(t, model, size, False, 0, "no_image")
            continue
        usd = est_cost(t, False, c)
        spent += usd
        log(t, model, size, False, usd, "ok")
        meta = save(t, raw, mime, model, size, False, usd, c)
        meta["attempt"], meta["prompt_extra"] = i + 1, extra
        f = t["dir"] / meta["file"]
        if f.stat().st_size > c["max_kb"] * 1024:
            reasons = ["size"]
            meta["check"] = image_check.check(t, meta, c)
            meta_path(t).write_text(json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8")
            continue
        try:
            v = qa(f, t["kind"], n_parts, c)
        except Exception as ex:   # 검수 모델 오류 — 그림을 버리지 않고 사람 눈 검수로 남긴다
            meta["visual_error"] = f"{type(ex).__name__}"
            meta_path(t).write_text(json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8")
            return "error", meta
        meta["visual"] = {"ok": v["ok"], "reason": ",".join(v["reasons"]), "parts": v["raw"].get("parts") if n_parts else None,
                          "order_ok": (v["raw"].get("single_axis") if n_parts else None), "by": "Gemini 비전 자동 검수", "note": v["raw"].get("note")}
        meta["check"] = image_check.check(t, meta, c)
        meta_path(t).write_text(json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8")
        if meta["check"]["result"] in ("pass", "warn") and v["ok"]:
            return "pass", meta
        reasons = v["reasons"]
        import image_qa as Q
        extra = Q.fixes(reasons, n_parts)
    return "fail", {"reasons": reasons, "spent": round(spent, 3)}


def gaps(cid=None, slug=None, c=None):
    """그리기 전에 막히는 곳 — BOM 없음·'확인' 부품 6개 미만·영어 이름 없음(설명문이 한국어로 나간다)"""
    c = c or cfg()
    out = []
    if slug:
        bom = json.loads((product_dir(slug) / "bom.json").read_text(encoding="utf-8"))
        n = len(confirmed(bom))
        if n < c["min_confirmed_parts"]:
            out.append(f"{slug}: '확인' 부품 {n}개 — 분해도는 6개부터(출처 있는 부품을 더 찾는다)")
        out += [f"{slug}: 부품 {x['no']} part_en 없음" for x in confirmed(bom) if not x.get("part_en")]
        return out
    dp = json.loads((company_dir(cid) / "datapack.json").read_text(encoding="utf-8"))
    for p in ((dp.get("narrative") or {}).get("lead") or {}).get("products") or []:
        if not p.get("name_en"):
            out.append(f"{p['name']}: name_en 없음(영어 설명문)")
        if p.get("kind") != "서비스" and not p.get("what_en"):
            out.append(f"{p['name']}: what_en 없음")
        b = p.get("bom")
        if not b:
            out.append(f"{p['name']}: bom 없음 — 분해도 불가(공시·IR·어닝콜로 부품·공급사·출처를 채운다)")
        elif len(confirmed(b)) < c["min_confirmed_parts"]:
            out.append(f"{p['name']}: '확인' 부품 {len(confirmed(b))}개 — 6개부터 분해도")
    return out


def order_batch(ts, c=None):
    """모델별로 일괄 주문(가격 절반) — 작업 ID를 batch_jobs.json에"""
    c = c or cfg()
    jobs = json.loads(JOBS.read_text(encoding="utf-8")) if JOBS.exists() else []
    by = {}
    for t in ts:
        by.setdefault(model_size(t, c)[0], []).append(t)
    out = []
    for model, group in by.items():
        body = {"batch": {"display_name": f"chiip-images-{now():%Y%m%d%H%M}",
                          "input_config": {"requests": {"requests": [{"request": request_body(t, c), "metadata": {"key": f"{t['scope']}|{t['id']}|{stem(t)}"}} for t in group]}}}}
        try:
            r = _post(f"{API}/models/{model}:batchGenerateContent", body)
        except urllib.error.HTTPError as e:
            st, msg = classify_error(e)
            for t in group:
                log(t, model, model_size(t, c)[1], True, 0, st)
            out.append((model, st, msg))
            continue
        name = r.get("name")
        jobs.append({"name": name, "model": model, "at": now().isoformat(timespec="minutes"),
                     "items": [{"scope": t["scope"], "id": t["id"], "kind": t["kind"], "n": t["n"], "view": t.get("view")} for t in group], "done": False})
        for t in group:
            log(t, model, model_size(t, c)[1], True, est_cost(t, True, c), "batch_ordered")
        out.append((model, "ordered", name))
    IMG.mkdir(parents=True, exist_ok=True)
    JOBS.write_text(json.dumps(jobs, ensure_ascii=False, indent=1), encoding="utf-8")
    return out


def _target_from(item, c=None):
    ts = targets_company(item["id"], c) if item["scope"] == "company" else targets_product(item["id"], item.get("view"), c)
    return next((t for t in ts if t["kind"] == item["kind"] and t["n"] == item["n"]), None)


def fetch_batch(c=None):
    c = c or cfg()
    if not JOBS.exists():
        return []
    jobs = json.loads(JOBS.read_text(encoding="utf-8"))
    out = []
    for j in jobs:
        if j.get("done"):
            continue
        try:
            r = _get(f"{API}/{j['name']}")
        except Exception as e:
            out.append((j["name"], f"조회 실패 {type(e).__name__}"))
            continue
        state = r.get("state") or (r.get("metadata") or {}).get("state")
        if state not in ("JOB_STATE_SUCCEEDED", "BATCH_STATE_SUCCEEDED"):
            if state in ("JOB_STATE_FAILED", "JOB_STATE_CANCELLED", "JOB_STATE_EXPIRED"):
                j["done"] = True
            out.append((j["name"], state))
            continue
        dest = r.get("dest") or (r.get("response") or {}).get("dest") or r.get("response") or {}
        resps = (dest.get("inlinedResponses") or {}).get("inlinedResponses") if isinstance(dest.get("inlinedResponses"), dict) else dest.get("inlinedResponses") or []
        for k, item in enumerate(j["items"]):
            t = _target_from(item, c)
            rr = resps[k] if k < len(resps) else {}
            raw, mime = image_bytes(rr.get("response") or {})
            if t and raw:
                save(t, raw, mime, j["model"], model_size(t, c)[1], True, est_cost(t, True, c), c)
        j["done"] = True
        out.append((j["name"], "회수"))
    JOBS.write_text(json.dumps(jobs, ensure_ascii=False, indent=1), encoding="utf-8")
    return out


def pick(ts, only):
    return [t for t in ts if not only or t["kind"] == only]


def main(argv):
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["plan", "make", "ensure", "gaps", "fetch-batch", "ledger", "resume"])
    ap.add_argument("id", nargs="?")
    ap.add_argument("--product")
    ap.add_argument("--pair", action="store_true")
    ap.add_argument("--view", choices=["cross-section"])
    ap.add_argument("--only", choices=["exploded", "product", "service"])
    ap.add_argument("--batch", action="store_true")
    a = ap.parse_args(argv)
    c = cfg()
    if a.cmd == "ledger":
        print(json.dumps({"month": date.today().isoformat()[:7], "usd": month_spend(), "industry_usd": month_spend("industry"), "budget": c["monthly_budget_usd"],
                          "stopped": month_stopped(), "images": sum(1 for r in ledger_rows() if r["date"].startswith(date.today().isoformat()[:7]) and r["status"] == "ok")}, ensure_ascii=False))
        return 0
    if a.cmd == "resume":   # 마스터가 구글 충전·한도를 확인한 뒤에만(google_cap 해제)
        log({"scope": "company", "id": "-", "kind": "resume", "n": 0}, "-", "-", False, 0, "resumed")
        print("[이미지] 이번 달 생성 재개")
        return 0
    if a.cmd == "fetch-batch":
        for x in fetch_batch(c):
            print(x)
        return 0
    if a.product:
        ts = [t for slug in a.product.split(",") for t in targets_product(slug, a.view, c)]
        if a.pair:   # 세대 비교 — 두 제품의 같은 종류만, 같은 화풍·크기·각도(설명문 틀이 같다)
            ts = [t for t in ts if t["kind"] == (a.only or "product")]
    else:
        ts = targets_company(a.id, c)
    ts = pick(ts, a.only)
    if a.cmd == "gaps":
        for g in (gaps(slug=s) for s in a.product.split(",")) if a.product else [gaps(a.id)]:
            print("\n".join(g) or "막힌 곳 없음")
        return 0
    if a.cmd == "ensure":
        for t in ts:
            st, x = ensure(t, c)
            print(stem(t), st, x.get("file") if isinstance(x, dict) and x.get("file") else x)
        return 0
    if a.cmd == "plan":
        for t in ts:
            hit = cached(t, c)
            print(f"{t['scope']}:{t['id']} {stem(t)} {t['name']} · {'캐시' if hit else f'${est_cost(t, a.batch, c):.3f}'} · {model_size(t, c)[0]} {model_size(t, c)[1]}")
        print(f"이번 달 ${month_spend():.2f} / ${c['monthly_budget_usd']} (산업 ${month_spend('industry'):.2f})")
        return 0
    todo, res = [], []
    for t in ts:
        st, x = make_one(t, a.batch, c)
        if st == "batch":
            todo.append(t)
        else:
            res.append((stem(t), st, x.get("file") if isinstance(x, dict) else x))
    if todo:
        res += [("batch", *r[1:]) for r in order_batch(todo, c)]
    for r in res:
        print(r)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
