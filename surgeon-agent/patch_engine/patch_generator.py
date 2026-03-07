def generate_patch(code):

    lines = code.split("\n")
    patched_lines = []

    for line in lines:

        if "transaction.id" in line:
            patched_lines.append(
                "const id = transaction ? transaction.id : null;"
            )
        else:
            patched_lines.append(line)

    return "\n".join(patched_lines)