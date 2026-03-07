import logging

from backend.agents.gemini_client import (
    DEFAULT_LLM_MODEL,
    GeminiQuotaExceededError,
    invoke_text,
    parse_json_dict,
)
from backend.agents.state import AgentState
from backend.prompts.infra_prompt import INFRA_PATHOLOGIST_PROMPT

logger = logging.getLogger("agents.infra_pathologist")


def _fallback_result(state: AgentState) -> dict[str, object]:
    return {
        "diagnosis_type": "CONFIG",
        "file_path": "unknown",
        "line_number": 0,
        "fix_description": f"Infra analysis fallback: {str(state.get('error_log', ''))[:240]}",
        "replacement_code": "",
    }


def infra_pathologist(state: AgentState):
    print("[InfraPathologist] entered")

    prompt = INFRA_PATHOLOGIST_PROMPT
    prompt = prompt.replace("{current_error}", str(state.get("current_error", "")))
    prompt = prompt.replace("{error_log}", str(state.get("error_log", "")))
    prompt = prompt.replace("{suspected_service}", str(state.get("suspected_service", "")))
    prompt = prompt.replace("{files_context}", str(state.get("files_context", {})))

    try:
        response_text = invoke_text(prompt, model=DEFAULT_LLM_MODEL, temperature=0)
        result = parse_json_dict(response_text)
    except GeminiQuotaExceededError:
        logger.warning("infra_pathologist_llm_quota_exhausted")
        result = _fallback_result(state)
    except Exception:
        logger.exception("infra_pathologist_llm_fallback")
        result = _fallback_result(state)

    print(
        f"[InfraPathologist] diagnosis_type={result.get('diagnosis_type')} "
        f"file_path={result.get('file_path')} line_number={result.get('line_number')}"
    )
    return {
        "diagnosis_type": result.get("diagnosis_type"),
        "file_path": result.get("file_path"),
        "line_number": result.get("line_number"),
        "fix_description": result.get("fix_description"),
        "replacement_code": result.get("replacement_code"),
        "agent_logs": ["Infra Pathologist produced diagnosis"]
    }


def handle_event(state: AgentState):
    return infra_pathologist(state)


def run(state: AgentState):
    return infra_pathologist(state)

