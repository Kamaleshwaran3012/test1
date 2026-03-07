import os
import json
import re
from groq import Groq
from prompts.root_cause_prompt import ROOT_CAUSE_PROMPT


class RootCauseAgent:

    def __init__(self):

        self.client = Groq(
            api_key=os.getenv("GROQ_API_KEY")
        )

        self.model = "llama-3.3-70b-versatile"

    def extract_json(self, text):

        match = re.search(r"\{.*?\}", text, re.DOTALL)

        if match:
            return json.loads(match.group())

        return {}

    def analyze(self, state):

        diagnosis = {
            "error_log": state.get("error_log"),
            "file_path": state.get("file_path"),
            "fix_description": state.get("fix_description")
        }

        prompt = ROOT_CAUSE_PROMPT.format(
            diagnosis=json.dumps(diagnosis, indent=2)
        )

        response = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": "You are a CI debugging expert."},
                {"role": "user", "content": prompt}
            ]
        )

        text = response.choices[0].message.content

        result = self.extract_json(text)

        state["root_cause"] = result.get(
            "root_cause",
            "Root cause could not be determined."
        )

        state["confidence_score"] = result.get("confidence_score", 0.7)

        state["agent_logs"].append(
            "[RootCauseAgent] Root cause analysis completed"
        )

        return state