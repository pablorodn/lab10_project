import pytest

from app.tools.with_tracking import run_with_tracking


class _FakeResult:
    def __init__(self, data):
        self.data = data


class _FakeQuery:
    def __init__(self, db):
        self._db = db
        self._payload: dict | None = None

    def insert(self, payload):
        self._payload = payload
        self._db.insert_payloads.append(payload)
        return self

    async def execute(self):
        return _FakeResult([{"id": "tc-1", "session_id": "s-1", "tool_name": "t", **(self._payload or {})}])


class _FakeDb:
    """DB fake que registra cada payload de insert() para contar/inspeccionar escrituras."""

    def __init__(self):
        self.insert_payloads: list[dict] = []

    def table(self, _name):
        return _FakeQuery(self)


@pytest.mark.anyio
async def test_run_with_tracking_success_writes_single_insert():
    db = _FakeDb()

    async def _handler(args):
        return {"ok": True}

    result = await run_with_tracking(
        db=db,
        session_id="s-1",
        tool_id="get_user_preferences",
        args={},
        handler=_handler,
        model_tool_call_id="mtc-1",
    )

    assert result == {"ok": True}
    assert len(db.insert_payloads) == 1
    payload = db.insert_payloads[0]
    assert payload["status"] == "executed"
    assert payload["result_json"] == {"ok": True}
    assert "finished_at" in payload


@pytest.mark.anyio
async def test_run_with_tracking_failure_writes_single_insert_and_reraises():
    db = _FakeDb()

    async def _handler(args):
        raise RuntimeError("boom")

    with pytest.raises(RuntimeError):
        await run_with_tracking(
            db=db,
            session_id="s-1",
            tool_id="get_user_preferences",
            args={},
            handler=_handler,
        )

    assert len(db.insert_payloads) == 1
    payload = db.insert_payloads[0]
    assert payload["status"] == "failed"
    assert "result_json" not in payload
