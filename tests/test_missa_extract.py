import io
import json
import unittest
from contextlib import redirect_stdout
from datetime import date, datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
from zoneinfo import ZoneInfo

from missa_extract import (
    MissaParseError,
    extract_multiple_dates,
    extract_readings,
    main,
    make_output_filename,
    parse_date,
    parse_date_expression,
    reveal_in_finder,
    save_results,
)


SAMPLE_HTML = """
<html><body>
  <div class="bottompadding-sm">
    <div class="row bottompadding-sm"><div class="title-block">
      <h4>제1독서</h4><span>&lt;첫째 독서 제목&gt;</span>
    </div></div>
    <div class="row"><div>▥ 창세기의 말씀입니다.<h5><span>1,1-2</span></h5></div></div>
    <div class="row tjustify"><div><div>1 첫째 줄</div><div>2 둘째 줄</div></div>
      <div>◎ 하느님, 감사합니다.</div>
    </div>
    <div class="row contents2_6"><div><span>&lt;또는&gt;</span></div>
      <div>&lt;대체 독서 제목&gt;</div><div>▥ 다른 책의 말씀입니다.</div>
      <div><h5><span>2,1</span></h5></div><div><div>1 대체 본문</div></div>
    </div>
  </div>
  <div class="bottompadding-sm">
    <div class="row bottompadding-sm"><div class="title-block"><h4>화답송</h4></div></div>
    <div class="row tjustify"><div>독서에 포함되면 안 되는 내용</div></div>
  </div>
  <div class="bottompadding-sm">
    <div class="row bottompadding-sm"><div class="title-block"><h4>제2독서</h4></div></div>
    <div class="row tjustify"><div><div>제2독서 본문</div></div></div>
  </div>
  <div class="bottompadding-sm">
    <div class="row bottompadding-sm"><div class="title-block"><h4>복음 환호송</h4></div></div>
    <div class="row tjustify"><div>복음에 포함되면 안 되는 내용</div></div>
  </div>
  <div class="bottompadding-sm">
    <div class="row bottompadding-sm"><div class="title-block">
      <h4>복음</h4><span>&lt;복음 제목&gt;</span>
    </div></div>
    <div class="row tjustify"><div><div>✠ 거룩한 복음입니다.</div><div>기본 복음 본문</div></div></div>
    <div class="row contents2_6"><div><span>&lt;또는&gt;</span></div><div>대체 복음 본문</div></div>
  </div>
  <div class="bottompadding-sm">
    <div class="row bottompadding-sm"><div class="title-block"><h4>예물 기도</h4></div></div>
    <div class="row tjustify"><div>복음에 포함되면 안 되는 기도</div></div>
  </div>
</body></html>
"""

NO_SECOND_READING_HTML = """
<html><body>
  <div class="bottompadding-sm">
    <div class="row bottompadding-sm"><div class="title-block"><h4>제1독서</h4></div></div>
    <div class="row tjustify"><div><div>제1독서만 있는 날의 본문</div></div></div>
  </div>
  <div class="bottompadding-sm">
    <div class="row bottompadding-sm"><div class="title-block"><h4>복음</h4></div></div>
    <div class="row tjustify"><div><div>제1독서만 있는 날의 복음</div></div></div>
  </div>
</body></html>
"""


class DateParsingTests(unittest.TestCase):
    def test_accepts_compact_and_hyphenated_dates(self):
        self.assertEqual(parse_date("20260722"), ("20260722", "2026-07-22"))
        self.assertEqual(parse_date("2026-07-22"), ("20260722", "2026-07-22"))

    def test_rejects_invalid_calendar_date(self):
        with self.assertRaises(ValueError):
            parse_date("20260230")


