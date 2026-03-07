import os
import subprocess
import tempfile


class SurgeonAgent:
    def _read_text_with_fallback(self, file_path):
        encodings = ("utf-8", "utf-8-sig", "cp1252", "latin-1")
        for encoding in encodings:
            try:
                with open(file_path, "r", encoding=encoding, newline="") as f:
                    return f.read(), encoding
            except UnicodeDecodeError:
                continue
        raise ValueError(f"Unable to decode file as text: {file_path}")

    def _detect_newline(self, text):
        if "\r\n" in text:
            return "\r\n"
        if "\r" in text:
            return "\r"
        return "\n"

    def _generate_git_patch(self, file_path, modified_text, encoding):
        temp_path = None
        try:
            target_dir = os.path.dirname(file_path) or "."
            fd, temp_path = tempfile.mkstemp(
                dir=target_dir,
                suffix=".surgeon.tmp"
            )
            os.close(fd)
            with open(temp_path, "w", encoding=encoding, newline="") as tmp:
                tmp.write(modified_text)

            temp_rel = os.path.relpath(temp_path).replace("\\", "/")
            file_norm = file_path.replace("\\", "/")

            result = subprocess.run(
                [
                    "git",
                    "diff",
                    "--no-index",
                    "--src-prefix=a/",
                    "--dst-prefix=b/",
                    "--",
                    file_norm,
                    temp_rel
                ],
                capture_output=True,
                text=True,
                check=False
            )

            # git diff returns 1 when differences exist.
            if result.returncode not in (0, 1):
                raise RuntimeError(result.stderr.strip() or "git diff failed")

            patch = result.stdout
            if not patch:
                return ""

            patch = patch.replace(temp_rel, file_norm)

            if not patch.endswith("\n"):
                patch += "\n"

            return patch
        finally:
            if temp_path and os.path.exists(temp_path):
                os.remove(temp_path)

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

        # Read text while preserving original newline style.
        original_text, encoding = self._read_text_with_fallback(file_path)
        newline = self._detect_newline(original_text)
        original_lines = original_text.splitlines(keepends=True)

        modified_lines = list(original_lines)
        replacement_line = replacement_code
        if not replacement_line.endswith(("\n", "\r")):
            replacement_line += newline

        # Apply modification dynamically.
        if line_number is not None and 0 < line_number <= len(modified_lines):
            modified_lines[line_number - 1] = replacement_line
        else:
            if modified_lines and not modified_lines[-1].endswith(("\n", "\r")):
                modified_lines[-1] += newline
            modified_lines.append(replacement_line)

        modified_text = "".join(modified_lines)
        patch = self._generate_git_patch(file_path, modified_text, encoding)

        state["patch_generated"] = patch or None

        state["pr_title"] = f"Automated Fix: {os.path.basename(file_path)}"

        state["pr_description"] = (
            f"Automated fix generated after root cause analysis.\n\n"
            f"Root Cause: {state.get('root_cause')}"
        )

        state["agent_logs"].append(
            "[SurgeonAgent] Patch generated dynamically"
        )

        return state
