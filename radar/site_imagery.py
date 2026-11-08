"""생산시설 위성 영상 수집과 변화 측정 (마스터 지시 2026-11-03). 판단은 하지 않는다 — 단계 판독은 모델, 캐파 계산은 scripts/tenbagger/site_view.py

- Sentinel-2 L2A(10m, 5일 주기, 세계): 시점별 맑은 장면의 실사진, 구름 층, 분석 밴드(SWIR·NIR·적색)
- NAIP(최대 0.3m, 2~3년 주기, 미국): 면적 판독용 항공사진. 다른 나라에서는 검색 결과가 없다
- OpenStreetMap 건물 윤곽: 면적. 30일에 한 번, Overpass 사용 지침 안에서만 조회하고 결과를 저장한다
영상은 radar/state/sites/(git 제외), 측정값은 knowledge/models/sites/latest/, 윤곽은 knowledge/models/sites/footprints/.
패키지 추가 없이 표준 라이브러리로 PNG를 읽고 쓴다.
사용: py radar/site_imagery.py --run · --site <id> · --company <회사 id> · --status
      --grid <id> [날짜]     눈금을 얹은 판독용 영상을 만든다
      --measure <id> <날짜> x,y x,y x,y…   영상 픽셀 꼭짓점의 위도·경도와 면적
"""
import argparse
import datetime
import json
import math
import struct
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import zlib
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from pollers import common  # noqa: E402

sys.path.insert(0, str(common.ROOT / "scripts" / "tenbagger"))
import site_view as sv  # noqa: E402

UA = None   # 요청 때 common.contact_ua() — 연락처를 코드에 두지 않는다
STATE = common.ROOT / "radar" / "state" / "sites"
CHANNELS = {0: 1, 2: 3, 4: 2, 6: 4}
COLOR = {v: k for k, v in CHANNELS.items()}
BAD_SCL = (0, 1, 3, 8, 9, 10)   # 자료 없음·불량·그림자·구름·권운
GRID_M = 100
RECENT_MONTHS = 6


def decode_png(raw):
    """8비트 비인터레이스 PNG → (폭, 높이, 채널, 바이트)"""
    pos, chunks, head = 8, [], None
    while pos < len(raw):
        n = struct.unpack(">I", raw[pos:pos + 4])[0]
        tag, body = raw[pos + 4:pos + 8], raw[pos + 8:pos + 8 + n]
        pos += 12 + n
        if tag == b"IHDR":
            head = struct.unpack(">IIBBBBB", body)
        elif tag == b"IDAT":
            chunks.append(body)
    w, h, depth, color, _, _, interlace = head
    if depth != 8 or interlace or color not in CHANNELS:
        raise ValueError(f"읽을 수 없는 PNG 형식: depth={depth} color={color} interlace={interlace}")
    ch, data = CHANNELS[color], zlib.decompress(b"".join(chunks))
    row = w * ch
    prev, out, i = bytearray(row), bytearray(), 0
    for _ in range(h):
        kind, cur = data[i], bytearray(data[i + 1:i + 1 + row])
        i += row + 1
        if kind == 1:
            for x in range(ch, row):
                cur[x] = (cur[x] + cur[x - ch]) & 255
        elif kind == 2:
            for x in range(row):
                cur[x] = (cur[x] + prev[x]) & 255
        elif kind == 3:
            for x in range(row):
                cur[x] = (cur[x] + (((cur[x - ch] if x >= ch else 0) + prev[x]) >> 1)) & 255
        elif kind == 4:
            for x in range(row):
                a, b, c = (cur[x - ch], prev[x], prev[x - ch]) if x >= ch else (0, prev[x], 0)
                p = a + b - c
                pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
                cur[x] = (cur[x] + (a if pa <= pb and pa <= pc else b if pb <= pc else c)) & 255
        out += cur
        prev = cur
    return w, h, ch, bytes(out)


def encode_png(w, h, ch, px):
    def chunk(tag, body):
        return struct.pack(">I", len(body)) + tag + body + struct.pack(">I", zlib.crc32(tag + body))
    rows = b"".join(b"\0" + px[y * w * ch:(y + 1) * w * ch] for y in range(h))
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, COLOR[ch], 0, 0, 0)) + chunk(b"IDAT", zlib.compress(rows, 9)) + chunk(b"IEND", b"")


