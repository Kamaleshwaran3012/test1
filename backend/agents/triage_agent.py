import json
from langchain_google_genai import ChatGoogleGenerativeAI
from agents.state import AgentState
from prompts.triage_prompt import TRIAGE_SYSTEM_PROMPT


llm = ChatGoogleGenerativeAI(
    model="gemini-1.5-flash",
    temperature=0
)


def triage_agent(state: AgentState):

    prompt = TRIAGE_SYSTEM_PROMPT.format(
        current_error=state.get("current_error", ""),
        error_log=state.get("error_log", ""),
        event_source=state.get("event_source", "")
    )

    response = llm.invoke(prompt)

    try:
        result = json.loads(response.content)
    except Exception:
        result = {
            "error_type": "runtime",
            "suspected_service": "unknown"
        }

    return {
        "error_type": result.get("error_type"),
        "suspected_service": result.get("suspected_service"),
        "agent_logs": [f"Triage classified error as {result.get('error_type')}"]
    }