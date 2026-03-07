def run_tests(file_path):

    with open(file_path, "r") as f:
        code = f.read()

    if "transaction ?" in code:
        return True

    return False