#!/usr/bin/env python3
"""한국천주교주교회의 매일미사에서 독서와 복음 원문을 추출한다.

필요 패키지:
    python3 -m pip install requests beautifulsoup4

사용 예:
    python3 missa_extract.py
    python3 missa_extract.py "오늘이랑 내일"
    python3 missa_extract.py "이번 주 토요일과 일요일"
    python3 missa_extract.py "2026-07-22부터 2026-07-25까지"
    python3 missa_extract.py "오늘이랑 내일" --json
    python3 missa_extract.py "오늘이랑 내일" --print
    python3 missa_extract.py "오늘이랑 내일" --txt --reveal

개인적인 묵상 자료를 만들기 위한 도구다. 요청한 날짜마다 한 페이지만 가져온다.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import warnings
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple, Union
from zoneinfo import ZoneInfo

# macOS 기본 Python이 LibreSSL로 빌드된 경우 urllib3 2.x가 내는 환경 경고다.
# 이 스크립트의 HTTPS 요청은 아래 실제 요청 테스트로 확인하며, 해당 문구만 숨긴다.
warnings.filterwarnings(
    "ignore",
    message=r"urllib3 v2 only supports OpenSSL 1\.1\.1\+.*",
)

import requests
from bs4 import BeautifulSoup, NavigableString, Tag
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


BASE_URL = "https://missa.cbck.or.kr/DailyMissa/{date_compact}"
KST = ZoneInfo("Asia/Seoul")
DEFAULT_TIMEOUT_SECONDS = 20
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/126.0 Safari/537.36 DailyMissaPersonalExtractor/1.0"
)
TARGET_SECTIONS = ("제1독서", "제2독서", "복음")
ALTERNATIVE_MARKER = re.compile(r"^[<〈]?\s*또는\s*[>〉]?$")
DATE_TOKEN_PATTERN = r"(?:\d{8}|\d{4}-\d{2}-\d{2})"
RELATIVE_DAY_OFFSETS = {"오늘": 0, "내일": 1, "모레": 2}
WEEKDAY_INDEXES = {
    "월요일": 0,
    "화요일": 1,
    "수요일": 2,
    "목요일": 3,
    "금요일": 4,
    "토요일": 5,
    "일요일": 6,
}
LIST_SEPARATOR = re.compile(r"\s*(?:이랑|랑|과|와|및|,)\s*")

ExtractionResult = Tuple[str, str, Dict[str, str]]


class MissaParseError(RuntimeError):
    """페이지에서 필수 독서 구간을 찾지 못했을 때 발생한다."""


class MissaExtractionError(RuntimeError):
    """특정 날짜의 페이지 요청 또는 추출이 실패했을 때 발생한다."""


def parse_date(value: Optional[str]) -> Tuple[str, str]:
    """날짜를 검증하고 (YYYYMMDD, YYYY-MM-DD) 형태로 반환한다."""
    dates = parse_date_expression(value or "오늘")
    if len(dates) != 1:
        raise ValueError("한 날짜가 필요한 곳에 여러 날짜가 입력되었습니다.")
    target = dates[0]
    return target.strftime("%Y%m%d"), target.strftime("%Y-%m-%d")


def parse_absolute_date(value: str) -> date:
    """YYYYMMDD 또는 YYYY-MM-DD 문자열을 실제 달력 날짜로 변환한다."""
    for date_format in ("%Y%m%d", "%Y-%m-%d"):
        try:
            return datetime.strptime(value, date_format).date()
        except ValueError:
            continue
    raise ValueError(f"올바르지 않은 날짜입니다: {value}")


def expand_date_range(start: date, end: date) -> List[date]:
    """시작일과 종료일을 모두 포함하는 날짜 목록을 만든다."""
    if end < start:
        raise ValueError("종료일은 시작일보다 빠를 수 없습니다.")
    return [start + timedelta(days=offset) for offset in range((end - start).days + 1)]


def split_list_terms(value: str) -> List[str]:
    return [term for term in LIST_SEPARATOR.split(value.strip()) if term]


def parse_date_expression(
    expression: Optional[str],
    now: Optional[datetime] = None,
) -> List[date]:
    """한국어 날짜 명령을 중복 없는 오름차순 날짜 목록으로 변환한다."""
    text = re.sub(r"\s+", " ", (expression or "오늘").strip())
    if not text:
        text = "오늘"

    current = now or datetime.now(KST)
    if current.tzinfo is None:
        current = current.replace(tzinfo=KST)
    today = current.astimezone(KST).date()

    absolute_range = re.fullmatch(
        rf"({DATE_TOKEN_PATTERN})\s*부터\s*({DATE_TOKEN_PATTERN})\s*까지",
        text,
    )
    if absolute_range:
        start = parse_absolute_date(absolute_range.group(1))
        end = parse_absolute_date(absolute_range.group(2))
        return expand_date_range(start, end)

    relative_range = re.fullmatch(
        r"(오늘|내일|모레)\s*부터\s*(오늘|내일|모레)\s*까지",
        text,
    )
    if relative_range:
        start = today + timedelta(days=RELATIVE_DAY_OFFSETS[relative_range.group(1)])
        end = today + timedelta(days=RELATIVE_DAY_OFFSETS[relative_range.group(2)])
        return expand_date_range(start, end)

    this_week = re.fullmatch(r"이번\s*주\s*(.+)", text)
    if this_week:
        weekday_terms = split_list_terms(this_week.group(1))
        if not weekday_terms or any(term not in WEEKDAY_INDEXES for term in weekday_terms):
            raise ValueError("'이번 주' 다음에는 월요일부터 일요일까지의 요일을 입력해 주세요.")
        monday = today - timedelta(days=today.weekday())
        return sorted({monday + timedelta(days=WEEKDAY_INDEXES[term]) for term in weekday_terms})

    resolved: List[date] = []
    for term in split_list_terms(text):
        if term in RELATIVE_DAY_OFFSETS:
            resolved.append(today + timedelta(days=RELATIVE_DAY_OFFSETS[term]))
        elif re.fullmatch(DATE_TOKEN_PATTERN, term):
            resolved.append(parse_absolute_date(term))
        else:
            raise ValueError(
                f"날짜 표현을 이해하지 못했습니다: {term!r}. "
                "예: 오늘, 오늘이랑 내일, 이번 주 토요일과 일요일"
            )

    if not resolved:
        raise ValueError("날짜를 하나 이상 입력해 주세요.")
    return sorted(set(resolved))


def resolve_dates(
    expression: Optional[str],
    now: Optional[datetime] = None,
) -> List[date]:
    """이전 함수명과의 호환을 위한 별칭이다."""
    return parse_date_expression(expression, now=now)


def build_session() -> requests.Session:
    """일시적인 서버 오류에 짧게 재시도하는 HTTP 세션을 만든다."""
    retry = Retry(
        total=3,
        connect=3,
        read=3,
        status=3,
        backoff_factor=0.5,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=frozenset({"GET"}),
        raise_on_status=False,
    )
    adapter = HTTPAdapter(max_retries=retry)
    session = requests.Session()
    session.headers.update({"User-Agent": USER_AGENT})
    session.mount("https://", adapter)
    return session


def fetch_page(
    date_compact: str,
    session: Optional[requests.Session] = None,
) -> Tuple[bytes, str]:
    """해당 날짜 페이지의 원본 HTML 바이트와 출처 URL을 반환한다."""
    url = BASE_URL.format(date_compact=date_compact)
    owns_session = session is None
    client = session or build_session()

    try:
        response = client.get(url, timeout=DEFAULT_TIMEOUT_SECONDS)
        response.raise_for_status()
        if not response.content.strip():
            raise MissaParseError("서버가 빈 페이지를 반환했습니다.")
        return response.content, url
    finally:
        if owns_session:
            client.close()


def clean_line(value: str) -> str:
    """HTML 들여쓰기만 없애고 한 줄 안의 공백을 정돈한다."""
    return re.sub(r"\s+", " ", value).strip()


def heading_text(heading: Tag) -> str:
    return clean_line(heading.get_text(" ", strip=True))


def find_section_heading(soup: BeautifulSoup, label: str) -> Optional[Tag]:
    """'복음 환호송'을 '복음'으로 오인하지 않고 정확한 제목을 찾는다."""
    for heading in soup.find_all(re.compile(r"^h[1-6]$")):
        if heading_text(heading) == label:
            return heading
    return None


def find_section_container(heading: Tag) -> Optional[Tag]:
    """제목과 본문을 함께 감싸는 가장 가까운 매일미사 구간을 찾는다."""
    for ancestor in heading.parents:
        if not isinstance(ancestor, Tag) or ancestor.name != "div":
            continue
        classes = ancestor.get("class", [])
        if "bottompadding-sm" not in classes:
            continue
        # 제목 행 자체에도 bottompadding-sm이 있으므로, 본문 행을 포함한 바깥
        # 컨테이너만 선택한다.
        if ancestor.select_one(".tjustify") is not None:
            return ancestor
    return None


def section_lines(container: Tag, heading: Tag) -> List[str]:
    """구간 제목만 제외하고 사이트가 제공한 텍스트 노드를 순서대로 읽는다."""
    lines: List[str] = []

    for node in container.descendants:
        if not isinstance(node, NavigableString):
            continue
        if heading in node.parents:
            continue
        line = clean_line(str(node))
        if line:
            lines.append(line)

    return lines


def split_alternatives(lines: Sequence[str]) -> List[List[str]]:
    """<또는> 표식으로 같은 구간 안의 선택 본문을 분리한다."""
    parts: List[List[str]] = [[]]

    for line in lines:
        if ALTERNATIVE_MARKER.fullmatch(line):
            if parts[-1]:
                parts.append([])
            continue
        parts[-1].append(line)

    return [part for part in parts if part]


def extract_section(soup: BeautifulSoup, label: str) -> List[str]:
    """한 구간을 기본 본문과 0개 이상의 대체 본문으로 반환한다."""
    heading = find_section_heading(soup, label)
    if heading is None:
        return []

    container = find_section_container(heading)
    if container is None:
        raise MissaParseError(f"'{label}' 제목은 찾았지만 본문 구간을 찾지 못했습니다.")

    parts = split_alternatives(section_lines(container, heading))
    return ["\n".join(part).strip() for part in parts if part]


def extract_readings(html: Union[str, bytes]) -> Dict[str, str]:
    """HTML에서 제1독서, 제2독서(있을 때), 복음을 순서대로 추출한다."""
    soup = BeautifulSoup(html, "html.parser")
    result: Dict[str, str] = {}

    for label in TARGET_SECTIONS:
        for index, content in enumerate(extract_section(soup, label)):
            if index == 0:
                output_label = label
            elif index == 1:
                output_label = f"{label}(대체)"
            else:
                output_label = f"{label}(대체 {index})"
            result[output_label] = content

    missing = [label for label in ("제1독서", "복음") if label not in result]
    if missing:
        joined = ", ".join(missing)
        raise MissaParseError(
            f"필수 구간({joined})을 찾지 못했습니다. "
            "날짜에 미사 자료가 있는지 또는 사이트 구조가 바뀌었는지 확인해 주세요."
        )

    return result


def extract_multiple_dates(
    dates: Sequence[date],
    session: Optional[requests.Session] = None,
) -> List[ExtractionResult]:
    """날짜마다 기존 추출 로직을 실행하고 결과를 입력 순서대로 반환한다."""
    owns_session = session is None
    client = session or build_session()
    results: List[ExtractionResult] = []

    try:
        for target_date in dates:
            date_compact = target_date.strftime("%Y%m%d")
            date_iso = target_date.strftime("%Y-%m-%d")
            try:
                html, url = fetch_page(date_compact, session=client)
                readings = extract_readings(html)
            except requests.RequestException as exc:
                raise MissaExtractionError(f"{date_iso} 페이지 요청 실패: {exc}") from exc
            except MissaParseError as exc:
                raise MissaExtractionError(f"{date_iso} 추출 실패: {exc}") from exc
            results.append((date_iso, url, readings))
    finally:
        if owns_session:
            client.close()

    return results


def render_text(date_iso: str, url: str, readings: Dict[str, str]) -> str:
    divider = "=" * 72
    blocks = [divider, f"매일미사 {date_iso}", divider, f"출처: {url}"]
    for title, content in readings.items():
        blocks.append(f"[{title}]\n{content}")
    return "\n\n".join(blocks)


def render_results(results: Sequence[ExtractionResult]) -> str:
    return "\n\n".join(
        render_text(date_iso, url, readings)
        for date_iso, url, readings in results
    )


def make_output_filename(dates: Sequence[date]) -> str:
    if not dates:
        raise ValueError("파일명을 만들 날짜가 없습니다.")
    first = dates[0].strftime("%Y%m%d")
    if len(dates) == 1:
        return f"매일미사_{first}.txt"
    last = dates[-1].strftime("%Y%m%d")
    return f"매일미사_{first}-{last}.txt"


def save_results(
    results: Sequence[ExtractionResult],
    dates: Sequence[date],
    output_dir: Path,
) -> Path:
    """결과 전체를 UTF-8 텍스트 파일 하나로 저장한다."""
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / make_output_filename(dates)
    output_path.write_text(render_results(results) + "\n", encoding="utf-8")
    return output_path.resolve()


def reveal_in_finder(output_path: Path) -> None:
    """macOS Finder에서 생성된 파일을 선택한 상태로 표시한다."""
    if sys.platform != "darwin":
        raise RuntimeError("--reveal 옵션은 macOS에서만 사용할 수 있습니다.")
    subprocess.run(["open", "-R", str(output_path)], check=True)


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="자연어로 지정한 날짜들의 매일미사 독서와 복음을 저장하거나 출력합니다."
    )
    parser.add_argument(
        "date_expression",
        nargs="?",
        default="오늘",
        help='날짜 명령. 예: "오늘이랑 내일", "이번 주 토요일과 일요일"',
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path.cwd() / "output",
        help="저장 폴더. 기본값: 현재 실행 폴더의 output",
    )
    output_group = parser.add_mutually_exclusive_group()
    output_group.add_argument(
        "--txt",
        dest="output_mode",
        action="store_const",
        const="txt",
        help="UTF-8 텍스트 파일로 저장(기본 동작)",
    )
    output_group.add_argument(
        "--json",
        dest="output_mode",
        action="store_const",
        const="json",
        help="결과를 JSON으로 터미널에 출력",
    )
    output_group.add_argument(
        "--print",
        dest="output_mode",
        action="store_const",
        const="print",
        help="결과를 일반 텍스트로 터미널에 출력",
    )
    parser.set_defaults(output_mode="txt")
    parser.add_argument(
        "--reveal",
        action="store_true",
        help="저장 후 macOS Finder에서 생성 파일을 표시(--txt 전용)",
    )
    return parser.parse_args(argv)


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = parse_args(argv)

    if args.reveal and args.output_mode != "txt":
        print("옵션 오류: --reveal은 파일을 저장하는 --txt와 함께만 사용할 수 있습니다.", file=sys.stderr)
        return 2

    try:
        dates = parse_date_expression(args.date_expression)
    except ValueError as exc:
        print(f"날짜 오류: {exc}", file=sys.stderr)
        return 2

    try:
        results = extract_multiple_dates(dates)
    except MissaExtractionError as exc:
        print(exc, file=sys.stderr)
        return 1

    if args.output_mode == "json":
        payload = {
            "query": args.date_expression,
            "results": [
                {
                    "date": date_iso,
                    "source_url": url,
                    "readings": readings,
                }
                for date_iso, url, readings in results
            ],
        }
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    elif args.output_mode == "print":
        print(render_results(results))
    else:
        try:
            output_path = save_results(results, dates, args.output_dir)
        except OSError as exc:
            print(f"파일 저장 실패: {exc}", file=sys.stderr)
            return 1
        print(f"저장 완료: {output_path}")
        if args.reveal:
            try:
                reveal_in_finder(output_path)
            except (RuntimeError, OSError, subprocess.CalledProcessError) as exc:
                print(f"Finder 표시 실패: {exc}", file=sys.stderr)
                return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
