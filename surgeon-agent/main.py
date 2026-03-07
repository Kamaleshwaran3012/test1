from agents.surgeon import Surgeon

diagnosis = {
    "file": "example_repo/payment_service.js",
    "line": 2,
    "issue": "Possible null pointer access on transaction.id"
}

if __name__ == "__main__":
    surgeon = Surgeon()
    result = surgeon.perform_fix(diagnosis)

    print("===== RESULT =====")
    print(result)