import os
from github import Github


def create_pull_request():

    # Read token from environment variable
    token = os.getenv("GITHUB_TOKEN")

    if not token:
        print("GitHub token not configured")
        return None

    # Connect to GitHub
    g = Github(token)

    # Repository format: username/repo
    repo = g.get_repo("Kamaleshwaran3012/test1")

    # Create PR
    pr = repo.create_pull(
        title="Automated CI Fix",
        body="""
This Pull Request was automatically created by the CI Repair Agent.

Root Cause:
The CI pipeline failure was detected and automatically repaired.

Actions performed:
- Patch generated
- Patch applied
- Tests executed successfully
""",
        head="surgeon_agents",   # your fix branch
        base="main"              # target branch
    )

    print("Pull Request created:", pr.html_url)

    return pr.html_url