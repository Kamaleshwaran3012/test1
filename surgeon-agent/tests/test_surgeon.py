from agents.surgeon import Surgeon

def test_fix():

    diagnosis = {
        "file": "example_repo/payment_service.js"
    }

    surgeon = Surgeon()
    result = surgeon.perform_fix(diagnosis)

    assert result["tests_passed"] == True