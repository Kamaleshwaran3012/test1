import json
from agents.surgeon_agent import SurgeonAgent

state = {

    "diagnosis_type": "BUILD",

    "file_path": "Test1/.github/workflows/ci.yml",

    "line_number": 19,

    "fix_description": "npm install is unreliable in CI",

    "replacement_code": "        run: npm ci",

    "root_cause": "npm install may produce inconsistent dependency trees in CI environments",

    "agent_logs": []
}

surgeon = SurgeonAgent()

state = surgeon.repair(state)

print("\nFINAL OUTPUT:\n")

print(json.dumps(state, indent=2))


if state["patch_generated"]:

    with open("fix.patch","w") as f:
        f.write(state["patch_generated"])

    print("\nPatch saved as fix.patch")