import difflib

def create_diff(original, patched):

    diff = difflib.unified_diff(
        original.splitlines(keepends=True),
        patched.splitlines(keepends=True),
        lineterm="\n"
    )

    patch = "".join(diff)
    if patch and not patch.endswith("\n"):
        patch += "\n"
    return patch
