import asyncio
import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.runnables import RunnableConfig
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, interrupt
from supabase import AsyncClient

from app.agent.checkpointer import get_checkpointer
from app.agent.langfuse import augment_invoke_config
from app.agent.model import PRIMARY_CHAT_MODEL, ainvoke_chat_with_fallback
from app.agent.nodes.compaction_node import compaction_node
from app.agent.nodes.memory_injection_node import memory_injection_node
from app.agent.state import AgentState
from app.db.queries.tool_calls import find_or_create_pending_tool_call, update_tool_call_status
from app.services.hitl import build_confirmation_message, sanitize_args
from app.tools.adapters import TOOL_HANDLERS
from app.tools.catalog import get_tool_risk, tool_requires_confirmation
from app.tools.schemas import build_tool_schemas
from app.tools.with_tracking import run_with_tracking

MAX_TOOL_ITERATIONS = 6
MAX_TOOL_ITERATIONS_LIMIT_MESSAGE = (
    "Alcancé el límite de 6 iteraciones de herramientas para este turno. "
    "Respondo con lo obtenido hasta ahora; si necesitás más pasos, enviá otro mensaje."
)


@dataclass
class AgentInput:
    user_id: str
    session_id: str
    system_prompt: str
    db: AsyncClient
    enabled_tools: list[str]
    chat_model: str = PRIMARY_CHAT_MODEL
    message: str | None = None
    resume_decision: str | None = None
    attachment_blocks: list[dict[str, Any]] | None = None


@dataclass
class PendingConfirmation:
    tool_call_id: str
    model_tool_call_id: str
    tool_name: str
    risk: str
    message: str
    args_preview: dict[str, Any]
    session_id: str


@dataclass
class AgentOutput:
    response: str
    tool_calls: list[str]
    pending_confirmation: PendingConfirmation | None = None


def parse_pending_confirmation(final_state: dict[str, Any]) -> PendingConfirmation | None:
    interrupts = final_state.get("__interrupt__", [])
    if not interrupts:
        return None
    first = interrupts[0]
    payload = first.value if hasattr(first, "value") else first
    required_keys = {
        "tool_call_id",
        "model_tool_call_id",
        "tool_name",
        "risk",
        "message",
        "session_id",
    }
    if not isinstance(payload, dict) or not required_keys.issubset(payload):
        return None
    return PendingConfirmation(
        tool_call_id=payload["tool_call_id"],
        model_tool_call_id=payload["model_tool_call_id"],
        tool_name=payload["tool_name"],
        risk=payload["risk"],
        message=payload["message"],
        args_preview=payload.get("args_preview", {}),
        session_id=payload["session_id"],
    )


async def agent_node(state: AgentState, config: RunnableConfig) -> dict[str, list[AIMessage]]:
    current_date = datetime.now(ZoneInfo("America/Bogota")).strftime("%A, %d de %B de %Y, %H:%M")
    system_prompt = f"{state['system_prompt']}\n\nFecha y hora actual: {current_date} (hora Colombia)."
    chat_model = state.get("chat_model") or PRIMARY_CHAT_MODEL
    tool_ctx = config.get("configurable", {}).get("tool_ctx", {})
    enabled_tools = tool_ctx.get("enabled_tools") or []
    tool_schemas = build_tool_schemas(enabled_tools)
    response = await ainvoke_chat_with_fallback(
        [SystemMessage(content=system_prompt), *state["messages"]],
        primary_model=chat_model,
        tool_schemas=tool_schemas,
    )
    return {"messages": [response]}


def should_continue(state: AgentState) -> str:
    last = state["messages"][-1]
    if isinstance(last, AIMessage) and last.tool_calls:
        if state.get("tool_iteration_count", 0) >= MAX_TOOL_ITERATIONS:
            return "limit_reached"
        return "tools"
    return "end"


async def limit_reached_node(state: AgentState) -> dict[str, list[AIMessage]]:
    return {"messages": [AIMessage(content=MAX_TOOL_ITERATIONS_LIMIT_MESSAGE)]}


