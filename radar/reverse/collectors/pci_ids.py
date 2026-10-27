"""L5 PCI ID 공개 저장소 (pci-ids.ucw.cz) — T0 벤더 ID 아래 새로 등록된 장치 감지
벤더 ID는 첫 실행 때 파일에서 벤더명으로 찾아 기록(기억에 의존하지 않음).
"""
import re

from common_rev import common, lexicon, save_candidates

SOURCE_ID = "src-pci-ids"
URL = "https://pci-ids.ucw.cz/v2.2/pci.ids"
BASE = common.ROOT / "radar" / "reverse" / "baselines" / "pci_ids_t0.txt"
VENDOR_HINTS = {"co-samsung": ["Samsung Electronics"], "co-skhynix": ["SK hynix", "Solidigm"]}


def run():
    text = common.http_get(URL, timeout=60).decode("utf-8", errors="ignore")
    current, entries = None, set()
    for line in text.splitlines():
        if not line or line.startswith("#"):
            continue
        m = re.match(r"^([0-9a-f]{4})\s+(.+)$", line)
        if m:
            current = None
            for eid, hints in VENDOR_HINTS.items():
                if any(h.lower() in m.group(2).lower() for h in hints):
                    current = (eid, m.group(1), m.group(2).strip())
            continue
        d = re.match(r"^\t([0-9a-f]{4})\s+(.+)$", line)
        if current and d:
            entries.add(f"{current[0]}|{current[1]}|{current[2]}|{d.group(1)}|{d.group(2).strip()}")
    BASE.parent.mkdir(parents=True, exist_ok=True)
    old = set(BASE.read_text(encoding="utf-8").splitlines()) if BASE.exists() else None
    BASE.write_text("\n".join(sorted(entries)), encoding="utf-8")
    cands = []
    if old is not None:
        for e in sorted(entries - old):
            eid, vid, vname, did, dname = e.split("|", 4)
            cands.append({"uid": f"{vid}:{did}", "mentioned_entity": eid, "match_text": vname,
                          "counterparty": "pci-ids", "form": "PCI ID", "published_at": common.iso(common.now_kst()),
                          "language": "en", "url": f"https://pci-ids.ucw.cz/read/PC/{vid}/{did}",
                          "original_title": f"{vname} {did} {dname}", "signal_type_hint": "커널"})
    n = save_candidates("L5", SOURCE_ID, cands)
    common.record_health(SOURCE_ID, True)
    return len(entries), n


if __name__ == "__main__":
    print("PCI ID: T0 장치 %d, 신규 후보 %d (첫 실행은 기준선)" % run())