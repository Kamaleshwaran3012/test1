import requests
import os

def send_slack_notification(message):

    webhook_url = os.getenv("SLACK_WEBHOOK_URL")

    if not webhook_url:
        print("Slack webhook not configured")
        return

    payload = {
        "text": message
    }
   

    requests.post(webhook_url, json=payload)