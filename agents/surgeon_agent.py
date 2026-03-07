import os
import json
from groq import Groq
from prompts.surgeon_prompt import CI_PATCH_GENERATION_PROMPT


class SurgeonAgent:

    def __init__(self):
        self.client = Groq(
            api_key=os.getenv("GROQ_API_KEY")
        )

        # Strong reasoning model for patch generation
        self.model = "llama-3.3-70b-versatile"

    def _clean_json(self, text):
        """
        Remove markdown fences if the model adds them.
        """

        text = text.strip()

        if text.startswith("```"):
            text = text.split("```")[1]

            if text.startswith("json"):
                text = text[4:]

        return text.strip()

    def repair(self, state):

        diagnosis_type = state.get("diagnosis_type")

        # -------------------------------------------------
        # CASE 1 — INFRASTRUCTURE ERROR
        # -------------------------------------------------
        if diagnosis_type == "INFRA":

            state["patch_generated"] = None
            state["pr_title"] = "Infrastructure Issue Detected"
            state["pr_description"] = (
                "The failure was classified as an infrastructure issue "
                "(e.g., cloud configuration, container orchestration, "
                "networking, or deployment environment). "
                "Automated code repair is not applicable. "
                "Developer or DevOps intervention is required."
            )

            if "agent_logs" not in state:
                state["agent_logs"] = []

            state["agent_logs"].append(
                "[SurgeonAgent] Infra issue detected – notifying developer"
            )

            return state

        # -------------------------------------------------
        # CASE 2 — BUILD OR CODE ERROR (Fixable)
        # -------------------------------------------------
        if diagnosis_type in ["CODE", "BUILD"]:

            prompt = CI_PATCH_GENERATION_PROMPT.format(
                root_cause=state.get("root_cause"),
                fix_description=state.get("fix_description"),
                file_path=state.get("file_path"),
                line_number=state.get("line_number"),
                replacement_code=state.get("replacement_code")
            )

            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {
                        "role": "system",
                        "content": "You are a DevOps CI/CD repair agent."
                    },
                    {
                        "role": "user",
                        "content": prompt
                    }
                ],
                temperature=0.1
            )

            output_text = response.choices[0].message.content
            cleaned = self._clean_json(output_text)

            try:

                result = json.loads(cleaned)

                state["patch_generated"] = result["patch_generated"]
                state["pr_title"] = result["pr_title"]
                state["pr_description"] = result["pr_description"]

            except Exception:

                state["patch_generated"] = output_text
                state["pr_title"] = "Automated CI Fix"
                state["pr_description"] = (
                    "Patch generated automatically but JSON parsing failed."
                )

            if "agent_logs" not in state:
                state["agent_logs"] = []

            state["agent_logs"].append(
                "[SurgeonAgent] Patch generated for build/code issue"
            )

            return state

        # -------------------------------------------------
        # CASE 3 — RUNTIME ERROR
        # -------------------------------------------------
        if diagnosis_type == "RUNTIME":

            # if replacement code exists → attempt fix
            if state.get("replacement_code"):

                prompt = CI_PATCH_GENERATION_PROMPT.format(
                    root_cause=state.get("root_cause"),
                    fix_description=state.get("fix_description"),
                    file_path=state.get("file_path"),
                    line_number=state.get("line_number"),
                    replacement_code=state.get("replacement_code")
                )

                response = self.client.chat.completions.create(
                    model=self.model,
                    messages=[
                        {
                            "role": "system",
                            "content": "You are a DevOps CI/CD repair agent."
                        },
                        {
                            "role": "user",
                            "content": prompt
                        }
                    ],
                    temperature=0.1
                )

                output_text = response.choices[0].message.content
                cleaned = self._clean_json(output_text)

                try:

                    result = json.loads(cleaned)

                    state["patch_generated"] = result["patch_generated"]
                    state["pr_title"] = result["pr_title"]
                    state["pr_description"] = result["pr_description"]

                except Exception:

                    state["patch_generated"] = output_text
                    state["pr_title"] = "Runtime Fix"
                    state["pr_description"] = (
                        "Runtime issue patched automatically."
                    )

                state["agent_logs"].append(
                    "[SurgeonAgent] Runtime issue fixed automatically"
                )

                return state

            # -------------------------------------------------
            # Runtime error but no safe fix
            # -------------------------------------------------
            else:

                state["patch_generated"] = None
                state["pr_title"] = "Runtime Issue Requires Manual Fix"
                state["pr_description"] = (
                    "The runtime failure could not be safely repaired "
                    "automatically. Developer investigation is required."
                )

                state["agent_logs"].append(
                    "[SurgeonAgent] Runtime issue requires manual intervention"
                )

                return state

        # -------------------------------------------------
        # FALLBACK
        # -------------------------------------------------

        state["patch_generated"] = None
        state["pr_title"] = "Unknown Failure Type"
        state["pr_description"] = (
            "The failure type could not be determined automatically."
        )

        if "agent_logs" not in state:
            state["agent_logs"] = []

        state["agent_logs"].append(
            "[SurgeonAgent] Unknown diagnosis type"
        )

        return state