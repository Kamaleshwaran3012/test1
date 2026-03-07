from __future__ import annotations

import importlib
import logging
from typing import Any, Awaitable, Callable

from langgraph.graph import END, StateGraph

from backend.agents.state import AgentState


logger = logging.getLogger("graph.workflow")

AgentHandler = Callable[[AgentState], Awaitable[dict[str, Any] | AgentState | None] | dict[str, Any] | AgentState | None]


def _append_log(state: AgentState, message: str) -> None:
    logs = state.setdefault("agent_logs", [])
    logs.append(message)


async def _call_agent(module_path: str, fallback_label: str, state: AgentState) -> dict[str, Any]:
    try:
        module = importlib.import_module(module_path)
    except Exception:
        _append_log(state, f"{fallback_label} not implemented; skipped")
        return {}

    for fn_name in ("handle_event", "run", "execute", "diagnose"):
        handler = getattr(module, fn_name, None)
        if handler is None:
            continue
        result = handler(state)
        if hasattr(result, "__await__"):
            result = await result
        if isinstance(result, dict):
            return result
        return {}

    _append_log(state, f"{fallback_label} has no callable handler; skipped")
    return {}


async def triage_node(state: AgentState) -> dict[str, Any]:
    _append_log(state, "Orchestrator entered triage")
    return await _call_agent("backend.agents.triage_agent", "Triage agent", state)


async def infra_pathologist_node(state: AgentState) -> dict[str, Any]:
    _append_log(state, "Infra pathologist selected")
    return await _call_agent("backend.agents.pathologists.infra_pathologist", "Infra pathologist", state)


async def runtime_pathologist_node(state: AgentState) -> dict[str, Any]:
    _append_log(state, "Runtime pathologist selected")
    return await _call_agent("backend.agents.pathologists.runtime_pathologist", "Runtime pathologist", state)


async def build_pathologist_node(state: AgentState) -> dict[str, Any]:
    _append_log(state, "Build pathologist selected")
    return await _call_agent("backend.agents.pathologists.build_pathologist", "Build pathologist", state)


async def root_cause_node(state: AgentState) -> dict[str, Any]:
    _append_log(state, "Root cause analysis started")
    return await _call_agent("backend.agents.root_cause_agent", "Root cause agent", state)


async def surgeon_node(state: AgentState) -> dict[str, Any]:
    _append_log(state, "Surgeon agent started")
    return await _call_agent("backend.agents.surgeon_agent", "Surgeon agent", state)


def _route_pathologist(state: AgentState) -> str:
    diagnosis_type = (state.get("diagnosis_type") or state.get("error_type") or "").strip().lower()
    if diagnosis_type == "infra":
        return "infra_pathologist"
    if diagnosis_type == "build":
        return "build_pathologist"
    return "runtime_pathologist"


def build_workflow():
    graph = StateGraph(AgentState)
    graph.add_node("triage", triage_node)
    graph.add_node("infra_pathologist", infra_pathologist_node)
    graph.add_node("runtime_pathologist", runtime_pathologist_node)
    graph.add_node("build_pathologist", build_pathologist_node)
    graph.add_node("root_cause", root_cause_node)
    graph.add_node("surgeon", surgeon_node)

    graph.set_entry_point("triage")
    graph.add_conditional_edges(
        "triage",
        _route_pathologist,
        {
            "infra_pathologist": "infra_pathologist",
            "runtime_pathologist": "runtime_pathologist",
            "build_pathologist": "build_pathologist",
        },
    )
    graph.add_edge("infra_pathologist", "root_cause")
    graph.add_edge("runtime_pathologist", "root_cause")
    graph.add_edge("build_pathologist", "root_cause")
    graph.add_edge("root_cause", "surgeon")
    graph.add_edge("surgeon", END)

    return graph.compile()


workflow_app = build_workflow()


async def run_workflow(state: AgentState) -> AgentState:
    result = await workflow_app.ainvoke(state)
    return result if isinstance(result, dict) else state
