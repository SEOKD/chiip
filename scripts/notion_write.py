"""노션에 '치입 검토' 같은 하위 페이지 만들기 (NOTION_TOKEN 필요) — 헤드리스 작업용

마크다운 일부(#·##·### 제목, - 목록, > 인용, 빈 줄로 나뉜 문단, | 표 줄은 문단으로)를 노션 블록으로 바꿔
부모 페이지 아래 새 페이지를 만든다. 블록은 요청당 100개, 텍스트 조각은 2000자 제한(developers.notion.com/reference/post-page).
마스터 페이지 본문은 고치지 않는다 — 새 하위 페이지만 만든다.
사용: py scripts/notion_write.py child <parent_page_id> "<제목>" <markdown_file>
"""
import json
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "radar"))
from pollers import common  # noqa: E402


def _rt(text):
    text = text.strip()
    return [{"type": "text", "text": {"content": text[i:i + 2000]}} for i in range(0, max(len(text), 1), 2000)][:100]


def md_blocks(md):
    blocks, para = [], []

    def flush():
        if para:
            blocks.append({"object": "block", "type": "paragraph", "paragraph": {"rich_text": _rt(" ".join(para))}})
            para.clear()
    for line in md.splitlines():
        s = line.rstrip()
        if not s.strip():
            flush()
            continue
        for n in (3, 2, 1):
            if s.startswith("#" * n + " "):
                flush()
                t = f"heading_{n}"
                blocks.append({"object": "block", "type": t, t: {"rich_text": _rt(s[n + 1:])}})
                break
        else:
            if s.lstrip().startswith(("- ", "* ")):
                flush()
                blocks.append({"object": "block", "type": "bulleted_list_item",
                               "bulleted_list_item": {"rich_text": _rt(s.lstrip()[2:])}})
            elif s.startswith("> "):
                flush()
                blocks.append({"object": "block", "type": "quote", "quote": {"rich_text": _rt(s[2:])}})
            elif s.startswith("|") and set(s.replace("|", "").strip()) <= set("-: "):
                continue      # 표 구분선
            else:
                para.append(s)
    flush()
    return blocks


def _post(path, body, method="POST"):
    api = common.load_yaml("config/notion.yaml")["api"]
    tok = common.load_env().get(api.get("token_env", "NOTION_TOKEN"))
    if not tok:
        raise SystemExit("NOTION_TOKEN 없음")
    req = urllib.request.Request(f"{api['base']}{path}", json.dumps(body).encode(), method=method,
                                 headers={"Authorization": f"Bearer {tok}", "Notion-Version": api.get("version", "2026-03-11"),
                                          "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read().decode("utf-8"))


def create_child(parent_id, title, md):
    blocks = md_blocks(md)
    page = _post("/pages", {"parent": {"type": "page_id", "page_id": parent_id},
                            "properties": {"title": {"title": [{"text": {"content": title[:200]}}]}},
                            "children": blocks[:100]})
    for i in range(100, len(blocks), 100):
        _post(f"/blocks/{page['id']}/children", {"children": blocks[i:i + 100]}, method="PATCH")
    return page.get("url", page["id"])


def main(argv):
    if len(argv) != 4 or argv[0] != "child":
        print(__doc__)
        return 1
    print(create_child(argv[1], argv[2], Path(argv[3]).read_text(encoding="utf-8")))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
