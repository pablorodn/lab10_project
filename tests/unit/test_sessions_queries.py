import pytest

from app.db.queries.sessions import list_sessions


class _FakeResult:
    def __init__(self, data):
        self.data = data


class _RecordingQuery:
    def __init__(self, calls):
        self._calls = calls

    def select(self, *args, **kwargs):
        self._calls.append(("select", args, kwargs))
        return self

    def eq(self, *args, **kwargs):
        self._calls.append(("eq", args, kwargs))
        return self

    def order(self, *args, **kwargs):
        self._calls.append(("order", args, kwargs))
        return self

    def limit(self, *args, **kwargs):
        self._calls.append(("limit", args, kwargs))
        return self

    async def execute(self):
        return _FakeResult([])


class _RecordingDb:
    def __init__(self):
        self.calls: list[tuple] = []

    def table(self, name):
        self.calls.append(("table", name))
        return _RecordingQuery(self.calls)


@pytest.mark.anyio
async def test_list_sessions_orders_desc_and_limits_to_10():
    db = _RecordingDb()

    await list_sessions(db, "user-1", channel="web")

    call_names = [c[0] for c in db.calls]
    assert call_names == ["table", "select", "eq", "eq", "eq", "order", "limit"]

    order_call = next(c for c in db.calls if c[0] == "order")
    # Ordena por created_at (no last_used_at) a propósito desde ef4b7fb: así la posición
    # de cada sesión en el sidebar no salta cada vez que se envía un mensaje y se actualiza
    # last_used_at vía touch_session.
    assert order_call[1] == ("created_at",)
    assert order_call[2] == {"desc": True}

    limit_call = next(c for c in db.calls if c[0] == "limit")
    assert limit_call[1] == (10,)
