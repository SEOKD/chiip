"""시설 위성 판독 — 면적·진척·면적 비교 캐파 (마스터 지시 2026-11-03)"""
import copy
import datetime
import json
import sys
import tempfile
import unittest
import zlib
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "tenbagger"))
sys.path.insert(0, str(ROOT / "radar"))
import capacity_view as cv  # noqa: E402
import report_html  # noqa: E402
import site_imagery as si  # noqa: E402
import site_view as sv  # noqa: E402

CFG = sv.config()


def unit(name, area, value=None, **kw):
    u = {"name": name, "role": "생산", "footprint": {"area_m2": area, "source": "공시"}, "stage_seen": "외장 완료", "seen_on": "2026-10-01", **kw}
    if value:
        u["capacity"] = {"value": value, "unit": "웨이퍼/월", "source": "발표"}
    return u


def site(sid, company, units, cls="팹A"):
    return {"id": sid, "name": sid, "kind": "팹", "class": cls, "company": company, "units": units, "location_source": "10-K", "center": [33.0, -112.0], "half_km": 1.0}


REG = {"a": site("a", "co-x", [unit("1기", 100000, 20000), unit("2기", 50000)]),
       "b": site("b", "co-y", [unit("1기", 100000, 40000)]),
       "c": site("c", "co-z", [unit("1기", 100000)])}
LATE = {"as_of": "2026-10-20", "images": [{"date": "2026-10-01", "path": "x.png"}], "aerial": []}


class TestArea(unittest.TestCase):
    def test_ring_area_square(self):
        d = 100 / sv.M_PER_DEG
        self.assertAlmostEqual(sv.ring_area([[0, 0], [0, d], [d, d], [d, 0]]), 10000, delta=10)

    def test_osm_needs_every_id(self):
        u = {"footprint": {"osm": ["way/1", "way/2"]}}
        self.assertEqual(sv.unit_area(u, {"way/1": {"area_m2": 5}, "way/2": {"area_m2": 6}})[0], 11)
        self.assertIsNone(sv.unit_area(u, {"way/1": {"area_m2": 5}})[0])


class TestEstimate(unittest.TestCase):
    def setUp(self):
        p = mock.patch.object(sv, "footprints", return_value={})
        p.start()
        self.addCleanup(p.stop)

    def est(self, sid, name, reg=REG):
        s = reg[sid]
        u = next(x for x in s["units"] if x["name"] == name)
        return sv.estimate(s, u, sv.unit_area(u, {})[0], reg, CFG)

    def test_same_company_comes_first(self):
        e = self.est("a", "2기")
        self.assertEqual(e["mid"], 10000)
        self.assertEqual(e["basis"], "같은 회사 시설")
        self.assertEqual((round(e["low"]), round(e["high"])), (6000, 14000))

    def test_other_company_when_no_own_reference(self):
        e = self.est("c", "1기")
        self.assertEqual(e["basis"], "다른 회사 같은 종류 시설")
        self.assertEqual(e["confidence"], "하")
        self.assertEqual((e["low"], e["high"]), (20000, 40000))

    def test_other_class_is_not_compared(self):
        reg = {**REG, "d": site("d", "co-w", [unit("1기", 100000)], cls="패키징B")}
        self.assertIsNone(self.est("d", "1기", reg))

    def test_mixed_units_are_not_comparable(self):
        reg = copy.deepcopy(REG)
        reg["b"]["units"][0]["capacity"]["unit"] = "MW"
        self.assertIsNone(self.est("c", "1기", reg))

    def test_floors_only_when_both_known(self):
        reg = copy.deepcopy(REG)
        reg["a"]["units"][0]["floors"] = 2
        reg["a"]["units"][1]["floors"] = 1
        self.assertEqual(self.est("a", "2기", reg)["mid"], 5000)


