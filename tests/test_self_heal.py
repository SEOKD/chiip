"""수집 채널 자가 복구 (마스터 지시 2026-11-02)"""
import sys
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "radar"))
import self_heal as sh  # noqa: E402

NOW = datetime(2026, 11, 2, 12, 0, tzinfo=sh.common.KST)
CFG = {"error_count": 3, "max_retries": 2, "telegram_min_score": 7, "report_keep_h": 12, "route_hold_h": 3, "routed": ["fiscal"], "jobs": {"trade-ppi": "trade_ppi"}, "files": []}


class Store:
    """load_state·save_state를 메모리로"""

    def __init__(self, **kw):
        self.d = kw

    def load(self, name, default=None):
        return self.d.get(name, {} if default is None else default)

    def save(self, name, data):
        self.d[name] = data


def run(store, found, now=NOW, retry_ok=False):
    with mock.patch.object(sh.common, "load_state", store.load), mock.patch.object(sh.common, "save_state", store.save), mock.patch.object(sh.common, "record_health"), \
            mock.patch.object(sh, "detect", return_value=found), mock.patch.object(sh, "retry", return_value=retry_ok) as r, mock.patch.object(sh, "tell", return_value=1) as t:
        sh.run(now, CFG)
    return r, t


class TestClassify(unittest.TestCase):
    def test_classes(self):
        for text, kind in (("DART_API_KEY 없음", "key"), ("NAVER_CLIENT_ID/SECRET 없음", "key"), ("HTTP Error 403: Forbidden", "key"), ("HTTP 429", "rate"), ("You've hit your weekly limit", "rate"), ("URLError timed out", "network"),
                           ("HTTP Error 503", "network"), ("JSONDecodeError: x", "schema"), ("KeyError: 'value'", "schema"), ("이상한 일", "unknown")):
            self.assertEqual(sh.classify(text), kind, text)


class TestLadder(unittest.TestCase):
    def test_transient_is_retried_with_growing_gap(self):
        s = Store()
        r, _ = run(s, {"trade-ppi": "URLError timed out"})
        r.assert_called_once()
        e = s.d["self_heal"]["items"]["trade-ppi"]
        self.assertEqual(e["attempts"], 1)
        r, _ = run(s, {"trade-ppi": "URLError timed out"}, NOW + timedelta(minutes=30))
        r.assert_not_called()

    def test_recovered_channel_clears_quietly(self):
        s = Store()
        run(s, {"trade-ppi": "URLError"})
        _, t = run(s, {})
        t.assert_not_called()
        self.assertEqual(s.d["self_heal"]["items"], {})
        self.assertEqual(s.d["self_heal"]["history"][-1]["how"], "자동 복구")

    def test_retries_exhausted_go_to_model(self):
        s = Store()
        for h in (0, 3, 8):
            run(s, {"trade-ppi": "KeyError: 'x'"}, NOW + timedelta(hours=h))
        self.assertTrue(s.d["self_heal"]["items"]["trade-ppi"]["repair_at"])

    def test_key_problem_tells_master_once(self):
        s = Store()
        _, t = run(s, {"src-x": "키 없음"})
        t.assert_called_once()
        _, t = run(s, {"src-x": "키 없음"})
        t.assert_not_called()

    def test_data_channel_is_routed_around(self):
        s = Store()
        run(s, {"fiscal": "HTTP 429"})
        self.assertIn("fiscal", s.d["channel_down"])
        run(s, {})
        self.assertEqual(s.d["channel_down"], {})


class TestModelStep(unittest.TestCase):
    def state(self):
        return Store(self_heal={"items": {"a": {"repair_at": "x", "kind": "schema", "why": "w", "attempts": 3}}})

    def test_due_then_hold(self):
        s = self.state()
        with mock.patch.object(sh.common, "load_state", s.load), mock.patch.object(sh.common, "save_state", s.save):
            self.assertTrue(sh.status(NOW)["due"])
            sh.offered(NOW)
            self.assertFalse(sh.status(NOW + timedelta(hours=1))["due"])
            self.assertTrue(sh.status(NOW + timedelta(hours=7))["due"])

    def test_resolved_clears(self):
        s = self.state()
        with mock.patch.object(sh.common, "load_state", s.load), mock.patch.object(sh.common, "save_state", s.save):
            sh.finish("a", "주소 교체", True, NOW)
        self.assertEqual(s.d["self_heal"]["items"], {})

    def test_failed_tells_master_and_stops_retrying(self):
        s = self.state()
        with mock.patch.object(sh.common, "load_state", s.load), mock.patch.object(sh.common, "save_state", s.save), mock.patch.object(sh, "tell", return_value=1) as t:
            sh.finish("a", "원천 폐지", False, NOW)
            self.assertFalse(sh.status(NOW)["due"])
        t.assert_called_once()

    def test_model_report_counts_as_problem(self):
        s = Store()
        with mock.patch.object(sh.common, "load_state", s.load), mock.patch.object(sh.common, "save_state", s.save), mock.patch.object(sh, "age_hours", return_value=1):
            sh.report("zacks", "429", NOW)
            found = sh.detect(NOW, {**CFG, "files": []})
        self.assertEqual(found.get("zacks"), "429")


class TestWiring(unittest.TestCase):
    def test_job_and_config(self):
        self.assertIn('"self_heal"', (ROOT / "radar" / "run_hourly.py").read_text(encoding="utf-8"))
        cfg = sh.config()
        self.assertIn("fiscal", cfg["routed"])

    def test_router_skips_down_channel(self):
        sys.path.insert(0, str(ROOT / "scripts" / "fiscal"))
        import source_router as sr
        down = {"easyconomics": (NOW + timedelta(hours=1)).isoformat()}
        with mock.patch.object(sr.common, "load_state", lambda n, d=None: down if n == "channel_down" else (d or {})):
            self.assertFalse(sr.available("easyconomics", {}, {}, NOW))
            self.assertTrue(sr.available("zacks", {}, {}, NOW))


if __name__ == "__main__":
    unittest.main()


class TestTimeoutNotRetriedInline(unittest.TestCase):
    """시간 초과 작업은 self-heal 안에서 다시 돌리지 않는다(2026-11-13 점검: self-heal 26회 연속 10분 초과)"""

    def test_timeout_waits(self):
        import self_heal as sh
        from unittest import mock
        called = []
        st = {}
        with mock.patch.object(sh, "detect", lambda now, cfg: {"trade-ppi": "시간 초과 10분 — 다음 회차에 다시"}), \
             mock.patch.object(sh, "retry", lambda ch, cfg: called.append(ch) or True), \
             mock.patch.object(sh, "plan", lambda e, k, n, c: "retry"), \
             mock.patch.object(sh.common, "load_state", lambda n, d=None: st.get(n, d)), \
             mock.patch.object(sh.common, "save_state", lambda n, v: st.__setitem__(n, v)):
            sh.run(cfg={"jobs": {}, "routed": [], "route_hold_h": 1})
        self.assertEqual(called, [])
