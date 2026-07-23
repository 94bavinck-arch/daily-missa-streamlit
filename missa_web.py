"""Streamlit 매일미사 앱에서 사용하는 테스트 가능한 순수 보조 함수."""

from __future__ import annotations

import calendar
import re
import time
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Callable, List, Optional, Sequence, Tuple

from missa_extract import ExtractionResult, KST, extract_multiple_dates, make_output_filename


MAX_REQUEST_DAYS = 31
REQUEST_INTERVAL_SECONDS = 0.3
QUICK_DATE_OPTIONS = (
    "오늘",
    "내일",
    "오늘과 내일",
    "이번 주말",
    "이번 달 남은 기간",
)

ExtractOneCallable = Callable[[date], ExtractionResult]
ProgressCallable = Callable[[date, int, int], None]
Failure = Tuple[date, str]


class DateRangeError(ValueError):
    """웹 화면에서 사용자에게 바로 보여 줄 날짜 범위 오류."""


@dataclass(frozen=True)
class BatchExtraction:
    results: Tuple[ExtractionResult, ...]
    failures: Tuple[Failure, ...]


def korean_today(now: Optional[datetime] = None) -> date:
    """주입 가능한 기준 시각을 Asia/Seoul의 오늘 날짜로 변환한다."""
    current = now or datetime.now(KST)
    if current.tzinfo is None:
        current = current.replace(tzinfo=KST)
    return current.astimezone(KST).date()


def quick_date_range(
    selection: str,
    now: Optional[datetime] = None,
) -> Tuple[date, date]:
    today = korean_today(now)
    if selection == "오늘":
        return today, today
    if selection == "내일":
        tomorrow = today + timedelta(days=1)
        return tomorrow, tomorrow
    if selection == "오늘과 내일":
        return today, today + timedelta(days=1)
    if selection == "이번 주말":
        monday = today - timedelta(days=today.weekday())
        return monday + timedelta(days=5), monday + timedelta(days=6)
    if selection == "이번 달 남은 기간":
        last_day = calendar.monthrange(today.year, today.month)[1]
        return today, date(today.year, today.month, last_day)
    raise ValueError(f"지원하지 않는 빠른 날짜 선택입니다: {selection}")


def validate_date_range(start: date, end: date) -> List[date]:
    if end < start:
        raise DateRangeError("종료 날짜는 시작 날짜보다 빠를 수 없습니다.")
    day_count = (end - start).days + 1
    if day_count > MAX_REQUEST_DAYS:
        raise DateRangeError(
            f"한 번에 최대 {MAX_REQUEST_DAYS}일까지 요청할 수 있습니다. "
            f"현재 선택은 {day_count}일입니다."
        )
    return [start + timedelta(days=offset) for offset in range(day_count)]


def extract_one_date(target_date: date) -> ExtractionResult:
    """기존 공개 추출 함수를 한 날짜에 그대로 사용한다."""
    return extract_multiple_dates([target_date])[0]


def _safe_error_message(exc: Exception) -> str:
    message = re.sub(r"\s+", " ", str(exc)).strip()
    return message or "알 수 없는 오류가 발생했습니다."


def collect_readings(
    dates: Sequence[date],
    extract_one: ExtractOneCallable = extract_one_date,
    on_progress: Optional[ProgressCallable] = None,
    pause_seconds: float = REQUEST_INTERVAL_SECONDS,
    sleep_fn: Callable[[float], None] = time.sleep,
) -> BatchExtraction:
    """각 날짜를 독립 처리하여 실패 뒤에도 다음 날짜를 계속 추출한다."""
    results: List[ExtractionResult] = []
    failures: List[Failure] = []
    total = len(dates)

    for index, target_date in enumerate(dates, start=1):
        if on_progress:
            on_progress(target_date, index, total)
        try:
            results.append(extract_one(target_date))
        except Exception as exc:
            failures.append((target_date, _safe_error_message(exc)))

        if index < total and pause_seconds > 0:
            sleep_fn(pause_seconds)

    return BatchExtraction(tuple(results), tuple(failures))


def display_reading_label(label: str) -> str:
    return re.sub(r"\s*\(", " (", label, count=1)


def format_korean_date(date_iso: str) -> str:
    parsed = date.fromisoformat(date_iso)
    return f"{parsed.year}년 {parsed.month}월 {parsed.day}일"


def build_txt_content(results: Sequence[ExtractionResult]) -> str:
    """성공한 날짜들을 UTF-8 다운로드용 일반 텍스트로 조립한다."""
    date_blocks: List[str] = []
    divider = "=" * 50

    for date_iso, _url, readings in results:
        reading_blocks = [
            f"{display_reading_label(label)}\n{content}"
            for label, content in readings.items()
        ]
        date_blocks.append(
            f"{format_korean_date(date_iso)}\n{divider}\n\n"
            + "\n\n\n".join(reading_blocks)
        )

    return "\n\n\n".join(date_blocks).rstrip() + ("\n" if date_blocks else "")


def build_txt_bytes(results: Sequence[ExtractionResult]) -> bytes:
    return build_txt_content(results).encode("utf-8")


def make_download_filename(dates: Sequence[date]) -> str:
    return make_output_filename(dates)
