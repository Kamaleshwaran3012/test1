from agents.root_cause_agent import RootCauseAgent
from backend.agents.state import AgentState


def handle_event(state: AgentState):
    agent = RootCauseAgent()
    return agent.analyze(state)


def run(state: AgentState):
    return handle_event(state)
