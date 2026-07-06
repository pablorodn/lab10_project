from app.tools.schemas import build_tool_schemas


def test_build_tool_schemas_filters_by_enabled_tool_ids():
    schemas = build_tool_schemas(["get_user_preferences", "read_file"])

    names = {schema["function"]["name"] for schema in schemas}
    assert names == {"get_user_preferences", "read_file"}


def test_build_tool_schemas_empty_enabled_returns_no_schemas():
    assert build_tool_schemas([]) == []


def test_build_tool_schemas_read_file_parameters_require_path():
    schemas = build_tool_schemas(["read_file"])

    parameters = schemas[0]["function"]["parameters"]
    assert parameters["required"] == ["path"]
    assert "offset" in parameters["properties"]
    assert "limit" in parameters["properties"]


def test_build_tool_schemas_no_args_tool_has_empty_properties():
    schemas = build_tool_schemas(["get_user_preferences"])

    parameters = schemas[0]["function"]["parameters"]
    assert parameters["properties"] == {}
