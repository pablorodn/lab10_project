import pytest

from app.db.queries.messages import get_first_user_message_with_content, get_last_user_message


class _FakeResult:
    def __init__(self, data):
        self.data = data


class _RecordingQuery:
    def __init__(self, calls, data):
        self._calls = calls
        self._data = data

    def select(self, *args, **kwargs):
        self._calls.append(("select", args, kwargs))
        return self

    def eq(self, *args, **kwargs):
        self._calls.append(("eq", args, kwargs))
        return self

    def neq(self, *args, **kwargs):
        self._calls.append(("neq", args, kwargs))
        return self

    def order(self, *args, **kwargs):
        self._calls.append(("order", args, kwargs))
        return self

    def limit(self, *args, **kwargs):
        self._calls.append(("limit", args, kwargs))
        return self

    async def execute(self):
        return _FakeResult(self._data)


class _RecordingDb:
    def __init__(self, data):
        self.calls: list[tuple] = []
        self._data = data

    def table(self, name):
        self.calls.append(("table", name))
        return _RecordingQuery(self.calls, self._data)


@pytest.mark.anyio
async def test_get_first_user_message_with_content_filters_role_and_empty_content():
    row = {
        "id": "msg-1",
        "session_id": "session-1",
        "role": "user",
        "content": "hola",
        "structured_payload": None,
    }
    db = _RecordingDb([row])

    result = await get_first_user_message_with_content(db, "session-1")

    assert result is not None
    assert result.id == "msg-1"

    call_names = [c[0] for c in db.calls]
    assert call_names == ["table", "select", "eq", "eq", "neq", "order", "limit"]

    eq_calls = [c for c in db.calls if c[0] == "eq"]
    assert eq_calls[0][1] == ("session_id", "session-1")
    assert eq_calls[1][1] == ("role", "user")

    neq_call = next(c for c in db.calls if c[0] == "neq")
    assert neq_call[1] == ("content", "")

    order_call = next(c for c in db.calls if c[0] == "order")
    assert order_call[1] == ("created_at",)
    assert order_call[2] == {"desc": False}

    limit_call = next(c for c in db.calls if c[0] == "limit")
    assert limit_call[1] == (1,)


@pytest.mark.anyio
async def test_get_first_user_message_with_content_returns_none_when_empty():
    db = _RecordingDb([])

    result = await get_first_user_message_with_content(db, "session-1")

    assert result is None


@pytest.mark.anyio
async def test_get_last_user_message_orders_desc_without_content_filter():
    row = {
        "id": "msg-2",
        "session_id": "session-1",
        "role": "user",
        "content": "",
        "structured_payload": None,
    }
    db = _RecordingDb([row])

    result = await get_last_user_message(db, "session-1")

    assert result is not None
    assert result.id == "msg-2"

    call_names = [c[0] for c in db.calls]
    assert call_names == ["table", "select", "eq", "eq", "order", "limit"]
    assert not any(c[0] == "neq" for c in db.calls)

    order_call = next(c for c in db.calls if c[0] == "order")
    assert order_call[1] == ("created_at",)
    assert order_call[2] == {"desc": True}


@pytest.mark.anyio
async def test_get_last_user_message_returns_none_when_empty():
    db = _RecordingDb([])

    result = await get_last_user_message(db, "session-1")

    assert result is None
