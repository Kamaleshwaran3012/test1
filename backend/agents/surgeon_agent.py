from __future__ import annotations

from agents.surgeon_agent import SurgeonAgent as LegacySurgeonAgent
from backend.agents.state import AgentState


def surgeon_agent(state: AgentState):
    agent = LegacySurgeonAgent()
    return agent.repair(state)


def handle_event(state: AgentState):
    return surgeon_agent(state)


def run(state: AgentState):
    return surgeon_agent(state)