class NaturalLanguageDateTests(unittest.TestCase):
    NOW = datetime(2026, 7, 22, 12, 0, tzinfo=ZoneInfo("Asia/Seoul"))

    def test_resolves_relative_days_and_lists(self):
        self.assertEqual(parse_date_expression("오늘", self.NOW), [date(2026, 7, 22)])
        self.assertEqual(parse_date_expression("내일", self.NOW), [date(2026, 7, 23)])
        self.assertEqual(
            parse_date_expression("오늘이랑 내일", self.NOW),
            [date(2026, 7, 22), date(2026, 7, 23)],
        )

    def test_resolves_relative_range(self):
        self.assertEqual(
            parse_date_expression("오늘부터 모레까지", self.NOW),
            [date(2026, 7, 22), date(2026, 7, 23), date(2026, 7, 24)],
        )

    def test_resolves_this_week_weekend(self):
        self.assertEqual(
            parse_date_expression("이번 주 토요일과 일요일", self.NOW),
            [date(2026, 7, 25), date(2026, 7, 26)],
        )

    def test_resolves_absolute_dates_and_range(self):
        self.assertEqual(parse_date_expression("20260722", self.NOW), [date(2026, 7, 22)])
        self.assertEqual(parse_date_expression("2026-07-22", self.NOW), [date(2026, 7, 22)])
        self.assertEqual(
            parse_date_expression("2026-07-22부터 2026-07-25까지", self.NOW),
            [
                date(2026, 7, 22),
                date(2026, 7, 23),
                date(2026, 7, 24),
                date(2026, 7, 25),
            ],
        )

    def test_rejects_reverse_range_and_unknown_expression(self):
        with self.assertRaises(ValueError):
            parse_date_expression("2026-07-25부터 2026-07-22까지", self.NOW)
        with self.assertRaises(ValueError):
            parse_date_expression("다음 달쯤", self.NOW)


class ReadingExtractionTests(unittest.TestCase):
    def test_extracts_required_optional_and_alternative_sections(self):
        readings = extract_readings(SAMPLE_HTML)

        self.assertEqual(
            list(readings),
            ["제1독서", "제1독서(대체)", "제2독서", "복음", "복음(대체)"],
        )
        self.assertIn("1 첫째 줄", readings["제1독서"])
        self.assertIn("1 대체 본문", readings["제1독서(대체)"])
        self.assertEqual(readings["제2독서"], "제2독서 본문")
        self.assertIn("기본 복음 본문", readings["복음"])
        self.assertEqual(readings["복음(대체)"], "대체 복음 본문")

    def test_does_not_absorb_neighboring_sections(self):
        combined = "\n".join(extract_readings(SAMPLE_HTML).values())
        self.assertNotIn("독서에 포함되면 안 되는 내용", combined)
        self.assertNotIn("복음에 포함되면 안 되는 내용", combined)
        self.assertNotIn("복음에 포함되면 안 되는 기도", combined)

    def test_requires_first_reading_and_gospel(self):
        with self.assertRaises(MissaParseError):
            extract_readings("<html><body><h4>제1독서</h4></body></html>")

    def test_omits_second_reading_when_page_has_none(self):
        readings = extract_readings(NO_SECOND_READING_HTML)

        self.assertEqual(list(readings), ["제1독서", "복음"])
        self.assertNotIn("제2독서", readings)

    def test_keeps_alternative_reading_as_separate_item(self):
        readings = extract_readings(SAMPLE_HTML)

        self.assertIn("제1독서", readings)
        self.assertIn("제1독서(대체)", readings)
        self.assertNotEqual(readings["제1독서"], readings["제1독서(대체)"])


class MultipleDateExtractionTests(unittest.TestCase):
    @patch("missa_extract.fetch_page", return_value=(SAMPLE_HTML.encode("utf-8"), "https://example.test"))
    def test_reuses_existing_extraction_for_each_date(self, fetch_page_mock):
        dates = [date(2026, 7, 22), date(2026, 7, 23)]

        results = extract_multiple_dates(dates, session=object())

        self.assertEqual([result[0] for result in results], ["2026-07-22", "2026-07-23"])
        self.assertEqual(
            [call.args[0] for call in fetch_page_mock.call_args_list],
            ["20260722", "20260723"],
        )


