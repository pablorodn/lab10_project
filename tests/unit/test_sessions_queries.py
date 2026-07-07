import asyncio

import pytest

from app.db.queries import sessions as sessions_module
from app.db.queries.sessions import get_or_create_active_session, list_sessions


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


class _FakeSessionResult:
    def __init__(self, data):
        self.data = data


class _FakeSessionQuery:
    """Simula la tabla agent_sessions con estado real compartido (self._state),
    para poder reproducir la carrera check-then-insert: dos get_active_session
    concurrentes deben ver el mismo estado ("no hay sesion activa todavia") si
    corren antes de que el create_session de la otra termine."""

    def __init__(self, state: dict):
        self._state = state
        self._op: str | None = None
        self._payload: dict | None = None

    def select(self, *_a, **_kw):
        self._op = "select"
        return self

    def eq(self, *_a, **_kw):
        return self

    def order(self, *_a, **_kw):
        return self

    def limit(self, *_a, **_kw):
        return self

    def insert(self, payload):
        self._op = "insert"
        self._payload = payload
        return self

    async def execute(self):
        if self._op == "select":
            self._state["get_active_calls"] += 1
            # Simula latencia de red (~RTT) en la lectura -- es la ventana durante
            # la cual, SIN el lock por usuario, dos requests concurrentes verian
            # ambas "no hay sesion activa" y ambas crearian una.
            await asyncio.sleep(0.05)
            current = self._state["active_session"]
            return _FakeSessionResult([current] if current else [])
        if self._op == "insert":
            self._state["create_calls"] += 1
            row = {
                "id": f"session-{self._state['create_calls']}",
                "user_id": self._payload["user_id"],
                "channel": self._payload["channel"],
                "status": self._payload["status"],
                "last_used_at": self._payload["last_used_at"],
                "title": None,
                "budget_tokens_used": 0,
                "budget_tokens_limit": 100000,
                "created_at": self._payload["last_used_at"],
                "updated_at": self._payload["last_used_at"],
            }
            self._state["active_session"] = row
            return _FakeSessionResult([row])
        raise AssertionError(f"unexpected op: {self._op}")


class _FakeSessionDb:
    def __init__(self, state: dict):
        self._state = state

    def table(self, name):
        assert name == "agent_sessions"
        return _FakeSessionQuery(self._state)


@pytest.fixture(autouse=True)
def _clean_user_session_locks():
    sessions_module._user_session_locks.clear()
    yield
    sessions_module._user_session_locks.clear()


@pytest.mark.anyio
async def test_get_or_create_active_session_is_race_safe_under_concurrent_calls():
    # Reproduce el escenario del diagnostico: dos GET /chat casi simultaneas del
    # mismo usuario (ej. un refresh a mitad de carga, muy probable con el RTT de
    # red medido). Sin el lock por usuario, ambas verian "no hay sesion activa" y
    # ambas crearian una, duplicando la sesion.
    state = {"active_session": None, "get_active_calls": 0, "create_calls": 0}
    db = _FakeSessionDb(state)

    first, second = await asyncio.gather(
        get_or_create_active_session(db, user_id="user-race-1", channel="web"),
        get_or_create_active_session(db, user_id="user-race-1", channel="web"),
    )

    assert state["create_calls"] == 1
    assert first.id == second.id


@pytest.mark.anyio
async def test_get_or_create_active_session_different_users_do_not_serialize():
    # El lock es por user_id: dos usuarios distintos no deberian esperarse entre si.
    state_a = {"active_session": None, "get_active_calls": 0, "create_calls": 0}
    state_b = {"active_session": None, "get_active_calls": 0, "create_calls": 0}
    db_a = _FakeSessionDb(state_a)
    db_b = _FakeSessionDb(state_b)

    session_a, session_b = await asyncio.gather(
        get_or_create_active_session(db_a, user_id="user-race-a", channel="web"),
        get_or_create_active_session(db_b, user_id="user-race-b", channel="web"),
    )

    assert state_a["create_calls"] == 1
    assert state_b["create_calls"] == 1
    assert session_a.user_id == "user-race-a"
    assert session_b.user_id == "user-race-b"