def _last_ai_message(messages: list[Any]) -> AIMessage | None:
    """El AIMessage con tool_calls no es necesariamente el ultimo mensaje del
    estado: tool_executor_auto_node ya pudo haber agregado ToolMessage(s)
    detras de el (add_messages los apendea) antes de que
    tool_executor_confirm_node corra como Pregel step separado. Hay que
    buscar hacia atras, no asumir messages[-1]."""
    for message in reversed(messages):
        if isinstance(message, AIMessage):
            return message
    return None


async def _run_untracked_tool_call(
    tool_id: str,
    args: dict[str, Any],
    model_tc_id: str,
    session_id: str,
    tool_ctx: dict[str, Any],
) -> ToolMessage:
    async def _handler(tool_args: dict[str, Any], *, _tool_id: str = tool_id) -> dict[str, Any]:
        return await TOOL_HANDLERS[_tool_id](tool_args, tool_ctx)

    result = await run_with_tracking(
        db=tool_ctx["db"],
        session_id=session_id,
        tool_id=tool_id,
        args=args,
        handler=_handler,
        model_tool_call_id=model_tc_id or None,
    )
    return ToolMessage(content=json.dumps(result), tool_call_id=model_tc_id)


async def tool_executor_auto_node(state: AgentState, config: RunnableConfig) -> dict[str, Any]:
    """Ejecuta las tool calls que NO requieren confirmacion (desconocidas,
    deshabilitadas, o de riesgo bajo/auto-run) de este batch. Las que si
    requieren confirmacion se dejan sin tocar para tool_executor_confirm_node.

    Deliberadamente en un nodo aparte de tool_executor_confirm_node: si ese
    segundo nodo llama interrupt() y el grafo se reanuda mas tarde con
    Command(resume=...), LangGraph solo re-invoca el nodo que quedo pausado —
    este nodo, al ser un Pregel step ya completo y checkpointeado antes de la
    pausa, NO se vuelve a ejecutar. Si ambas ramas vivieran en la misma
    funcion (como antes), las tool calls sin confirmacion que ya corrieron
    antes del interrupt() se re-ejecutarian en cada resume (LangGraph reproduce
    la funcion completa del nodo interrumpido desde el inicio; interrupt()
    solo evita repetir la pausa en si, no el codigo previo)."""
    last_msg = _last_ai_message(state["messages"])
    if last_msg is None:
        return {}
    configurable = config.get("configurable", {})
    tool_ctx = configurable.get("tool_ctx", {})
    results: list[ToolMessage] = []
    # Tool calls sin confirmación son independientes entre sí: se acumulan y
    # se ejecutan con asyncio.gather en vez de una por una. Se vacía
    # (_flush_untracked_batch) antes de la rama unknown/disabled para
    # preservar el orden original de tool_calls en `results`.
    #
    # L5 (tradeoff documentado): esta paralelizacion asume que toda tool de
    # riesgo "low" (la unica categoria que entra en este batch, ver
    # app/tools/catalog.py) es de solo lectura o, al menos, conmutativa/segura
    # de correr concurrentemente con las demas del mismo batch. Hoy se cumple
    # (get_user_preferences, list_enabled_tools, read_file, mcp_example_ping
    # son todas de solo lectura). Si se agrega una tool "low" con un patron
    # read-modify-write (ej. incrementar un contador, hacer append a una
    # columna), correr dos instancias de esa tool en el mismo batch via
    # gather introduciria una carrera real de lost-update que NO existia
    # cuando esto era secuencial. Antes de marcar una tool nueva como "low",
    # confirmar que es de solo lectura o idempotente bajo concurrencia.
    pending_batch: list[Any] = []

    async def _flush_untracked_batch() -> None:
        if pending_batch:
            results.extend(await asyncio.gather(*pending_batch))
            pending_batch.clear()

    for tc in last_msg.tool_calls:
        tool_id = tc["name"]
        model_tc_id = tc.get("id") or ""
        args = tc.get("args", {})
        if tool_id not in TOOL_HANDLERS:
            await _flush_untracked_batch()
            results.append(ToolMessage(content=json.dumps({"error": f"Unknown tool: {tool_id}"}), tool_call_id=model_tc_id))
            continue
        if tool_id not in (tool_ctx.get("enabled_tools") or []):
            await _flush_untracked_batch()
            results.append(
                ToolMessage(
                    content=json.dumps({"error": f"Tool not enabled: {tool_id}"}),
                    tool_call_id=model_tc_id,
                )
            )
            continue
        if tool_requires_confirmation(tool_id):
            # Se maneja en tool_executor_confirm_node; no ejecutar nada aca.
            continue

        pending_batch.append(
            _run_untracked_tool_call(tool_id, args, model_tc_id, state["session_id"], tool_ctx)
        )

    await _flush_untracked_batch()
    return {"messages": results}


