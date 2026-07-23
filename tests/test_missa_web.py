import unittest
from datetime import date, datetime, timezone

from missa_web import (
    DateRangeError,
    build_date_txt_content,
    build_txt_bytes,
    build_txt_content,
    collect_readings,
    korean_today,
    make_download_filename,
    quick_date_range,
    validate_date_range,
)


NOW_UTC = datetime(2026, 7, 21, 15, 30, tzinfo=timezone.utc)
FIRST = "아가 3,1-4ㄴ\n\n나는 내가 사랑하는 이를 찾았네."
SECOND = "로마 8,26-27\n\n성령께서 나약한 우리를 도와주십니다."
ALTERNATIVE_ONE = "2코린 5,14-17\n\n그리스도의 사랑이 우리를 다그칩니다."
ALTERNATIVE_TWO = "이사 55,6\n\n만나 뵐 수 있을 때에 주님을 찾아라."
GOSPEL = "요한 20,1-2.11-18\n\n예수님께서 마리아야 하고 부르셨다."


class DateSelectionTests(unittest.TestCase):
    def test_today_uses_asia_seoul_boundary(self):
        self.assertEqual(korean_today(NOW_UTC), date(2026, 7, 22))

    def test_today_and_tomorrow_range(self):
        self.assertEqual(
            quick_date_range("오늘과 내일", NOW_UTC),
            (date(2026, 7, 22), date(2026, 7, 23)),
        )

    def test_this_weekend(self):
        self.assertEqual(
            quick_date_range("이번 주말", NOW_UTC),
            (date(2026, 7, 25), date(2026, 7, 26)),
        )

    def test_rest_of_this_month(self):
        self.assertEqual(
            quick_date_range("이번 달 남은 기간", NOW_UTC),
            (date(2026, 7, 22), date(2026, 7, 31)),
        )

    def test_end_before_start_is_rejected(self):
        with self.assertRaisesRegex(DateRangeError, "종료 날짜"):
            validate_date_range(date(2026, 7, 23), date(2026, 7, 22))

    def test_more_than_31_days_is_rejected(self):
        with self.assertRaisesRegex(DateRangeError, "최대 31일"):
            validate_date_range(date(2026, 7, 1), date(2026, 8, 1))


class DownloadTests(unittest.TestCase):
    def test_single_date_filename(self):
        self.assertEqual(
            make_download_filename([date(2026, 7, 22)]),
            "매일미사_20260722.txt",
        )

    def test_multiple_date_filename(self):
        self.assertEqual(
            make_download_filename([date(2026, 7, 22), date(2026, 7, 31)]),
            "매일미사_20260722-20260731.txt",
        )

    def test_txt_content_omits_missing_second_reading(self):
        results = [
            (
                "2026-07-22",
                "https://example.test/20260722",
                {"제1독서": FIRST, "복음": GOSPEL},
            )
        ]

        content = build_txt_content(results)

        self.assertIn("2026년 7월 22일\n" + "=" * 50, content)
        self.assertIn("제1독서\n" + FIRST, content)
        self.assertIn("복음\n" + GOSPEL, content)
        self.assertNotIn("제2독서", content)

    def test_single_date_copy_content_matches_download_block(self):
        result = (
            "2026-07-22",
            "https://example.test/20260722",
            {"제1독서": FIRST, "복음": GOSPEL},
        )

        copy_content = build_date_txt_content(result)

        self.assertEqual(copy_content + "\n", build_txt_content([result]))
        self.assertTrue(copy_content.startswith("2026년 7월 22일\n"))
        self.assertIn("제1독서\n" + FIRST, copy_content)
        self.assertIn("복음\n" + GOSPEL, copy_content)

    def test_txt_content_includes_multiple_alternatives_in_order(self):
        results = [
            (
                "2026-07-22",
                "https://example.test/20260722",
                {
                    "제1독서": FIRST,
                    "제1독서(대체)": ALTERNATIVE_ONE,
                    "제1독서(대체 2)": ALTERNATIVE_TWO,
                    "복음": GOSPEL,
                },
            )
        ]

        content = build_txt_content(results)

        self.assertIn("제1독서 (대체)\n" + ALTERNATIVE_ONE, content)
        self.assertIn("제1독서 (대체 2)\n" + ALTERNATIVE_TWO, content)
        self.assertLess(content.index(ALTERNATIVE_ONE), content.index(ALTERNATIVE_TWO))

    def test_txt_content_supports_second_reading(self):
        results = [
            (
                "2026-07-26",
                "https://example.test/20260726",
                {"제1독서": FIRST, "제2독서": SECOND, "복음": GOSPEL},
            )
        ]

        self.assertIn("제2독서\n" + SECOND, build_txt_content(results))

    def test_utf8_korean_download_bytes(self):
        results = [
            (
                "2026-07-22",
                "https://example.test/20260722",
                {"제1독서": FIRST, "복음": GOSPEL},
            )
        ]

        decoded = build_txt_bytes(results).decode("utf-8")

        self.assertIn("제1독서", decoded)
        self.assertIn("사랑하는 이를 찾았네", decoded)


class BatchExtractionTests(unittest.TestCase):
    def test_failure_on_one_date_does_not_stop_next_date(self):
        targets = [date(2026, 7, 22), date(2026, 7, 23), date(2026, 7, 24)]
        calls = []

        def fake_extract(target):
            calls.append(target)
            if target == date(2026, 7, 23):
                raise RuntimeError("페이지를 불러오지 못했습니다.")
            return (
                target.isoformat(),
                f"https://example.test/{target:%Y%m%d}",
                {"제1독서": FIRST, "복음": GOSPEL},
            )

        batch = collect_readings(targets, extract_one=fake_extract, pause_seconds=0)

        self.assertEqual(calls, targets)
        self.assertEqual(len(batch.results), 2)
        self.assertEqual(len(batch.failures), 1)
        self.assertEqual(batch.failures[0][0], date(2026, 7, 23))
        self.assertIn("페이지를 불러오지 못했습니다", batch.failures[0][1])


if __name__ == "__main__":
    unittest.main()