class TestCheck(unittest.TestCase):
    TODAY = datetime.date(2026, 10, 25)

    def test_ok(self):
        sv.check_site(REG["a"], CFG, LATE, self.TODAY)

    def test_military_kind_is_refused(self):
        with self.assertRaises(ValueError):
            sv.check_site({**REG["a"], "kind": "군사 기지"}, CFG, LATE, self.TODAY)

    def test_stale_collection_stops(self):
        with self.assertRaises(ValueError):
            sv.check_site(REG["a"], CFG, LATE, datetime.date(2027, 1, 1))

    def test_seen_on_must_be_a_collected_image(self):
        with self.assertRaises(ValueError):
            sv.check_site(site("x", "c", [unit("1기", 1, seen_on="2026-09-09")]), CFG, LATE, self.TODAY)

    def test_stale_reading_stops(self):
        late = {**LATE, "images": LATE["images"] + [{"date": "2026-10-02"}], "as_of": "2026-10-20"}
        s = site("x", "c", [unit("1기", 1, seen_on="2026-01-01")])
        late["images"].append({"date": "2026-01-01"})
        with self.assertRaises(ValueError):
            sv.check_site(s, CFG, late, self.TODAY)

    def test_capacity_needs_sites_or_reason(self):
        with self.assertRaises(ValueError):
            sv.check({}, REG, CFG)
        sv.check({"sites_none": "임차뿐"}, REG, CFG)
        with self.assertRaises(ValueError):
            sv.check({"sites": ["없는 시설"]}, REG, CFG)


class TestSection(unittest.TestCase):
    def test_estimate_is_labelled_and_kept_apart(self):
        dp = {"capacity": {"sites": ["a"]}}
        with mock.patch.object(sv, "footprints", return_value={}), mock.patch.object(sv, "latest", return_value=LATE):
            b = sv.blocks(dp, REG, CFG)
            with mock.patch.object(sv, "registry", return_value=REG):
                head = sv.headline(dp, "웨이퍼/월")
        rows = b[0]["rows"]
        self.assertEqual(rows[0][2], "20,000 웨이퍼/월")
        self.assertIn("추정 6,000~14,000", rows[1][2])
        self.assertIn("외장 완료 65%", rows[1][3])
        self.assertIn("공시 값이 아니다", head)
        self.assertIn("장비 반입", b[-1]["text"])

    def test_blocks_survive_json(self):
        reg = {"a": site("a", "co-x", [unit("1기", 100, 5, seen_on=datetime.date(2026, 10, 1))])}
        with mock.patch.object(sv, "footprints", return_value={}), mock.patch.object(sv, "latest", return_value=LATE):
            self.assertIn("2026-10-01", json.dumps(sv.blocks({"capacity": {"sites": ["a"]}}, reg, CFG), ensure_ascii=False))

    def test_no_sites_no_blocks(self):
        self.assertEqual(sv.blocks({"capacity": {"sites_none": "x"}}, REG, CFG), [])
        self.assertIsNone(sv.chart({"capacity": {"sites_none": "x"}}, REG, CFG))


class TestChart(unittest.TestCase):
    def test_svg_holds_images_and_credit(self):
        png = si.encode_png(1, 1, 3, b"\x01\x02\x03")
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "a.png"
            p.write_bytes(png)
            with mock.patch.object(sv, "ROOT", Path(d)):
                svg = report_html.chart_satellite({"panels": [{"name": "시설", "credit": "Contains modified Copernicus Sentinel data 2026", "images": [{"path": "a.png", "date": "2026-10-01"}]}]})
        self.assertIn("data:image/png;base64,", svg)
        self.assertIn("Copernicus", svg)
        self.assertTrue(svg.startswith('<svg viewBox="0 0 480 '))

    def test_missing_file_draws_nothing(self):
        self.assertEqual(report_html.chart_satellite({"panels": [{"name": "x", "images": [{"path": "없음.png", "date": "d"}]}]}), "")

    def test_money_units_leave_image_alone(self):
        png = si.encode_png(2, 2, 3, bytes(range(12)))
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "a.png").write_bytes(png)
            with mock.patch.object(sv, "ROOT", Path(d)):
                svg = report_html.chart_satellite({"panels": [{"name": "x", "images": [{"path": "a.png", "date": "d"}]}]})
        self.assertEqual(report_html.money_units(svg), svg)


