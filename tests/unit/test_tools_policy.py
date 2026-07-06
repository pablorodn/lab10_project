from app.tools.catalog import get_tool_risk, tool_requires_confirmation


def test_high_risk_tool_requires_confirmation():
    assert tool_requires_confirmation("write_file") is True


def test_low_risk_tool_no_confirmation():
    assert tool_requires_confirmation("read_file") is False


def test_unknown_tool_defaults_high_risk():
    assert get_tool_risk("unknown-tool") == "high"


def test_search_properties_is_low_risk_and_needs_no_confirmation():
    assert get_tool_risk("search_properties") == "low"
    assert tool_requires_confirmation("search_properties") is False
