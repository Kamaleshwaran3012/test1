import os
from github import Github

def create_pull_request():

    token = os.getenv("GITHUB_TOKEN")

    g = Github(token)

    repo = g.get_repo("Kamaleshwaran3012/test1")

    pr = repo.create_pull(
        title="Automated CI Fix",
        body="Patch generated automatically by CI repair agent.",
        head="surgeon_agents",
        base="main"
    )

    print("PR created:", pr.html_url)

    return pr.html_url