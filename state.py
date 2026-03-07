import json
import subprocess

from agents.root_cause_agent import RootCauseAgent
from agents.surgeon_agent import SurgeonAgent

from utils.slack_notify import send_slack_notification
from utils.run_tests import run_tests
from utils.git_push import push_changes
from utils.create_pr import create_pull_request


# -------------------------------------------------
# Initial State (Input from Pathologist / Watchman)
# -------------------------------------------------

state = {

    "diagnosis_type": "BUILD",

    "file_path": "Test1/.github/workflows/ci.yml",

    "line_number": 19,

    "fix_description": "npm install is unreliable in CI",

    "replacement_code": "        run: npm install",

    "error_log": "CI pipeline failed during dependency installation",

    "agent_logs": []
}


# -------------------------------------------------
# Root Cause Analysis
# -------------------------------------------------

root_agent = RootCauseAgent()

state = root_agent.analyze(state)

print("\nROOT CAUSE OUTPUT:\n")

print(json.dumps({
    "root_cause": state.get("root_cause"),
    "confidence_score": state.get("confidence_score")
}, indent=2))


# -------------------------------------------------
# Surgeon Agent
# -------------------------------------------------

surgeon = SurgeonAgent()

state = surgeon.repair(state)

print("\nSURGEON OUTPUT:\n")

print(json.dumps({
    "patch_generated": bool(state.get("patch_generated")),
    "pr_title": state.get("pr_title"),
    "pr_description": state.get("pr_description")
}, indent=2))


# -------------------------------------------------
# Save Patch
# -------------------------------------------------

if state.get("patch_generated"):

    patch_file = "fix.patch"

    with open(patch_file, "w", encoding="utf-8", newline="\n") as f:
        f.write(state["patch_generated"])

    print("\nPatch saved as fix.patch")

    try:

        # -------------------------------------------------
        # Validate Patch
        # -------------------------------------------------

        subprocess.run(
            ["git", "apply", "--check", patch_file],
            check=True
        )

        # -------------------------------------------------
        # Apply Patch
        # -------------------------------------------------

        subprocess.run(
            ["git", "apply", patch_file],
            check=True
        )

        print("\nPatch applied successfully!")

        # -------------------------------------------------
        # Run Tests
        # -------------------------------------------------

        logs = run_tests()

        if logs["success"]:

            print("\nTests passed!")

            # push changes
            push_changes()

            # create PR
            pr_link = create_pull_request()

            send_slack_notification(
                f"✅ CI issue fixed automatically\n"
                f"Root Cause: {state.get('root_cause')}\n"
                f"Pull Request: {pr_link}"
            )

        else:

            print("\nTests failed again!")

            send_slack_notification(
                "⚠️ Automated fix attempted but tests still failing.\n"
                "Developer intervention required."
            )

    except subprocess.CalledProcessError:

        print("\nPatch could not be applied automatically.")

        send_slack_notification(
            "❌ Patch generation succeeded but git apply failed."
        )


else:

    print("\nNo patch was generated.")

    send_slack_notification(
        "⚠️ SurgeonAgent could not generate a patch."
    )