class TextFileTests(unittest.TestCase):
    def test_makes_single_and_multiple_date_filenames(self):
        self.assertEqual(make_output_filename([date(2026, 7, 22)]), "매일미사_20260722.txt")
        self.assertEqual(
            make_output_filename([date(2026, 7, 22), date(2026, 7, 25)]),
            "매일미사_20260722-20260725.txt",
        )

    def test_creates_output_directory_and_writes_clear_date_sections(self):
        dates = [date(2026, 7, 22), date(2026, 7, 23)]
        results = [
            ("2026-07-22", "https://example.test/20260722", {"제1독서": "첫 본문", "복음": "첫 복음"}),
            ("2026-07-23", "https://example.test/20260723", {"제1독서": "둘째 본문", "복음": "둘째 복음"}),
        ]

        with TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir) / "output"
            output_path = save_results(results, dates, output_dir)
            content = output_path.read_text(encoding="utf-8")

            self.assertEqual(output_path.name, "매일미사_20260722-20260723.txt")
            self.assertIn("매일미사 2026-07-22", content)
            self.assertIn("매일미사 2026-07-23", content)
            self.assertIn("[제1독서]", content)
            self.assertIn("[복음]", content)
            self.assertIn("첫 본문", content)
            self.assertEqual(content.encode("utf-8").decode("utf-8"), content)


class OutputModeTests(unittest.TestCase):
    RESULTS = [
        (
            "2026-07-22",
            "https://example.test/20260722",
            {"제1독서": "한글 독서 본문", "복음": "한글 복음 본문"},
        )
    ]

    @patch("missa_extract.extract_multiple_dates", return_value=RESULTS)
    def test_default_mode_saves_and_prints_absolute_path(self, _extract_mock):
        with TemporaryDirectory() as temp_dir:
            stdout = io.StringIO()
            with redirect_stdout(stdout):
                exit_code = main(["20260722", "--output-dir", temp_dir])

            expected = (Path(temp_dir) / "매일미사_20260722.txt").resolve()
            self.assertEqual(exit_code, 0)
            self.assertEqual(stdout.getvalue().strip(), f"저장 완료: {expected}")
            self.assertTrue(expected.exists())

    @patch("missa_extract.extract_multiple_dates", return_value=RESULTS)
    def test_explicit_txt_mode_saves_file(self, _extract_mock):
        with TemporaryDirectory() as temp_dir:
            stdout = io.StringIO()
            with redirect_stdout(stdout):
                exit_code = main(["20260722", "--txt", "--output-dir", temp_dir])

            self.assertEqual(exit_code, 0)
            self.assertIn("저장 완료:", stdout.getvalue())

    @patch("missa_extract.extract_multiple_dates", return_value=RESULTS)
    def test_json_mode_prints_json_without_saving_text(self, _extract_mock):
        with TemporaryDirectory() as temp_dir:
            stdout = io.StringIO()
            with redirect_stdout(stdout):
                exit_code = main(["20260722", "--json", "--output-dir", temp_dir])

            payload = json.loads(stdout.getvalue())
            self.assertEqual(exit_code, 0)
            self.assertEqual(payload["results"][0]["date"], "2026-07-22")
            self.assertFalse(list(Path(temp_dir).glob("*.txt")))

    @patch("missa_extract.extract_multiple_dates", return_value=RESULTS)
    def test_print_mode_prints_plain_text_without_saving(self, _extract_mock):
        with TemporaryDirectory() as temp_dir:
            stdout = io.StringIO()
            with redirect_stdout(stdout):
                exit_code = main(["20260722", "--print", "--output-dir", temp_dir])

            self.assertEqual(exit_code, 0)
            self.assertIn("한글 독서 본문", stdout.getvalue())
            self.assertFalse(list(Path(temp_dir).glob("*.txt")))

    @patch("missa_extract.subprocess.run")
    def test_reveal_uses_macos_open_dash_r(self, run_mock):
        output_path = Path("/tmp/매일미사_20260722.txt")

        with patch("missa_extract.sys.platform", "darwin"):
            reveal_in_finder(output_path)

        run_mock.assert_called_once_with(["open", "-R", str(output_path)], check=True)


if __name__ == "__main__":
    unittest.main()
