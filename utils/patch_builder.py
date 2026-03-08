import difflib


def generate_git_patch_from_text(file_path, original_text, modified_text):
    normalized_path = str(file_path or "unknown_file").replace("\\", "/")
    original_lines = (original_text or "").splitlines(keepends=True)
    modified_lines = (modified_text or "").splitlines(keepends=True)

    diff = difflib.unified_diff(
        original_lines,
        modified_lines,
        fromfile=f"a/{normalized_path}",
        tofile=f"b/{normalized_path}",
        lineterm="\n",
    )
    # Keep unified diff output as-is; joining with an extra separator corrupts patch format.
    patch = "".join(diff)
    if patch and not patch.endswith("\n"):
        patch += "\n"
    return patch


def generate_git_patch(file_path, replacement_line, line_number):

    with open(file_path, "r") as f:
        original_lines = f.readlines()

    modified_lines = original_lines.copy()

    # insert fix
    modified_lines.insert(line_number - 1, replacement_line + "\n")

    diff = difflib.unified_diff(
        original_lines,
        modified_lines,
        fromfile=f"a/{file_path}",
        tofile=f"b/{file_path}",
        lineterm=""
    )

    patch = "\n".join(diff)

    return patch