@dataclass
class _PendingConfirmationCall:
    tool_id: str
    model_tc_id: str
    args: dict[str, Any]


def _find_next_pending_confirmation(
    last_msg: AIMessage, tool_ctx: dict[str, Any], resolved_ids: list[str]
) -> _PendingConfirmationCall | None:
    """Primera tool call del batch que requiere confirmacion y todavia no fue
    resuelta en esta ronda. Replica los mismos filtros que tool_executor_auto_node
    (TOOL_HANDLERS/enabled_tools/tool_requires_confirmation) para no volver a
    procesar algo que ya quedo resuelto (con error) por ese otro nodo — un tool_id
    desconocido tiene risk="high" por default (fail-closed) y tool_requires_confirmation
    devolveria True para el, asi que hace falta re-chequear TOOL_HANDLERS/enabled_tools
    aca tambien, no alcanza con tool_requires_confirmation solo."""
    for tc in last_msg.tool_calls:
        tool_id = tc["name"]
        model_tc_id = tc.get("id") or ""
        if tool_id not in TOOL_HANDLERS:
            continue  # ya resuelto por tool_executor_auto_node
        if tool_id not in (tool_ctx.get("enabled_tools") or []):
            continue  # ya resuelto por tool_executor_auto_node
        if not tool_requires_confirmation(tool_id):
            continue  # ya resuelto por tool_executor_auto_node
        if model_tc_id in resolved_ids:
            continue  # ya resuelto en un paso anterior de esta misma ronda
        return _PendingConfirmationCall(tool_id=tool_id, model_tc_id=model_tc_id, args=tc.get("args", {}))
    return None


async def tool_executor_confirm_node(state: AgentState, config: RunnableConfig) -> dict[str, Any]:
    """Maneja UNA sola tool call que requiere confirmacion por invocacion
    (interrupt() incluido) — nunca mas de una. Si el batch trae 2+ tool calls
    que requieren confirmacion, route_after_confirm() vuelve a rutear aca en
    un Pregel step nuevo y separado para la siguiente, en vez de procesar
    todas en un mismo for dentro de la misma invocacion del nodo.

    Esto es deliberado: LangGraph reproduce la funcion completa del nodo
    interrumpido desde el inicio en cada Command(resume=...). Si este nodo
    procesara varias tool calls con interrupt() secuenciales en el mismo for
    (como antes), cada resume re-ejecutaria el handler+escritura en DB de las
    ya aprobadas en resumes anteriores de esa misma invocacion. Al procesar
    como maximo una por invocacion, cada confirmacion resuelta queda en un
    Pregel step propio ya checkpointeado, que un resume posterior no vuelve a
    tocar (mismo principio que la separacion tools_auto/tools_confirm).

    Verificado empiricamente con un grafo minimo (loop-back condicional +
    interrupt/resume repetido varias veces sobre el mismo thread) antes de
    aplicar este patron aca: cada resume solo re-ejecuta la confirmacion
    pendiente actual, nunca las ya resueltas.
    """
    last_msg = _last_ai_message(state["messages"])
    if last_msg is None:
        return {}
    configurable = config.get("configurable", {})
    tool_ctx = configurable.get("tool_ctx", {})
    resolved_ids: list[str] = state.get("resolved_confirm_tool_call_ids", [])

    pending = _find_next_pending_confirmation(last_msg, tool_ctx, resolved_ids)
    if pending is None:
        # Nada (mas) que confirmar en este batch: la ronda de tools queda
        # cerrada aca. Se limpia resolved_confirm_tool_call_ids para que no
        # arrastre ids de esta ronda hacia el proximo batch de tool_calls.
        return {
            "tool_iteration_count": state.get("tool_iteration_count", 0) + 1,
            "resolved_confirm_tool_call_ids": [],
        }

    tool_id, model_tc_id, args = pending.tool_id, pending.model_tc_id, pending.args
    record = await find_or_create_pending_tool_call(
        db=tool_ctx["db"],
        session_id=state["session_id"],
        tool_name=tool_id,
        args=args,
        model_tool_call_id=model_tc_id,
    )
    payload = {
        "tool_call_id": record.id,
        "model_tool_call_id": model_tc_id,
        "tool_name": tool_id,
        "risk": get_tool_risk(tool_id),
        "message": build_confirmation_message(tool_id, args),
        "args_preview": sanitize_args(tool_id, args),
        "session_id": state["session_id"],
    }
    decision = interrupt(payload)
    new_resolved_ids = [*resolved_ids, model_tc_id]
    if decision != "approve":
        await update_tool_call_status(tool_ctx["db"], record.id, "rejected")
        return {
            "messages": [ToolMessage(content="Acción cancelada por el usuario.", tool_call_id=model_tc_id)],
            "resolved_confirm_tool_call_ids": new_resolved_ids,
        }
    await update_tool_call_status(tool_ctx["db"], record.id, "approved")
    try:
        result = await TOOL_HANDLERS[tool_id](args, tool_ctx)
    except Exception as exc:
        await update_tool_call_status(tool_ctx["db"], record.id, "failed")
        return {
            "messages": [
                ToolMessage(
                    content=json.dumps({"error": f"Tool execution failed: {exc}"}),
                    tool_call_id=model_tc_id,
                )
            ],
            "resolved_confirm_tool_call_ids": new_resolved_ids,
        }
    await update_tool_call_status(tool_ctx["db"], record.id, "executed", result)
    return {
        "messages": [ToolMessage(content=json.dumps(result), tool_call_id=model_tc_id)],
        "resolved_confirm_tool_call_ids": new_resolved_ids,
    }


