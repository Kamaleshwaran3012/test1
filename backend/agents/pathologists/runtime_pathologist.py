import logging

from backend.agents.gemini_client import (
    DEFAULT_LLM_MODEL,
    GeminiQuotaExceededError,
    invoke_text,
    parse_json_dict,
)
from backend.agents.state import AgentState
from backend.prompts.runtime_prompt import RUNTIME_PATHOLOGIST_PROMPT

logger = logging.getLogger("agents.runtime_pathologist")


def runtime_pathologist(state: AgentState):

    prompt = RUNTIME_PATHOLOGIST_PROMPT.format(
        current_error=state.get("current_error", ""),
        error_log=state.get("error_log", ""),
        suspected_service=state.get("suspected_service", ""),
        files_context=state.get("files_context", {})
    )

    try:
        response_text = invoke_text(prompt, model=DEFAULT_LLM_MODEL, temperature=0)
        result = parse_json_dict(response_text)
    except GeminiQuotaExceededError:
        logger.warning("runtime_pathologist_llm_quota_exhausted")
        result = {}
    except Exception:
        logger.exception("runtime_pathologist_llm_fallback")
        result = {}

    return {
        "diagnosis_type": result.get("diagnosis_type"),
        "file_path": result.get("file_path"),
        "line_number": result.get("line_number"),
        "fix_description": result.get("fix_description"),
        "replacement_code": result.get("replacement_code"),
        "agent_logs": ["Runtime Pathologist produced diagnosis"]
    }
