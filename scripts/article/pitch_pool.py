"""기사 소재 후보 풀 — 지난 24시간 재료를 결정론으로 모아 순위를 매긴다 (2026-11-08 마스터 지시 "매일 아침 제공하는 기사 소재 전달 시스템을 점검하고 보완")

점검에서 드러난 것: 회차(약 5분)가 재료 찾기와 1차 문서 확인을 한꺼번에 해 11/5부터 하루 1건으로 줄었고, 프로바이저가 '1차 문서 미열람'으로 이틀 연속 깎았다.
그래서 찾기는 스크립트가 미리 하고, 모델은 상위 후보의 1차 문서 확인·신규성 검색·글쓰기에 시간을 쓴다.
재료(지난 24시간):
  ① Pulse 피드 판단 건(outputs/article/sources/*_feed.json, 인사이트 4 이상) — 이미 1차 근거(basis)·반론·다음 확인이 붙어 있다
  ② 속보 판단 알림 P0·P1(radar/state/alerts.json)
  ③ 새 IR 문서(일본·한국·대만·홍콩·Fiscal IR — PT·결산·Q&A)와 SEC·DART 공시(radar/inbox)
  ④ 오늘 쓴 Industry·Analysis 리포트(outputs/industry·outputs/tenbagger/reports)
  ⑥ 한국 전자기업 특허 등록·분쟁 — 기자 페이지(지디넷코리아 이기종)·미 ITC 공고(Federal Register)·언론 색인, 키가 오면 법원·PTAB·특허 등록·DART 소송 공시
     (knowledge/models/patents/latest.json, radar/patent_watch.py, 2026-11-08 마스터 지시)
  ⑦ 연구·학회·협회 — 논문(arXiv·OpenAlex·연구 피드)·협회·학회 새 항목 중 한국 기업·감시 기술이 든 것(2026-11-09)
  ③의 IR 문서가 한국 전자기업의 공급망 상대방(config/korea_counterparties.yaml)이면 한국 연결 2점·10일 창(2026-11-09 마스터 지시)
  ⑤ 한국 전자기업 해외 생산 거점 — 그 나라 정부 자료 새 항목·거점 품목 수출입 급변(+품목 PPI)(knowledge/models/overseas_sites/latest.json, 2026-11-08 마스터 지시)
점수 = 1차 문서 있음 3 + 한국 연결(직접 2 / 같은 산업군에 국내 종목 1) + 인사이트(0~10 → 0~3) + 숫자 1
감점: 최근 7일 기사 소재로 낸 종목 −3, 마스터 딘스티커 최근 7일에 쓴 종목 −2(같은 각도 되풀이 방지 — 후속 각도면 모델이 살린다)
사용: py scripts/article/pitch_pool.py [--date YYYYMMDD] [--top 12]
출력: outputs/article/pitch/<날짜>_pool.json(전체)·표준 출력(상위 n)
"""
import argparse
import csv
import json
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "radar"))
sys.path.insert(0, str(ROOT / "scripts" / "industry"))
KST = timezone(timedelta(hours=9))
OUT = ROOT / "outputs" / "article" / "pitch"
NUM_RE = re.compile(r"[\d.,]+\s*(%|%p|억|조|원|엔|\$|B|M|배|GW|MW|장|개)")
IR_SOURCES = ("src-jp-ir-docs", "src-kr-ir-docs", "src-tw-hk-ir-docs", "src-fiscal-ir-docs", "src-jp-ir-qa", "src-kr-ir-qa", "src-tw-hk-ir-qa", "src-sec-filings", "src-dart")