def route_after_confirm(state: AgentState, config: RunnableConfig) -> str:
    """Si quedan tool calls de este batch que requieren confirmacion y aun no
    se resolvieron, vuelve a rutear a tools_confirm (un Pregel step nuevo);
    si no, sigue a compaction. Replica el mismo chequeo que hace el nodo para
    decidir si hay trabajo pendiente."""
    last_msg = _last_ai_message(state["messages"])
    if last_msg is None:
        return "next"
    configurable = config.get("configurable", {})
    tool_ctx = configurable.get("tool_ctx", {})
    resolved_ids: list[str] = state.get("resolved_confirm_tool_call_ids", [])
    if _find_next_pending_confirmation(last_msg, tool_ctx, resolved_ids) is not None:
        return "loop"
    return "next"


def _build_initial_messages(
    message: str | None, attachment_blocks: list[dict[str, Any]] | None
) -> list[HumanMessage]:
    if not message and not attachment_blocks:
        return []
    if not attachment_blocks:
        return [HumanMessage(content=message)]
    parts: list[str | dict[Any, Any]] = []
    if message:
        parts.append({"type": "text", "text": message})
    parts.extend(attachment_blocks)
    return [HumanMessage(content=parts)]


_app = None
_app_lock = asyncio.Lock()


async def _get_graph_app():
    global _app
    if _app is not None:
        return _app
    async with _app_lock:
        if _app is None:
            graph = StateGraph(AgentState)
            graph.add_node("memory_injection", memory_injection_node)
            graph.add_node("compaction", compaction_node)
            graph.add_node("agent", agent_node)
            graph.add_node("tools_auto", tool_executor_auto_node)
            graph.add_node("tools_confirm", tool_executor_confirm_node)
            graph.add_node("limit_reached", limit_reached_node)
            # memory_injection y compaction son independientes entre si (el primero
            # solo lee messages/system_prompt y escribe system_prompt; el segundo
            # solo lee/escribe messages/compaction_*), asi que corren en paralelo
            # como fan-out desde START, con join en "agent" (que espera a ambos).
            # En los loops posteriores de tool-calling (tools_confirm -> compaction
            # -> agent) memory_injection no vuelve a dispararse — verificado que
            # LangGraph triggerea "agent" correctamente solo con la actualizacion
            # de "compaction" en ese caso, sin esperar a que memory_injection
            # vuelva a correr (no es un join estricto por-superstep, es por nodo
            # predecesor activo).
            graph.add_edge(START, "memory_injection")
            graph.add_edge(START, "compaction")
            graph.add_edge("memory_injection", "agent")
            graph.add_edge("compaction", "agent")
            graph.add_conditional_edges(
                "agent",
                should_continue,
                {"tools": "tools_auto", "end": END, "limit_reached": "limit_reached"},
            )
            graph.add_edge("limit_reached", END)
            # tools_auto y tools_confirm son dos Pregel steps separados (no una
            # sola funcion) para que un interrupt() dentro de tools_confirm no
            # provoque, al reanudar, la re-ejecucion de las tool calls sin
            # confirmacion que tools_auto ya corrio y checkpointeo.
            graph.add_edge("tools_auto", "tools_confirm")
            # tools_confirm procesa como maximo UNA tool call que requiere
            # confirmacion por invocacion; si el batch trae 2+, este edge
            # condicional vuelve a rutear a tools_confirm (un Pregel step
            # nuevo) para la siguiente, en vez de compaction directo.
            graph.add_conditional_edges(
                "tools_confirm",
                route_after_confirm,
                {"loop": "tools_confirm", "next": "compaction"},
            )
            checkpointer = await get_checkpointer()
            _app = graph.compile(checkpointer=checkpointer)
    return _app


