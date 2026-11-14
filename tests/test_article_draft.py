"""기사 소재 채택 → 기사 초안(2026-11-15 마스터 지시)"""
import csv
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "article"))
import article_draft as ad  # noqa: E402
import pitch_feedback as pf  # noqa: E402

GOOD = {"pitch_id": "PITCH-20261115-01", "date": "2026-11-15", "title": "HBF의 걸림돌, GPU가 치운다",
        "subtitle": ["엔비디아 연구진 지연 20배 숨기는 설계 공개", "버퍼 40MB로 이상 성능의 92% 끌어올려"[:20] + "가나다라마바사아자차카타파하", "삼성·SK하이닉스 표준 경쟁에 새 변수 부상"],
        "body": {"lead": ["리드 문장이다."], "newfact": ["뉴팩트 문장이다."], "body1": ["본론 일."], "body2": ["본론 이."], "body3": ["본론 삼."],
                 "quote": {"text": "인용", "speaker": "저자", "title": "엔비디아 리서치", "source": "https://arxiv.org/abs/2611.14776"}},
        "sources": [{"label": "arXiv", "url": "https://arxiv.org/abs/2611.14776"}], "checks": ["샘플 고객 미확인"]}


def fix_sub(d):
    n = len(d["subtitle"][0])
    d["subtitle"] = [s[:n].ljust(n, "다") for s in d["subtitle"]]
    return d


class TestCheck(unittest.TestCase):
    def test_good_passes(self):
        self.assertEqual(ad.check(fix_sub(dict(GOOD))), [])

    def test_uneven_subtitle_fails(self):
        d = dict(GOOD, subtitle=["짧다", "이 줄은 더 길다"])
        self.assertTrue(any("글자 수" in x for x in ad.check(d)))

    def test_order_and_quote_source(self):
        d = fix_sub(dict(GOOD))
        d["body"] = {k: v for k, v in GOOD["body"].items() if k != "body3"}
        d["body"]["quote"] = {"text": "말", "speaker": "", "source": "책"}
        bad = ad.check(d)
        self.assertTrue(any("본론3" in x for x in bad))
        self.assertTrue(any("speaker" in x for x in bad))
        self.assertTrue(any("링크" in x for x in bad))

    def test_quote_null_allowed(self):
        d = fix_sub(dict(GOOD))
        d["body"] = dict(GOOD["body"], quote=None)
        self.assertEqual(ad.check(d), [])

    def test_render_has_parts(self):
        h = ad.render(fix_sub(dict(GOOD)))
        for part in ("<h1>", "class=\"deck\"", "<blockquote>", "arxiv.org", "보강 취재"):
            self.assertIn(part, h)


class TestCallback(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp()) / "log.csv"
        with self.tmp.open("w", encoding="utf-8", newline="") as f:
            w = csv.writer(f)
            w.writerow(["date", "pitch_id", "yama", "sources", "adopted"])
            w.writerow(["2026-11-15", "PITCH-20261115-01", "야마", "src", ""])

    def test_adopt_queues_article(self):
        with mock.patch.object(ad, "queue") as q:
            note, markup = pf.on_callback("pitch:20261115:1:y", self.tmp)
        q.assert_called_once_with("PITCH-20261115-01")
        self.assertIn("기사", note)
        self.assertEqual(markup["inline_keyboard"][0][0]["callback_data"], "noop")
        self.assertTrue(list(csv.DictReader(self.tmp.open(encoding="utf-8")))[0]["adopted"].startswith("채택"))

    def test_pass_does_not_queue(self):
        with mock.patch.object(ad, "queue") as q:
            note, _ = pf.on_callback("pitch:20261115:0:n", self.tmp)
        q.assert_not_called()
        self.assertIn("패스", note)


if __name__ == "__main__":
    unittest.main()
