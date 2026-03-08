import os
import tempfile
import subprocess
from groq import Groq
from utils.patch_builder import generate_git_patch_from_text


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

    def _resolve_existing_file_path(self, file_path):
        if not file_path:
            return None
        if os.path.exists(file_path):
            return file_path

        normalized = str(file_path).replace("\\", "/").strip()
        candidate_roots = [os.getcwd(), os.path.join(os.getcwd(), "aibrainy")]

        # Try common repo-root anchored resolution first.
        for root in candidate_roots:
            candidate = os.path.normpath(os.path.join(root, normalized))
            if os.path.exists(candidate):
                return candidate

        # Fallback: basename lookup in workspace to handle file hints like "package.json".
        target_name = os.path.basename(normalized)
        if not target_name:
            return None

        best_match = None
        best_depth = None
        for root in candidate_roots:
            if not os.path.isdir(root):
                continue
            for dirpath, dirnames, filenames in os.walk(root):
                dirnames[:] = [d for d in dirnames if d not in {".git", "venv", "node_modules", "__pycache__"}]
                if target_name in filenames:
                    rel = os.path.relpath(os.path.join(dirpath, target_name), root)
                    depth = rel.count(os.sep)
                    if best_match is None or depth < best_depth:
                        best_match = os.path.join(dirpath, target_name)
                        best_depth = depth
            if best_match:
                break
        return best_match

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
        old_code = state.get("old_code")
        new_code = state.get("new_code")
        state.setdefault("agent_logs", [])
        state["agent_logs"].append(
            f"[SurgeonAgent] Start repair file_path={file_path} line_number={line_number} "
            f"has_replacement_code={bool(replacement_code)} has_old_new={bool(old_code and new_code)}"
        )
        resolved_file_path = self._resolve_existing_file_path(file_path)
        if resolved_file_path and resolved_file_path != file_path:
            state["agent_logs"].append(
                f"[SurgeonAgent] Resolved file path {file_path} -> {resolved_file_path}"
            )
            file_path = resolved_file_path
            state["file_path"] = resolved_file_path

        # Deterministic direct patch path for webhook simulations that provide before/after code.
        if isinstance(old_code, str) and isinstance(new_code, str) and old_code and new_code:
            patch = None
            if file_path and os.path.exists(file_path):
                try:
                    current_code, _ = self._read_file(file_path)
                except Exception:
                    current_code = ""
                replacement_attempted = False
                old_variants = [old_code, old_code.replace("\r\n", "\n"), old_code.replace("\n", "\r\n")]
                for old_variant in old_variants:
                    if not old_variant:
                        continue
                    if old_variant in current_code:
                        # Keep newline style aligned with matched variant.
                        if "\r\n" in old_variant and "\r\n" not in new_code:
                            new_variant = new_code.replace("\n", "\r\n")
                        elif "\n" in old_variant and "\r\n" in new_code:
                            new_variant = new_code.replace("\r\n", "\n")
                        else:
                            new_variant = new_code
                        updated_code = current_code.replace(old_variant, new_variant, 1)
                        patch = generate_git_patch_from_text(file_path, current_code, updated_code)
                        replacement_attempted = True
                        break
                if not replacement_attempted:
                    state["agent_logs"].append(
                        "[SurgeonAgent] old_code not found in target file; using raw old/new patch"
                    )
            if not patch:
                patch = generate_git_patch_from_text(file_path or "unknown_file", old_code, new_code)
            if patch:
                state["agent_logs"].append(
                    f"[SurgeonAgent] Deterministic old/new patch generated length={len(patch)}"
                )
                state["patch_generated"] = patch
                state["pr_title"] = f"Automated Fix: {os.path.basename(file_path or 'unknown_file')}"
                state["pr_description"] = (
                    f"Automated CI Repair\n\n"
                    f"Root Cause:\n{state.get('root_cause')}\n\n"
                    f"File Modified:\n{file_path}\n\n"
                    f"This fix was generated automatically by the AI repair agent."
                )
                state["agent_logs"].append("[SurgeonAgent] Patch generated from old_code/new_code payload")
                return state
            state["agent_logs"].append("[SurgeonAgent] old_code/new_code present but produced empty patch")

        if not os.path.exists(file_path):
            synthetic_patch = None
            if isinstance(old_code, str) and isinstance(new_code, str) and old_code and new_code:
                synthetic_patch = generate_git_patch_from_text(file_path or "unknown_file", old_code, new_code)
            elif replacement_code:
                replacement_line = replacement_code
                if not replacement_line.endswith(("\n", "\r")):
                    replacement_line += "\n"
                synthetic_patch = generate_git_patch_from_text(
                    file_path or "unknown_file",
                    "",
                    replacement_line,
                )

            if synthetic_patch:
                state["agent_logs"].append(
                    f"[SurgeonAgent] Synthetic patch generated for missing file length={len(synthetic_patch)}"
                )
                state["patch_generated"] = synthetic_patch
                state["pr_title"] = f"Automated Fix: {os.path.basename(file_path or 'unknown_file')}"
                state["pr_description"] = (
                    f"Automated CI Repair\n\n"
                    f"Root Cause:\n{state.get('root_cause')}\n\n"
                    f"File Modified:\n{file_path}\n\n"
                    f"This fix was generated automatically by the AI repair agent."
                )
                state["agent_logs"].append(
                    f"[SurgeonAgent] Generated synthetic patch for missing file: {file_path}"
                )
                return state

            state["patch_generated"] = None
            state["pr_title"] = None
            state["pr_description"] = None

            state["agent_logs"].append(
                f"[SurgeonAgent] File not found: {file_path}"
            )
            state["agent_logs"].append("[SurgeonAgent] patch_generated=None reason=file_missing_no_synthetic_patch")

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
            state["agent_logs"].append(
                f"[SurgeonAgent] AI fix generated original_len={len(original_code)} fixed_len={len(fixed_code)}"
            )

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
            state["agent_logs"].append("[SurgeonAgent] patch_generated=None reason=invalid_ai_output")

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
        state["agent_logs"].append(
            f"[SurgeonAgent] Git patch attempt length={len(patch) if patch else 0}"
        )
        if not patch:
            # Fallback to utility patch builder to keep patch generation resilient.
            patch = generate_git_patch_from_text(file_path, original_code, fixed_code)
            state["agent_logs"].append(
                f"[SurgeonAgent] Patch-builder fallback length={len(patch) if patch else 0}"
            )

        if not patch:

            state["patch_generated"] = None
            state["agent_logs"].append(
                "[SurgeonAgent] No patch generated"
            )
            state["agent_logs"].append("[SurgeonAgent] patch_generated=None reason=empty_diff")

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
        state["agent_logs"].append(
            f"[SurgeonAgent] patch_generated=SET length={len(patch)}"
        )

        return state
