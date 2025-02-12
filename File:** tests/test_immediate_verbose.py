import time
from tac.core.test_runner import TestRunner

def test_immediate_verbose_output(tmp_path):
    # Create a dummy test file in the temporary directory
    dummy_test = tmp_path / "dummy_immediate_test.py"
    dummy_test.write_text(
        "import time\n"
        "def test_print_one():\n"
        "    print('Immediate message one')\n"
        "    time.sleep(0.1)\n"
        "    assert True\n"
        "\n"
        "def test_print_two():\n"
        "    print('Immediate message two')\n"
        "    time.sleep(0.1)\n"
        "    assert True\n"
    )
    runner = TestRunner()
    # Run the dummy test file
    runner.run_tests(str(dummy_test))
    output = runner.get_test_results()
    first_idx = output.find("Immediate message one")
    second_idx = output.find("Immediate message two")
    assert first_idx != -1, "First message not found in output"
    assert second_idx != -1, "Second message not found in output"
    assert first_idx < second_idx, "Messages not in order"
