"""터미널 없이 사용하는 매일미사 말씀 추출 Streamlit 앱."""

from __future__ import annotations

from datetime import date
from typing import Sequence

import streamlit as st

from missa_extract import ExtractionResult
from missa_web import (
    QUICK_DATE_OPTIONS,
    BatchExtraction,
    DateRangeError,
    build_date_txt_content,
    build_txt_bytes,
    build_txt_content,
    collect_readings,
    display_reading_label,
    format_korean_date,
    korean_today,
    make_download_filename,
    quick_date_range,
    validate_date_range,
)


CACHE_TTL_SECONDS = 60 * 60


@st.cache_data(ttl=CACHE_TTL_SECONDS, show_spinner=False)
def extract_one_cached(target_date: date) -> ExtractionResult:
    """성공한 날짜 결과만 한 시간 재사용한다. 예외는 Streamlit이 캐시하지 않는다."""
    from missa_web import extract_one_date

    return extract_one_date(target_date)


def _initialize_state() -> None:
    defaults = {
        "missa_running": False,
        "missa_batch": None,
        "missa_requested_dates": (),
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


def _selected_dates() -> Sequence[date]:
    mode = st.session_state.get("date_selection_mode", "빠른 날짜 선택")
    if mode == "빠른 날짜 선택":
        start, end = quick_date_range(st.session_state.get("quick_date", "오늘"))
    else:
        start = st.session_state.get("direct_start", korean_today())
        end = st.session_state.get("direct_end", korean_today())
    return validate_date_range(start, end)


def _render_date_controls() -> None:
    st.radio(
        "선택 방식",
        ("빠른 날짜 선택", "직접 날짜 선택"),
        horizontal=True,
        key="date_selection_mode",
    )

    if st.session_state.date_selection_mode == "빠른 날짜 선택":
        selection = st.radio(
            "빠른 날짜 선택",
            QUICK_DATE_OPTIONS,
            horizontal=True,
            key="quick_date",
        )
        start, end = quick_date_range(selection)
    else:
        left, right = st.columns(2)
        today = korean_today()
        with left:
            start = st.date_input("시작 날짜", value=today, key="direct_start")
        with right:
            end = st.date_input("종료 날짜", value=today, key="direct_end")

    try:
        dates = validate_date_range(start, end)
        st.caption(
            f"선택 기간: {start.isoformat()} ~ {end.isoformat()} · 총 {len(dates)}일 "
            "(최대 31일)"
        )
    except DateRangeError as exc:
        st.error(str(exc))


def _run_extraction(dates: Sequence[date]) -> BatchExtraction:
    progress = st.progress(0.0)
    current = st.empty()

    def update(target_date: date, index: int, total: int) -> None:
        current.info(f"현재 처리 중: {target_date.isoformat()} ({index}/{total})")
        progress.progress((index - 1) / total)

    batch = collect_readings(dates, extract_one=extract_one_cached, on_progress=update)
    progress.progress(1.0)
    current.success("추출 작업이 끝났습니다.")
    return batch


def _render_reading_text(content: str) -> None:
    # st.text는 HTML을 해석하지 않아 사이트 원문을 안전한 일반 텍스트로 표시한다.
    st.text(content)


def _render_copy_button(content: str, key: str) -> None:
    """Streamlit의 클립보드 기능을 한 번 누르는 전체 너비 버튼으로 표시한다."""
    with st.container(key=key):
        st.code(content, language=None, wrap_lines=True)


def _render_results(batch: BatchExtraction, requested_dates: Sequence[date]) -> None:
    st.divider()
    success_count = len(batch.results)
    failure_count = len(batch.failures)
    left, right = st.columns(2)
    left.success(f"성공: {success_count}일")
    if failure_count:
        right.error(f"실패: {failure_count}일")
    else:
        right.success("실패: 0일")

    if batch.failures:
        st.subheader("확인하지 못한 날짜")
        for failed_date, reason in batch.failures:
            st.warning(f"{failed_date.isoformat()}: {reason}")

    for date_iso, source_url, readings in batch.results:
        with st.expander(format_korean_date(date_iso), expanded=success_count == 1):
            st.caption(f"출처: {source_url}")
            _render_copy_button(
                build_date_txt_content((date_iso, source_url, readings)),
                f"missa_copy_date_{date_iso.replace('-', '')}",
            )
            for label, content in readings.items():
                st.markdown(f"#### {display_reading_label(label)}")
                _render_reading_text(content)

    if batch.results:
        st.subheader("복사 또는 다운로드")
        if success_count > 1:
            _render_copy_button(build_txt_content(batch.results), "missa_copy_all")
        st.download_button(
            "TXT 파일 다운로드",
            data=build_txt_bytes(batch.results),
            file_name=make_download_filename(requested_dates),
            mime="text/plain; charset=utf-8",
            use_container_width=True,
        )


def main() -> None:
    st.set_page_config(
        page_title="매일미사 말씀 추출기",
        page_icon="📖",
        layout="centered",
    )
    st.markdown(
        """
        <style>
        .block-container {max-width: 780px; padding-top: 2rem; padding-bottom: 3rem;}
        [data-testid="stText"] pre {
            white-space: pre-wrap;
            overflow-wrap: anywhere;
            font-family: inherit;
            font-size: 1rem;
            line-height: 1.75;
        }
        [class*="st-key-missa_copy_"] [data-testid="stCode"] {
            min-height: 46px;
            padding: 0 !important;
            border: 0 !important;
            background: transparent !important;
        }
        [class*="st-key-missa_copy_"] [data-testid="stCode"] pre {
            display: none !important;
        }
        [class*="st-key-missa_copy_"] [data-testid="stCode"] div:has([data-testid="stElementToolbarButton"]),
        [class*="st-key-missa_copy_"] [data-testid="stCode"] div:has(> [data-testid="stCodeCopyButton"]),
        [class*="st-key-missa_copy_"] [data-testid="stElementToolbarButton"],
        [class*="st-key-missa_copy_"] [data-testid="stTooltipHoverTarget"],
        [class*="st-key-missa_copy_"] [data-testid="stCodeCopyButton"] {
            position: static !important;
            width: 100% !important;
            min-height: 44px !important;
            height: auto !important;
            inset: auto !important;
            transform: none !important;
            display: flex !important;
            align-items: center !important;
            justify-content: center !important;
            opacity: 1 !important;
            visibility: visible !important;
            pointer-events: auto !important;
        }
        [class*="st-key-missa_copy_"] [data-testid="stCodeCopyButton"],
        [class*="st-key-missa_copy_"] button[aria-label="Copy to clipboard"],
        [class*="st-key-missa_copy_"] button[aria-label="Copied!"] {
            width: 100% !important;
            min-height: 44px !important;
            position: static !important;
            border: 1px solid #c9cdd3 !important;
            border-radius: 0.55rem !important;
            background: #fff !important;
            color: #202124 !important;
            font-size: 1rem !important;
            font-weight: 600 !important;
            display: flex !important;
            align-items: center !important;
            justify-content: center !important;
            opacity: 1 !important;
            visibility: visible !important;
            pointer-events: auto !important;
        }
        [class*="st-key-missa_copy_date_"] button::after {
            content: "이 날짜 본문 전체 복사";
            margin-left: 0.45rem;
        }
        .st-key-missa_copy_all button::after {
            content: "모든 날짜 본문 전체 복사";
            margin-left: 0.45rem;
        }
        [class*="st-key-missa_copy_"] button[aria-label="Copied!"]::after {
            content: "복사되었습니다";
        }
        @media (max-width: 640px) {
            .block-container {padding: 1.25rem 1rem 2rem;}
            h1 {font-size: 1.8rem !important;}
        }
        </style>
        """,
        unsafe_allow_html=True,
    )
    _initialize_state()

    st.title("매일미사 말씀 추출기")
    st.write(
        "날짜를 선택하면 제1독서, 제2독서가 있는 경우 제2독서, "
        "대체 독서와 복음을 추출합니다."
    )
    st.caption("한국 시간(Asia/Seoul) 기준 · 한 번에 최대 31일")

    with st.container(border=True):
        _render_date_controls()
        clicked = st.button(
            "말씀 추출하기",
            type="primary",
            use_container_width=True,
            disabled=st.session_state.missa_running,
        )

    if clicked and not st.session_state.missa_running:
        try:
            dates = _selected_dates()
        except DateRangeError as exc:
            st.error(str(exc))
        else:
            st.session_state.missa_running = True
            try:
                batch = _run_extraction(dates)
                st.session_state.missa_batch = batch
                st.session_state.missa_requested_dates = tuple(dates)
            except Exception:
                st.error("추출 작업을 시작하지 못했습니다. 잠시 후 다시 시도해 주세요.")
            finally:
                st.session_state.missa_running = False

    batch = st.session_state.missa_batch
    if batch is not None:
        _render_results(batch, st.session_state.missa_requested_dates)


if __name__ == "__main__":
    main()
