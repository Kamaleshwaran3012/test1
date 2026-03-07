import difflib

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