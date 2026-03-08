import logging
import re
from pathlib import Path

from backend.agents.gemini_client import (
    DEFAULT_LLM_MODEL,
    GeminiQuotaExceededError,
    invoke_text,
    parse_json_dict,
)
from backend.agents.state import AgentState
from backend.prompts.build_prompt import BUILD_PATHOLOGIST_PROMPT

logger = logging.getLogger("agents.build_pathologist")


def _fallback_result(state: AgentState) -> dict[str, object]:
    return {
        "diagnosis_type": "CI",
        "file_path": "unknown",
        "line_number": 0,
        "fix_description": f"Build analysis fallback: {str(state.get('error_log', ''))[:240]}",
        "replacement_code": "",
    }


def _infer_file_hint_from_state(state: AgentState) -> str | None:
    files_context = state.get("files_context") or {}
    if isinstance(files_context, dict) and files_context:
        first_key = next(iter(files_context.keys()), None)
        if isinstance(first_key, str) and first_key.strip():
            return first_key.strip()

    text = " ".join(
        [
            str(state.get("current_error") or ""),
            str(state.get("error_log") or ""),
            str(state.get("fix_description") or ""),
        ]
    )
    lowered = text.lower()

    explicit_match = re.search(r"([a-zA-Z0-9_\-./]+\.(?:ya?ml|json|js|jsx|ts|tsx|py|toml|ini|cfg|lock))", text)
    if explicit_match:
        return explicit_match.group(1)

    common_candidates = (
        "package.json",
        "package-lock.json",
        "pnpm-lock.yaml",
        "yarn.lock",
        "requirements.txt",
        "pyproject.toml",
        "Dockerfile",
    )
    for candidate in common_candidates:
        if candidate.lower() in lowered:
            return candidate
    return None


def _resolve_existing_workflow_file(preferred_path: str, state: AgentState) -> str | None:
    preferred = (preferred_path or "").strip()
    if not preferred:
        return None
    if Path(preferred).exists():
        return preferred

    # Prefer known context keys first if available.
    files_context = state.get("files_context") or {}
    if isinstance(files_context, dict):
        for candidate in files_context.keys():
            candidate_str = str(candidate or "").strip()
            if candidate_str.startswith(".github/workflows/") and candidate_str.endswith((".yml", ".yaml")):
                return candidate_str

    # Common fallback for repos that use ci.yml instead of main.yml.
    if preferred.endswith("/main.yml"):
        ci_candidate = preferred[:-len("main.yml")] + "ci.yml"
        if Path(ci_candidate).exists():
            return ci_candidate

    # Search local workflow directory for any existing workflow file.
    roots = [Path.cwd(), Path.cwd() / "aibrainy"]
    for root in roots:
        workflows_dir = root / ".github" / "workflows"
        if not workflows_dir.exists():
            continue
        workflow_files = sorted(workflows_dir.glob("*.yml")) + sorted(workflows_dir.glob("*.yaml"))
        if workflow_files:
            rel = workflow_files[0].resolve().relative_to(root.resolve())
            return str(rel).replace("\\", "/")

    return None


def build_pathologist(state: AgentState):
    print("[BuildPathologist] entered")

    prompt = BUILD_PATHOLOGIST_PROMPT
    prompt = prompt.replace("{current_error}", str(state.get("current_error", "")))
    prompt = prompt.replace("{error_log}", str(state.get("error_log", "")))
    prompt = prompt.replace("{suspected_service}", str(state.get("suspected_service", "")))
    prompt = prompt.replace("{files_context}", str(state.get("files_context", {})))

    try:
        response_text = invoke_text(prompt, model=DEFAULT_LLM_MODEL, temperature=0)
        result = parse_json_dict(response_text)
    except GeminiQuotaExceededError:
        logger.warning("build_pathologist_llm_quota_exhausted")
        result = _fallback_result(state)
    except Exception:
        logger.exception("build_pathologist_llm_fallback")
        result = _fallback_result(state)

    # Keep business flow intact, but avoid choosing generic CI files when a concrete event file exists.
    model_file_path = str(result.get("file_path") or "").strip()
    event_file_path = str(state.get("file_path") or "").strip()
    ci_workflow_files = {".github/workflows/main.yml", ".github/workflows/ci.yml"}
    if event_file_path:
        event_file_exists = Path(event_file_path).exists()
        model_file_missing = not model_file_path or model_file_path == "unknown"
        model_file_is_generic_ci = model_file_path in ci_workflow_files
        if event_file_exists and (model_file_missing or model_file_is_generic_ci):
            result["file_path"] = event_file_path

    # If model picked generic workflow file, prefer concrete dependency/code file from state/log hints.
    chosen_file_path = str(result.get("file_path") or "").strip()
    if chosen_file_path in ci_workflow_files or not chosen_file_path or chosen_file_path == "unknown":
        inferred_file = _infer_file_hint_from_state(state)
        if inferred_file and Path(inferred_file).exists():
            result["file_path"] = inferred_file

    # If workflow file is non-existent (e.g., main.yml), swap to an existing workflow file.
    chosen_file_path = str(result.get("file_path") or "").strip()
    if chosen_file_path.startswith(".github/workflows/") and chosen_file_path.endswith((".yml", ".yaml")):
        resolved_workflow = _resolve_existing_workflow_file(chosen_file_path, state)
        if resolved_workflow:
            result["file_path"] = resolved_workflow

    print(
        f"[BuildPathologist] diagnosis_type={result.get('diagnosis_type')} "
        f"file_path={result.get('file_path')} line_number={result.get('line_number')}"
    )
    return {
        "diagnosis_type": result.get("diagnosis_type"),
        "file_path": result.get("file_path"),
        "line_number": result.get("line_number"),
        "fix_description": result.get("fix_description"),
        "replacement_code": result.get("replacement_code"),
        "agent_logs": ["Build Pathologist produced diagnosis"]
    }


def handle_event(state: AgentState):
    return build_pathologist(state)


def run(state: AgentState):
    return build_pathologist(state)
