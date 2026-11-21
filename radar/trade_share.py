"""미국 수입 중 나라별 비중 — HTS 10단위 (마스터 지시 2026-11-21 "USITC DataWeb과 연결할 수 있는 데이터 파이프라인", 설계안 채택)

USITC DataWeb 그래프(예: 미국 라면 수입 중 한국 비중, HTS 1902300060)와 같은 통계를 미국 Census 국제무역 API에서 받는다(DataWeb의 원천이 Census — 2026-11-21 대조: 2026-04~09 한국 비중 78.2·80.9·78.8·69.8·65.9·70.5%로 일치).
HS 6단위(radar/trade_hs.py --consumer)는 냉동·통조림이 섞이고 금액만 본다. 여기는 10단위·금액·물량(kg)·단가·전체 대비 비중이다.
  설정   config/consumer.yaml trade.share(품목·주목 나라·연결 회사·고른 이유)
  저장   knowledge/models/consumer/trade_share.csv(월·품목·나라·달러·kg·비중·kg당 달러, WORLD = 전체)
  변화   knowledge/models/consumer/trade_share_changes.json — 주목 나라 비중이 전월 대비 alert_pp %p 이상, 수입액 전년 대비 ±alert_yoy 이상(새로 받은 달만) → Pulse
연결은 가설이다: 나라·품목 합계이지 회사 매출이 아니다(금지표: 산업 성장 → 기업 이익). 미국 현지 생산분은 수입 통계에 없다.
DataWeb 보조 경로(관세액·통관 항구·특혜 프로그램)는 knowledge/methods/usitc_dataweb.md — 계정·토큰은 마스터 몫.
사용: py radar/trade_share.py --run · --status · --about <회사 id>
"""
import argparse
import csv
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from pollers import common  # noqa: E402
import trade_ppi as tp  # noqa: E402

SOURCE_ID = "src-trade-share"
API = "https://api.census.gov/data/timeseries/intltrade/imports/hs"
DIR = common.ROOT / "knowledge" / "models" / "consumer"
CSV_P = DIR / "trade_share.csv"
CHANGES = DIR / "trade_share_changes.json"
COLS = ["month", "hts", "partner", "usd", "kg", "share", "usd_per_kg"]
WORLD, TOTAL_CODE = "WORLD", "-"


def cfg():
    return ((common.load_yaml("config/consumer.yaml") or {}).get("trade") or {})


def load():
    if not CSV_P.exists():
        return {}
    with CSV_P.open(encoding="utf-8", newline="") as f:
        return {(r["month"], r["hts"], r["partner"]): r for r in csv.DictReader(f)}


def save(rows):
    DIR.mkdir(parents=True, exist_ok=True)
    with CSV_P.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, COLS)
        w.writeheader()
        w.writerows(sorted(rows.values(), key=lambda r: (r["hts"], r["month"], r["partner"] != WORLD, r["partner"])))


def parse(rows, hts, codes, want):
    """Census 응답 → {(월, 품목, 나라): 행}. 전체 합계는 CTY_CODE '-'. 물량은 단위가 KG일 때만"""
    if not rows:
        return {}
    h = rows[0]
    ix = {k: h.index(k) for k in ("CTY_CODE", "GEN_VAL_MO", "GEN_QY1_MO", "UNIT_QY1", "time")}
    iso = {v: k for k, v in codes.items()}
    iso[TOTAL_CODE] = WORLD
    raw = {}
    for r in rows[1:]:
        p = iso.get(r[ix["CTY_CODE"]])
        if p is None or (p != WORLD and p not in want) or r[ix["GEN_VAL_MO"]] in ("", None):
            continue
        kg = float(r[ix["GEN_QY1_MO"]]) if r[ix["UNIT_QY1"]] == "KG" and r[ix["GEN_QY1_MO"]] not in ("", None) else None
        raw[(r[ix["time"]], p)] = (float(r[ix["GEN_VAL_MO"]]), kg)
    out = {}
    for (m, p), (usd, kg) in raw.items():
        w = raw.get((m, WORLD))
        out[(m, hts, p)] = {"month": m, "hts": hts, "partner": p, "usd": int(usd), "kg": "" if kg is None else int(kg),
                            "share": "" if not w or not w[0] else round(usd / w[0], 4), "usd_per_kg": "" if not kg else round(usd / kg, 3)}
    return out


