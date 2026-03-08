import subprocess


def _run_git(args):
    return subprocess.run(["git", *args], check=True, capture_output=True, text=True)


def _current_branch() -> str:
    result = _run_git(["rev-parse", "--abbrev-ref", "HEAD"])
    return result.stdout.strip()


def push_changes():
    target_branch = "surgeon_agents"
    source_branch = _current_branch()

    subprocess.run(["git", "add", "."], check=True)

    subprocess.run(
        ["git", "commit", "-m", "Automated fix by CI Repair Agent"],
        check=True
    )

    # Push current HEAD to target branch even if local target branch does not exist.
    subprocess.run(
        ["git", "push", "origin", f"{source_branch}:{target_branch}"],
        check=True
    )