def _load(p, default):
    try:
        return json.loads(Path(p).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def entity_maps():
    """코드·이름 → id, id → (이름, 한국 여부), id → 산업들, 산업 → 국내 종목 있음"""
    import weekly_pick
    by_code, info = {}, {}
    with (ROOT / "config" / "watchlist.csv").open(encoding="utf-8", newline="") as f:
        for r in csv.DictReader(f):
            t = str(r.get("ticker") or "")
            info[r["entity_id"]] = (r["name"], t.isdigit() and len(t) == 6)
            by_code[t.replace(".US", "").upper()] = r["entity_id"]
            by_code[r["name"].upper()] = r["entity_id"]
    import yaml
    for i, v in ((yaml.safe_load((ROOT / "config" / "fiscal_ir_docs.yaml").read_text(encoding="utf-8")) or {}).get("extra") or {}).items():   # 유럽 IR 종목 이름
        if isinstance(v, dict) and v.get("name"):
            info.setdefault(i, (v["name"], False))
    mem = weekly_pick.members()
    ind_of, korea_ind = {}, {}
    for k, ms in mem.items():
        korea_ind[k] = any(m["korea"] for m in ms)
        for m in ms:
            ind_of.setdefault(m["id"], []).append(k)
            info.setdefault(m["id"], (m["name"], m["korea"]))
            by_code.setdefault(str(m["ticker"] or "").replace(".US", "").upper(), m["id"])
            by_code.setdefault(str(m["name"] or "").upper(), m["id"])
    return by_code, info, ind_of, korea_ind


def counterparty(text, ids):
    """한국 전자기업의 공급망 상대방이면 (상대방 이름, 한국 기업들, 역할) — config/korea_counterparties.yaml(감시 목록, 관계 확정 아님)"""
    import yaml
    c = yaml.safe_load((ROOT / "config" / "korea_counterparties.yaml").read_text(encoding="utf-8")) or {}
    for x in c.get("counterparties") or []:
        if set(ids) & set(x.get("ids") or []) or any(re.search(r"(?<![A-Za-z])" + re.escape(n) + r"(?![A-Za-z])", text) for n in x["names"]):
            return x["names"][0], x["korea"], x.get("role", "")
    return None


def korea_link(ids, info, ind_of, korea_ind):
    """(점수, 근거) — 직접 한국 종목 2, 같은 산업군에 국내 종목 1"""
    if any(info.get(i, ("", False))[1] for i in ids):
        return 2, "국내 종목"
    inds = sorted({k for i in ids for k in ind_of.get(i, []) if korea_ind.get(k)})
    return (1, "같은 산업군에 국내 종목(" + ", ".join(inds[:2]) + ")") if inds else (0, "")


def recent_pitched(today, days=7):
    """최근 n일 기사 소재의 야마 문장(종목 이름 대조용)"""
    p = OUT / "log.csv"
    if not p.exists():
        return ""
    lim = (today - timedelta(days=days)).isoformat()
    with p.open(encoding="utf-8", newline="") as f:
        return " ".join(r.get("yama", "") for r in csv.DictReader(f) if (r.get("date") or "") >= lim)


def recent_dticker(days=7):
    """마스터 딘스티커 최근 글 본문(읽기만 — 종목 이름 대조용)"""
    try:
        import subprocess
        out = subprocess.run([sys.executable, str(ROOT / "radar" / "dticker.py"), "--recent", str(days)], capture_output=True, timeout=60)
        return out.stdout.decode("utf-8", "replace")
    except Exception:
        return ""


def gather(now):
    since = now - timedelta(hours=24)
    by_code, info, ind_of, korea_ind = entity_maps()
    cands = []
    # ① Pulse 피드
    for f in sorted((ROOT / "outputs" / "article" / "sources").glob("*_feed.json")):
        try:
            t = datetime.strptime(f.stem[:13], "%Y%m%d_%H%M").replace(tzinfo=KST)
        except ValueError:
            continue
        if t < since:
            continue
        for it in _load(f, {}).get("items") or []:
            try:
                ins = float(it.get("insight") or 0)
            except ValueError:
                ins = 0
            if ins < 4:
                continue
            eid = by_code.get(str(it.get("code") or "").upper()) or by_code.get(str(it.get("name") or "").upper())
            cands.append({"src": "Pulse 피드", "at": t.isoformat(timespec="minutes"), "name": it.get("name"), "ids": [eid] if eid else [], "event": it.get("event"),
                          "view": it.get("view"), "insight": ins, "primary": "1차" in str(it.get("basis") or ""), "basis": it.get("basis"),
                          "why": it.get("why"), "against": it.get("against"), "next": it.get("next"), "links": it.get("links")})
    # ② 속보 판단 P0·P1
    for ref, a in (_load(ROOT / "radar" / "state" / "alerts.json", {}) or {}).items():
        if a.get("level") not in ("P0", "P1"):
            continue
        try:
            t = datetime.fromisoformat(str(a.get("sent_at")))
        except ValueError:
            continue
        if t < since:
            continue
        cands.append({"src": f"알림 {a['level']}", "at": t.isoformat(timespec="minutes"), "name": a.get("title"), "ids": list(a.get("entities") or []), "event": a.get("what"),
                      "view": a.get("impact"), "insight": 6 if a["level"] == "P0" else 4, "primary": a.get("doc_type") in ("공시", "보도자료", "실적") or "適時開示" in str(a.get("title")),
                      "basis": a.get("doc_type"), "links": [["원문", a.get("url")]] if a.get("url") else []})
    # ③ 새 IR 문서·공시
    ir = {}
    for day in {now.strftime("%Y%m%d"), (now - timedelta(days=1)).strftime("%Y%m%d")}:
        for f in (ROOT / "radar" / "inbox" / day).glob("src-*.json") if (ROOT / "radar" / "inbox" / day).exists() else []:
            it = _load(f, {})
            if it.get("source_id") not in IR_SOURCES:
                continue
            try:
                t = datetime.fromisoformat(str(it.get("saved_at") or it.get("detected_at")))
            except ValueError:
                continue
            if t < since:
                continue
            dd = str(it.get("doc_date") or it.get("published_at") or "")[:10]
            cp = counterparty(str(it.get("title") or ""), it.get("entities_matched") or [])
            # 수집이 늦게 들어온 옛 발표는 소재가 아니다 — 다만 한국 기업 공급망 상대방의 실적 자료는 국내 보도가 늦으므로 10일까지 본다(2026-11-09)
            if dd and dd < (now - timedelta(days=10 if cp else 3)).date().isoformat():
                continue
            key = (tuple(it.get("entities_matched") or []), it.get("period"))
            hit = ir.get(key)
            doc = it.get("local_text") or it.get("local_pdf") or it.get("fetch") or it.get("url")
            if hit:   # 같은 회사·기간의 PT·보도자료·보고서는 한 후보로
                hit["docs"].append(f"{it.get('kind') or it.get('tier')}: {doc}")
                continue
            ir[key] = {"counterparty": cp, "src": "IR 문서·공시(공급망 상대방)" if cp else "IR 문서·공시", "at": t.isoformat(timespec="minutes"), "name": it.get("title"), "ids": list(it.get("entities_matched") or []),
                       "event": f"{it.get('period') or ''} 실적 자료 · 발표 {dd}", "insight": 4, "primary": True, "basis": it.get("source_id"), "docs": [f"{it.get('kind') or it.get('tier')}: {doc}"]}
    cands += list(ir.values())
    # ④ 오늘 리포트
    for f in (ROOT / "outputs" / "industry").glob(now.strftime("%Y%m%d") + "_*.json"):
        d = _load(f, {})
        if d.get("title"):
            cands.append({"src": "Industry Report", "at": now.isoformat(timespec="minutes"), "name": d["title"], "ids": [], "event": d.get("event"),
                          "view": (d.get("verdict") or {}).get("view", "")[:200], "insight": 5, "primary": True, "basis": "Chiip 리포트(1차 자료 인용)", "doc": str(f.relative_to(ROOT))})
    # ⑤ 한국 전자기업 해외 생산 거점 — 그 나라 정부 자료(새 항목)와 거점 품목 수출입 급변(2026-11-08 마스터 지시, radar/overseas_sites.py)
    ov = _load(ROOT / "knowledge" / "models" / "overseas_sites" / "latest.json", {})
    for g in ov.get("gov") or []:
        cands.append({"src": "해외 거점 정부 자료", "at": now.isoformat(timespec="minutes"), "name": f"[{g.get('juris')}] {g.get('title')}", "ids": [],
                      "event": g.get("title"), "insight": 4, "primary": not str(g.get("id", "")).endswith("-gn"), "basis": f"{g.get('juris')} — {'원문' if not str(g.get('id', '')).endswith('-gn') else '색인 제목, 원문 확인 필요'}",
                      "links": [["원문", g.get("url")]], "overseas": g.get("country")})
    for x in ov.get("signals") or []:
        if str(x.get("first_seen") or "") < (now - timedelta(days=1)).date().isoformat():   # 새 달 통계가 나온 날만(같은 신호를 매일 되풀이하지 않는다)
            continue
        cands.append({"src": "해외 거점 수출입", "at": now.isoformat(timespec="minutes"), "name": f"{x['flow']} HS{x['hs']}({', '.join(x['items'])}) {x['yoy_3m']:+.0%}",
                      "ids": list(x.get("company_ids") or []), "company_names": x.get("companies"), "event": f"{', '.join(x['places'])} 거점 품목 {x['flow']} 최근 3개월 {x['yoy_3m']:+.0%}(${x['usd_3m'] / 1e6:,.0f}M, ~{x['last']})",
                      "view": "; ".join(x.get("ppi") or []), "insight": 5, "primary": True, "basis": x.get("source"), "overseas": x.get("country"),
                      "why": "수출입 급변은 단서 — 가격·물량을 나누지 않은 값이고 특정 기업 매출로 바로 잇지 않는다(금지표)"})
    # ⑥ 한국 전자기업 특허 등록·분쟁(2026-11-08 마스터 지시, radar/patent_watch.py) — 지난 24시간에 처음 본 항목
    pw = _load(ROOT / "knowledge" / "models" / "patents" / "latest.json", {})
    for x in pw.get("items") or []:
        if str(x.get("first_seen") or "") < (now - timedelta(days=1)).date().isoformat():
            continue
        cands.append({"src": "특허 레이더", "at": now.isoformat(timespec="minutes"), "name": x["title"], "ids": list(x.get("ids") or []), "company_names": x.get("companies"),
                      "event": f"{x['kind']} · {x['title']}", "insight": 5 if x.get("primary") else 4, "primary": bool(x.get("primary")),
                      "basis": f"{x['kind']} — {x.get('note', '')}", "links": [["원문", x["url"]]], "patent": True,
                      "why": "특허 분쟁은 단계를 나눈다 — 청구·개시·예비판정·최종판정·합의. 소송 제기 → 손해 확정, 재심사 청구 → 특허 무효, 등록 → 매출은 금지표"})
    # ⑦ 연구·학회·협회(2026-11-09 마스터 지시 "논문, 학회 세미나, 협회 자료 등도 참조") — 한국 기업 이름·감시 기술이 든 새 항목
    import yaml
    kc = yaml.safe_load((ROOT / "config" / "korea_counterparties.yaml").read_text(encoding="utf-8")) or {}
    rx = re.compile(kc.get("research_terms") or "HBM", re.I)
    pre = tuple(kc.get("research_sources") or [])
    for day in {now.strftime("%Y%m%d"), (now - timedelta(days=1)).strftime("%Y%m%d")}:
        folder = ROOT / "radar" / "inbox" / day
        for f in folder.glob("src-*.json") if folder.exists() else []:
            it = _load(f, {})
            if not str(it.get("source_id") or "").startswith(pre):
                continue
            text = f"{it.get('title') or ''} {it.get('snippet') or ''}"
            if not rx.search(text):
                continue
            kind = "논문" if any(k in it["source_id"] for k in ("arxiv", "openalex", "research")) else "협회" if "assoc" in it["source_id"] else "학회"
            cands.append({"src": f"연구·학회·협회({kind})", "at": now.isoformat(timespec="minutes"), "name": it.get("title"), "ids": list(it.get("entities_matched") or []),
                          "event": it.get("title"), "insight": 4, "primary": True, "basis": f"{kind} 원문 — {it.get('source_id')}", "links": [["원문", it.get("url")]],
                          "counterparty": counterparty(text, it.get("entities_matched") or []),
                          "why": "논문·학회 발표는 양산이 아니다(금지표: 신기술 발표 → 경쟁우위, 샘플 → 양산) — 저자 소속·실험 조건·수율 언급을 본다"})
    seen_u = {c.get("links", [[None, None]])[0][1] for c in cands if c.get("links")}
    for f in sorted((ROOT / "radar" / "pulse").glob(f"{now:%Y%m%d}_*.json")) + sorted((ROOT / "radar" / "pulse").glob(f"{now - timedelta(days=1):%Y%m%d}_*.json")):
        for it in _load(f, {}).get("sources") or []:   # Pulse가 직접 받는 arXiv 등 논문(받은편지함에 없다)
            if it.get("source_class") != "논문" or it.get("url") in seen_u or not rx.search(f"{it.get('title') or ''} {it.get('snippet') or ''}"):
                continue
            seen_u.add(it.get("url"))
            cands.append({"src": "연구·학회·협회(논문)", "at": now.isoformat(timespec="minutes"), "name": it.get("title"), "ids": list(it.get("entities_matched") or []),
                          "event": it.get("title"), "insight": 4, "primary": True, "basis": f"논문 원문 — {it.get('source_id')}", "links": [["원문", it.get("url")]],
                          "counterparty": counterparty(it.get("title") or "", it.get("entities_matched") or []),
                          "why": "논문은 양산이 아니다(금지표) — 저자 소속·실험 조건·수율 언급을 본다"})
    return cands, (by_code, info, ind_of, korea_ind)


def score(cands, maps, today):
    _, info, ind_of, korea_ind = maps
    pitched, dt = recent_pitched(today), recent_dticker()
    seen, out = set(), []
    for c in cands:
        key = (tuple(sorted(c["ids"])), str(c.get("event"))[:40])
        if key in seen:
            continue
        seen.add(key)
        k, why = korea_link(c["ids"], info, ind_of, korea_ind)
        if c.get("counterparty") and k < 2:   # 한국 전자기업의 공급망 상대방 — 역방향 레이더(상대방이 먼저 말한다)
            k, why = 2, f"공급망 상대방 {c['counterparty'][0]}({c['counterparty'][2]}) → {', '.join(c['counterparty'][1][:3])}"
            c.setdefault("company_names", list(c["counterparty"][1]))
        if c.get("patent") and not k and c.get("company_names"):   # 특허표의 한국 기업(감시 목록 밖 LG디스플레이 등)도 직접 연결
            k, why = 2, f"한국 기업 특허({', '.join(c['company_names'])})"
        if c.get("overseas") and not k:   # 해외 거점 나라 자료는 그 나라에 거점을 둔 한국 기업과 이어진다
            k, why = 1, f"한국 기업 해외 거점({c['overseas']})"
        names = [info.get(i, (i, False))[0] for i in c["ids"]]
        if c.get("company_names") and any(n == i for n, i in zip(names, c["ids"])):   # 감시 목록 밖 한국 기업(LG전자 등)은 거점표 이름
            names = list(c["company_names"])
        text = f"{c.get('event') or ''} {c.get('view') or ''} {c.get('why') or ''}"
        s = (3 if c.get("primary") else 0) + k + min(3.0, float(c.get("insight") or 0) * 0.3) + (1 if NUM_RE.search(text) else 0)
        notes = []
        if any(n and n in pitched for n in names):
            s -= 3
            notes.append("최근 7일 기사 소재로 냄")
        if any(n and n in dt for n in names):
            s -= 2
            notes.append("마스터 딘스티커 최근 7일에 씀 — 후속 각도만")
        out.append({**c, "names": names, "korea": why, "score": round(s, 2), "notes": notes})
    return sorted(out, key=lambda x: -x["score"])


def main(argv):
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("--date")
    ap.add_argument("--top", type=int, default=12)
    a = ap.parse_args(argv)
    now = datetime.strptime(a.date, "%Y%m%d").replace(hour=6, tzinfo=KST) if a.date else datetime.now(KST)
    cands, maps = gather(now)
    pool = score(cands, maps, now.date())
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / f"{now:%Y%m%d}_pool.json").write_text(json.dumps(pool, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    print(f"[기사 소재 풀] 후보 {len(pool)}건(지난 24시간) — 상위 {min(a.top, len(pool))}")
    for i, c in enumerate(pool[: a.top], 1):
        print(f"{i:2d}. {c['score']:4.1f} [{c['src']}] {', '.join(n for n in c['names'] if n) or c.get('name')} — {str(c.get('event'))[:70]}"
              f" | 1차 {'있음' if c.get('primary') else '없음'} | 한국 {c['korea'] or '없음'}" + (f" | {'; '.join(c['notes'])}" if c["notes"] else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