class TestPng(unittest.TestCase):
    def test_roundtrip(self):
        px = bytes(range(24))
        self.assertEqual(si.decode_png(si.encode_png(2, 2, 3, px[:12]))[3], px[:12])
        self.assertEqual(si.decode_png(si.encode_png(2, 3, 4, px))[3], px)

    def test_every_filter(self):
        """필터 0~4 다섯 줄을 손으로 만든 PNG"""
        rows = [(0, 10, 20, 30, 40), (1, 5, 6, 1, 1), (2, 1, 1, 1, 1), (3, 2, 2, 2, 2), (4, 1, 1, 1, 1)]
        import struct

        def chunk(tag, body):
            return struct.pack(">I", len(body)) + tag + body + struct.pack(">I", zlib.crc32(tag + body))
        raw = b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", 2, 5, 8, 4, 0, 0, 0)) + chunk(b"IDAT", zlib.compress(bytes(v for r in rows for v in r))) + chunk(b"IEND", b"")
        w, h, ch, px = si.decode_png(raw)
        self.assertEqual((w, h, ch), (2, 5, 2))
        self.assertEqual(list(px[:8]), [10, 20, 30, 40, 5, 6, 6, 7])
        self.assertEqual(list(px[8:12]), [6, 7, 7, 8])


class TestMeasure(unittest.TestCase):
    def img(self, pixels):
        return 2, 1, 3, bytes(pixels)

    def test_changed_share(self):
        a = self.img([50, 50, 50, 50, 50, 50])
        b = self.img([50, 50, 50, 200, 20, 20])
        self.assertEqual(si.changed_share(a, b, (0, 0, 2, 1), 0.15), 0.5)

    def test_nodata_is_skipped(self):
        a = (1, 1, 4, bytes([50, 50, 50, 0]))
        self.assertIsNone(si.changed_share(a, a, (0, 0, 1, 1), 0.15))

    def test_cloud_share(self):
        self.assertEqual(si.cloud_share((2, 1, 2, bytes([9, 255, 4, 255])), (0, 0, 2, 1)), 0.5)

    def test_rect_of_box(self):
        s = {"center": [0.0, 0.0], "half_km": 1.0}
        d = 1000 / sv.M_PER_DEG
        self.assertEqual(si.rect_of(s, [0, -d, d, 0], 100), (0, 0, 50, 50))
        self.assertEqual(si.rect_of(s, None, 100), (0, 0, 100, 100))

    def test_buildings_keep_name_and_area_only(self):
        d = 100 / sv.M_PER_DEG
        got = si.parse_buildings({"elements": [{"id": 7, "tags": {"name": "P1", "building": "industrial", "phone": "1"}, "geometry": [{"lat": 0, "lon": 0}, {"lat": 0, "lon": d}, {"lat": d, "lon": d}, {"lat": d, "lon": 0}]}]})
        self.assertEqual(set(got[0]), {"osm", "name", "building", "area_m2", "center"})
        self.assertEqual(got[0]["osm"], "way/7")

    def test_refused_kind_is_not_collected(self):
        with mock.patch.object(sv, "registry", return_value={"m": {"company": "c", "kind": "군사 기지"}}), mock.patch.object(si, "collect_site") as go:
            with self.assertRaises(RuntimeError):
                si.run(today=datetime.date(2026, 11, 3))
        go.assert_not_called()


class TestWiring(unittest.TestCase):
    def test_collector_is_scheduled_and_healed(self):
        self.assertIn('"site_imagery"', (ROOT / "radar" / "run_hourly.py").read_text(encoding="utf-8"))
        self.assertIn("site-imagery", (ROOT / "config" / "pipeline_health.yaml").read_text(encoding="utf-8"))

    def test_capacity_section_uses_sites(self):
        self.assertIn("site_view.blocks", (ROOT / "scripts" / "tenbagger" / "capacity_view.py").read_text(encoding="utf-8"))
        self.assertTrue(cv.site_view is sv)


if __name__ == "__main__":
    unittest.main()
