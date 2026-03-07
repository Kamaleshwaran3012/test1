import json
import subprocess

from agents.surgeon_agent import SurgeonAgent
from utils.slack_notify import send_slack_notification
from utils.run_tests import run_tests


state = {
    "diagnosis_type": "CODE",
    "file_path": "test_repo/requirements.txt",
    "line_number": None,
    "fix_description": "Missing pandas dependency",
    "replacement_code": "pandas>=2.0.0",
    "error_log": "ModuleNotFoundError: No module named pandas",
    "root_cause": "The dependency pandas is not listed in requirements.txt",
    "confidence_score": 0.92,
    "agent_logs": []
}


# -----------------------------
# Run Surgeon Agent
# -----------------------------

surgeon = SurgeonAgent()
state = surgeon.repair(state)

print("\nFINAL OUTPUT:\n")
print(json.dumps(state, indent=2))


# -----------------------------
# Save Patch
# -----------------------------

if state.get("patch_generated"):

    patch_file = "fix.patch"

    with open(patch_file, "w", encoding="utf-8", newline="\n") as f:
        f.write(state["patch_generated"])

    print("\nPatch saved as fix.patch")

    try:

        # -----------------------------
        # Check Patch
        # -----------------------------

        subprocess.run(
            ["git", "apply", "--check", patch_file],
            check=True
        )

        # -----------------------------
        # Apply Patch
        # -----------------------------

        subprocess.run(
            ["git", "apply", patch_file],
            check=True
        )

        print("\nPatch applied successfully!")

        # -----------------------------
        # Run Tests After Patch
        # -----------------------------

        logs = run_tests()

        if logs["success"]:

            print("\nTests passed!")

            send_slack_notification(
                "✅ CI issue fixed automatically.\n"
                "Patch applied successfully.\n"
                "All tests passed."
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