import os
import difflib


class SurgeonAgent:

    def repair(self, state):

        diagnosis_type = state.get("diagnosis_type")
        file_path = state.get("file_path")
        line_number = state.get("line_number")
        replacement_code = state.get("replacement_code")

        # Infrastructure errors cannot be auto-fixed
        if diagnosis_type == "INFRA":
            state["patch_generated"] = None
            state["pr_title"] = "Infrastructure Issue Detected"
            state["pr_description"] = (
                "The error was classified as an infrastructure issue. "
                "Automatic code modification is not applicable."
            )
            state["agent_logs"].append(
                "[SurgeonAgent] Infra issue detected — developer notified"
            )
            return state

        # Ensure file exists
        if not os.path.exists(file_path):
            state["patch_generated"] = None
            state["agent_logs"].append(
                f"[SurgeonAgent] File not found: {file_path}"
            )
            return state

        # Read real repository file
        with open(file_path, "r", encoding="utf-8") as f:
            original_lines = f.readlines()

        modified_lines = original_lines.copy()

        # Apply modification dynamically
        if line_number is not None and 0 < line_number <= len(modified_lines):
            modified_lines[line_number - 1] = replacement_code + "\n"
        else:
            # fallback: append fix if line not available
            modified_lines.append(replacement_code + "\n")

        # Generate unified diff patch dynamically
        diff = difflib.unified_diff(
            original_lines,
            modified_lines,
            fromfile=f"a/{file_path}",
            tofile=f"b/{file_path}",
            lineterm="\n"
        )

        patch = "".join(diff)
        if patch and not patch.endswith("\n"):
            patch += "\n"

        state["patch_generated"] = patch

        state["pr_title"] = f"Automated Fix: {os.path.basename(file_path)}"

        state["pr_description"] = (
            f"Automated fix generated after root cause analysis.\n\n"
            f"Root Cause: {state.get('root_cause')}"
        )

        state["agent_logs"].append(
            "[SurgeonAgent] Patch generated dynamically"
        )

        return state
