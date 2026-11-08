"""Vertex 인증 — 키 우선, 없으면 로그인(마스터 지시 2026-11-08 로그인 만료 없는 자동 수집)"""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "tenbagger"))
import vertex_auth as VA  # noqa: E402


class TestAuth(unittest.TestCase):
    def test_key_first(self):
        orig = VA._key
        try:
            VA._key = lambda: "k"
            self.assertEqual(VA.mode(), "api_key")
            VA._key = lambda: None
            self.assertEqual(VA.mode(), "adc")
        finally:
            VA._key = orig

    def test_all_callers_use_helper(self):
        for f in ("product_images.py", "image_qa.py", "bom_discover.py"):
            src = (ROOT / "scripts" / "tenbagger" / f).read_text(encoding="utf-8")
            self.assertIn("vertex_auth.client(", src, f)
            self.assertNotIn("genai.Client(vertexai=True, project=", src, f)   # 로그인 전용 경로 직접 호출 금지


if __name__ == "__main__":
    unittest.main()
