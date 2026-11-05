"""제품·생산시설 실사 사진(마스터 지시 2026-11-05 "제품 포트폴리오 설명란에서 직관적으로 이해할 수 있게 실사에 가까운 이미지를 찾거나 생성해 넣어줘. 생산시설(공장, 팹 등)도 마찬가지")

원천 = 위키미디어 공용(Wikimedia Commons) — 재배포가 허용된 자유 라이선스 사진만 쓴다. 저작자·라이선스 표기를 사진 아래에 남긴다.
회사 홍보 사진·언론 사진은 라이선스가 불분명해 받지 않는다. 생성 이미지는 쓰지 않는다 — 실제 제품·시설로 오인될 수 있어서다.
모델은 datapack `photos`에 공용 파일 이름만 쓴다(찾지 못하면 그 항목을 빼면 된다, 없어도 리포트는 멈추지 않는다):
  "photos": [{"for": "product" | "site", "name": "<lead.products 이름 또는 시설 이름>", "file": "File:<공용 파일 이름>", "caption": "무엇이 보이는지 한 줄"}]
받기: py scripts/tenbagger/photo_view.py --fetch <datapack.json>   (결정론, 모델 없음 — 리포트 렌더 전에 1회)
찾기: py scripts/tenbagger/photo_view.py --search "<검색어>"     (후보 파일 이름·라이선스 목록, 모델이 고른다)
"""
import base64
import hashlib
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "radar"))
from pollers import common  # noqa: E402

API = "https://commons.wikimedia.org/w/api.php"
DIR = ROOT / "knowledge" / "models" / "photos"
WIDTH = 640
FREE = re.compile(r"^(CC0|CC BY(-SA)? [0-9.]+|CC BY(-SA)?|Public domain|PD.*|GFDL.*)", re.I)   # 자유 라이선스만
UA = {"User-Agent": "chiip-research/0.1 (personal research; https://github.com/SEOKD/chiip)"}   # 위키미디어 UA 정책 — 개인 이메일 넣지 않는다


def api(params):
    return json.loads(common.http_get(API, {"format": "json", **params}, headers=UA, timeout=30))


def info(file):
    """공용 파일 → 썸네일 주소·라이선스·저작자. 자유 라이선스가 아니면 None"""
    d = api({"action": "query", "titles": file, "prop": "imageinfo", "iiprop": "url|extmetadata|mime", "iiurlwidth": str(WIDTH)})
    page = next(iter(d.get("query", {}).get("pages", {}).values()), {})
    ii = (page.get("imageinfo") or [None])[0]
    if not ii:
        return None
    meta = ii.get("extmetadata") or {}
    lic = (meta.get("LicenseShortName") or {}).get("value", "")
    if not FREE.match(lic.strip()):
        return None
    artist = common.strip_tags((meta.get("Artist") or {}).get("value", "")) or "미상"
    return {"file": page.get("title", file), "thumb": ii.get("thumburl") or ii["url"], "page": ii.get("descriptionurl"), "license": lic, "artist": artist[:80], "mime": ii.get("mime")}


def search(q, n=10):
    d = api({"action": "query", "list": "search", "srsearch": q, "srnamespace": "6", "srlimit": str(n)})
    out = []
    for r in d.get("query", {}).get("search", []):
        x = info(r["title"])
        if x:
            out.append({"file": x["file"], "license": x["license"], "artist": x["artist"]})
    return out


def path_of(file):
    return DIR / (hashlib.sha1(file.encode("utf-8")).hexdigest()[:16] + ".jpg")


def fetch(dp):
    """datapack photos를 받아 knowledge/models/photos/에 저장. 이미 있으면 건너뛴다"""
    DIR.mkdir(parents=True, exist_ok=True)
    got = []
    for p in dp.get("photos") or []:
        f, meta = path_of(p["file"]), path_of(p["file"]).with_suffix(".json")
        if f.exists() and meta.exists():
            got.append(p["file"]); continue
        x = info(p["file"])
        if not x:
            print(json.dumps({"skip": p["file"], "why": "파일 없음 또는 자유 라이선스 아님"}, ensure_ascii=False))
            continue
        f.write_bytes(common.http_get(x["thumb"], headers=UA, timeout=60))
        meta.write_text(json.dumps(x, ensure_ascii=False, indent=1), encoding="utf-8")
        got.append(p["file"])
    return got


def load(file):
    f = path_of(file)
    m = f.with_suffix(".json")
    if not (f.exists() and m.exists()):
        return None
    x = json.loads(m.read_text(encoding="utf-8"))
    mime = x.get("mime") if str(x.get("mime", "")).startswith("image/") and x.get("mime") != "image/svg+xml" else "image/jpeg"
    return {**x, "uri": f"data:{mime};base64," + base64.b64encode(f.read_bytes()).decode(), "rel": f"knowledge/models/photos/{f.name}"}


def block(dp, kind, names=None):
    """사진 블록 — kind product|site. 받아 둔 사진만 싣는다"""
    items = []
    for p in dp.get("photos") or []:
        if p.get("for") != kind or (names is not None and p.get("name") not in names):
            continue
        x = load(p["file"])
        if x:   # 리포트 JSON에는 파일 이름만 — 그림 데이터는 렌더 때 읽는다(JSON이 커지지 않게)
            items.append({"name": p.get("name"), "caption": p.get("caption") or "", "file": p["file"], "jpg": path_of(p["file"]).name, "page": x.get("page"),
                          "credit": f"사진: {x['artist']} · {x['license']} · Wikimedia Commons"})
    return {"type": "photos", "items": items} if items else None


def main(argv):
    sys.stdout.reconfigure(encoding="utf-8")
    if argv[:1] == ["--search"]:
        print(json.dumps(search(" ".join(argv[1:])), ensure_ascii=False, indent=1))
    elif argv[:1] == ["--fetch"]:
        print(json.dumps({"fetched": fetch(json.loads(Path(argv[1]).read_text(encoding="utf-8")))}, ensure_ascii=False))
    else:
        print(__doc__)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
