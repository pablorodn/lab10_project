from app.template_filters import format_session_date


def test_format_session_date_formats_iso_timestamp():
    result = format_session_date("2026-06-05T14:30:00+00:00")
    assert result == "5 jun, 14:30"


def test_format_session_date_handles_empty_values():
    assert format_session_date("") == ""
    assert format_session_date(None) == ""


def test_format_session_date_accepts_zulu_and_offset_inputs():
    zulu = format_session_date("2026-06-05T14:30:00Z")
    offset = format_session_date("2026-06-05T09:30:00-05:00")
    assert zulu == "5 jun, 14:30"
    assert offset == "5 jun, 09:30"
