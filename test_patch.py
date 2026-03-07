import subprocess

with open("fix.patch", "w") as f:
    f.write(state["patch_generated"])

subprocess.run(["git", "apply", "fix.patch"])