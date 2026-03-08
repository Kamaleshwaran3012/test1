from __future__ import annotations

import operator
from typing import Annotated, Dict, List, Optional, TypedDict


class AgentState(TypedDict, total=False):
    # WATCHMAN INPUT
    error_log: str
    detected_errors: List[str]
    current_error: Optional[str]
    files_context: Dict[str, str]
    event_source: str
    timestamp: str

    # TRIAGE
    error_type: Optional[str]
    suspected_service: Optional[str]

    # PATHOLOGIST
    diagnosis_type: Optional[str]
    file_path: Optional[str]
    line_number: Optional[int]
    fix_description: Optional[str]
    replacement_code: Optional[str]
    old_code: Optional[str]
    new_code: Optional[str]
    error_source: Optional[str]

    # ROOT CAUSE
    root_cause: Optional[str]
    confidence_score: Optional[float]
    fix_suggestion: Optional[str]

    # SURGEON
    patch_generated: Optional[str]
    pr_title: Optional[str]
    pr_description: Optional[str]
    repo_fix_applied: Optional[bool]
    slack_notified: Optional[bool]
    pr_created: Optional[bool]
    code_review_triggered: Optional[bool]

    # PROCESS CONTROL
    iteration_count: int
    processed_errors: List[str]

    # SHARED LOGS
    agent_logs: Annotated[List[str], operator.add]
