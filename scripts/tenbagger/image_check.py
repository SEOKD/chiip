"""리포트 이미지 검수 (마스터 지시 2026-11-08, 지시서 4절 · 산업판 4절)

항목마다 통과 1 · 경고 0.5 · 실패 0. 실패가 하나라도 있으면 리포트에 넣지 않는다(product_images가 retries만큼 다시 그린다).
  ① 메타·해시 ② 고정 캡션(렌더러가 붙인다 — 설정에 있어야) ③ 눈 검수(Claude가 Read로 이미지를 보고 --visual로 적는다:
     로고·글자·숫자·실존 인물 없음, 사진처럼 보이지 않음, 산업 이미지는 특정 회사 실물로 보이지 않음)
  ④ 분해도: '확인' 부품 6개 이상, 그림 속 부품 덩어리 수가 ±1, 순서가 layers_order와 맞음(눈 검수 값)
  ⑤ BOM: '확인' 항목마다 source, this_company 1개 이상 또는 'this_company_none'(고객 제품) 명시, 산업 BOM은 공급사마다 source(없으면 표에서 추정)
  ⑥ 200KB 이하
승인: 처음 회사 5곳·산업 3건은 텔레그램 미리보기 → 마스터 승인(approve) 뒤에만 넣는다. 그 뒤 자동 승인 전환은 마스터에게 묻는다(auto_approve는 마스터 몫).
사용:
  py scripts/tenbagger/image_check.py run <id>|--product <slug>          # 자동 검수 + 눈 검수 대기 목록
  py scripts/tenbagger/image_check.py visual <메타 json> --ok|--fail "<사유>" [--parts N] [--order-ok]
  py scripts/tenbagger/image_check.py preview <id>|--product <slug>      # 텔레그램(마스터 개인 봇) 미리보기·승인 요청
  py scripts/tenbagger/image_check.py approve|reject <id>|--product <slug>
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import product_images as P  # noqa: E402

STATE = P.IMG / "approvals.json"


def _state():
    return json.loads(STATE.read_text(encoding="utf-8")) if STATE.exists() else {"company": {}, "industry": {}, "auto": {"company": False, "industry": False}}


def _save_state(s):
    P.IMG.mkdir(parents=True, exist_ok=True)
    STATE.write_text(json.dumps(s, ensure_ascii=False, indent=1), encoding="utf-8")


def bom_checks(bom, scope):
    out = []
    conf = P.confirmed(bom)
    out.append(("확인 항목 source", 1 if all(x.get("source") for x in conf) else 0))
    if scope == "company":
        has = any(x.get("this_company") for x in bom.get("items") or []) or bom.get("this_company_none") or bom.get("this_company_product")   # 회사 자체 제품의 분해도
        out.append(("이 회사 부품 표시", 1 if has else 0))
    else:
        miss = [s["name"] for x in conf for s in x.get("suppliers") or [] if not s.get("source")]
        out.append(("공급사 source", 1 if not miss else 0.5))   # 없는 공급사는 표에서 '추정'으로 내린다
    return out


def check(t, meta, c=None):
    c = c or P.cfg()
    items = [("메타·해시", 1 if meta and meta.get("hash") or (meta or {}).get("source") == "Gemini 앱 수동 생성" else 0),
             ("고정 캡션", 1 if c.get("caption_fixed") else 0)]
    f = t["dir"] / (meta or {}).get("file", "")
    size = f.stat().st_size if f.exists() else 0
    items.append(("용량", 1 if 0 < size <= c["max_kb"] * 1024 else (0.5 if size else 0)))
    v = (meta or {}).get("visual") or {}
    items.append(("눈 검수(로고·글자·인물·사진 연출)", 1 if v.get("ok") is True else 0 if v.get("ok") is False else 0.5))
    if t["kind"] == "exploded":
        n = len(P.confirmed(t["bom"]))
        items.append((f"확인 부품 {c['min_confirmed_parts']}개 이상", 1 if n >= c["min_confirmed_parts"] else 0))
        if v.get("parts") is not None:
            items.append(("부품 덩어리 수 ±1", 1 if abs(int(v["parts"]) - n) <= 1 else 0))
        if v.get("order_ok") is not None:
            items.append(("층 순서", 1 if v["order_ok"] else 0))
        items += bom_checks(t["bom"], t["scope"])
    score = min(x[1] for x in items)
    return {"items": items, "result": "fail" if score == 0 else ("warn" if score < 1 else "pass"), "pending_visual": not v}


def approved(t, c=None):
    if ((c or P.cfg()).get("auto_approve") or {}).get(t["scope"]):   # 자동 승인(2026-11-08 마스터 지시) — 검수 통과가 곧 승인
        return True
    s = _state()
    if s["auto"].get(t["scope"]):
        return True
    return s[t["scope"]].get(t["id"]) == "approved"


def usable(t, c=None):
    """리포트에 넣어도 되는가 → (메타 또는 None, 사유)"""
    m = P.load_meta(t)
    if not m:
        return None, "아직 생성 전"
    ck = m.get("check") or check(t, m, c)
    if ck["result"] == "fail":
        return None, "검수 실패"
    if ck.get("pending_visual"):
        return None, "눈 검수 대기"
    if not approved(t, c):
        return None, "마스터 승인 대기"
    return m, ""


def run(ts, c=None):
    out = []
    for t in ts:
        m = P.load_meta(t)
        if not m:
            out.append((P.stem(t), "이미지 없음"))
            continue
        m["check"] = check(t, m, c)
        P.meta_path(t).write_text(json.dumps(m, ensure_ascii=False, indent=1), encoding="utf-8")
        out.append((P.stem(t), m["check"]["result"], "눈 검수 대기 — Read로 보고 visual" if m["check"]["pending_visual"] else ""))
    return out


def visual(meta_file, ok, reason="", parts=None, order_ok=None):
    p = Path(meta_file)
    m = json.loads(p.read_text(encoding="utf-8"))
    m["visual"] = {"ok": ok, "reason": reason, "parts": parts, "order_ok": order_ok}
    p.write_text(json.dumps(m, ensure_ascii=False, indent=1), encoding="utf-8")
    return m["visual"]


def preview(ts, c=None):
    """마스터 개인 봇으로 미리보기 — 처음 n건만(그 뒤는 auto 전환 여부를 묻는다)"""
    import notify
    c = c or P.cfg()
    s = _state()
    sent = 0
    for t in ts:
        m = P.load_meta(t)
        if not m or approved(t):
            continue
        done = sum(1 for v in s[t["scope"]].values() if v in ("approved", "rejected"))
        if done >= c["approval_first"][t["scope"]] and not s["auto"].get(t["scope"]):
            notify.send(f"[Chiip 이미지] 처음 {c['approval_first'][t['scope']]}건 승인이 끝났습니다. 이후 {t['scope']} 이미지를 검수 통과 시 자동 승인으로 바꿀까요? (마스터 결정)", "REPORT")
            return sent
        notify.send_document(str(t["dir"] / m["file"]), caption=f"[Chiip 이미지 승인 요청] {t['id']} · {m['name']} · {c['caption_fixed']} — 승인/거절을 답해 주세요", level="REPORT")
        s[t["scope"]].setdefault(t["id"], "pending")
        sent += 1
    _save_state(s)
    return sent


def decide(scope, key, verdict):
    s = _state()
    s[scope][key] = verdict
    _save_state(s)


def targets(a, c=None):
    return [t for slug in a.product.split(",") for t in P.targets_product(slug, None, c)] if a.product else P.targets_company(a.id, c)


def main(argv):
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["run", "visual", "preview", "approve", "reject"])
    ap.add_argument("id", nargs="?")
    ap.add_argument("--product")
    ap.add_argument("--ok", action="store_true")
    ap.add_argument("--fail")
    ap.add_argument("--parts", type=int)
    ap.add_argument("--order-ok", action="store_true")
    a = ap.parse_args(argv)
    if a.cmd == "visual":
        print(visual(a.id, not a.fail, a.fail or "", a.parts, True if a.order_ok else None))
        return 0
    ts = targets(a)
    if a.cmd == "run":
        for r in run(ts):
            print(r)
    elif a.cmd == "preview":
        print(f"[미리보기] {preview(ts)}건")
    else:
        decide("industry" if a.product else "company", a.product or a.id, "approved" if a.cmd == "approve" else "rejected")
        print(a.cmd)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
