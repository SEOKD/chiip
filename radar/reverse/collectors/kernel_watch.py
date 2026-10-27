"""L5 기술 아티팩트 — 리눅스 커널 메일링리스트(lore.kernel.org 공개 Atom 검색)
최근 7일 패치·토론에서 T0 영문명 언급 → 출시 전 하드웨어 지원 정황(S2) 후보.
"""
import urllib.error
import urllib.parse

from common_rev import common, english_names, lexicon, save_candidates
from pollers import rss

SOURCE_ID = "src-kernel-lore"
URL = "https://lore.kernel.org/all/?q={q}&x=A"


def run():
    lex = lexicon()
    cands = []
    for eid in lex:
        for name in english_names(eid, lex)[:2]:
            q = urllib.parse.quote_plus(f'"{name}" d:7.days.ago..')
            try:
                raw = common.http_get(URL.format(q=q), timeout=60)
            except urllib.error.HTTPError as exc:
                if exc.code == 404:  # public-inbox: 검색 결과 없음
                    continue
                raise
            for e in rss.parse_feed(raw)[:30]:
                cands.append({"uid": e["link"], "mentioned_entity": eid, "match_text": name,
                              "counterparty": "lore.kernel.org", "form": "커널", "published_at": rss.to_iso(e["date"]),
                              "language": "en", "url": e["link"], "original_title": common.strip_tags(e["title"])[:200],
                              "signal_type_hint": "커널"})
    n = save_candidates("L5", SOURCE_ID, cands)
    common.record_health(SOURCE_ID, True)
    return len(cands), n


if __name__ == "__main__":
    print("커널 메일링리스트: 후보 %d, 신규 %d" % run())