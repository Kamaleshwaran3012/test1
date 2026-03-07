import subprocess


def push_changes():

    subprocess.run(["git", "add", "."], check=True)

    subprocess.run(
        ["git", "commit", "-m", "Automated fix by CI Repair Agent"],
        check=True
    )

    subprocess.run(
        ["git", "push", "origin", "surgeon_agents"],
        check=True
    )