def fetch(url, data=None, timeout=90, pause=30):
    headers = {"User-Agent": common.contact_ua()}
    if data is not None:
        headers["Content-Type"] = "application/json" if isinstance(data, dict) else "application/x-www-form-urlencoded"
    body = json.dumps(data).encode() if isinstance(data, dict) else data
    for attempt in (1, 2):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, data=body, headers=headers), timeout=timeout) as r:
                return r.read()
        except urllib.error.HTTPError as e:
            if e.code not in (429, 406, 502, 503, 504) or attempt == 2:
                raise
            time.sleep(pause)


def site_bbox(site):
    """(남, 서, 북, 동)"""
    lat, lon = site["center"]
    dlat = site["half_km"] * 1000 / sv.M_PER_DEG
    dlon = dlat / math.cos(math.radians(lat))
    return lat - dlat, lon - dlon, lat + dlat, lon + dlon


def size_px(site, cfg):
    return min(int(round(site["half_km"] * 200)), cfg["collect"]["max_px"])


def crop_url(cfg, collection, item, box, px, query):
    s, w, n, e = box
    return f"{cfg['collect']['data']}/item/bbox/{w:.6f},{s:.6f},{e:.6f},{n:.6f}/{px}x{px}.png?collection={collection}&item={item}{query}"


def scenes(cfg, collection, box, start, end, limit, cloud=True):
    s, w, n, e = box
    q = {"collections": [collection], "bbox": [w, s, e, n], "limit": limit, "sortby": [{"field": "properties.datetime", "direction": "desc"}]}
    if start:
        q["datetime"] = f"{start}/{end}"
    if cloud:
        q["query"] = {"eo:cloud_cover": {"lt": cfg["collect"]["scene_cloud_max"]}}
    return json.loads(fetch(cfg["collect"]["stac"], q))["features"]


def rect_of(site, box, px):
    """변화 측정 범위의 픽셀 사각형"""
    s, w, n, e = site_bbox(site)
    if not box:
        return 0, 0, px, px
    x = lambda v: max(0, min(px, int((v - w) / (e - w) * px)))
    y = lambda v: max(0, min(px, int((n - v) / (n - s) * px)))
    return x(box[1]), y(box[2]), x(box[3]), y(box[0])


def cloud_share(scl, rect):
    w, _, ch, px = scl
    x0, y0, x1, y1 = rect
    vals = [px[(y * w + x) * ch] for y in range(y0, y1) for x in range(x0, x1)]
    return sum(v in BAD_SCL for v in vals) / max(len(vals), 1)


def indices(a, b, i):
    """(NDVI, NDBI) — a·b는 채널 수, 바이트 (SWIR, NIR, 적색)"""
    s, n, r = b[i], b[i + 1], b[i + 2]
    return (n - r) / (n + r) if n + r else 0.0, (s - n) / (s + n) if s + n else 0.0


def changed_share(img_a, img_b, rect, threshold):
    """두 시점 사이 NDVI·NDBI 변화 벡터가 문턱을 넘는 픽셀 비율"""
    w, _, ch, a = img_a
    b = img_b[3]
    x0, y0, x1, y1 = rect
    hit = total = 0
    for y in range(y0, y1):
        for x in range(x0, x1):
            i = (y * w + x) * ch
            if ch == 4 and (a[i + 3] == 0 or b[i + 3] == 0):
                continue
            v1, b1 = indices(ch, a, i)
            v2, b2 = indices(ch, b, i)
            total += 1
            hit += math.hypot(v2 - v1, b2 - b1) > threshold
    return hit / total if total else None


