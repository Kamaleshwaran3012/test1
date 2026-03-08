import os
import queue
import threading
from dataclasses import dataclass, field
from pathlib import Path

from groq import Groq
from dotenv import load_dotenv
from agents.surgeon_agent import SurgeonAgent


@dataclass
class _AnalyzeRequest:
    agent: "RootCauseAgent"
    state: dict
    done: threading.Event = field(default_factory=threading.Event)
    result: dict | None = None
    error: Exception | None = None


class RootCauseAgent:
    _request_queue: queue.Queue[_AnalyzeRequest] = queue.Queue()
    _worker_lock = threading.Lock()
    _worker_thread: threading.Thread | None = None

    def __init__(self):
        api_key = os.getenv("GROQ_API_KEY")
        if not api_key:
            # Support backend runs where env vars live in backend/.env.
            env_candidates = [
                Path.cwd() / "backend" / ".env",
                Path.cwd() / ".env",
            ]
            for env_path in env_candidates:
                if env_path.exists():
                    load_dotenv(dotenv_path=env_path, override=False)
                    break
            api_key = os.getenv("GROQ_API_KEY")
        if not api_key:
            raise ValueError("GROQ_API_KEY is not set (checked environment and backend/.env)")

        self.client = Groq(
            api_key=api_key
        )

        self.model = "llama-3.3-70b-versatile"

    @classmethod
    def _ensure_worker_running(cls):
        with cls._worker_lock:
            if cls._worker_thread and cls._worker_thread.is_alive():
                return
            cls._worker_thread = threading.Thread(
                target=cls._queue_worker,
                name="root-cause-agent-worker",
                daemon=True,
            )
            cls._worker_thread.start()

    @classmethod
    def _queue_worker(cls):
        while True:
            request = cls._request_queue.get()
            try:
                request.result = request.agent._analyze_now(request.state)
            except Exception as exc:
                request.error = exc
            finally:
                request.done.set()
                cls._request_queue.task_done()

    def _analyze_now(self, state):

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

    def analyze(self, state):
        self.__class__._ensure_worker_running()
        request = _AnalyzeRequest(agent=self, state=state)
        self.__class__._request_queue.put(request)
        request.done.wait()

        if request.error is not None:
            raise request.error

        return request.result if isinstance(request.result, dict) else state
