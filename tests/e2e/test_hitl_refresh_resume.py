"""Bloque A3 (Fase 5): este archivo se llamaba test_hitl_refresh_resume.py pero
su unico test (movido a tests/unit/test_pending_confirmation_parsing.py) solo
parseaba un dict a mano -- no ejecutaba el grafo, no persistia/recargaba un
checkpoint, no simulaba una recarga de pagina real. El nombre prometia algo
que el contenido no respaldaba.

El test de abajo SI ejercita reanudacion tras refresh de verdad: dos llamadas
TestClient completamente independientes (cada una con su propio
dependency-injection context de FastAPI, sin compartir nada de estado Python
de una request a otra salvo el checkpointer). La primera crea una confirmacion
pendiente via POST /api/chat (grafo real, interrupt() real). La segunda,
simulando "el usuario recargo la pagina y aprobo", resuelve la confirmacion
via POST /api/chat/confirm SIN reusar la sesion/objeto de la primera request
-- solo el checkpointer compartido (que en produccion seria Postgres) permite
que la segunda reconstruya el estado pausado del grafo. Si LangGraph perdiera
el estado interrumpido entre requests, o si el resume ejecutara la tool de
nuevo desde cero en vez de continuar donde quedo, este test lo detectaria.
"""

from types import SimpleNamespace

from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage
from langgraph.checkpoint.memory import InMemorySaver

import app.agent.graph as graph_module
from app.dependencies import get_current_user_id, get_db
from app.main import app


def test_hitl_confirmation_survives_across_independent_requests_via_checkpointer(
    monkeypatch, patch_auth_middleware, auth_cookie
):
    graph_module._app = None
    try:
        write_calls = 0

        async def _fake_write_file(_args, _ctx):
            nonlocal write_calls
            write_calls += 1
            return {"status": "written"}

        monkeypatch.setitem(graph_module.TOOL_HANDLERS, "write_file", _fake_write_file)

        class _FakeToolCallRecord:
            id = "tool-call-refresh-1"

        async def _fake_find_or_create_pending_tool_call(**_kwargs):
            return _FakeToolCallRecord()

        async def _fake_update_tool_call_status(_db, _tool_call_id, _status, _result=None):
            return None

        monkeypatch.setattr(
            graph_module, "find_or_create_pending_tool_call", _fake_find_or_create_pending_tool_call
        )
        monkeypatch.setattr(graph_module, "update_tool_call_status", _fake_update_tool_call_status)

        async def _fake_memory_injection_node(state, config):
            return {}

        monkeypatch.setattr(graph_module, "memory_injection_node", _fake_memory_injection_node)

        model_calls = 0

        async def _fake_ainvoke_chat_with_fallback(_messages, primary_model=None, tool_schemas=None):
            nonlocal model_calls
            model_calls += 1
            if model_calls == 1:
                return AIMessage(
                    content="",
                    tool_calls=[
                        {
                            "id": "tc-write-refresh-1",
                            "name": "write_file",
                            "args": {"path": "a.txt", "content": "hi"},
                        }
                    ],
                )
            return AIMessage(content="Archivo listo.")

        monkeypatch.setattr(graph_module, "ainvoke_chat_with_fallback", _fake_ainvoke_chat_with_fallback)

        # Unico estado compartido entre las dos requests independientes: el
        # checkpointer. En produccion esto es Postgres (AsyncPostgresSaver);
        # aca un InMemorySaver alcanza para probar el mecanismo de LangGraph
        # (thread_id -> estado persistido) sin levantar una base real.
        shared_checkpointer = InMemorySaver()

        async def _fake_get_checkpointer():
            return shared_checkpointer

        monkeypatch.setattr(graph_module, "get_checkpointer", _fake_get_checkpointer)

        async def _fake_db():
            return object()

        async def _fake_user_id():
            return "user-1"

        async def _fake_session(_db, _session_id):
            return SimpleNamespace(id="session-refresh-1", user_id="user-1", title=None)

        async def _fake_profile(_db, _user_id):
            return None

        async def _fake_tools(_db, _user_id):
            return ["write_file"]

        persisted_messages: list[dict] = []

        async def _fake_add_message(_db, session_id, role, content, structured_payload=None):
            persisted_messages.append(
                {"session_id": session_id, "role": role, "content": content, "structured_payload": structured_payload}
            )
            return SimpleNamespace(id=f"msg-{len(persisted_messages)}", role=role, content=content)

        app.dependency_overrides[get_db] = _fake_db
        app.dependency_overrides[get_current_user_id] = _fake_user_id
        monkeypatch.setattr("app.routers.chat.get_session_by_id", _fake_session)
        monkeypatch.setattr("app.routers.chat.get_profile", _fake_profile)
        monkeypatch.setattr("app.routers.chat.list_enabled_tool_ids", _fake_tools)
        monkeypatch.setattr("app.routers.chat.add_message", _fake_add_message)

        # --- Request 1: el usuario pide crear un archivo; el modelo dispara
        # una tool call de riesgo alto -> el grafo se pausa en interrupt(). ---
        client = TestClient(app)
        first_response = client.post(
            "/api/chat",
            cookies=auth_cookie,
            data={"message": "crea un archivo", "session_id": "session-refresh-1"},
        )

        assert first_response.status_code == 200
        assert write_calls == 0
        # Un mensaje de usuario ("crea un archivo") + un mensaje de asistente
        # con la confirmacion pendiente adjunta como structured_payload.
        assert len(persisted_messages) == 2
        assert persisted_messages[0]["role"] == "user"
        pending_payload = persisted_messages[1]["structured_payload"]
        assert pending_payload is not None
        assert pending_payload["type"] == "pending_confirmation"
        assert pending_payload["tool_call_id"] == "tool-call-refresh-1"
        assert pending_payload["confirmation_status"] == "pending"

        # --- "Recarga de pagina": segunda request TestClient totalmente
        # independiente (nuevo dependency-injection context), simulando que
        # el usuario aprueba la confirmacion desde una vista fresca de /chat.
        # get_pending_tool_call es lo unico nuevo que hace falta mockear aca
        # -- en produccion esa fila ya existe en Postgres desde la request 1. ---
        async def _fake_pending_tool_call(_db, tool_call_id):
            return SimpleNamespace(id=tool_call_id, session_id="session-refresh-1")

        monkeypatch.setattr("app.routers.chat.get_pending_tool_call", _fake_pending_tool_call)

        second_response = client.post(
            "/api/chat/confirm",
            cookies=auth_cookie,
            data={"tool_call_id": "tool-call-refresh-1", "action": "approve"},
        )

        assert second_response.status_code == 200
        assert "Archivo listo." in second_response.text
        # La tool se ejecuto exactamente una vez, en la segunda request -- el
        # estado interrumpido de la primera se reconstruyo correctamente
        # desde el checkpointer, sin volver a disparar la tool desde cero.
        assert write_calls == 1
        assert len(persisted_messages) == 3
        assert persisted_messages[2] == {
            "session_id": "session-refresh-1",
            "role": "assistant",
            "content": "Archivo listo.",
            "structured_payload": None,
        }

        app.dependency_overrides.clear()
    finally:
        graph_module._app = None
