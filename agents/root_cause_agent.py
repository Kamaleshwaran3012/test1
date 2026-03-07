import os
import json
from groq import Groq
from prompts.root_cause_prompt import ROOT_CAUSE_PROMPT


class RootCauseAgent:

    def __init__(self):
        self.client = Groq(
            api_key=os.getenv("GROQ_API_KEY")
        )

        # recommended Groq reasoning model
        self.model = "llama-3.3-70b-versatile"

    def _clean_json(self, text: str):
        """
        Remove markdown code fences if the LLM adds them.
        """

        text = text.strip()

        if text.startswith("```"):
            text = text.split("```")[1]

            if text.startswith("json"):
                text = text[4:]

        return text.strip()

    def analyze(self, state):

        # Prepare diagnosis input for the prompt
        diagnosis = {
            "diagnosis_type": state.get("diagnosis_type"),
            "file_path": state.get("file_path"),
            "line_number": state.get("line_number"),
            "fix_description": state.get("fix_description"),
            "replacement_code": state.get("replacement_code"),
            "error_log": state.get("error_log")
        }

        prompt = ROOT_CAUSE_PROMPT.format(
            diagnosis=json.dumps(diagnosis, indent=2)
        )

        response = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {
                    "role": "system",
                    "content": "You are an expert DevOps debugging and root cause analysis agent."
                },
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            temperature=0.2
        )

        output_text = response.choices[0].message.content

        cleaned = self._clean_json(output_text)

        try:
            result = json.loads(cleaned)

            state["root_cause"] = result["root_cause"]
            state["confidence_score"] = result["confidence_score"]

        except Exception:
            # fallback if parsing fails
            state["root_cause"] = output_text
            state["confidence_score"] = 0.5

        # add shared logs
        if "agent_logs" not in state:
            state["agent_logs"] = []

        state["agent_logs"].append(
            "[RootCauseAgent] Root cause analysis completed"
        )

        return state