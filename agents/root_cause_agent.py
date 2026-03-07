import os
from groq import Groq
from agents.surgeon_agent import SurgeonAgent


class RootCauseAgent:

    def __init__(self):

        self.client = Groq(
            api_key=os.getenv("GROQ_API_KEY")
        )

        self.model = "llama-3.3-70b-versatile"

    def analyze(self, state):

        error_log = state.get("error_log")
        file_path = state.get("file_path")

        prompt = f"""
You are a DevOps root cause analysis expert.

File:
{file_path}

Error log:
{error_log}

Identify the root cause of the failure.
"""

        response = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": "You are a debugging expert."},
                {"role": "user", "content": prompt}
            ]
        )

        root_cause = response.choices[0].message.content.strip()

        state["root_cause"] = root_cause
        state["confidence_score"] = 0.9

        state["agent_logs"].append(
            "[RootCauseAgent] Root cause identified"
        )

        # Send state directly to SurgeonAgent
        surgeon = SurgeonAgent()

        return surgeon.repair(state)