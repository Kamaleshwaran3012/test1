import subprocess
import os


def run_tests():

    try:

        # Python project
        if os.path.exists("requirements.txt") or os.path.exists("pytest.ini"):

            result = subprocess.run(
                ["pytest"],
                capture_output=True,
                text=True
            )

        # Node project
        elif os.path.exists("package.json"):

            result = subprocess.run(
                ["npm", "test"],
                capture_output=True,
                text=True,
                shell=True
            )

        else:

            return {
                "success": True,
                "logs": "No test framework detected"
            }

        return {
            "success": result.returncode == 0,
            "logs": result.stdout + result.stderr
        }

    except Exception as e:

        return {
            "success": False,
            "logs": str(e)
        }