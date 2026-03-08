from github import Github
import os
import re
import subprocess
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


def _infer_repo_full_name() -> str:
    explicit = os.getenv("GITHUB_REPO", "").strip()
    if explicit:
        return explicit

    result = subprocess.run(
        ["git", "remote", "get-url", "origin"],
        check=True,
        capture_output=True,
        text=True,
    )
    remote = result.stdout.strip()

    # Supports:
    # - https://github.com/owner/repo.git
    # - git@github.com:owner/repo.git
    match = re.search(r"github\.com[:/](?P<owner>[^/]+)/(?P<repo>[^/.]+)(?:\.git)?$", remote)
    if not match:
        raise ValueError(f"Unable to infer GitHub repo from origin URL: {remote}")
    return f"{match.group('owner')}/{match.group('repo')}"

def create_pull_request():

    token = (os.getenv("GITHUB_TOKEN") or os.getenv("GITHUB_PAT") or "").strip()
    if not token:
        raise ValueError("Missing GitHub token. Set GITHUB_TOKEN (or GITHUB_PAT) in .env.")

    g = Github(token)

    repo = g.get_repo(_infer_repo_full_name())
    head_branch = os.getenv("PR_HEAD_BRANCH", "surgeon_agents").strip() or "surgeon_agents"
    base_branch = os.getenv("PR_BASE_BRANCH", "main").strip() or "main"

    pr = repo.create_pull(
        title="Automated CI Fix",
        body="Patch generated automatically by CI repair agent.",
        head=head_branch,
        base=base_branch
    )

    return pr.html_url
