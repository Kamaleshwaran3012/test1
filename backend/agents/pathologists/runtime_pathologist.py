import json
from langchain_google_genai import ChatGoogleGenerativeAI
from agents.state import AgentState
from prompts.runtime_prompt import RUNTIME_PATHOLOGIST_PROMPT


llm = ChatGoogleGenerativeAI(
    model="gemini-1.5-flash",
    temperature=0
)


def runtime_pathologist(state: AgentState):

    prompt = RUNTIME_PATHOLOGIST_PROMPT.format(
        current_error=state.get("current_error", ""),
        error_log=state.get("error_log", ""),
        suspected_service=state.get("suspected_service", ""),
        files_context=state.get("files_context", {})
    )

    response = llm.invoke(prompt)

    try:
        result = json.loads(response.content)
    except Exception:
        result = {}

    return {
        "diagnosis_type": result.get("diagnosis_type"),
        "file_path": result.get("file_path"),
        "line_number": result.get("line_number"),
        "fix_description": result.get("fix_description"),
        "replacement_code": result.get("replacement_code"),
        "agent_logs": ["Runtime Pathologist produced diagnosis"]
    }