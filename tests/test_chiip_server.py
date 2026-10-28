"""치입 로컬 서버(크롬 확장 창구) 오프라인 시험 — scripts/chiip_server.py"""
import json
import sys
import tempfile
import threading
import types
import unittest
import urllib.error
import urllib.request
from datetime import timedelta
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "radar"))
sys.path.insert(0, str(ROOT / "scripts"))

from pollers import common  # noqa: E402
import chiip_server as srv  # noqa: E402

OUTBOX = """2026-10-28T18:08:10+09:00 [발송됨][P1] [P1] co-skhynix | 기사 | 18:06
무엇: SK하이닉스 3분기 실적 상회
영향: HBM 비중 확대
2026-10-28T18:10:00+09:00 [미발송-키없음][P2] 키 없어 못 보냄
2026-10-28T19:00:00+09:00 [발송됨][SCORE] [AI 밸류체인 포커스 10/28] 41종목
"""


class TestAlertsAndSummary(unittest.TestCase):
    def test_recent_alerts_blocks_sent_only(self):
        with tempfile.TemporaryDirectory() as d, mock.patch.object(common, "STATE", Path(d)):
            (Path(d) / "outbox.log").write_text(OUTBOX, encoding="utf-8")
            a = srv.recent_alerts()
        self.assertEqual([x["level"] for x in a], ["SCORE", "P1"])        # 최신 먼저, 미발송 제외
        self.assertIn("HBM 비중 확대", a[1]["text"])                        # 여러 줄 블록을 한 알림으로

    def test_summary_empty_and_filters(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            with mock.patch.object(srv, "ROOT", root), mock.patch.object(common, "STATE", root / "state"):
                empty = srv.summary()
                self.assertEqual(empty["earnings"], [])
                self.assertEqual(empty["alpha_top"], [])
                self.assertIsNone(empty["regime"]["rf_us"])
                today = common.now_kst().date()
                (root / "knowledge/models/alpha").mkdir(parents=True)
                (root / "knowledge/models/earnings").mkdir(parents=True)
                (root / "knowledge/models/alpha/latest.json").write_text(json.dumps({
                    "threshold": 5.0, "pass": ["co-isc"],
                    "rows": {"co-isc": {"name": "ISC", "total": 6.2, "delta": None},
                             "co-samsung": {"name": "삼성전자", "total": 4.9, "delta": -0.1},
                             "co-x": {"name": "X", "total": None}}}), encoding="utf-8")
                ev = lambda days, cid, name: {"id": cid, "name": name, "date": (today + timedelta(days=days)).isoformat(),
                                              "time_kst": "10:00", "local": "", "title": "실적", "source": "KIND IR일정", "url": ""}
                (root / "knowledge/models/earnings/upcoming.json").write_text(json.dumps({"events": [
                    ev(-1, "co-isc", "ISC"), ev(1, "co-isc", "ISC"), ev(2, "co-samsung", "삼성전자")]}), encoding="utf-8")
                s = srv.summary()
        self.assertEqual(len(s["earnings"]), 2)                               # 지난 일정 제외
        self.assertTrue(s["earnings"][0]["alpha_pass"])
        self.assertFalse(s["earnings"][1]["alpha_pass"])
        self.assertEqual([r["name"] for r in s["alpha_top"]], ["ISC", "삼성전자"])   # 미산정 제외, 높은 순


class TestSend(unittest.TestCase):
    def test_rejects_non_http(self):
        ok, _ = srv.send({"url": "file:///C:/secret.txt", "action": "radar"})
        self.assertFalse(ok)
        ok, _ = srv.send({"url": "javascript:alert(1)"})
        self.assertFalse(ok)

    def test_radar_writes_inbox_once(self):
        with tempfile.TemporaryDirectory() as d, mock.patch.object(common, "STATE", Path(d) / "state"), \
                mock.patch.object(common, "INBOX", Path(d) / "inbox"):
            (Path(d) / "state").mkdir()
            p = {"url": "https://example.com/a", "title": "HBM 기사", "selection": "x" * 500, "note": "중요", "action": "radar"}
            ok, msg = srv.send(p)
            self.assertTrue(ok)
            files = list((Path(d) / "inbox").rglob("*.json"))
            self.assertEqual(len(files), 1)
            item = json.loads(files[0].read_text(encoding="utf-8"))
            self.assertEqual(item["doc_type"], "마스터 제보")
            self.assertEqual(item["source_id"], "src-chrome-ext")
            self.assertEqual(len(item["master_selection"]), 500)               # 200자 snippet과 달리 선택 영역 보존
            ok2, msg2 = srv.send(p)
            self.assertTrue(ok2)
            self.assertIn("이미", msg2)
            self.assertEqual(len(list((Path(d) / "inbox").rglob("*.json"))), 1)   # 중복 저장 없음

    def test_notion_queues_without_inbox(self):
        calls = {}
        fake_notify = types.SimpleNamespace(remember_alert=lambda item, level, what=None, impact=None: calls.setdefault("ref", "abc123"))
        fake_inbox = types.SimpleNamespace(enqueue=lambda ref, memo=None: calls.update(enq=(ref, memo)))
        with tempfile.TemporaryDirectory() as d, mock.patch.dict(sys.modules, {"notify": fake_notify, "telegram_inbox": fake_inbox}), \
                mock.patch.object(common, "INBOX", Path(d) / "inbox"):
            ok, msg = srv.send({"url": "https://example.com/b", "title": "t", "note": "메모", "action": "notion"})
            self.assertTrue(ok)
            self.assertEqual(calls["enq"], ("abc123", "메모"))
            self.assertFalse((Path(d) / "inbox").exists())                    # 노션 기록은 레이더 inbox에 쓰지 않음


class TestHttp(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.p_tok = mock.patch.object(srv, "TOKEN_FILE", Path(self.tmp.name) / "tok.txt")
        self.p_tok.start()
        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), srv.Handler)
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()
        self.base = f"http://127.0.0.1:{self.httpd.server_address[1]}"

    def tearDown(self):
        self.httpd.shutdown()
        self.httpd.server_close()
        self.p_tok.stop()
        self.tmp.cleanup()

    def _get(self, path, headers=None):
        req = urllib.request.Request(self.base + path, headers=headers or {})
        try:
            with urllib.request.urlopen(req, timeout=10) as r:
                return r.status, dict(r.headers), json.loads(r.read())
        except urllib.error.HTTPError as e:
            return e.code, dict(e.headers), json.loads(e.read())

    def test_token_required(self):
        self.assertEqual(self._get("/api/ping")[0], 200)
        self.assertEqual(self._get("/api/summary")[0], 401)
        self.assertEqual(self._get("/api/summary", {"X-Chiip-Token": "wrong"})[0], 401)
        code, headers, body = self._get("/api/summary", {"X-Chiip-Token": srv.token(), "Origin": "chrome-extension://abc"})
        self.assertEqual(code, 200)
        self.assertIn("earnings", body)
        self.assertEqual(headers.get("Access-Control-Allow-Origin"), "chrome-extension://abc")
        _, h2, _ = self._get("/api/ping", {"Origin": "https://evil.example"})
        self.assertIsNone(h2.get("Access-Control-Allow-Origin"))              # 일반 웹사이트에는 CORS 허용 안 함


if __name__ == "__main__":
    unittest.main()
