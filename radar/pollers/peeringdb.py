"""PeeringDB 대체 데이터 수집 (마스터 지시 2026-11-20 "넣어라", ADR-049, 설정 config/peeringdb.yaml)

표적 질의만 한다 — 시설 net_count·ix_count, 하이퍼스케일러·AI 클라우드 네트워크의 접속 시설(netfac)·IX(netixlan), 주요 IX 총 포트 용량.
전체 복제·sync·since= 동기화를 하지 않는다. 익명 GET, common.contact_ua(), 요청 사이 gap_sec초, 회차당 요청 max_requests건 이하, 하루 1회.
429·오류면 그 회차를 멈추고 아무것도 쓰지 않는다(fail-closed) — pipeline_health에 실패로 남긴다.
저장(knowledge/models/peeringdb/): facilities.csv·ixs.csv(날짜별 숫자), net_presence.json(네트워크별 시설·IX ID와 처음 본 날짜), changes.json(의미 있는 변화 → Pulse·데이터 허브).
연락처·사람 이름은 저장하지 않는다.
사용: py radar/pollers/peeringdb.py [--force]
"""
import csv
import json
import sys
import time
import urllib.parse
from datetime import datetime, timedelta, timezone
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from pollers import common   # noqa: E402
else:
    from . import common

SOURCE_ID = "src-peeringdb"
API = "https://www.peeringdb.com/api/"
DIR = common.ROOT / "knowledge" / "models" / "peeringdb"
KST = timezone(timedelta(hours=9))


def cfg():
    return common.load_yaml("config/peeringdb.yaml")


class Budget:
    def __init__(self, c):
        self.n, self.max, self.gap, self.last = 0, int(c.get("max_requests", 8)), float(c.get("gap_sec", 6)), 0.0

    def get(self, path, **q):
        if self.n >= self.max:
            raise RuntimeError("회차 요청 상한")
        wait = self.gap - (time.time() - self.last)
        if wait > 0 and self.last:
            time.sleep(wait)
        self.n += 1
        self.last = time.time()
        raw = common.http_get(API + path + "?" + urllib.parse.urlencode(q), headers={"User-Agent": common.contact_ua()}, timeout=90)
        return json.loads(raw)["data"]


def ids(d):
    return ",".join(str(k) for k in d)


def collect(c, b):
    fac = {str(x["id"]): x for x in b.get("fac", id__in=ids(c["facilities"]), fields="id,net_count,ix_count")}
    nets = c["networks"]
    nf = b.get("netfac", net_id__in=ids(nets), fields="net_id,fac_id,created")
    nx = b.get("netixlan", net_id__in=ids(nets), fields="net_id,ix_id,created")
    cap = {}
    for ix in c["ixs"]:
        rows = b.get("netixlan", ix_id=ix, fields="speed")
        cap[str(ix)] = {"ports": len(rows), "capacity_mbps": sum(int(r.get("speed") or 0) for r in rows)}
    pres = {}
    for r in nf:
        pres.setdefault(str(r["net_id"]), {"fac": {}, "ix": {}})["fac"][str(r["fac_id"])] = str(r.get("created") or "")[:10]
    for r in nx:
        pres.setdefault(str(r["net_id"]), {"fac": {}, "ix": {}})["ix"][str(r["ix_id"])] = str(r.get("created") or "")[:10]
    return fac, cap, pres


def append_csv(path, cols, rows):
    new = not path.exists()
    with path.open("a", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, cols)
        if new:
            w.writeheader()
        w.writerows(rows)


def last_rows(path, key):
    if not path.exists():
        return {}
    out = {}
    with path.open(encoding="utf-8", newline="") as f:
        for r in csv.DictReader(f):
            out[r[key]] = r
    return out


def diff(c, fac, prev_fac, pres, prev_pres, today):
    """의미 있는 변화 — 하이퍼스케일러·AI 클라우드의 새 시설·IX 접속, 시설 net_count 급증"""
    out = []
    kinds = set(c["alerts"]["new_fac_kinds"])
    for nid, meta in c["networks"].items():
        if meta.get("kind") not in kinds or str(nid) not in prev_pres:
            continue   # 첫 회차는 기준선 — 변화로 보지 않는다
        for k in ("fac", "ix"):
            new = set(pres.get(str(nid), {}).get(k, {})) - set(prev_pres[str(nid)].get(k, {}))
            for x in sorted(new):
                out.append({"date": today, "type": f"new_{k}", "net": meta["name"], "kind": meta["kind"], f"{k}_id": x})
    pct = float(c["alerts"]["fac_net_jump_pct"])
    for fid, r in fac.items():
        p = prev_fac.get(fid)
        if p and int(p["net_count"] or 0) and (r["net_count"] - int(p["net_count"])) / int(p["net_count"]) * 100 >= pct:
            out.append({"date": today, "type": "fac_net_jump", "fac_id": fid, "fac": c["facilities"][int(fid)]["name"],
                        "from": int(p["net_count"]), "to": r["net_count"]})
    return out