def changes(rows, it, new_months, c):
    """주목 나라의 비중 급변(전월 대비 %p)·수입액 전년 대비 급변 — 새로 받은 달만"""
    out, f, hts = [], it["focus"], it["hts"]
    for m in sorted(new_months):
        cur = rows.get((m, hts, f))
        if not cur or cur["share"] == "":
            continue
        y, mo = int(m[:4]), int(m[5:7])
        pm = f"{y - 1}-12" if mo == 1 else f"{y}-{mo - 1:02d}"
        prev, ya = rows.get((pm, hts, f)), rows.get((f"{y - 1}-{mo:02d}", hts, f))
        base = {"month": m, "hts": hts, "name": it["name"], "partner": f, "ids": it.get("ids") or [], "share": float(cur["share"]), "usd": int(cur["usd"])}
        if prev and prev["share"] != "" and abs(float(cur["share"]) - float(prev["share"])) * 100 >= float(c.get("alert_pp", 5)):
            out.append({**base, "type": "share_move", "prev_share": float(prev["share"])})
        if ya and int(ya["usd"]) and abs(int(cur["usd"]) / int(ya["usd"]) - 1) >= float(c.get("alert_yoy", 0.3)):
            out.append({**base, "type": "value_yoy", "yoy": round(int(cur["usd"]) / int(ya["usd"]) - 1, 3)})
    return out


def run(today=None, env=None):
    t = cfg()
    c = t.get("share") or {}
    env = common.load_env() if env is None else env
    key = env.get("CENSUS_API_KEY")
    if not c.get("items") or not key:
        return {"skipped": "설정 또는 CENSUS_API_KEY 없음"}
    today = today or common.now_kst().date()
    rows, errors, got, found = load(), [], 0, []
    first = not rows
    for it in c["items"]:
        hts = it["hts"]
        have = sorted({k[0] for k in rows if k[1] == hts})
        since = have[-3] if len(have) > 2 else tp.start_month(today, int(c.get("months", 120)))   # 최근 3개월은 다시 받는다(수정 발표)
        url = f"{API}?get=CTY_CODE,GEN_VAL_MO,GEN_QY1_MO,UNIT_QY1&I_COMMODITY={hts}&COMM_LVL=HS10&time=from+{since}&key={key}"
        try:
            new = parse(json.loads(tp.get(url, timeout=120) or "[]"), hts, t["census_country"], set(it["partners"]))
        except Exception as e:
            errors.append(f"{hts}: {type(e).__name__}")
            continue
        fresh = {k[0] for k in new} - set(have)
        rows.update(new)
        got += len(new)
        if have:   # 품목의 첫 수집은 기준선
            found += changes(rows, it, fresh, c)
        time.sleep(0.4)
    if got:
        save(rows)
    if found and not first:
        log = json.loads(CHANGES.read_text(encoding="utf-8")) if CHANGES.exists() else []
        CHANGES.write_text(json.dumps((log + found)[-300:], ensure_ascii=False, indent=1), encoding="utf-8")
    common.record_health(SOURCE_ID, not errors, "; ".join(errors[:3]) or None)
    return {"rows": got, "changes": len(found), "errors": errors}


def lines(it, rows):
    """한 품목 요약 — 주목 나라의 최근 6개월 비중·금액·단가와 전년 대비"""
    f, hts = it["focus"], it["hts"]
    ms = sorted({k[0] for k in rows if k[1] == hts and k[2] == f})[-6:]
    if not ms:
        return [f"{it['name']}(HTS {hts}): 아직 수집 전"]
    out = [f"미국 수입 중 {f} 비중 — {it['name']}(HTS {hts}, 미국 Census 월간, 수입 통계라 미국 현지 생산분 제외)"]
    for m in ms:
        r = rows[(m, hts, f)]
        ya = rows.get((f"{int(m[:4]) - 1}{m[4:]}", hts, f))
        yoy = f", 전년 대비 {int(r['usd']) / int(ya['usd']) - 1:+.0%}" if ya and int(ya["usd"]) else ""
        upk = f", kg당 ${float(r['usd_per_kg']):.2f}" if r["usd_per_kg"] != "" else ""
        out.append(f"  {m}: 비중 {float(r['share']):.1%}, ${int(r['usd']) / 1e6:.1f}M{yoy}{upk}")
    return out


def about(cid):
    c = cfg().get("share") or {}
    rows = load()
    hit = [it for it in c.get("items") or [] if cid in (it.get("ids") or [])]
    if not hit:
        return "연결 품목 없음"
    return "\n".join(l for it in hit for l in lines(it, rows)) + "\n(나라·품목 합계 — 회사 매출이 아니다. 점유율이 높을 때만 방향 신호로 쓴다)"


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", action="store_true")
    ap.add_argument("--status", action="store_true")
    ap.add_argument("--about")
    a = ap.parse_args()
    if a.run:
        print(json.dumps(run(), ensure_ascii=False))
    if a.status:
        rows = load()
        for it in (cfg().get("share") or {}).get("items") or []:
            print("\n".join(lines(it, rows)))
    if a.about:
        print(about(a.about))


if __name__ == "__main__":
    main()