async def warmup_agent_runtime() -> None:
    await _get_graph_app()


async def run_agent(agent_input: AgentInput) -> AgentOutput:
    app = await _get_graph_app()
    tool_ctx = {
        "db": agent_input.db,
        "user_id": agent_input.user_id,
        "session_id": agent_input.session_id,
        "enabled_tools": agent_input.enabled_tools,
    }
    config = augment_invoke_config(
        {"configurable": {"thread_id": agent_input.session_id, "tool_ctx": tool_ctx}},
        user_id=agent_input.user_id,
        session_id=agent_input.session_id,
        is_resume=bool(agent_input.resume_decision),
    )
    if agent_input.resume_decision:
        final_state = await app.ainvoke(Command(resume=agent_input.resume_decision), config=config)
    else:
        initial_messages = _build_initial_messages(agent_input.message, agent_input.attachment_blocks)
        initial_state: dict[str, Any] = {
            "messages": initial_messages,
            "session_id": agent_input.session_id,
            "user_id": agent_input.user_id,
            "system_prompt": agent_input.system_prompt,
            "chat_model": agent_input.chat_model,
            "tool_iteration_count": 0,
            # A diferencia de compaction_*, este campo es scratch de UNA sola
            # ronda de tool-calling (que tool_call_ids de ESTE batch ya se
            # confirmaron) y debe resetearse en cada turno nuevo, no persistir.
            "resolved_confirm_tool_call_ids": [],
        }
        # compaction_count/compaction_failure_count/compaction_breaker_skips no
        # tienen reducer (a diferencia de "messages" con add_messages): LangGraph
        # sobreescribe esos canales con lo que venga en el input de CADA ainvoke,
        # no solo en el primero del thread (verificado empiricamente con un grafo
        # minimo). Si los inicializaramos en 0 aca en cada turno, el circuit
        # breaker de compaction_node nunca podria acumularse entre turnos reales
        # de una misma sesion (solo dentro del tool-loop de un mismo turno). Por
        # eso solo se inicializan en 0 cuando el thread es nuevo (sin checkpoint
        # previo); si ya existe uno, se omiten del input para que el valor
        # persistido fluya sin resetearse.
        existing_snapshot = await app.aget_state(config)
        if not existing_snapshot.values:
            initial_state["compaction_count"] = 0
            initial_state["compaction_failure_count"] = 0
            initial_state["compaction_breaker_skips"] = 0
        final_state = await app.ainvoke(initial_state, config=config)
    if isinstance(final_state, dict):
        pending = parse_pending_confirmation(final_state)
        if pending:
            return AgentOutput(
                response=pending.message,
                tool_calls=[pending.tool_name],
                pending_confirmation=pending,
            )
    messages = final_state.get("messages", [])
    ai_messages = [m for m in messages if isinstance(m, AIMessage)]
    response = ai_messages[-1].content if ai_messages else ""
    tool_calls = [tc["name"] for m in ai_messages for tc in m.tool_calls]
    return AgentOutput(response=str(response), tool_calls=tool_calls)
