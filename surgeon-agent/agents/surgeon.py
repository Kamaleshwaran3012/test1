from repo_tools.repo_reader import read_file
from repo_tools.repo_writer import write_file
from patch_engine.patch_generator import generate_patch
from sandbox.test_executor import run_tests


class Surgeon:

    def perform_fix(self, diagnosis):

        file_path = diagnosis["file"]

        print("Reading file...")
        code = read_file(file_path)

        print("Generating patch...")
        patched_code = generate_patch(code)

        print("Applying patch...")
        write_file(file_path, patched_code)

        print("Running tests...")
        test_result = run_tests(file_path)

        return {
            "file": file_path,
            "tests_passed": test_result
        }