def months_ago(today, n):
    i = today.year * 12 + today.month - 1 - n
    return datetime.date(i // 12, i % 12 + 1, min(today.day, 28))


def sentinel(site, cfg, today, folder):
    """시점마다 시설 위에 구름이 없는 장면을 받는다. 오래된 순으로 낸다"""
    c, box, px, found = cfg["collect"], site_bbox(site), size_px(site, cfg), {}
    whole = (0, 0, px, px)
    for months in c["offsets_months"]:
        end = months_ago(today, months)
        start = end - datetime.timedelta(days=c["window_days"])
        for f in scenes(cfg, "sentinel-2-l2a", box, f"{start}T00:00:00Z", f"{end}T23:59:59Z", c["candidates"]):
            day = f["properties"]["datetime"][:10]
            if day in found:
                break
            scl_path, vis, ana = folder / f"{day}.scl.png", folder / f"{day}.png", folder / f"{day}.bands.png"
            if not scl_path.exists():
                scl_path.write_bytes(fetch(crop_url(cfg, "sentinel-2-l2a", f["id"], box, px, "&assets=SCL&resampling=nearest")))
            cloud = cloud_share(decode_png(scl_path.read_bytes()), whole)
            if cloud > c["site_cloud_max"]:
                continue
            if not vis.exists():
                vis.write_bytes(fetch(crop_url(cfg, "sentinel-2-l2a", f["id"], box, px, "&assets=visual&asset_bidx=visual%7C1,2,3&nodata=0")))
                ana.write_bytes(fetch(crop_url(cfg, "sentinel-2-l2a", f["id"], box, px, "&assets=B11&assets=B08&assets=B04&rescale=0,6000&nodata=0")))
                time.sleep(c["pause_s"])
            found[day] = {"date": day, "scene": f["id"], "cloud": round(cloud, 3), "res_m": 10, "path": vis.relative_to(common.ROOT).as_posix()}
            break
    return [found[d] for d in sorted(found)]


def aerial(site, cfg, folder):
    """미국 시설의 NAIP — 시설 중심을 담은 가장 최근 항목"""
    box = site_bbox(site)
    lat, lon = site["center"]
    best = next((f for f in scenes(cfg, "naip", box, None, None, 12, cloud=False) if f["bbox"][0] <= lon <= f["bbox"][2] and f["bbox"][1] <= lat <= f["bbox"][3]), None)
    if not best:
        return []
    day = best["properties"]["datetime"][:10]
    path = folder / f"{day}.naip.png"
    if not path.exists():
        path.write_bytes(fetch(crop_url(cfg, "naip", best["id"], box, cfg["collect"]["max_px"], "&assets=image&asset_bidx=image%7C1,2,3")))
    return [{"date": day, "scene": best["id"], "res_m": best["properties"].get("gsd"), "path": path.relative_to(common.ROOT).as_posix()}]


def overpass_query(box):
    s, w, n, e = box
    return f'[out:json][timeout:60];way["building"]({s:.6f},{w:.6f},{n:.6f},{e:.6f});out tags geom;'


def parse_buildings(doc):
    out = []
    for e in doc.get("elements") or []:
        ring = [[g["lat"], g["lon"]] for g in e.get("geometry") or []]
        if len(ring) >= 3:
            tags = e.get("tags") or {}
            out.append({"osm": f"way/{e['id']}", "name": tags.get("name"), "building": tags.get("building"), "area_m2": round(sv.ring_area(ring)),
                        "center": [round(sum(p[0] for p in ring) / len(ring), 5), round(sum(p[1] for p in ring) / len(ring), 5)]})
    return sorted(out, key=lambda b: -b["area_m2"])


def buildings(site, cfg, today):
    """건물 윤곽 — 이름과 면적만 저장한다"""
    path = sv.SITES / "footprints" / f"{site['id']}.json"
    if path.exists():
        age = (today - datetime.date.fromisoformat(json.loads(path.read_text(encoding="utf-8"))["as_of"])).days
        if age < cfg["collect"]["footprint_max_age_days"]:
            return
    raw = fetch(cfg["collect"]["overpass"], urllib.parse.urlencode({"data": overpass_query(site_bbox(site))}).encode(), pause=cfg["collect"]["overpass_pause_s"])
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"as_of": today.isoformat(), "source": "OpenStreetMap", "buildings": parse_buildings(json.loads(raw))}, ensure_ascii=False, indent=1), encoding="utf-8")


def measure_units(site, images, cfg, today):
    """호기별 변화 — 첫 영상 대비와 최근 6개월"""
    if len(images) < 2:
        return {}
    px, th = size_px(site, cfg), cfg["change"]["threshold"]
    load = {i["date"]: decode_png((common.ROOT / i["path"].replace(".png", ".bands.png")).read_bytes()) for i in images}
    first, last = images[0]["date"], images[-1]["date"]
    cut = months_ago(today, RECENT_MONTHS).isoformat()
    base_recent = next((i["date"] for i in reversed(images) if i["date"] <= cut), first)
    out = {}
    for u in site.get("units") or [{"name": "전체"}]:
        rect = rect_of(site, u.get("box"), px)
        out[u["name"]] = {"series": [{"date": i["date"], "changed": round(changed_share(load[first], load[i["date"]], rect, th) or 0, 3)} for i in images[1:]],
                          "recent": changed_share(load[base_recent], load[last], rect, th) if base_recent != last else None}
    return out


