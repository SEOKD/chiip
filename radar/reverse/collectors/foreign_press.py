"""L9 외국어 언론 — Google News RSS 번체(대만)·간체(중국)·일본어, lexicon 현지 표기 + 이벤트 키워드.
원문 제목 보존(번역은 scout가 병기). 유료 매체 본문은 수집하지 않는다.
"""
import hashlib
import urllib.parse

from common_rev import common, lexicon, save_candidates
from pollers import rss

SOURCE_ID = "src-foreign-press"
GN = "https://news.google.com/rss/search?q={q}&hl={hl}&gl={gl}&ceid={gl}:{ceid}"
LOCALES = [  # (lexicon 키, hl, gl, ceid 언어, 이벤트 키워드)
    ("zh_hant", "zh-TW", "TW", "zh-Hant", "訂單 OR 擴產 OR 認證 OR 供應"),
    ("zh_hans", "zh-CN", "CN", "zh-Hans", "订单 OR 扩产 OR 认证 OR 供应"),
    ("ja", "ja", "JP", "ja", "受注 OR 採用 OR 量産 OR 供給"),
]


TOPIC = ["HBM", "DRAM", "NAND", "記憶體", "存储", "メモリ", "晶圓", "晶圆", "半導體", "半导体", "半導体", "代工", "ファウンドリ",
         "載板", "载板", "基板", "PCB", "CCL", "銅箔", "铜箔", "MLCC", "封裝", "封装", "パッケージ", "CoWoS", "AI", "伺服器",
         "サーバー", "訂單", "订单", "受注", "擴產", "扩产", "量産", "認證", "认证", "供應", "供应", "供給", "鏡頭", "カメラモジュール"]


def run():
    cands = []
    for eid in lexicon():
        lex = common.load_yaml(f"config/lexicon/{eid}.yaml") or {}
        for key, hl, gl, ceid, kw in LOCALES:
            for name in ((lex.get("names") or {}).get(key) or [])[:1]:
                q = urllib.parse.quote(f'"{name}" ({kw}) when:2d')
                for e in rss.parse_feed(common.http_get(GN.format(q=q, hl=hl, gl=gl, ceid=ceid)))[:15]:
                    title = common.strip_tags(e["title"])
                    # 반도체·소재·부품 문맥만(소비자 가전 기사 등 잡음 제외)
                    if not any(k.lower() in title.lower() for k in TOPIC):
                        continue
                    cands.append({"uid": hashlib.sha1(e["link"].encode()).hexdigest()[:16], "mentioned_entity": eid,
                                  "match_text": name, "counterparty": "", "form": "현지언론",
                                  "published_at": rss.to_iso(e["date"]), "language": hl, "url": e["link"],
                                  "original_title": common.strip_tags(e["title"]), "signal_type_hint": "현지언론"})
    n = save_candidates("L9", SOURCE_ID, cands)
    common.record_health(SOURCE_ID, True)
    return len(cands), n


if __name__ == "__main__":
    print("외국어 언론: 후보 %d, 신규 %d" % run())