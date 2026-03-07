from agents.surgeon_agent import SurgeonAgent
from backend.agents.state import AgentState


def handle_event(state: AgentState):
    agent = SurgeonAgent()
    return agent.repair(state)


def run(state: AgentState):
    return handle_event(state)