def collect_site(site, cfg, today):
    folder = STATE / site["id"] / "_".join(f"{v:.3f}" for v in (*site["center"], site["half_km"]))   # 범위를 고치면 옛 영상을 다시 쓰지 않는다
    folder.mkdir(parents=True, exist_ok=True)
    images = sentinel(site, cfg, today, folder)
    air = aerial(site, cfg, folder)
    note = None
    try:
        buildings(site, cfg, today)
    except (urllib.error.URLError, TimeoutError) as e:   # Overpass가 바쁘면 영상만 받고 다음 회차에 윤곽을 받는다
        note = f"건물 윤곽 조회 실패: {e}"
    doc = {"site": site["id"], "as_of": today.isoformat(), "bbox": site_bbox(site), "px": size_px(site, cfg), "images": images, "aerial": air, "units": measure_units(site, images, cfg, today), "footprint_error": note}
    path = sv.SITES / "latest" / f"{site['id']}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(doc, ensure_ascii=False, indent=1), encoding="utf-8")
    return len(images), len(air)


def run(today=None, only=None):
    today, cfg, reg = today or common.now_kst().date(), sv.config(), sv.registry()
    done, errors = 0, []
    for sid, site in reg.items():
        if only and only not in (sid, site["company"]):
            continue
        if site.get("kind") not in cfg["kinds"]:
            errors.append(f"{sid}: 받지 않는 시설 종류 {site.get('kind')}")
            continue
        try:
            n, a = collect_site(site, cfg, today)
            done += 1
            print(f"{sid}: 위성 {n}장, 항공 {a}장")
        except Exception as e:
            errors.append(f"{sid}: {type(e).__name__} {e}")
    if errors and not done:
        raise RuntimeError("위성 영상을 받지 못했다: " + "; ".join(errors[:3]))
    return f"시설 {done}곳, 오류 {len(errors)}건" + ("".join("\n  " + e for e in errors[:5]))


def grid_image(site_id, name=None):
    """눈금(100m, 500m마다 굵게)을 얹어 두 배로 키운 판독용 영상"""
    late = sv.latest(site_id)
    item = next((i for i in late["aerial"] + late["images"] if i["date"] == name), None) if name else late["images"][-1]
    w, h, ch, px = decode_png((common.ROOT / item["path"]).read_bytes())
    s, west, n, e = late["bbox"]
    m_per_px = (n - s) * sv.M_PER_DEG / h
    step, out = max(1, int(round(GRID_M / m_per_px))), bytearray()
    scale = 2
    for y in range(h * scale):
        for x in range(w * scale):
            sx, sy = x // scale, y // scale
            i = (sy * w + sx) * ch
            line = x % (step * scale) == 0 or y % (step * scale) == 0
            major = x % (step * scale * 5) == 0 or y % (step * scale * 5) == 0
            out += bytes((255, 240, 0)) if major else bytes(min(255, 110 + v // 2) for v in px[i:i + 3]) if line else px[i:i + 3]
    path = common.ROOT / item["path"].replace(".png", ".grid.png")
    path.write_bytes(encode_png(w * scale, h * scale, 3, bytes(out)))
    return path, m_per_px / scale


def measure(site_id, day, points):
    """영상 픽셀 꼭짓점 → 위도·경도와 면적"""
    late = sv.latest(site_id)
    item = next(i for i in late["images"] + late["aerial"] if i["date"] == day)
    w, h, _, _ = decode_png((common.ROOT / item["path"]).read_bytes())
    s, west, n, e = late["bbox"]
    ring = [[round(n - y / h * (n - s), 6), round(west + x / w * (e - west), 6)] for x, y in points]
    return ring, round(sv.ring_area(ring))


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", action="store_true")
    ap.add_argument("--site")
    ap.add_argument("--company")
    ap.add_argument("--status", action="store_true")
    ap.add_argument("--grid", nargs="+")
    ap.add_argument("--measure", nargs="+")
    a = ap.parse_args()
    if a.run or a.site or a.company:
        print(run(only=a.site or a.company))
    if a.grid:
        path, mpp = grid_image(*a.grid)
        print(path, f"픽셀당 {mpp:.1f}m, 눈금 {GRID_M}m")
    if a.measure:
        print(measure(a.measure[0], a.measure[1], [tuple(map(float, p.split(","))) for p in a.measure[2:]]))
    if a.status:
        for sid, site in sv.registry().items():
            late = sv.latest(sid) or {}
            print(sid, site["name"], late.get("as_of"), [i["date"] for i in late.get("images") or []], [i["date"] for i in late.get("aerial") or []])


if __name__ == "__main__":
    main()
