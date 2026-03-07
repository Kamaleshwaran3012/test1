import os
import tempfile
import subprocess
from groq import Groq


class SurgeonAgent:

    def __init__(self):

        self.client = None
        self.model = "llama-3.3-70b-versatile"

    # -------------------------------------------------
    # Read file safely
    # -------------------------------------------------

    def _read_file(self, file_path):

        encodings = ["utf-8", "utf-8-sig", "latin-1"]

        for enc in encodings:
            try:
                with open(file_path, "r", encoding=enc, newline="") as f:
                    return f.read(), enc
            except UnicodeDecodeError:
                continue

        raise ValueError(f"Unable to read file: {file_path}")

    def _detect_newline(self, text):
        if "\r\n" in text:
            return "\r\n"
        if "\r" in text:
            return "\r"
        return "\n"

    def _strip_code_fences(self, text):
        cleaned = (text or "").strip()
        if cleaned.startswith("```"):
            lines = cleaned.splitlines()
            if lines:
                lines = lines[1:]
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            cleaned = "\n".join(lines).strip()
        return cleaned

    # -------------------------------------------------
    # Ask Groq AI to generate fix
    # -------------------------------------------------

    def _generate_fix_with_ai(self, code, state):
        if self.client is None:
            api_key = os.getenv("GROQ_API_KEY")
            if not api_key:
                raise ValueError("GROQ_API_KEY is not set")
            self.client = Groq(api_key=api_key)

        file_path = state.get("file_path", "")
        if file_path.endswith((".yml", ".yaml")):
            output_hint = "Output must be valid YAML for this file."
        elif file_path.endswith(".json"):
            output_hint = "Output must be valid JSON for this file."
        else:
            output_hint = "Output must preserve the original file syntax."

        prompt = f"""
You are an autonomous CI/CD repair agent.

Your job is to FIX the file.

STRICT RULES:
- Return ONLY the corrected file
- No explanations
- No markdown
- No reasoning
- {output_hint}

File path:
{state.get("file_path")}

Root cause:
{state.get("root_cause")}

Current file:
{code}
"""

        response = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {
                    "role": "system",
                    "content": "You fix CI/CD pipeline failures."
                },
                {
                    "role": "user",
                    "content": prompt
                }
            ]
        )

        return self._strip_code_fences(response.choices[0].message.content)

    # -------------------------------------------------
    # Generate git patch (Git-native format)
    # -------------------------------------------------

    def _generate_git_patch(self, file_path, fixed_code, encoding):
        temp_path = None
        try:
            target_dir = os.path.dirname(file_path) or "."
            fd, temp_path = tempfile.mkstemp(
                dir=target_dir,
                suffix=".surgeon.tmp"
            )
            os.close(fd)

            with open(temp_path, "w", encoding=encoding, newline="") as f:
                f.write(fixed_code)

            file_rel = os.path.relpath(file_path).replace("\\", "/")
            temp_rel = os.path.relpath(temp_path).replace("\\", "/")

            result = subprocess.run(
                [
                    "git",
                    "diff",
                    "--no-index",
                    "--src-prefix=a/",
                    "--dst-prefix=b/",
                    "--",
                    file_rel,
                    temp_rel
                ],
                capture_output=True,
                text=True
            )

            if result.returncode not in (0, 1):
                raise RuntimeError(result.stderr.strip() or "git diff failed")

            patch = result.stdout.replace(temp_rel, file_rel)
            if patch and not patch.endswith("\n"):
                patch += "\n"
            return patch
        finally:
            if temp_path and os.path.exists(temp_path):
                os.remove(temp_path)

    # -------------------------------------------------
    # Main repair function
    # -------------------------------------------------

    def repair(self, state):

        file_path = state.get("file_path")
        line_number = state.get("line_number")
        replacement_code = state.get("replacement_code")
        state.setdefault("agent_logs", [])

        if not os.path.exists(file_path):

            state["patch_generated"] = None
            state["pr_title"] = None
            state["pr_description"] = None

            state["agent_logs"].append(
                f"[SurgeonAgent] File not found: {file_path}"
            )

            return state

        # read original code
        original_code, encoding = self._read_file(file_path)
        newline = self._detect_newline(original_code)

        fixed_code = None
        # Prefer deterministic replacement from state when available.
        if replacement_code:
            lines = original_code.splitlines(keepends=True)
            replacement_line = replacement_code
            if not replacement_line.endswith(("\n", "\r")):
                replacement_line += newline
            if line_number and 0 < line_number <= len(lines):
                lines[line_number - 1] = replacement_line
            else:
                if lines and not lines[-1].endswith(("\n", "\r")):
                    lines[-1] += newline
                lines.append(replacement_line)
            fixed_code = "".join(lines)
            state["agent_logs"].append(
                "[SurgeonAgent] Applied deterministic fix from state"
            )
        else:
            # generate AI fix
            fixed_code = self._generate_fix_with_ai(original_code, state)

        # detect invalid AI response
        if (
            fixed_code.startswith("To identify")
            or "analysis" in fixed_code.lower()
            or len(fixed_code) < 10
        ):

            state["patch_generated"] = None
            state["agent_logs"].append(
                "[SurgeonAgent] AI returned analysis instead of code"
            )

            return state

        # fallback fix if AI didn't modify file
        if original_code == fixed_code:

            if "npm install" in original_code:
                fixed_code = original_code.replace(
                    "npm install",
                    "npm ci"
                )

        # generate patch
        patch = self._generate_git_patch(file_path, fixed_code, encoding)

        if not patch:

            state["patch_generated"] = None
            state["agent_logs"].append(
                "[SurgeonAgent] No patch generated"
            )

            return state

        # -------------------------------------------------
        # SURGEON OUTPUT
        # -------------------------------------------------

        state["patch_generated"] = patch

        state["pr_title"] = f"Automated Fix: {os.path.basename(file_path)}"

        state["pr_description"] = (
            f"Automated CI Repair\n\n"
            f"Root Cause:\n{state.get('root_cause')}\n\n"
            f"File Modified:\n{file_path}\n\n"
            f"This fix was generated automatically by the AI repair agent."
        )

        state["agent_logs"].append(
            "[SurgeonAgent] Valid git patch generated"
        )

        return state