def run(force=False):
    c = cfg()
    DIR.mkdir(parents=True, exist_ok=True)
    today = datetime.now(KST).date().isoformat()
    fpath, ipath, ppath, cpath = DIR / "facilities.csv", DIR / "ixs.csv", DIR / "net_presence.json", DIR / "changes.json"
    prev_fac = last_rows(fpath, "fac_id")
    if not force and any(r.get("date") == today for r in prev_fac.values()):
        return {"skipped": "오늘 수집함"}
    b = Budget(c)
    try:
        fac, cap, pres = collect(c, b)
    except Exception as e:   # 429·오류 — 이 회차는 아무것도 쓰지 않는다
        common.record_health(SOURCE_ID, False, f"{type(e).__name__}: {str(e)[:80]}")
        return {"error": f"{type(e).__name__}", "requests": b.n}
    prev_pres = json.loads(ppath.read_text(encoding="utf-8")) if ppath.exists() else {}
    changes = diff(c, fac, prev_fac, {k: {kk: v for kk, v in d.items()} for k, d in pres.items()}, {k: v.get("now", v) for k, v in prev_pres.items()}, today)
    append_csv(fpath, ["date", "fac_id", "name", "net_count", "ix_count"],
               [{"date": today, "fac_id": k, "name": c["facilities"][int(k)]["name"], "net_count": v.get("net_count"), "ix_count": v.get("ix_count")} for k, v in sorted(fac.items())])
    append_csv(ipath, ["date", "ix_id", "name", "ports", "capacity_mbps"],
               [{"date": today, "ix_id": k, "name": c["ixs"][int(k)]["name"], **v} for k, v in sorted(cap.items())])
    seen = {}
    for nid, d in pres.items():   # 처음 본 날짜를 지킨다
        old = prev_pres.get(nid, {}).get("first_seen", {"fac": {}, "ix": {}})
        fs = {k: {x: old.get(k, {}).get(x, today) for x in d[k]} for k in ("fac", "ix")}
        seen[nid] = {"name": c["networks"].get(int(nid), {}).get("name"), "now": d, "first_seen": fs}
    ppath.write_text(json.dumps(seen, ensure_ascii=False, indent=1), encoding="utf-8")
    log = json.loads(cpath.read_text(encoding="utf-8")) if cpath.exists() else []
    cpath.write_text(json.dumps((log + changes)[-500:], ensure_ascii=False, indent=1), encoding="utf-8")
    common.record_health(SOURCE_ID, True, None)
    return {"requests": b.n, "facilities": len(fac), "ixs": len(cap), "networks": len(pres), "changes": len(changes)}


def show():
    """데이터 허브(gather.py --market)용 요약 — 시설·IX 최신값과 직전 대비, 최근 30일 의미 있는 변화"""
    fpath, ipath, cpath = DIR / "facilities.csv", DIR / "ixs.csv", DIR / "changes.json"
    if not fpath.exists():
        return {"note": "아직 수집 전"}
    out = {}
    for path, key, val in ((fpath, "fac_id", "net_count"), (ipath, "ix_id", "capacity_mbps")):
        hist = {}
        if path.exists():
            with path.open(encoding="utf-8", newline="") as f:
                for r in csv.DictReader(f):
                    hist.setdefault(r[key], []).append(r)
        out[path.stem] = {k: {"name": v[-1]["name"], "date": v[-1]["date"], val: v[-1][val], "prev": v[-2][val] if len(v) > 1 else None} for k, v in hist.items()}
    cut = (datetime.now(KST) - timedelta(days=30)).date().isoformat()
    out["changes_30d"] = [x for x in (json.loads(cpath.read_text(encoding="utf-8")) if cpath.exists() else []) if x["date"] >= cut]
    return out


def main(argv):
    sys.stdout.reconfigure(encoding="utf-8")
    print(json.dumps(show() if "--show" in argv else run(force="--force" in argv), ensure_ascii=False))


if __name__ == "__main__":
    main(sys.argv[1:])
