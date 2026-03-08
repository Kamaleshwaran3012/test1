import requests
import os
from pathlib import Path
from dotenv import load_dotenv


_ENV_CANDIDATES = [
    Path.cwd() / ".env",
    Path.cwd() / "backend" / ".env",
    Path(__file__).resolve().parents[1] / ".env",
    Path(__file__).resolve().parents[1] / "backend" / ".env",
]
for _env in _ENV_CANDIDATES:
    if _env.exists():
        load_dotenv(dotenv_path=_env, override=False)

def send_slack_notification(message):

    webhook_url = os.getenv("SLACK_WEBHOOK_URL")

    if not webhook_url:
        print("Slack webhook not configured")
        return

    payload = {
        "text": message
    }
   

    requests.post(webhook_url, json=payload)
