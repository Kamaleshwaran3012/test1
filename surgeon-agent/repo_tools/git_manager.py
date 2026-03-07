import os

def commit_changes(message="Auto fix by Surgeon Agent"):
    os.system("git add .")
    os.system(f'git commit -m "{message}"')